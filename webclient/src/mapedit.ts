import { WebSocketConnection, WebSocketLike } from './webclient/connection';
import { ConnectionState, WireMessage } from './webclient/types';
import { CanvasState } from './state/CanvasState';
import { Cell } from './types';

export interface MapEditExit {
    name: string;
    aliases: string[];
    coord: [string, number, number, number];
}

export interface MapRoom {
    x: number;
    y: number;
    desc?: string;
    exits: MapEditExit[];
}

export interface MapEditPayload {
    area: string;
    z: number;
    grid: [number, number, string][];
    rooms?: MapRoom[];
}

export interface MapEditOrigin {
    originX: number;
    originY: number;
    roomCells: Set<string>;
}

export type MapEditEvent =
    | { type: 'synced' }
    | { type: 'reject'; reason: string }
    | { type: 'error'; message: string };

export type MapEditListener = (event: MapEditEvent) => void;

const SYNC_DELAY_MS = 200;

export function loadMapPayload(canvas: CanvasState, payload: MapEditPayload): MapEditOrigin {
    if (payload.grid.length === 0) {
        canvas.resize(1, 1);
        return { originX: 0, originY: 0, roomCells: new Set() };
    }
    let minX = payload.grid[0][0];
    let minY = payload.grid[0][1];
    let maxX = minX;
    let maxY = minY;
    for (const [x, y] of payload.grid) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
    }
    const mapWidth = Math.max(1, maxX - minX + 1);
    const mapHeight = Math.max(1, maxY - minY + 1);
    canvas.resize(mapWidth * 2, mapHeight * 2);
    const toRow = (y: number) => canvas.height - 1 - (y - minY);
    const batch: { col: number; row: number; cell: Cell }[] = [];
    for (const [x, y, symbol] of payload.grid) {
        if (symbol === '') continue;
        batch.push({ col: x - minX, row: toRow(y), cell: { char: symbol, fg: [204, 204, 204], bg: [-1, -1, -1] } });
    }
    canvas.applyBatch(batch);
    const roomCells = new Set<string>();
    for (const room of payload.rooms ?? []) {
        roomCells.add(`${room.x - minX},${toRow(room.y)}`);
    }
    return { originX: minX, originY: minY, roomCells };
}

export function logRoomData(payload: MapEditPayload): void {
    console.log(`Room data for ${payload.area} (z=${payload.z}):`);
    const rooms = payload.rooms ?? [];
    if (rooms.length === 0) {
        console.log('No rooms found.');
        return;
    }
    for (const room of rooms) {
        const exits = room.exits
            .map((e) => `${e.name} -> ${e.coord[1]},${e.coord[2]} (${e.coord[0]}, z=${e.coord[3]})`)
            .join(', ');
        console.log(`(${room.x}, ${room.y}): ${room.desc ?? '(no description)'} | exits: ${exits || 'none'}`);
    }
}

export class MapEditSession {
    private conn: WebSocketConnection;
    private key: string;
    private seq = 1;
    private canvas: CanvasState;
    private originX: number;
    private originY: number;
    private baseline = new Map<string, string>();
    private queue: [number, number, string][][] = [];
    private inFlight: { seq: number; cells: [number, number, string][] } | null = null;
    private handshakeSent = false;
    private syncTimer: ReturnType<typeof setTimeout> | null = null;
    private stopped = false;
    private listener: MapEditListener | null = null;

    constructor(key: string, canvas: CanvasState, origin: MapEditOrigin, createSocket?: (url: string) => WebSocketLike) {
        this.key = key;
        this.canvas = canvas;
        this.originX = origin.originX;
        this.originY = origin.originY;
        this.snapshotBaseline();
        this.conn = new WebSocketConnection({
            createSocket,
            onMessage: (message) => this.handleMessage(message),
            onStateChange: (state) => this.handleStateChange(state),
        });
        this.conn.connect();
    }

    public onEvent(listener: MapEditListener): void {
        this.listener = listener;
    }

    public scheduleSync(): void {
        if (this.stopped || this.syncTimer !== null) return;
        this.syncTimer = setTimeout(() => {
            this.syncTimer = null;
            const cells = this.computeDiff();
            if (cells.length > 0) {
                this.queue.push(cells);
                this.flush();
            }
        }, SYNC_DELAY_MS);
    }

    public dispose(): void {
        this.stopped = true;
        if (this.syncTimer !== null) {
            clearTimeout(this.syncTimer);
            this.syncTimer = null;
        }
        this.queue = [];
        this.conn.close();
    }

    private snapshotBaseline(): void {
        for (let row = 0; row < this.canvas.height; row++) {
            for (let col = 0; col < this.canvas.width; col++) {
                const composite = this.canvas.getCompositeCell(col, row);
                this.baseline.set(`${col},${row}`, composite?.char ?? '');
            }
        }
    }

    private computeDiff(): [number, number, string][] {
        const cells: [number, number, string][] = [];
        for (let row = 0; row < this.canvas.height; row++) {
            for (let col = 0; col < this.canvas.width; col++) {
                const composite = this.canvas.getCompositeCell(col, row);
                const char = composite?.char ?? '';
                const key = `${col},${row}`;
                if (this.baseline.get(key) !== char) {
                    cells.push([col + this.originX, this.canvas.height - 1 - row + this.originY, char]);
                    this.baseline.set(key, char);
                }
            }
        }
        return cells;
    }

    private flush(): void {
        if (this.stopped || this.inFlight || this.queue.length === 0) return;
        if (this.conn.getState() !== 'open') return;
        const cells = this.queue.shift()!;
        this.inFlight = { seq: this.seq, cells };
        this.seq += 1;
        this.conn.send('map_edit', [this.key, this.inFlight.seq, this.inFlight.cells]);
    }

    private handleStateChange(state: ConnectionState): void {
        if (state === 'open') {
            if (!this.handshakeSent) {
                this.handshakeSent = true;
                this.inFlight = { seq: 0, cells: [] };
                this.conn.send('map_edit', [this.key, 0, []]);
            } else if (this.inFlight) {
                this.conn.send('map_edit', [this.key, this.inFlight.seq, this.inFlight.cells]);
            } else {
                this.flush();
            }
        } else if (state === 'failed') {
            this.stopped = true;
            this.listener?.({ type: 'error', message: 'Connection failed.' });
        }
    }

    private handleMessage(message: WireMessage): void {
        if (message.command === 'map_ack') {
            const args = message.args;
            if (!Array.isArray(args) || typeof args[0] !== 'number' || typeof args[1] !== 'string') return;
            if (this.inFlight && args[0] === this.inFlight.seq) {
                this.key = args[1];
                this.inFlight = null;
                this.listener?.({ type: 'synced' });
                this.flush();
            }
        } else if (message.command === 'map_edit_reject') {
            this.dispose();
            const reason = typeof message.args[0] === 'string' ? message.args[0] : 'unknown';
            this.listener?.({ type: 'reject', reason });
        }
    }
}
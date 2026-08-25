import { WebSocketConnection, WebSocketLike } from './webclient/connection';
import { ConnectionState, WireMessage } from './webclient/types';
import { CanvasState } from './state/CanvasState';
import { Cell, Color } from './types';
import { parseAnsiSymbol } from './utils/ansiParser';

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

/** One edited cell sent back to the engine:
 * `[x, y, char, fg, bg, attrs]` with fg/bg as [r,g,b] or [-1,-1,-1] (transparent)
 * and attrs a subset of ["bold", "italic", "underline"]. */
export type MapEditCell = [number, number, string, Color, Color, string[]];

/** One room-move op: `["room", fromX, fromY, toX, toY]`. */
export type MapEditOp = MapEditCell | [string, number, number, number, number];

export interface RoomMove {
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
}

export interface MapEditOrigin {
    originX: number;
    originY: number;
    roomCells: Set<string>;
    rooms: MapRoom[];
}

export type MapEditEvent =
    | { type: 'synced' }
    | { type: 'reject'; reason: string }
    | { type: 'error'; message: string }
    | { type: 'moves_denied'; moves: RoomMove[] }
    | { type: 'saved' };

export type MapEditListener = (event: MapEditEvent) => void;

const SYNC_DELAY_MS = 200;

export function loadMapPayload(canvas: CanvasState, payload: MapEditPayload): MapEditOrigin {
    if (payload.grid.length === 0) {
        canvas.resize(1, 1);
        return { originX: 0, originY: 0, roomCells: new Set(), rooms: payload.rooms ?? [] };
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
    for (const room of payload.rooms ?? []) {
        minX = Math.min(minX, room.x);
        minY = Math.min(minY, room.y);
        maxX = Math.max(maxX, room.x);
        maxY = Math.max(maxY, room.y);
    }
    const mapWidth = Math.max(1, maxX - minX + 1);
    const mapHeight = Math.max(1, maxY - minY + 1);
    canvas.resize(mapWidth * 2, mapHeight * 2);
    const toRow = (y: number) => canvas.height - 1 - (y - minY);
    const batch: { col: number; row: number; cell: Cell }[] = [];
    for (const [x, y, symbol] of payload.grid) {
        if (symbol === '') continue;
        batch.push({ col: x - minX, row: toRow(y), cell: parseAnsiSymbol(symbol) });
    }
    canvas.applyBatch(batch);
    const roomCells = new Set<string>();
    for (const room of payload.rooms ?? []) {
        roomCells.add(`${room.x - minX},${toRow(room.y)}`);
    }
    return { originX: minX, originY: minY, roomCells, rooms: payload.rooms ?? [] };
}

export function logRoomData(payload: MapEditPayload): void {
    if (!(import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV) return;
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

function serializeCell(cell: Cell | null): string {
    if (!cell) return '';
    return [
        cell.char,
        cell.fg.join(','),
        cell.bg.join(','),
        cell.bold ?? false,
        cell.italic ?? false,
        cell.underline ?? false,
    ].join('|');
}

function cellAttrs(cell: Cell | null): string[] {
    const attrs: string[] = [];
    if (!cell) return attrs;
    if (cell.bold) attrs.push('bold');
    if (cell.italic) attrs.push('italic');
    if (cell.underline) attrs.push('underline');
    return attrs;
}

type QueueItem =
    | { kind: 'edit'; cells: MapEditOp[]; isSave: boolean }
    | { kind: 'validate'; serverMoves: RoomMove[]; clientMoves: RoomMove[]; context: RoomMove[] };

const coordKey = (x: number, y: number): string => `${x},${y}`;

export class MapEditSession {
    private conn: WebSocketConnection;
    private key: string;
    private seq = 1;
    private canvas: CanvasState;
    private originX: number;
    private originY: number;
    private baseline = new Map<string, string>();
    private queue: QueueItem[] = [];
    private inFlight: { seq: number; item: QueueItem } | null = null;
    private handshakeSent = false;
    private syncTimer: ReturnType<typeof setTimeout> | null = null;
    private stopped = false;
    private listener: MapEditListener | null = null;
    /** original world coord -> current world coord for every known room */
    private roomPositions = new Map<string, string>();
    /** validated room moves (in server coords) not yet persisted */
    private pendingMoves: RoomMove[] = [];

    constructor(key: string, canvas: CanvasState, origin: MapEditOrigin, createSocket?: (url: string) => WebSocketLike) {
        this.key = key;
        this.canvas = canvas;
        this.originX = origin.originX;
        this.originY = origin.originY;
        for (const room of origin.rooms ?? []) {
            this.roomPositions.set(coordKey(room.x, room.y), coordKey(room.x, room.y));
        }
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
                this.queue.push({ kind: 'edit', cells, isSave: false });
                this.flush();
            }
        }, SYNC_DELAY_MS);
    }

    /** Queue room moves for server-side validation. Moves are expressed in
     * client (current) coords and folded back through pending moves so the
     * server — which has not yet received any save — sees its own state. */
    public validateRoomMoves(moves: RoomMove[]): void {
        if (this.stopped || moves.length === 0) return;
        const known = new Set(this.roomPositions.values());
        const clientMoves: RoomMove[] = [];
        const serverMoves: RoomMove[] = [];
        // context = pendings already validated (the moves being sent now are
        // not their own context)
        const context = this.pendingMoves.slice();
        for (const move of moves) {
            if (!known.has(coordKey(move.fromX, move.fromY))) continue;
            let fromX = move.fromX;
            let fromY = move.fromY;
            const prior = this.pendingMoves.find((p) => p.toX === move.fromX && p.toY === move.fromY);
            if (prior) {
                fromX = prior.fromX;
                fromY = prior.fromY;
                this.pendingMoves = this.pendingMoves.filter((p) => p !== prior);
            }
            clientMoves.push(move);
            serverMoves.push({ fromX, fromY, toX: move.toX, toY: move.toY });
            this.pendingMoves.push({ fromX, fromY, toX: move.toX, toY: move.toY });
        }
        if (clientMoves.length === 0) return;
        this.queue.push({ kind: 'validate', serverMoves, clientMoves, context });
        this.flush();
    }

    /** Send all unsnapshotted glyph changes plus every validated room move
     * to the server in a single batch. The server is only updated here. */
    public saveToServer(): void {
        if (this.stopped) return;
        const cells = this.computeDiff();
        const ops: MapEditOp[] = [
            ...cells,
            ...this.pendingMoves.map((m) => ['room', m.fromX, m.fromY, m.toX, m.toY] as MapEditOp),
        ];
        if (ops.length === 0) {
            this.listener?.({ type: 'error', message: 'Nothing to save.' });
            return;
        }
        this.queue.push({ kind: 'edit', cells: ops, isSave: true });
        this.flush();
    }

    /** Current world coords of all known rooms (after validated moves). */
    public currentRoomCoords(): { x: number; y: number }[] {
        return Array.from(this.roomPositions.values()).map((key) => {
            const [x, y] = key.split(',').map(Number);
            return { x, y };
        });
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
                this.baseline.set(`${col},${row}`, serializeCell(composite));
            }
        }
    }

    private computeDiff(): MapEditCell[] {
        const cells: MapEditCell[] = [];
        for (let row = 0; row < this.canvas.height; row++) {
            for (let col = 0; col < this.canvas.width; col++) {
                const composite = this.canvas.getCompositeCell(col, row);
                const key = `${col},${row}`;
                const serialized = serializeCell(composite);
                if (this.baseline.get(key) !== serialized) {
                    cells.push([
                        col + this.originX,
                        this.canvas.height - 1 - row + this.originY,
                        composite?.char ?? '',
                        composite ? [...composite.fg] : [204, 204, 204],
                        composite ? [...composite.bg] : [0, 0, 0],
                        cellAttrs(composite),
                    ]);
                    this.baseline.set(key, serialized);
                }
            }
        }
        return cells;
    }

    private flush(): void {
        if (this.stopped || this.inFlight || this.queue.length === 0) return;
        if (this.conn.getState() !== 'open') return;
        const item = this.queue.shift()!;
        this.inFlight = { seq: this.seq, item };
        this.seq += 1;
        if (item.kind === 'validate') {
            this.conn.send(
                'map_validate_moves',
                [
                    this.key,
                    this.inFlight.seq,
                    item.serverMoves.map((m) => [m.fromX, m.fromY, m.toX, m.toY]),
                    item.context.map((m) => [m.fromX, m.fromY, m.toX, m.toY]),
                ]
            );
        } else {
            this.conn.send('map_edit', [this.key, this.inFlight.seq, item.cells]);
        }
    }

    private handleStateChange(state: ConnectionState): void {
        if (state === 'open') {
            if (!this.handshakeSent) {
                this.handshakeSent = true;
                this.inFlight = { seq: 0, item: { kind: 'edit', cells: [], isSave: false } };
                this.conn.send('map_edit', [this.key, 0, []]);
            } else if (this.inFlight) {
                const { seq, item } = this.inFlight;
                if (item.kind === 'validate') {
                    this.conn.send(
                        'map_validate_moves',
                        [
                            this.key,
                            seq,
                            item.serverMoves.map((m) => [m.fromX, m.fromY, m.toX, m.toY]),
                            item.context.map((m) => [m.fromX, m.fromY, m.toX, m.toY]),
                        ]
                    );
                } else {
                    this.conn.send('map_edit', [this.key, seq, item.cells]);
                }
            } else {
                this.flush();
            }
        } else if (state === 'failed') {
            this.stopped = true;
            this.listener?.({ type: 'error', message: 'Connection failed.' });
        }
    }

    private handleMessage(message: WireMessage): void {
        const args: unknown[] = Array.isArray(message.args) ? message.args : [];
        if (message.command === 'map_ack') {
            if (typeof args[0] !== 'number' || typeof args[1] !== 'string') return;
            if (this.inFlight && args[0] === this.inFlight.seq) {
                const isSave = this.inFlight.item.kind === 'edit' && this.inFlight.item.isSave;
                this.key = args[1];
                this.inFlight = null;
                if (isSave) {
                    this.pendingMoves = [];
                    this.listener?.({ type: 'saved' });
                }
                this.listener?.({ type: 'synced' });
                this.flush();
            }
        } else if (message.command === 'moves_ok') {
            if (typeof args[0] !== 'number' || typeof args[1] !== 'string') return;
            if (this.inFlight && this.inFlight.item.kind === 'validate' && args[0] === this.inFlight.seq) {
                const { clientMoves } = this.inFlight.item;
                this.key = args[1];
                this.inFlight = null;
                for (const move of clientMoves) {
                    let original: string | null = null;
                    for (const [orig, current] of this.roomPositions.entries()) {
                        if (current === coordKey(move.fromX, move.fromY)) {
                            original = orig;
                            break;
                        }
                    }
                    if (original === null) original = coordKey(move.fromX, move.fromY);
                    this.roomPositions.set(original, coordKey(move.toX, move.toY));
                }
                this.flush();
            }
        } else if (message.command === 'moves_denied') {
            if (typeof args[0] !== 'number' || typeof args[1] !== 'string' || !Array.isArray(args[2])) return;
            if (this.inFlight && this.inFlight.item.kind === 'validate' && args[0] === this.inFlight.seq) {
                const { serverMoves, clientMoves } = this.inFlight.item;
                this.key = args[1];
                this.inFlight = null;
                // roll back pending entries for denied moves; allowed ones stay
                const deniedIdx = new Set(args[2].filter((i): i is number => typeof i === 'number'));
                for (let i = 0; i < serverMoves.length; i++) {
                    if (!deniedIdx.has(i)) continue;
                    const denied = serverMoves[i];
                    this.pendingMoves = this.pendingMoves.filter(
                        (p) => !(p.fromX === denied.fromX && p.fromY === denied.fromY && p.toX === denied.toX && p.toY === denied.toY)
                    );
                }
                const deniedClientMoves = clientMoves.filter((_, i) => deniedIdx.has(i));
                if (deniedClientMoves.length > 0) {
                    this.listener?.({ type: 'moves_denied', moves: deniedClientMoves });
                }
                this.flush();
            }
        } else if (message.command === 'map_edit_reject') {
            this.dispose();
            const reason = typeof args[0] === 'string' ? args[0] : 'unknown';
            this.listener?.({ type: 'reject', reason });
        }
    }
}
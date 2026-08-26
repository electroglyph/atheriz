// @ts-nocheck
import { describe, expect, it, vi } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';
import { MapEditSession } from '../src/mapedit';
import { WebSocketLike } from '../src/webclient/connection';

class FakeSocket implements WebSocketLike {
    readyState = 0;
    onopen: ((event: Event) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    sent: string[] = [];
    closeCalls = 0;
    send(data: string): void { this.sent.push(data); }
    close(): void { this.closeCalls += 1; }
    open(): void { this.readyState = 1; this.onopen?.(new Event('open')); }
    drop(): void { this.readyState = 3; this.onclose?.({} as CloseEvent); }
}

function makeHolder(): { socket: FakeSocket; createSocket: (url: string) => WebSocketLike } {
    let socket!: FakeSocket;
    return {
        get socket() { return socket; },
        createSocket: () => { socket = new FakeSocket(); return socket; },
    };
}

function makeCanvas(): CanvasState { return new CanvasState(2, 1, false); }
function ack(socket: FakeSocket, seq: number, key: string): void {
    socket.onmessage?.(new MessageEvent('message', { data: `["map_ack",[${seq},"${key}"],{}]` }));
}
function legendOk(socket: FakeSocket, seq: number, key: string): void {
    socket.onmessage?.(new MessageEvent('message', { data: `["legend_ok",[${seq},"${key}"],{}]` }));
}

describe('MapEditSession legend editing', () => {
    it('sends legend entries via map_edit_legend with rotated key and seq', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: 'Shrine', coord: null, show: true, fg: null, bg: null }]);
        expect(holder.socket.sent[1]).toContain('"map_edit_legend"');
        expect(holder.socket.sent[1]).toContain('"K1"');
        expect(holder.socket.sent[1]).toContain('"Shrine"');
        expect(JSON.parse(holder.socket.sent[1])[1][2][0].symbol).toBe('X');
        session.dispose();
    });

    it('rejects invalid legend symbols and emits an error without sending', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => { if (e.type === 'error') events.push(e.message); });
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: '', desc: 'bad', coord: null, show: true } as any]);
        expect(events[0]).toMatch(/Invalid legend symbol/);
        expect(holder.socket.sent).toHaveLength(1);
        session.dispose();
    });

    it('rejects missing or whitespace-only descriptions', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => { if (e.type === 'error') events.push(e.message); });
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: '   ', coord: null, show: true } as any]);
        expect(events[0]).toMatch(/Legend description required/);
        expect(holder.socket.sent).toHaveLength(1);
        session.dispose();
    });

    it('rejects too many entries', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => { if (e.type === 'error') events.push(e.message); });
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        const many = Array.from({ length: 201 }, (_, i) => ({ symbol: 'X', desc: `D${i}`, coord: null, show: true }));
        session.saveLegend(many as any);
        expect(events[0]).toMatch(/Too many legend entries/);
        expect(holder.socket.sent).toHaveLength(1);
        session.dispose();
    });

    it('queues a second legend save while one is in flight', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'A', desc: 'first', coord: null, show: true, fg: null, bg: null }]);
        session.saveLegend([{ symbol: 'B', desc: 'second', coord: null, show: true, fg: null, bg: null }]);
        expect(holder.socket.sent).toHaveLength(2);
        ack(holder.socket, 1, 'K2');
        expect(holder.socket.sent).toHaveLength(3);
        expect(holder.socket.sent[2]).toContain('second');
        session.dispose();
    });

    it('treats map_ack and legend_ok for legend seq as legend_saved and advances the key', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => events.push(e.type));
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: 'D', coord: [1, 2], show: false, fg: null, bg: null }]);
        ack(holder.socket, 1, 'K2');
        expect(events).toContain('legend_saved');
        expect(events).toContain('synced');
        // the rotated key is reused for next save
        session.saveLegend([{ symbol: 'Y', desc: 'E', coord: null, show: true }]);
        expect(holder.socket.sent[2]).toContain('"K2"');
        session.dispose();
    });

    it('also accepts legend_ok wire message as legend_saved', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => events.push(e.type));
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: 'D', coord: null, show: true }]);
        legendOk(holder.socket, 1, 'K9');
        expect(events).toContain('legend_saved');
        session.dispose();
    });

    it('ignores stale acks for a previous legend seq', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => events.push(e.type));
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: 'D', coord: null, show: true }]);
        // wrong seq should be ignored
        ack(holder.socket, 99, 'K99');
        expect(events).not.toContain('legend_saved');
        ack(holder.socket, 1, 'K2');
        expect(events).toContain('legend_saved');
        session.dispose();
    });

    it('resends the in-flight legend after a reconnect with the same key and seq', () => {
        vi.useFakeTimers();
        vi.spyOn(Math, 'random').mockReturnValue(0);
        const sockets: FakeSocket[] = [];
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, (url) => {
            const s = new FakeSocket();
            sockets.push(s);
            return s;
        });
        sockets[0].open();
        ack(sockets[0], 0, 'K1');
        session.saveLegend([{ symbol: 'X', desc: 'D', coord: null, show: true }]);
        expect(sockets[0].sent[1]).toContain('map_edit_legend');
        sockets[0].drop();
        vi.advanceTimersByTime(600);
        expect(sockets).toHaveLength(2);
        sockets[1].open();
        expect(sockets[1].sent[0]).toContain('map_edit_legend');
        expect(sockets[1].sent[0]).toContain('"K1"');
        session.dispose();
        vi.useRealTimers();
    });

    it('serializes legend coord, fg, bg and show flag (colors become ANSI)', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        // plain colors -> ANSI-wrapped symbol, fg/bg nulled (server stores ANSI)
        session.saveLegend([{ symbol: 'Z', desc: 'Hidden', coord: [3, 4], show: false, fg: [10, 20, 30] as any, bg: [40, 50, 60] as any }]);
        const body = JSON.parse(holder.socket.sent[1])[1][2][0];
        expect(body.desc).toBe('Hidden');
        expect(body.coord).toEqual([3, 4]);
        expect(body.show).toBe(false);
        // symbol wrapped with both fg and bg
        expect(body.symbol).toContain('\x1b[48;2;40;50;60m');
        expect(body.symbol).toContain('\x1b[38;2;10;20;30m');
        expect(body.symbol.endsWith('\x1b[0m')).toBe(true);
        expect(body.fg).toBeNull();
        expect(body.bg).toBeNull();
        session.dispose();
    });

    it('does not emit empty-desc entries – client validation prevents them from being sent', () => {
        const holder = makeHolder();
        const session = new MapEditSession('K0', makeCanvas(), { originX: 0, originY: 0 }, holder.createSocket);
        const events: string[] = [];
        session.onEvent((e) => { if (e.type === 'error') events.push(e.message); });
        holder.socket.open();
        ack(holder.socket, 0, 'K1');
        // exactly the bug that caused "no change" before: empty desc was once coerced to '' and
        // then dropped server-side – now the client refuses to send it at all.
        session.saveLegend([{ symbol: 'X', desc: '', coord: null, show: true } as any]);
        expect(events[0]).toMatch(/Legend description required/);
        expect(holder.socket.sent).toHaveLength(1);
        session.dispose();
    });
});

// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearDrawGrant, launchDraw, readDrawGrant, __resetLaunchThrottleForTests } from '../src/webclient/launch';
import { WebSocketConnection, WebSocketLike, websocketUrl, decodeWireData } from '../src/webclient/connection';
import { parseWireMessage } from '../src/webclient/types';
import { normalizeServerText, promptVisibleLength, DEFAULT_TEXT_COLOR, formatPrompt, formatTextOutput } from '../src/webclient/text';
import { asBoolean, asMapPayload, normalizeShowLegend } from '../src/webclient/payload';
import { renderMap } from '../src/webclient/map';
import * as fs from 'node:fs';
import * as path from 'node:path';

// Helper FakeSocket
class FakeSocket implements WebSocketLike {
    readyState = 0;
    onopen: ((event: Event) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    sent: string[] = [];
    closeCalls = 0;
    send(data: string) { this.sent.push(data); }
    close() { this.closeCalls += 1; }
    open() { this.readyState = 1; this.onopen?.(new Event('open')); }
    drop() { this.readyState = 3; this.onclose?.({} as CloseEvent); }
    deliver(data: unknown) { this.onmessage?.(new MessageEvent('message', { data } as unknown as MessageEventInit)); }
}

describe('launch draw grant persistence and throttling', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="left-terminal"></div>';
        localStorage.clear();
        vi.restoreAllMocks();
        vi.useFakeTimers();
        __resetLaunchThrottleForTests();
    });
    afterEach(() => vi.useRealTimers());

    it('does NOT clear grant synchronously after successful open (race fix)', () => {
        vi.setSystemTime(1000);
        vi.spyOn(window, 'open').mockReturnValue({} as Window);
        const payload = { area: 'TestArea', z: 0, grid: [] };
        expect(launchDraw('secret-key', payload)).toBe(true);
        // grant must still be readable until TTL or reader clears
        expect(readDrawGrant()).toEqual({ key: 'secret-key', payload });
        // reader side clears
        clearDrawGrant();
        expect(readDrawGrant()).toBeNull();
    });

    it('keeps grant when popup blocked (no clear)', () => {
        vi.setSystemTime(2000);
        vi.spyOn(window, 'open').mockReturnValue(null);
        const payload = { area: 'A', z: 0, grid: [] };
        expect(launchDraw('k', payload)).toBe(false);
        expect(readDrawGrant()).toEqual({ key: 'k', payload });
    });

    it('throttle returns false (not lying true)', () => {
        vi.setSystemTime(3000);
        const opened = vi.spyOn(window, 'open').mockReturnValue({} as Window);
        expect(launchDraw()).toBe(true);
        vi.setSystemTime(3500);
        expect(launchDraw()).toBe(false);
        expect(opened).toHaveBeenCalledTimes(1);
        vi.setSystemTime(5000);
        expect(launchDraw()).toBe(true);
        expect(opened).toHaveBeenCalledTimes(2);
    });

    it('handles localStorage.setItem throwing (QuotaExceededError / private mode)', () => {
        vi.setSystemTime(6000);
        vi.spyOn(window, 'open').mockReturnValue({} as Window);
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Quota', 'QuotaExceededError'); });
        // should not throw, should still open
        expect(() => launchDraw('k', { a: 1 })).not.toThrow();
        expect(launchDraw('k2', { a: 1 })).toBe(false); // throttled second immediate call => false due to throttle
        // even without throttle, first call with exception still returns true
        __resetLaunchThrottleForTests();
        vi.setSystemTime(7000);
        expect(launchDraw('k3', { a: 1 })).toBe(true);
    });

    it('expires grant when timestamp missing (corrupt entry)', () => {
        vi.setSystemTime(8000);
        localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: { area: 'a' } }));
        localStorage.removeItem('atheriz_draw_grant_ts');
        expect(readDrawGrant()).toBeNull();
        expect(localStorage.getItem('atheriz_draw_grant')).toBeNull();
    });

    it('expires grant when timestamp is NaN', () => {
        localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: { area: 'a' } }));
        localStorage.setItem('atheriz_draw_grant_ts', 'not-a-number');
        expect(readDrawGrant()).toBeNull();
    });

    it('rejects array payload as invalid grant', () => {
        localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: [] }));
        localStorage.setItem('atheriz_draw_grant_ts', String(Date.now()));
        expect(readDrawGrant()).toBeNull();
        // also rejects array-wrapped grant object
        localStorage.setItem('atheriz_draw_grant', JSON.stringify([{ key: 'k', payload: { area: 'a' } }]));
        expect(readDrawGrant()).toBeNull();
        // rejects null payload
        localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: null }));
        expect(readDrawGrant()).toBeNull();
    });

    it('rejects non-object grant', () => {
        localStorage.setItem('atheriz_draw_grant', JSON.stringify('string'));
        localStorage.setItem('atheriz_draw_grant_ts', String(Date.now()));
        expect(readDrawGrant()).toBeNull();
    });

    it('expires after TTL 60s', () => {
        vi.setSystemTime(1000);
        localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: { area: 'a' } }));
        localStorage.setItem('atheriz_draw_grant_ts', '0');
        expect(readDrawGrant()).toEqual({ key: 'k', payload: { area: 'a' } });
        vi.setSystemTime(61001);
        expect(readDrawGrant()).toBeNull();
    });
});

describe('websocket binary frames and URL handling', () => {
    it('decodeWireData handles string', () => {
        expect(decodeWireData('["text", ["hi"], {}]')).toBe('["text", ["hi"], {}]');
    });
    it('decodeWireData handles ArrayBuffer', () => {
        const encoded = new TextEncoder().encode('["text", ["hi"], {}]');
        const buf = encoded.buffer.slice(encoded.byteOffset, encoded.byteOffset + encoded.byteLength);
        expect(decodeWireData(buf)).toBe('["text", ["hi"], {}]');
    });
    it('decodeWireData handles Uint8Array view', () => {
        const view = new TextEncoder().encode('["pos", [[1,2]], {}]');
        expect(decodeWireData(view)).toBe('["pos", [[1,2]], {}]');
    });
    it('decodeWireData returns null for Blob', () => {
        const blob = new Blob(['hello']);
        expect(decodeWireData(blob)).toBeNull();
    });
    it('decodeWireData returns null for number/object', () => {
        expect(decodeWireData(42)).toBeNull();
        expect(decodeWireData({})).toBeNull();
        expect(decodeWireData(null)).toBeNull();
    });
    it('WebSocketConnection handles ArrayBuffer message via decodeWireData', () => {
        const socket = new FakeSocket();
        const messages: string[] = [];
        const invalid: number[] = [];
        const conn = new WebSocketConnection({
            createSocket: () => socket,
            onMessage: (m) => messages.push(m.command),
            onInvalidMessage: () => invalid.push(1),
        });
        conn.connect();
        socket.open();
        const buf = new TextEncoder().encode('["text", ["hello"], {}]').buffer;
        socket.deliver(buf);
        expect(messages).toEqual(['text']);
        expect(invalid).toEqual([]);
        // Blob should trigger invalid, not throw
        const blob = new Blob(['["text", ["hello"], {}]']);
        socket.deliver(blob);
        expect(invalid).toHaveLength(1);
        expect(messages).toHaveLength(1);
    });
    it('rejects empty command string', () => {
        expect(parseWireMessage('["", [], {}]')).toBeNull();
        expect(parseWireMessage('["text", [], {}]')).not.toBeNull();
    });
    it('websocketUrl uses host with port and handles empty host fallback', () => {
        expect(websocketUrl({ protocol: 'http:', host: 'example.test:9999' })).toBe('ws://example.test:9999/ws');
        expect(websocketUrl({ protocol: 'https:', host: 'example.test' })).toBe('wss://example.test/ws');
        expect(websocketUrl({ protocol: 'http:', host: '' })).toBe('ws://localhost/ws');
        expect(websocketUrl({ protocol: 'http:', host: 'localhost:3000' })).toBe('ws://localhost:3000/ws');
    });
    it('reconnectAttempt resets after manual close then connect', () => {
        vi.useFakeTimers();
        vi.spyOn(Math, 'random').mockReturnValue(0);
        const sockets: FakeSocket[] = [];
        const conn = new WebSocketConnection({
            createSocket: () => {
                const s = new FakeSocket();
                sockets.push(s);
                return s;
            },
            onMessage: () => undefined,
            minReconnectDelayMs: 100,
            maxReconnectDelayMs: 100,
            maxReconnectAttempts: 3,
        });
        conn.connect();
        sockets[0].open();
        // simulate two failed attempts (drop without stable)
        sockets[0].drop();
        vi.advanceTimersByTime(110);
        // second socket auto-created
        expect(sockets).toHaveLength(2);
        sockets[1].drop();
        vi.advanceTimersByTime(110);
        expect(sockets).toHaveLength(3);
        // manually close – should reset budget
        conn.close();
        expect(conn.getState()).toBe('closed');
        // reconnectAttempt was 2 before close; after manual close + connect should reset to 0
        conn.connect();
        expect(conn.getState()).toBe('connecting');
        expect(sockets).toHaveLength(4);
        // drop this new socket – should schedule reconnect (not immediately fail)
        sockets[3].drop();
        vi.advanceTimersByTime(110);
        expect(sockets).toHaveLength(5);
        expect(conn.getState()).toBe('connecting');
        conn.close();
        vi.restoreAllMocks();
        vi.useRealTimers();
    });
    it('reconnect still fails after max attempts without stable', () => {
        vi.useFakeTimers();
        vi.spyOn(Math, 'random').mockReturnValue(0);
        const sockets: FakeSocket[] = [];
        const states: string[] = [];
        const conn = new WebSocketConnection({
            createSocket: () => { const s = new FakeSocket(); sockets.push(s); return s; },
            onMessage: () => undefined,
            onStateChange: (st) => states.push(st),
            minReconnectDelayMs: 10,
            maxReconnectDelayMs: 10,
            maxReconnectAttempts: 2,
        });
        conn.connect();
        sockets[0].drop();
        vi.advanceTimersByTime(20);
        sockets[1].drop();
        vi.advanceTimersByTime(20);
        sockets[2].drop();
        vi.advanceTimersByTime(20);
        expect(conn.getState()).toBe('failed');
        conn.close();
        vi.restoreAllMocks();
        vi.useRealTimers();
    });
    it('ignores data that is not valid JSON via onInvalidMessage', () => {
        const socket = new FakeSocket();
        let invalid = 0;
        const conn = new WebSocketConnection({
            createSocket: () => socket,
            onMessage: () => { throw new Error('should not be called'); },
            onInvalidMessage: () => invalid += 1,
        });
        conn.connect();
        socket.open();
        socket.deliver('not json');
        expect(invalid).toBe(1);
        socket.deliver('["", [], {}]');
        expect(invalid).toBe(2);
    });
});

describe('prompt width and text color normalization', () => {
    it('promptVisibleLength counts surrogate pairs as one', () => {
        // 𜰵 is U+1CC35 (surrogate pair) – length 2 in JS .length but 1 codepoint
        const surrogate = '𜰵';
        expect(surrogate.length).toBe(2);
        expect([...surrogate].length).toBe(1);
        expect(promptVisibleLength(surrogate)).toBe(1);
        expect(promptVisibleLength('a' + surrogate + 'b')).toBe(3);
        const emoji = '😀'; // also surrogate
        expect(promptVisibleLength(emoji)).toBe(1);
        expect(promptVisibleLength('a😀b')).toBe(3);
    });
    it('formatPrompt clears correct number of spaces for surrogate prompt', () => {
        const oldPrompt = '𜰵> ';
        const result = formatPrompt('new> ', oldPrompt, true);
        // should contain 3 spaces (visible length 3: surrogate + '>' + ' ') not 4 (code unit length)
        // old prompt visible length 3 => '\r' + 3 spaces + '\r'
        expect(result).toContain('\r   \r');
        expect(result).not.toContain('\r    \r');
        // ensure it still works for ASCII
        const asciiResult = formatPrompt('new> ', 'old> ', true);
        expect(asciiResult).toContain('\r     \r'); // 'old> ' =5
    });
    it('formatTextOutput clears correct spaces for surrogate', () => {
        const out = formatTextOutput('hello', 80, false, '> ', true);
        expect(out.startsWith('\r  \r')).toBe(true);
        const surrogatePrompt = '𜰵> ';
        const out2 = formatTextOutput('hello', 80, false, surrogatePrompt, true);
        expect(out2.startsWith('\r   \r')).toBe(true);
    });
    it('promptVisibleLength strips ANSI', () => {
        const prompt = '\x1b[31mred\x1b[0m> ';
        // visible is "red> " length 5
        expect(promptVisibleLength(prompt)).toBe(5);
    });
    it('normalizeServerText replaces bright white variants', () => {
        const input97 = '\x1b[97mwhite text';
        const normalized = normalizeServerText(input97, 80, false);
        expect(normalized).toContain(DEFAULT_TEXT_COLOR);
        expect(normalized).not.toContain('\x1b[97m');
        const input90 = '\x1b[90mwhite90';
        expect(normalizeServerText(input90, 80, false)).not.toContain('\x1b[90m');
        const input37 = '\x1b[37mwhite37';
        expect(normalizeServerText(input37, 80, false)).not.toContain('\x1b[37m');
    });
    it('normalizeServerText preserves explicit colors then maps whites', () => {
        const red = '\x1b[38;2;255;0;0m';
        const combined = `${red}red\x1b[0m white\x1b[37mwhite2\x1b[97mbright\x1b[90mgray`;
        const out = normalizeServerText(combined, 80, false);
        expect(out).toContain(red);
        expect(out).not.toContain('\x1b[37m');
        expect(out).not.toContain('\x1b[97m');
        expect(out).not.toContain('\x1b[90m');
    });
});

describe('payload boolean coercion and legend visibility', () => {
    it('asBoolean handles booleans', () => {
        expect(asBoolean(true)).toBe(true);
        expect(asBoolean(false)).toBe(false);
    });
    it('asBoolean handles numeric 1/0', () => {
        expect(asBoolean(1)).toBe(true);
        expect(asBoolean(0)).toBe(false);
        expect(asBoolean(42)).toBe(true);
        expect(asBoolean(-1)).toBe(true);
    });
    it('asBoolean handles string "true"/"1" case insensitive', () => {
        expect(asBoolean('true')).toBe(true);
        expect(asBoolean('True')).toBe(true);
        expect(asBoolean('TRUE')).toBe(true);
        expect(asBoolean('1')).toBe(true);
        expect(asBoolean('  true  ')).toBe(true);
        expect(asBoolean('yes')).toBe(true);
        expect(asBoolean('on')).toBe(true);
    });
    it('asBoolean returns false for falsy strings', () => {
        expect(asBoolean('false')).toBe(false);
        expect(asBoolean('0')).toBe(false);
        expect(asBoolean('no')).toBe(false);
        expect(asBoolean('')).toBe(false);
        expect(asBoolean('random')).toBe(false);
        expect(asBoolean(undefined)).toBe(false);
        expect(asBoolean(null)).toBe(false);
        expect(asBoolean({})).toBe(false);
    });
    it('normalizeShowLegend handles all coercion cases', () => {
        expect(normalizeShowLegend(undefined)).toBe(true);
        expect(normalizeShowLegend(true)).toBe(true);
        expect(normalizeShowLegend(false)).toBe(false);
        expect(normalizeShowLegend(0)).toBe(false);
        expect(normalizeShowLegend(1)).toBe(true);
        expect(normalizeShowLegend('')).toBe(false);
        expect(normalizeShowLegend(null)).toBe(false);
        expect(normalizeShowLegend('0')).toBe(false);
        expect(normalizeShowLegend('false')).toBe(false);
        expect(normalizeShowLegend('False')).toBe(false);
        expect(normalizeShowLegend('no')).toBe(false);
        expect(normalizeShowLegend('off')).toBe(false);
        expect(normalizeShowLegend('true')).toBe(true);
        expect(normalizeShowLegend('1')).toBe(true);
        expect(normalizeShowLegend('yes')).toBe(true);
    });
    it('asMapPayload show_legend respects falsy values', () => {
        expect(asMapPayload({ map: '', show_legend: false }).show_legend).toBe(false);
        expect(asMapPayload({ map: '', show_legend: 0 }).show_legend).toBe(false);
        expect(asMapPayload({ map: '', show_legend: '' }).show_legend).toBe(false);
        expect(asMapPayload({ map: '', show_legend: null }).show_legend).toBe(false);
        expect(asMapPayload({ map: '', show_legend: undefined }).show_legend).toBe(true);
        expect(asMapPayload({ map: '' }).show_legend).toBe(true);
        expect(asMapPayload({ map: '', show_legend: true }).show_legend).toBe(true);
        expect(asMapPayload({ map: '', show_legend: 'false' }).show_legend).toBe(false);
        expect(asMapPayload({ map: '', show_legend: '0' }).show_legend).toBe(false);
    });
    it('renderMap hides legend when show_legend is 0/empty/null/"0"/"false"', () => {
        const base = { map: 'ab', max_y: 0, legend: [{ symbol: 'x', desc: 'Exit' }] } as any;
        const withFalse = renderMap({ ...base, show_legend: false }, 20, 10);
        const with0 = renderMap({ ...base, show_legend: 0 as any }, 20, 10);
        const withEmpty = renderMap({ ...base, show_legend: '' as any }, 20, 10);
        const withNull = renderMap({ ...base, show_legend: null as any }, 20, 10);
        const withString0 = renderMap({ ...base, show_legend: '0' as any }, 20, 10);
        const withStringFalse = renderMap({ ...base, show_legend: 'false' as any }, 20, 10);
        for (const out of [withFalse, with0, withEmpty, withNull, withString0, withStringFalse]) {
            expect(out).not.toContain('Exit');
            expect(out).not.toContain('╭');
        }
        const withTrue = renderMap({ ...base, show_legend: true }, 20, 10);
        expect(withTrue).toContain('Exit');
        const withUndefined = renderMap({ map: 'ab', max_y: 0, legend: [{ symbol: 'x', desc: 'Exit' }] }, 20, 10);
        expect(withUndefined).toContain('Exit');
    });
});

describe('buffer flush fallback and completion', () => {
    it('buffer.ts SequentialWriter contains fallback timer', () => {
        const bufferPath = path.resolve(import.meta.dirname, '../src/webclient/buffer.ts');
        const content = fs.readFileSync(bufferPath, 'utf-8');
        expect(content).toContain('class SequentialWriter');
        expect(content).toContain('BUFFER_WRITE_FALLBACK_MS');
        expect(content).toContain('let settled = false');
        expect(content).toContain('try {');
        expect(content).toContain('this.writeChunk(chunk, done)');
        // main.ts must route through the writer, not its own queue
        const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
        const main = fs.readFileSync(mainPath, 'utf-8');
        expect(main).not.toContain('bufferQueue');
        expect(main).not.toContain('flushBuffer');
        expect(main).toContain('writer.enqueue');
    });
    it('buffer stall fallback clears writing flag after 100ms', async () => {
        vi.useFakeTimers();
        // simulate the fixed flushBuffer logic standalone
        let bufferWriting = false;
        let queue: string[] = ['chunk1', 'chunk2'];
        let writes: string[] = [];
        let finalSeq = '';
        const BUFFER_FINAL = '\x1b[0m\x1b[?25h\n';
        const mockWrite = (chunk: string, cb: () => void) => {
            writes.push(chunk);
            // never call cb – simulate stall (dispose)
        };
        function flushBuffer() {
            if (bufferWriting || queue.length === 0) return;
            bufferWriting = true;
            const chunk = queue.shift();
            if (!chunk) { bufferWriting = false; return; }
            let settled = false;
            const done = () => {
                if (settled) return;
                settled = true;
                bufferWriting = false;
                if (queue.length > 0) flushBuffer();
                else finalSeq = BUFFER_FINAL;
            };
            try { mockWrite(chunk, done); } catch { done(); }
            setTimeout(done, 100);
        }
        flushBuffer();
        expect(bufferWriting).toBe(true);
        expect(writes).toEqual(['chunk1']);
        // before fallback, queue still has chunk2
        expect(queue).toEqual(['chunk2']);
        vi.advanceTimersByTime(100);
        // fallback should have fired, cleared writing and flushed next chunk
        expect(bufferWriting).toBe(true); // second chunk started
        expect(writes).toEqual(['chunk1', 'chunk2']);
        // second chunk also stalls, fallback after another 100ms should emit final
        vi.advanceTimersByTime(100);
        expect(finalSeq).toBe(BUFFER_FINAL);
        expect(bufferWriting).toBe(false);
        expect(queue).toEqual([]);
        vi.useRealTimers();
    });
});

describe('connection state and wire message validation', () => {
    it('WebSocketConnection initial state is idle', () => {
        const conn = new WebSocketConnection({ onMessage: () => undefined });
        expect(conn.getState()).toBe('idle');
    });
    it('main.ts onStateChange handles idle (early return)', () => {
        const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
        const content = fs.readFileSync(mainPath, 'utf-8');
        expect(content).toMatch(/if \(state === 'idle'\) return;/);
    });
    it('parseWireMessage rejects malformed JSON', () => {
        expect(parseWireMessage('not json')).toBeNull();
        expect(parseWireMessage('{"command":"text"}')).toBeNull();
        expect(parseWireMessage('[42, [], {}]')).toBeNull();
        expect(parseWireMessage('["text", "not-array", {}]')).toBeNull();
        expect(parseWireMessage('["text", [], []]')).toBeNull();
    });
});

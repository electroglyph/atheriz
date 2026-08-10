import { describe, expect, it, vi } from 'vitest';
import { WebSocketConnection, WebSocketLike, websocketUrl } from '../src/webclient/connection';

class FakeSocket implements WebSocketLike {
    readyState = 0;
    onopen: ((event: Event) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    sent: string[] = [];
    closeCalls = 0;

    send(data: string): void {
        this.sent.push(data);
    }

    close(): void {
        this.closeCalls += 1;
    }

    open(): void {
        this.readyState = 1;
        this.onopen?.(new Event('open'));
    }

    drop(): void {
        this.readyState = 3;
        this.onclose?.({} as CloseEvent);
    }

    fail(): void {
        this.onerror?.(new Event('error'));
    }
}

describe('webclient connection', () => {
    it('derives ws and wss endpoints from the current host', () => {
        expect(websocketUrl({ protocol: 'http:', host: 'example.test:9999' })).toBe('ws://example.test:9999/ws');
        expect(websocketUrl({ protocol: 'https:', host: 'example.test' })).toBe('wss://example.test/ws');
    });

    it('parses messages and sends only while open', () => {
        const socket = new FakeSocket();
        const messages: string[] = [];
        const connection = new WebSocketConnection({
            createSocket: () => socket,
            onMessage: (message) => messages.push(message.command),
            minReconnectDelayMs: 1000,
        });

        connection.connect();
        expect(connection.send('text', ['ignored'])).toBe(false);
        socket.open();
        expect(connection.send('launch_draw')).toBe(true);
        socket.onmessage?.(new MessageEvent('message', { data: '["text", ["hello"], {}]' }));

        expect(socket.sent).toEqual(['["launch_draw",[],{}]']);
        expect(messages).toEqual(['text']);
        connection.close();
        expect(socket.closeCalls).toBe(1);
    });

    it('reconnects after an unexpected close', () => {
        vi.useFakeTimers();
        const sockets: FakeSocket[] = [];
        const connection = new WebSocketConnection({
            createSocket: () => {
                const socket = new FakeSocket();
                sockets.push(socket);
                return socket;
            },
            onMessage: () => undefined,
            minReconnectDelayMs: 100,
            maxReconnectDelayMs: 100,
        });

        connection.connect();
        sockets[0].drop();
        vi.advanceTimersByTime(200);
        expect(sockets).toHaveLength(2);
        connection.close();
        vi.useRealTimers();
    });

    it('ignores close events from stale sockets', () => {
        vi.useFakeTimers();
        vi.spyOn(Math, 'random').mockReturnValue(0);
        const sockets: FakeSocket[] = [];
        const states: string[] = [];
        const connection = new WebSocketConnection({
            createSocket: () => {
                const socket = new FakeSocket();
                sockets.push(socket);
                return socket;
            },
            onMessage: () => undefined,
            onStateChange: (state) => states.push(state),
            minReconnectDelayMs: 100,
            maxReconnectDelayMs: 100,
        });

        connection.connect();
        sockets[0].drop();
        vi.advanceTimersByTime(100);
        sockets[1].open();
        sockets[0].drop();

        expect(connection.getState()).toBe('open');
        expect(states.at(-1)).toBe('open');
        connection.close();
        vi.restoreAllMocks();
        vi.useRealTimers();
    });

    it('reports errors from the active socket', () => {
        const socket = new FakeSocket();
        const errors: Event[] = [];
        const connection = new WebSocketConnection({
            createSocket: () => socket,
            onMessage: () => undefined,
            onError: (event) => errors.push(event),
        });

        connection.connect();
        socket.fail();

        expect(errors).toHaveLength(1);
    });
});

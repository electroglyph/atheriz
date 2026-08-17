import { ConnectionState, encodeWireMessage, MessageHandler, parseWireMessage } from './types';

export interface WebSocketLike {
    readyState: number;
    onopen: ((event: Event) => void) | null;
    onclose: ((event: CloseEvent) => void) | null;
    onerror: ((event: Event) => void) | null;
    onmessage: ((event: MessageEvent) => void) | null;
    send(data: string): void;
    close(): void;
}

export interface ConnectionOptions {
    createSocket?: (url: string) => WebSocketLike;
    onMessage: MessageHandler;
    onStateChange?: (state: ConnectionState) => void;
    onInvalidMessage?: () => void;
    onError?: (event: Event) => void;
    minReconnectDelayMs?: number;
    maxReconnectDelayMs?: number;
    maxReconnectAttempts?: number;
}

export const OPEN_STATE = 1;

export function websocketUrl(locationLike?: Pick<Location, 'protocol' | 'host'>): string {
    const currentLocation = locationLike ?? (
        typeof window === 'undefined'
            ? { protocol: 'http:', host: 'localhost' }
            : window.location
    );
    const protocol = currentLocation.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${currentLocation.host}/ws`;
}

export class WebSocketConnection {
    private readonly createSocket: (url: string) => WebSocketLike;
    private readonly onMessage: MessageHandler;
    private readonly onStateChange?: (state: ConnectionState) => void;
    private readonly onInvalidMessage?: () => void;
    private readonly onError?: (event: Event) => void;
    private readonly minReconnectDelayMs: number;
    private readonly maxReconnectDelayMs: number;
    private readonly maxReconnectAttempts: number;
    private socket: WebSocketLike | null = null;
    private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    private reconnectAttempt = 0;
    private manuallyClosed = false;
    private state: ConnectionState = 'idle';

    constructor(options: ConnectionOptions) {
        this.createSocket = options.createSocket ?? ((url) => new WebSocket(url));
        this.onMessage = options.onMessage;
        this.onStateChange = options.onStateChange;
        this.onInvalidMessage = options.onInvalidMessage;
        this.onError = options.onError;
        this.minReconnectDelayMs = options.minReconnectDelayMs ?? 500;
        this.maxReconnectDelayMs = options.maxReconnectDelayMs ?? 15_000;
        this.maxReconnectAttempts = Math.max(0, options.maxReconnectAttempts ?? 3);
    }

    connect(): void {
        this.manuallyClosed = false;
        if (this.state === 'failed') this.reconnectAttempt = 0;
        this.clearReconnectTimer();
        if (this.socket?.readyState === OPEN_STATE || this.state === 'connecting') return;

        this.setState('connecting');
        const socket = this.createSocket(websocketUrl());
        this.socket = socket;
        socket.onopen = () => {
            if (this.socket !== socket) return;
            this.reconnectAttempt = 0;
            this.setState('open');
        };
        socket.onmessage = (event) => {
            if (this.socket !== socket) return;
            const message = parseWireMessage(event.data);
            if (message) this.onMessage(message);
            else this.onInvalidMessage?.();
        };
        socket.onerror = (event) => {
            if (this.socket === socket) this.onError?.(event);
        };
        socket.onclose = () => {
            if (this.socket !== socket) return;
            this.socket = null;
            if (this.manuallyClosed) {
                this.setState('closed');
                return;
            }
            if (this.reconnectAttempt >= this.maxReconnectAttempts) {
                this.setState('failed');
                return;
            }
            this.scheduleReconnect();
            this.setState('closed');
        };
    }

    close(): void {
        this.manuallyClosed = true;
        this.clearReconnectTimer();
        this.socket?.close();
        this.socket = null;
        this.setState('closed');
    }

    send(command: string, args: unknown[] = [], kwargs: Record<string, unknown> = {}): boolean {
        if (this.socket?.readyState !== OPEN_STATE) return false;
        this.socket.send(encodeWireMessage(command, args, kwargs));
        return true;
    }

    getState(): ConnectionState {
        return this.state;
    }

    private setState(state: ConnectionState): void {
        this.state = state;
        this.onStateChange?.(state);
    }

    private scheduleReconnect(): void {
        this.clearReconnectTimer();
        const exponential = Math.min(
            this.maxReconnectDelayMs,
            this.minReconnectDelayMs * (2 ** this.reconnectAttempt),
        );
        const jitter = Math.floor(Math.random() * Math.min(250, exponential / 4));
        this.reconnectAttempt += 1;
        this.reconnectTimer = setTimeout(() => this.connect(), exponential + jitter);
    }

    private clearReconnectTimer(): void {
        if (this.reconnectTimer !== undefined) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = undefined;
        }
    }
}

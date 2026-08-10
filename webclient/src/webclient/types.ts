export type JsonObject = Record<string, unknown>;

export interface WireMessage {
    command: string;
    args: unknown[];
    kwargs: JsonObject;
}

export interface MapPayload {
    map: string;
    pos?: [number, number];
    symbol?: string;
    legend?: MapLegendEntry[];
    min_x?: number;
    max_y?: number;
    area?: string;
    show_legend?: boolean;
    background?: MapBackground | MapBackground[];
}

export interface MapLegendEntry {
    symbol: string;
    desc: string;
    coords?: [number, number];
}

export interface MapBackground {
    color: [number, number, number];
    coords: Array<[number, number]>;
}

export interface WebClientElements {
    leftTerminal: HTMLElement;
    rightTerminal: HTMLElement;
    divider: HTMLElement;
    input: HTMLTextAreaElement;
}

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed';

export type MessageHandler = (message: WireMessage) => void;

export function parseWireMessage(raw: string): WireMessage | null {
    let value: unknown;
    try {
        value = JSON.parse(raw);
    } catch {
        return null;
    }

    if (!Array.isArray(value) || typeof value[0] !== 'string') return null;
    const args = value.length > 1 ? value[1] : [];
    const kwargs = value.length > 2 ? value[2] : {};
    if (!Array.isArray(args) || !isJsonObject(kwargs)) return null;

    return { command: value[0], args, kwargs };
}

export function isJsonObject(value: unknown): value is JsonObject {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function encodeWireMessage(command: string, args: unknown[] = [], kwargs: JsonObject = {}): string {
    return JSON.stringify([command, args, kwargs]);
}

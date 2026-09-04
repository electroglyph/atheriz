export type RecordingEvent = [number, 'o' | 'r' | 'resize' | 'show_right' | 'hide_right', unknown];

export interface RecordingTerminalSize {
    cols: number;
    rows: number;
}

export interface RecordingHeader {
    version: 3;
    timestamp: number;
    title: string;
    left: RecordingTerminalSize;
    right: RecordingTerminalSize;
    divider_pct: number;
    right_visible: boolean;
}

export class SessionRecorder {
    // In-memory ring cap: a long recording must not grow RAM without bound.
    // Oldest events are dropped first; elapsed timestamps stay valid.
    static readonly MAX_EVENTS = 100000;
    private startedAt = 0;
    private header: RecordingHeader | null = null;
    private events: RecordingEvent[] = [];

    get active(): boolean {
        return this.header !== null;
    }

    start(left: RecordingTerminalSize, right: RecordingTerminalSize, dividerPct: number, rightVisible: boolean): void {
        this.startedAt = Date.now();
        this.header = {
            version: 3,
            timestamp: Math.round(this.startedAt / 1000),
            title: 'xtermia2 recording',
            left,
            right,
            divider_pct: dividerPct,
            right_visible: rightVisible,
        };
        this.events = [];
    }

    output(side: 'o' | 'r', text: string): void {
        if (this.header) this.push([this.elapsed(), side, text]);
    }

    resize(data: unknown): void {
        if (this.header) this.push([this.elapsed(), 'resize', data]);
    }

    layoutEvent(type: 'show_right' | 'hide_right'): void {
        if (this.header) this.push([this.elapsed(), type, {}]);
    }

    stop(): string | null {
        if (!this.header) return null;
        const result = [JSON.stringify(this.header), ...this.events.map((event) => JSON.stringify(event))].join('\n') + '\n';
        this.header = null;
        this.events = [];
        return result;
    }

    private push(event: RecordingEvent): void {
        this.events.push(event);
        if (this.events.length > SessionRecorder.MAX_EVENTS) {
            this.events.splice(0, Math.ceil(SessionRecorder.MAX_EVENTS / 2));
        }
    }

    private elapsed(): number {
        return Number(((Date.now() - this.startedAt) / 1000).toFixed(6));
    }
}

import { describe, expect, it, vi } from 'vitest';
import { SessionRecorder } from '../src/webclient/recorder';

describe('webclient session recorder', () => {
    it('writes an asciinema-compatible header and events', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
        const recorder = new SessionRecorder();
        recorder.start({ cols: 80, rows: 24 }, { cols: 40, rows: 24 }, 50, true);
        recorder.output('o', 'hello');
        const output = recorder.stop();

        expect(output).not.toBeNull();
        expect(output).toContain('"version":3');
        expect(output).toContain('[0,"o","hello"]');
        expect(recorder.active).toBe(false);
        vi.useRealTimers();
    });

    it('records layout changes as resize events', () => {
        const recorder = new SessionRecorder();
        recorder.start({ cols: 80, rows: 24 }, { cols: 40, rows: 24 }, 50, true);
        recorder.resize({ divider_pct: 65, right_visible: false });
        expect(recorder.stop()).toContain('[0,"resize",{"divider_pct":65,"right_visible":false}]');
    });

    it('returns null when stopping an inactive recorder', () => {
        expect(new SessionRecorder().stop()).toBeNull();
    });
});

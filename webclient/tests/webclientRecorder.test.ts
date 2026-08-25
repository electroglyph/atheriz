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
        expect(output).toContain('"title":"xtermia2 recording"');
        expect(output).toContain('[0,"o","hello"]');
        expect(recorder.active).toBe(false);
        vi.useRealTimers();
    });

    it('records layout changes as resize events', () => {
        const recorder = new SessionRecorder();
        recorder.start({ cols: 80, rows: 24 }, { cols: 40, rows: 24 }, 50, true);
        recorder.resize({ divider_pct: 65, right_visible: false });
        const output = recorder.stop() ?? '';
        expect(output).toContain('"resize"');
        expect(output).toContain('"divider_pct":65');
        expect(output).toContain('"right_visible":false');
    });

    it('records map clear output on the right side', () => {
        const recorder = new SessionRecorder();
        recorder.start({ cols: 80, rows: 24 }, { cols: 40, rows: 24 }, 50, true);
        recorder.output('r', '\x1b[2J\x1b[3J\x1b[H');
        expect(recorder.stop()).toContain('[0,"r","\\u001b[2J\\u001b[3J\\u001b[H"]');
    });

    it('keeps legacy map pane visibility events', () => {
        const recorder = new SessionRecorder();
        recorder.start({ cols: 80, rows: 24 }, { cols: 40, rows: 24 }, 50, false);
        recorder.layoutEvent('show_right');
        recorder.layoutEvent('hide_right');
        const output = recorder.stop();
        expect(output).toContain('[0,"show_right",{}]');
        expect(output).toContain('[0,"hide_right",{}]');
    });

    it('returns null when stopping an inactive recorder', () => {
        expect(new SessionRecorder().stop()).toBeNull();
    });
});

// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { SequentialWriter, BUFFER_WRITE_FALLBACK_MS } from '../src/webclient/buffer';
import { inputHeight } from '../src/webclient/input';
import { parseBackground } from '../src/webclient/map';
import { SessionRecorder } from '../src/webclient/recorder';
import {
  launchDraw,
  readDrawGrant,
  __resetLaunchThrottleForTests,
} from '../src/webclient/launch';

describe('finding: SequentialWriter keeps wire order and survives stalls', () => {
  it('writes chunks in order and drains once per cycle', () => {
    const writes: string[] = [];
    const pendingDone: Array<() => void> = [];
    let drained = 0;
    const writer = new SequentialWriter(
      (chunk, done) => { writes.push(chunk); pendingDone.push(done); },
      () => { drained += 1; },
    );
    writer.enqueue('a');
    writer.enqueue('b');
    // 'a' is in flight while 'b' waits: a single drain cycle.
    expect(writes).toEqual(['a']);
    pendingDone[0]();
    expect(writes).toEqual(['a', 'b']);
    expect(drained).toBe(0);
    pendingDone[1]();
    expect(drained).toBe(1);
    expect(writer.pending).toBe(0);
    expect(writer.busy).toBe(false);
  });

  it('clear() drops the queue and ignores the stale in-flight callback', () => {
    vi.useFakeTimers();
    try {
      const writes: string[] = [];
      let drained = 0;
      const writer = new SequentialWriter(
        (chunk, done) => { writes.push(chunk); done(); },
        () => { drained += 1; },
      );
      // Stall the first write: capture done without calling it.
      let stalledDone: (() => void) | null = null;
      const stalling = new SequentialWriter(
        (chunk, done) => { writes.push(`stall:${chunk}`); stalledDone = done; },
        () => { drained += 1; },
      );
      stalling.enqueue('a');
      stalling.enqueue('b');
      expect(writes).toEqual(['stall:a']);
      stalling.clear();
      expect(stalling.pending).toBe(0);
      expect(stalling.busy).toBe(false);
      // The fallback timer fires the stale callback, which must be ignored.
      vi.advanceTimersByTime(BUFFER_WRITE_FALLBACK_MS + 50);
      expect(writes).toEqual(['stall:a']);
      expect(drained).toBe(0);
      // The writer is usable again after the reset.
      stalledDone = null;
      stalling.enqueue('c');
      expect(writes).toEqual(['stall:a', 'stall:c']);
      expect(writer.pending).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('fallback fires onDrained when the write callback never runs', () => {
    vi.useFakeTimers();
    try {
      let drained = 0;
      const writer = new SequentialWriter(
        (_chunk, _done) => { /* stall forever */ },
        () => { drained += 1; },
      );
      writer.enqueue('x');
      expect(drained).toBe(0);
      vi.advanceTimersByTime(BUFFER_WRITE_FALLBACK_MS + 50);
      expect(drained).toBe(1);
      expect(writer.busy).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('a throwing writeChunk still advances the queue', () => {
    const writes: string[] = [];
    let drained = 0;
    let calls = 0;
    const writer = new SequentialWriter(
      (chunk, done) => {
        calls += 1;
        writes.push(chunk);
        if (calls === 1) throw new Error('disposed');
        done();
      },
      () => { drained += 1; },
    );
    writer.enqueue('a');
    writer.enqueue('b');
    expect(writes).toEqual(['a', 'b']);
    // Two drain cycles: the throw drains 'a' immediately via the catch path,
    // then 'b' drains normally. The queue must advance in both cases.
    expect(drained).toBe(2);
  });
});

describe('finding 7: inputHeight caps runaway input growth', () => {
  it('clamps to [minimum, maximum]', () => {
    expect(inputHeight(80)).toBe(80);
    expect(inputHeight(10)).toBe(30);
    expect(inputHeight(100000)).toBe(300);
    expect(inputHeight(500, 30, 100)).toBe(100);
  });
});

describe('finding 8: parseBackground rejects non-integer coords and colors', () => {
  it('rejects float coords', () => {
    expect(parseBackground([{ color: [255, 0, 0], coords: [[1.5, 2]] }])).toBeUndefined();
  });

  it('rejects non-integer and out-of-range colors', () => {
    expect(parseBackground([{ color: [255, 0, 0.5], coords: [[1, 2]] }])).toBeUndefined();
    expect(parseBackground([{ color: [255, 0, 300], coords: [[1, 2]] }])).toBeUndefined();
  });

  it('accepts well-formed integer payloads', () => {
    expect(parseBackground([{ color: [1, 2, 3], coords: [[4, 5]] }])).toEqual({
      color: [1, 2, 3],
      coords: [[4, 5]],
    });
  });

  it('map.ts guards absurd background padding against RangeError', () => {
    const mapPath = path.resolve(import.meta.dirname, '../src/webclient/map.ts');
    const content = fs.readFileSync(mapPath, 'utf-8');
    expect(content).toContain('MAX_BACKGROUND_PAD');
  });
});

describe('finding 14: recorder event cap bounds memory', () => {
  it('drops oldest events past MAX_EVENTS', () => {
    const rec = new SessionRecorder();
    rec.start({ cols: 80, rows: 24 }, { cols: 80, rows: 24 }, 50, true);
    for (let i = 0; i < SessionRecorder.MAX_EVENTS + 5; i++) {
      rec.output('o', `line ${i}`);
    }
    const events = (rec as unknown as { events: unknown[] }).events;
    expect(events.length).toBeLessThanOrEqual(SessionRecorder.MAX_EVENTS);
  });
});

describe('finding 2: launchDraw stores the grant before the throttle gate', () => {
  beforeEach(() => {
    __resetLaunchThrottleForTests();
    window.localStorage.clear();
    document.body.innerHTML = '';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a throttled second launch still stores the newest grant and opens once', () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    expect(launchDraw('k1', { room: 1 })).toBe(true);
    expect(launchDraw('k2', { room: 2 })).toBe(false);
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(readDrawGrant()).toEqual({ key: 'k2', payload: { room: 2 } });
  });

  it('readDrawGrant clears corrupt JSON instead of lingering', () => {
    window.localStorage.setItem('atheriz_draw_grant', 'not json{{{');
    window.localStorage.setItem('atheriz_draw_grant_ts', String(Date.now()));
    expect(readDrawGrant()).toBeNull();
    expect(window.localStorage.getItem('atheriz_draw_grant')).toBeNull();
  });

  it('readDrawGrant clears wrong-shaped grants instead of lingering', () => {
    window.localStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 42 }));
    window.localStorage.setItem('atheriz_draw_grant_ts', String(Date.now()));
    expect(readDrawGrant()).toBeNull();
    expect(window.localStorage.getItem('atheriz_draw_grant')).toBeNull();
  });
});

describe('webclient/main.ts regression wiring (source pins)', () => {
  const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
  const main = fs.readFileSync(mainPath, 'utf-8');
  const resetStart = main.indexOf('function resetSessionState');
  const resetFn = main.slice(resetStart, main.indexOf('\n}', resetStart));

  it('resetSessionState clears writer, audio, recorder, and map flags', () => {
    expect(resetStart).toBeGreaterThan(-1);
    expect(resetFn).toContain('writer.clear();');
    expect(resetFn).toContain('audio?.pause();');
    expect(resetFn).toContain('recorder');
    expect(resetFn).toContain('mapWanted = false;');
  });

  it('screenreader handler ignores non-boolean args', () => {
    expect(main).toContain("if (typeof message.args[0] === 'boolean') applyScreenReader(message.args[0], true);");
  });

  it('disabling the reader restores the map when the reader hid it', () => {
    expect(main).toContain('if (mapWanted) setMapVisibility(true);');
  });

  it(':reader reverts the local toggle when the send fails', () => {
    const occurrences = main.split('screenReaderEnabled = !screenReaderEnabled;').length - 1;
    expect(occurrences).toBe(2);
    expect(main).toContain("write('\\r\\nNot connected to server.\\r\\n');");
  });

  it(':scrollback is bounded above', () => {
    expect(main).toContain('scrollback > 100000');
  });

  it('offline commands do not pollute history', () => {
    const sendIdx = main.indexOf("submissionFeedback(connection.send('text', [trimmed]))");
    const addIdx = main.indexOf('history.add(trimmed)');
    expect(sendIdx).toBeGreaterThan(-1);
    expect(addIdx).toBeGreaterThan(sendIdx);
  });

  it('history navigation refreshes the ghost-hint completions', () => {
    const navIdx = main.indexOf('history.navigate(');
    const completionsIdx = main.indexOf('history.findCompletions(elements.input.value);', navIdx);
    expect(navIdx).toBeGreaterThan(-1);
    expect(completionsIdx).toBeGreaterThan(navIdx);
  });

  it('divider drag captures the pointer', () => {
    expect(main).toContain('setPointerCapture');
  });

  it('moves_denied in the draw editor reverts to the move checkpoint', () => {
    const drawMain = fs.readFileSync(path.resolve(import.meta.dirname, '../src/main.ts'), 'utf-8');
    expect(drawMain).toContain('pendingMoveCheckpoints');
    expect(drawMain).toContain('undoTo(checkpoint)');
  });
});

// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GlyphScanner } from '../src/utils/GlyphScanner';

function stubFontLoad(load: () => Promise<unknown>) {
  Object.defineProperty(document, 'fonts', {
    value: { load },
    configurable: true,
  });
}

function stubMeasureContext() {
  const fakeCtx = {
    font: '',
    textBaseline: '',
    measureText: (ch: string) => {
      const cp = ch.codePointAt(0);
      // Reference "missing glyph" codepoints measure differently from real glyphs.
      return cp === 0xffff || cp === 0x1ffff || cp === 0x10ffff
        ? { width: 7, actualBoundingBoxLeft: 0, actualBoundingBoxRight: 7 }
        : { width: 10, actualBoundingBoxLeft: 0, actualBoundingBoxRight: 10 };
    },
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(fakeCtx as unknown as CanvasRenderingContext2D);
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0));
  stubMeasureContext();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (document as unknown as Record<string, unknown>).fonts;
});

describe('finding 27: GlyphScanner awaits the real webfont and caches honestly', () => {
  it('waits for document.fonts.load and caches the result', async () => {
    const load = vi.fn().mockResolvedValue([]);
    stubFontLoad(load);

    const first = await GlyphScanner.scanFont('CacheMeFont', () => {});
    expect(load).toHaveBeenCalledTimes(1);
    expect(first.length).toBeGreaterThan(0);

    const second = await GlyphScanner.scanFont('CacheMeFont', () => {});
    expect(load).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
  });

  it('never caches fallback metrics when the font fails to load', async () => {
    const load = vi.fn().mockRejectedValue(new Error('font missing'));
    stubFontLoad(load);

    await GlyphScanner.scanFont('MissingFont', () => {});
    expect(load).toHaveBeenCalledTimes(1);

    await GlyphScanner.scanFont('MissingFont', () => {});
    expect(load).toHaveBeenCalledTimes(2);
  });
});

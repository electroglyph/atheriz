// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { measureCellMetrics, deriveCellMetrics } from '../src/utils/fontMetrics';
import { fontNameToCSS } from '../src/utils/googleFontLoader';

const BACKGROUND_CSS =
  'Most monospace fonts have a ~0.6 width to height ratio';

function mockCanvasCtx() {
  const fonts: string[] = [];
  const ctx: any = {
    font: '',
    measureText: () => ({ width: 10 }),
  };

  // Capture every ctx.font assignment so we can inspect what was requested.
  Object.defineProperty(ctx, 'font', {
    get: () => fonts.join('\n'),
    set: (v: string) => fonts.push(v),
  });

  const createElement = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    const el = createElement(tag);
    if (tag === 'canvas') {
      Object.defineProperty(el, 'getContext', {
        value: () => ctx,
      });
    }
    return el;
  });

  return { ctx, fonts };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('measureCellMetrics builds a valid ctx.font string', () => {
  it('does not double-quote or mangle a multi-family value', () => {
    const { fonts } = mockCanvasCtx();

    // appState.fontFamily can already be a CSS list: `'Fira Code', 'FiraCode'`
    const metrics = measureCellMetrics("'Fira Code', 'FiraCode'", 18);

    // The requested font must remain a valid CSS font-family list. The buggy
    // code wraps the whole value again -> "18px "'Fira Code', 'FiraCode'"",
    // which is invalid CSS and silently ignored by the canvas.
    expect(metrics.font).toBe("18px 'Fira Code', 'FiraCode'");

    const requested = fonts[fonts.length - 1];
    expect(requested).not.toMatch(/""/);
    expect(requested).not.toContain('""');
  });

  it('does not double-quote an already-quoted family name', () => {
    const { fonts } = mockCanvasCtx();
    measureCellMetrics('"Arial"', 18);
    const requested = fonts[fonts.length - 1] ?? '';
    expect(requested).not.toMatch(/""/);
    expect(requested).toBe('18px "Arial"');
  });

  it('returns metrics whose font uses the exact fontSize requested', () => {
    mockCanvasCtx();
    const metrics = measureCellMetrics('monospace', 22);
    expect(metrics.font).toMatch(/^22px /);
  });
});

describe('deriveCellMetrics (pure, no DOM)', () => {
  it('uses the font bounding box when ascent & descent are reported', () => {
    const { height } = deriveCellMetrics(18, {
      fontBoundingBoxAscent: 14,
      fontBoundingBoxDescent: 4,
    });
    // ascent + descent + leading (2)
    expect(height).toBe(20);
  });

  it('prefers fontBoundingBox over actualBoundingBox values', () => {
    const { height } = deriveCellMetrics(18, {
      fontBoundingBoxAscent: 14,
      fontBoundingBoxDescent: 4,
      actualBoundingBoxAscent: 12,
      actualBoundingBoxDescent: 3,
    });
    expect(height).toBe(20);
  });

  it('falls back to realistic actual glyph bounds when font box is absent', () => {
    const { height } = deriveCellMetrics(18, {
      actualBoundingBoxAscent: 14,
      actualBoundingBoxDescent: 3,
    });
    expect(height).toBe(19);
  });

  it('falls back to fontSize * 1.2 when no vertical metrics are reported', () => {
    const { height } = deriveCellMetrics(22, { width: 10 });
    expect(height).toBe(Math.ceil(22 * 1.2));
  });

  it('uses the measured width and a fontSize-ratio fallback when width is absent', () => {
    expect(deriveCellMetrics(20, { width: 15 }).width).toBe(15);
    expect(deriveCellMetrics(20, {}).width).toBe(Math.ceil(20 * 0.6));
  });

  it('never returns a zero/negative width', () => {
    expect(deriveCellMetrics(20, { width: 0 }).width).toBeGreaterThan(0);
  });
});

describe('fontNameToCSS', () => {
  it('does not double-quote a family list', () => {
    // A pre-quoted family list must flow through exactly as-is so that
    // document.fonts.load receives a valid value.
    expect(fontNameToCSS("'Fira Code', 'FiraCode'")).toBe("'Fira Code', 'FiraCode'");
  });

  it('quotes a single bare family name that contains a space', () => {
    expect(fontNameToCSS('Fira Code')).toBe('"Fira Code"');
  });
});

// keep the lint comment reference used by metrics.height logic
void BACKGROUND_CSS;
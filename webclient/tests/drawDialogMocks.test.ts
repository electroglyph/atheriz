// @vitest-environment jsdom
// @ts-nocheck
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../src/utils/GlyphScanner', () => ({
  GlyphScanner: { scanFont: vi.fn() },
}));
vi.mock('../src/utils/googleFontLoader', () => ({
  loadFontPreview: vi.fn(),
  preloadManifest: vi.fn(),
}));

import { CharMapDialog } from '../src/ui/CharMapDialog';
import { GlyphScanner } from '../src/utils/GlyphScanner';
import { GoogleFontPicker } from '../src/ui/GoogleFontPicker';

let ioInstances: Array<{ cb: (...args: any[]) => void; disconnect: () => void }> = [];

function stubIO() {
  ioInstances = [];
  vi.stubGlobal('IntersectionObserver', class {
    cb: (...args: any[]) => void;
    disconnect = vi.fn();
    constructor(cb: (...args: any[]) => void) {
      this.cb = cb;
      ioInstances.push(this);
    }
    observe() {}
    unobserve() {}
  });
}

function setupCharMapDom() {
  document.body.innerHTML = `
    <div id="char-map-modal" class="hidden">
      <div id="char-map-scroll-container"><div id="char-map-inner"></div></div>
      <div id="char-map-selection"></div>
      <button id="btn-char-cancel">Cancel</button>
      <button id="btn-char-confirm">OK</button>
      <div id="char-scan-status" style="display:none"></div>
    </div>`;
}

function setupGfpDom() {
  document.body.innerHTML = `
    <div id="google-font-picker-modal" class="hidden">
      <input id="gfp-search" type="text" />
      <div id="gfp-tabs"></div>
      <div id="gfp-list"></div>
      <div id="gfp-sentinel"></div>
      <button id="gfp-cancel">Cancel</button>
    </div>`;
}

beforeEach(() => {
  stubIO();
  vi.mocked(GlyphScanner.scanFont).mockReset();
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('finding 27: CharMapDialog scan generation guard', () => {
  it('a slow earlier scan does not overwrite a newer font grid', async () => {
    setupCharMapDom();
    const resolvers: Array<(glyphs: number[]) => void> = [];
    vi.mocked(GlyphScanner.scanFont).mockImplementation(
      () => new Promise((resolve) => { resolvers.push(resolve); }),
    );

    const dlg = new CharMapDialog(() => {});
    const pA = dlg.open('FontA');
    const pB = dlg.open('FontB');
    expect(vi.mocked(GlyphScanner.scanFont)).toHaveBeenCalledTimes(2);

    resolvers[1]([66]);
    await pB;
    expect(dlg['validGlyphs']).toEqual([66]);

    resolvers[0]([65]);
    await pA;
    expect(dlg['validGlyphs']).toEqual([66]);
  });
});

describe('finding 29: GoogleFontPicker preview-concurrency counter', () => {
  it('close() leaves in-flight accounting intact so the counter returns to zero', async () => {
    setupGfpDom();
    const picker = new GoogleFontPicker(() => {});
    picker.open();
    expect(ioInstances.length).toBeGreaterThanOrEqual(2);
    const fontObserver = ioInstances[1];

    const item = document.querySelector('.gfp-item');
    expect(item).not.toBeNull();
    fontObserver.cb([{ isIntersecting: true, target: item }]);
    expect(picker['previewInFlight']).toBe(1);

    picker.close();
    await new Promise((r) => setTimeout(r, 0));
    expect(picker['previewInFlight']).toBe(0);
  });

  it('disconnects the font observer when the list re-renders', () => {
    setupGfpDom();
    const picker = new GoogleFontPicker(() => {});
    picker.open();
    expect(ioInstances[1].disconnect).toHaveBeenCalled();
  });
});

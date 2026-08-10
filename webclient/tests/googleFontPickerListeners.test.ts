// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GoogleFontPicker } from '../src/ui/GoogleFontPicker';

function stubIntersectionObserver() {
  class MockObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', MockObserver);
}

function setupDom() {
  const ids = [
    'google-font-picker-modal',
    'gfp-search',
    'gfp-list',
    'gfp-tabs',
    'gfp-cancel',
    'gfp-sentinel',
  ];
  const els: Record<string, HTMLElement> = {};
  for (const id of ids) {
    const el = document.createElement(id === 'gfp-search' || id === 'gfp-cancel' ? 'input' : 'div');
    if (id === 'gfp-search') (el as HTMLInputElement).type = 'text';
    if (id === 'gfp-cancel') (el as HTMLInputElement).type = 'button';
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  return els;
}

describe('GoogleFontPicker document keydown listener lifecycle', () => {
  beforeEach(() => {
    stubIntersectionObserver();
    setupDom();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('removes its document keydown listener on destroy()', () => {
    const removeSpy = vi.spyOn(document, 'removeEventListener');
    const picker = new GoogleFontPicker(() => {});
    picker.destroy();

    const keydownRemovals = removeSpy.mock.calls.filter((call) => call[0] === 'keydown');
    expect(keydownRemovals.length).toBe(1);
  });
});

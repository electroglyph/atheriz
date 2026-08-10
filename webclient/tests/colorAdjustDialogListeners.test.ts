// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ColorAdjustDialog } from '../src/ui/ColorAdjustDialog';

function setupDom() {
  const ids = [
    'color-adjust-modal',
    'color-adjust-brightness',
    'color-adjust-brightness-val',
    'color-adjust-contrast',
    'color-adjust-contrast-val',
    'color-adjust-hue',
    'color-adjust-hue-val',
    'color-adjust-saturation',
    'color-adjust-saturation-val',
    'color-adjust-all-layers',
    'color-adjust-cancel',
    'color-adjust-ok',
  ];
  const els: Record<string, HTMLElement> = {};
  for (const id of ids) {
    const el = document.createElement(id.endsWith('-val') || id === 'color-adjust-modal' ? 'div' : 'input');
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  const content = document.createElement('div');
  content.className = 'modal-content';
  const title = document.createElement('h2');
  content.appendChild(title);
  els['color-adjust-modal'].appendChild(content);
  return els;
}

describe('ColorAdjustDialog window listener lifecycle', () => {
  beforeEach(() => {
    setupDom();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its window mousemove/mouseup listeners on destroy()', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const dialog = new ColorAdjustDialog(() => {}, () => {}, () => {});
    dialog.destroy();

    const removed = removeSpy.mock.calls.filter((call) =>
      ['mousemove', 'mouseup'].includes(call[0] as string),
    );

    expect(removed.filter((c) => c[0] === 'mousemove').length).toBe(1);
    expect(removed.filter((c) => c[0] === 'mouseup').length).toBe(1);
  });
});

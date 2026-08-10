// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ColorPickerModal } from '../src/ui/ColorPickerModal';

function setupDom() {
  const ids = [
    'color-picker-modal',
    'cp-sv-field',
    'cp-hue-bar',
    'cp-preview',
    'cp-r',
    'cp-g',
    'cp-b',
    'cp-hex',
    'cp-ok',
    'cp-cancel',
  ];
  const els: Record<string, HTMLElement> = {};
  for (const id of ids) {
    const el = document.createElement(id === 'cp-sv-field' || id === 'cp-hue-bar' ? 'canvas' : 'div');
    if (id === 'cp-r' || id === 'cp-g' || id === 'cp-b' || id === 'cp-hex') {
      el.id = id;
    }
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  return els;
}

describe('ColorPickerModal window listener lifecycle', () => {
  beforeEach(() => {
    setupDom();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its window mousemove/mouseup listeners on destroy()', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const modal = new ColorPickerModal();
    modal.destroy();

    const removed = removeSpy.mock.calls.filter((call) =>
      ['mousemove', 'mouseup'].includes(call[0] as string),
    );

    expect(removed.filter((c) => c[0] === 'mousemove').length).toBe(1);
    expect(removed.filter((c) => c[0] === 'mouseup').length).toBe(1);
  });
});

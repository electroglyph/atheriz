// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ColorPicker } from '../src/ui/ColorPicker';

function setupDom() {
  const container = document.createElement('div');
  container.id = 'color-picker-container';
  document.body.appendChild(container);
  return container;
}

describe('ColorPicker window colorPicked listener lifecycle', () => {
  beforeEach(() => {
    setupDom();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its window colorPicked listener on destroy()', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const appState: any = { fgColor: [255, 0, 0], bgColor: [0, 0, 255] };
    const picker = new ColorPicker('color-picker-container', true, appState, () => {});
    picker.destroy();

    const colorPickedRemovals = removeSpy.mock.calls.filter((call) => call[0] === 'colorPicked');
    expect(colorPickedRemovals.length).toBe(1);
  });
});

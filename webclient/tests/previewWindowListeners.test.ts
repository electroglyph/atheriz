// @ts-nocheck
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PreviewWindow } from '../src/ui/PreviewWindow';
import { CanvasState } from '../src/state/CanvasState';

describe('PreviewWindow window listener lifecycle', () => {
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    removeSpy = vi.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its window mousemove/mouseup/keydown listeners on destroy()', () => {
    const preview = new PreviewWindow(() => new CanvasState(3, 3), () => 'Unifont');
    preview.destroy();

    const removed = removeSpy.mock.calls.filter((call) =>
      ['mousemove', 'mouseup', 'keydown'].includes(call[0] as string),
    );

    expect(removed.filter((c) => c[0] === 'mousemove').length).toBe(1);
    expect(removed.filter((c) => c[0] === 'mouseup').length).toBe(1);
    expect(removed.filter((c) => c[0] === 'keydown').length).toBe(1);
  });
});

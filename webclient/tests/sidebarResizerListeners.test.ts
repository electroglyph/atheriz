// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SidebarResizer } from '../src/ui/SidebarResizer';

function setupDom() {
  const sidebar = document.createElement('div');
  sidebar.id = 'sidebar';
  const resizer = document.createElement('div');
  resizer.id = 'sidebar-resizer';
  document.body.appendChild(sidebar);
  document.body.appendChild(resizer);
  return { sidebar, resizer };
}

describe('SidebarResizer document listener lifecycle', () => {
  beforeEach(() => {
    setupDom();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its document mousemove/mouseup listeners on destroy()', () => {
    const removeSpy = vi.spyOn(document, 'removeEventListener');
    const resizer = new SidebarResizer('sidebar', 'sidebar-resizer');
    resizer.destroy();

    const removed = removeSpy.mock.calls.filter((call) =>
      ['mousemove', 'mouseup'].includes(call[0] as string),
    );

    expect(removed.filter((c) => c[0] === 'mousemove').length).toBe(1);
    expect(removed.filter((c) => c[0] === 'mouseup').length).toBe(1);
  });
});

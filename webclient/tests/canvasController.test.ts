// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CanvasController } from '../src/canvas/CanvasController';
import { ToolManager } from '../src/tools/ToolManager';
import { ToolContext } from '../src/tools/Tool';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { GridRenderer } from '../src/canvas/GridRenderer';
import { AppState } from '../src/types';
import { CellMetrics } from '../src/utils/fontMetrics';

const metrics: CellMetrics = { width: 10, height: 10, font: '10px monospace' };

function makeAppState(): AppState {
  return {
    activeToolId: 'brush',
    rectMode: 'light',
    ovalMode: 'light',
    lineMode: 'light',
    gradientTarget: 'foreground',
    typeStyle: 'regular',
    selectedChar: 'x',
    fgColor: [255, 255, 255],
    bgColor: [0, 0, 0],
    fontFamily: 'monospace',
    gradientStops: [],
    selectMode: 'single',
    rotateMode: 'cw90',
    fillMode: 'brush',
    lineDiagonal: false,
    eyedropperTarget: 'fg-fg',
  };
}

function makeCanvasDom() {
  const canvas = document.createElement('canvas');
  const bounds = { left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 };
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(bounds as unknown as DOMRect);
  return canvas;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('CanvasController tears down its global listeners', () => {
  it('exposes a destroy() that removes its global listeners', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));

    const controller = new CanvasController(canvas, metrics, tm);

    // Proper API surface: destroy() exists so re-creation doesn't leak handlers.
    expect(typeof (controller as any).destroy).toBe('function');

    const winRemove = vi.spyOn(window, 'removeEventListener');
    const canvasRemove = vi.spyOn(canvas, 'removeEventListener');
    (controller as any).destroy();

    for (const event of ['mousemove', 'mouseup', 'keydown']) {
      expect(winRemove).toHaveBeenCalledWith(event, expect.any(Function));
    }
    for (const event of ['mousedown', 'contextmenu']) {
      expect(canvasRemove).toHaveBeenCalledWith(event, expect.any(Function));
    }
  });

  it('does not react to input after destroy()', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));
    const controller = new CanvasController(canvas, metrics, tm);
    (controller as any).destroy();

    // A mousedown/pointer/key after teardown must not reach the tool manager.
    canvas.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 55, clientY: 55 }));
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 60, clientY: 60 }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }));

    const active = state.getActiveLayer();
    expect(active.cells.flat().every(c => c.char === '')).toBe(true);
  });
});

describe('strokes are clipped at the canvas edge', () => {
  it('does not paint cells outside the grid while dragging', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));

    new CanvasController(canvas, metrics, tm);

    // start inside at cell (5,5)
    canvas.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 55, clientY: 55 }));
    // drag far outside the right edge (way beyond col 9)
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 50000, clientY: 55 }));
    window.dispatchEvent(new MouseEvent('mouseup', { button: 0, clientX: 50000, clientY: 55 }));

    const active = state.getActiveLayer();
    // Proper behavior: no overflow cells written outside the grid.
    expect(active.overflowCells ? active.overflowCells.size : 0).toBe(0);
  });

  it('no longer keeps painting after the pointer leaves the canvas mid-drag', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));

    new CanvasController(canvas, metrics, tm);

    canvas.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 55, clientY: 55 }));
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 50000, clientY: 50000 }));

    // Because the pointer has left the canvas while dragging, no extra cells
    // may end up stored in the overflow map.
    const active = state.getActiveLayer();
    expect(active.overflowCells ? active.overflowCells.size : 0).toBe(0);
  });

  it('clips an off-canvas drag at the last valid cell instead of painting nothing', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));

    new CanvasController(canvas, metrics, tm);

    // start inside at cell (5,5), drag far past the right/bottom edges
    canvas.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 55, clientY: 55 }));
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 50000, clientY: 50000 }));

    const active = state.getActiveLayer();
    const boundary = active.cells[9][9];
    // The stroke should have clipped at the grid edge, painting the corner cell.
    expect(boundary.char).toBe('x');
    expect(active.overflowCells ? active.overflowCells.size : 0).toBe(0);
  });

  it('clamps coordinates that go past the top/left edges to the origin', () => {
    const canvas = makeCanvasDom();
    const state = new CanvasState(10, 10);
    const tm = new ToolManager(makeContext(state));

    new CanvasController(canvas, metrics, tm);

    canvas.dispatchEvent(new MouseEvent('mousedown', { button: 0, clientX: 55, clientY: 55 }));
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: -50000, clientY: -50000 }));

    const active = state.getActiveLayer();
    const origin = active.cells[0][0];
    expect(origin.char).toBe('x');
    expect(active.overflowCells ? active.overflowCells.size : 0).toBe(0);
  });
});

function makeContext(state: CanvasState): ToolContext {
  const undoStack = new UndoStack();
  const renderer = { setPreview: () => {}, clearPreview: () => {} } as unknown as GridRenderer;
  const appState = makeAppState();
  return { state, undoStack, renderer, appState, modifiers: { shiftKey: false, altKey: false, ctrlKey: false } };
}
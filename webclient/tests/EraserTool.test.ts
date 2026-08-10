import { describe, it, expect } from 'vitest';
import { EraserTool } from '../src/tools/EraserTool';
import { AppState } from '../src/types';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { GridRenderer } from '../src/canvas/GridRenderer';
import { ToolContext } from '../src/tools/Tool';

const DEFAULT_FG: [number, number, number] = [204, 204, 204];
const TRANSPARENT: [number, number, number] = [-1, -1, -1];
const BLACK: [number, number, number] = [0, 0, 0];

function makeState(): CanvasState {
  return new CanvasState(5, 5); // index 0 = background layer (black)
}

function makeCtx(state: CanvasState): ToolContext {
  const appState: AppState = {
    activeToolId: 'erase',
    rectMode: 'light',
    ovalMode: 'light',
    lineMode: 'light',
    gradientTarget: 'foreground',
    typeStyle: 'regular',
    selectedChar: 'x',
    fgColor: [255, 255, 255],
    bgColor: BLACK,
    fontFamily: 'monospace',
    gradientStops: [],
    selectMode: 'single',
    rotateMode: 'cw90',
    fillMode: 'brush',
    lineDiagonal: true,
    eyedropperTarget: 'fg-fg',
  };
  const renderer = { setPreview: () => {}, clearPreview: () => {} } as unknown as GridRenderer;
  return {
    state,
    undoStack: new UndoStack(),
    renderer,
    appState,
    modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
  };
}

describe('EraserTool', () => {
  it('erases to opaque black on the background layer', () => {
    const state = makeState();
    const tool = new EraserTool();
    tool.onMouseDown(makeCtx(state), { x: 1, y: 1 });
    const cell = state.getCell(1, 1)!;
    expect(cell.bg).toEqual(BLACK);
    expect(cell.char).toBe('');
    expect(cell.fg).toEqual(DEFAULT_FG);
  });

  it('erases to transparent on an upper layer', () => {
    const state = makeState();
    state.addLayer('Layer 2'); // becomes active layer 1
    const tool = new EraserTool();
    tool.onMouseDown(makeCtx(state), { x: 1, y: 1 });
    const layer2 = state.layers[1];
    expect(layer2.cells[1][1].bg).toEqual(TRANSPARENT);
    expect(layer2.cells[1][1].char).toBe('');
  });

  it('reveals the background through an erased upper layer', () => {
    const state = makeState();
    state.setCell(1, 1, { char: 'B', fg: [9, 9, 9], bg: BLACK });
    state.addLayer('above');
    state.setCell(1, 1, { char: 'Z', fg: [255, 0, 0], bg: [0, 255, 0] });

    const tool = new EraserTool();
    tool.onMouseDown(makeCtx(state), { x: 1, y: 1 });

    const composite = state.getCompositeCell(1, 1)!;
    expect(composite.char).toBe('B');
    expect(composite.bg).toEqual(BLACK);
  });

  it('keeps an upper layer transparent across a drag', () => {
    const state = makeState();
    state.addLayer('above');
    const tool = new EraserTool();
    tool.onMouseDown(makeCtx(state), { x: 0, y: 0 });
    tool.onDrag(makeCtx(state), { x: 0, y: 0 }, { x: 1, y: 1 });
    const above = state.layers[1];
    expect(above.cells[0][0].bg).toEqual(TRANSPARENT);
    expect(above.cells[1][1].bg).toEqual(TRANSPARENT);
  });
});
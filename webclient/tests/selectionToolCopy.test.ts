// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { SelectionTool } from '../src/tools/SelectionTool';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { ToolContext } from '../src/tools/Tool';
import { AppState } from '../src/types';
import { GridRenderer } from '../src/canvas/GridRenderer';

function makeAppState(): AppState {
  return {
    activeToolId: 'select',
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

function makeCtx(state: CanvasState): ToolContext {
  let selection = new Set<string>();
  const renderer = {
    getSelectedCells: () => selection,
    setSelection: (s: Set<string>) => { selection = s; },
    clearSelection: () => { selection = new Set(); },
    setPreview: () => {},
    clearPreview: () => {},
  } as unknown as GridRenderer;
  return {
    state,
    undoStack: new UndoStack(),
    renderer,
    appState: makeAppState(),
    modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
  };
}

describe('SelectionTool copy reads the active layer only', () => {
  it('copies the active-layer cell even when an upper layer shares the coordinate', () => {
    const state = new CanvasState(5, 5);
    state.addLayer('Content'); // becomes active layer 1
    state.setCell(1, 1, { char: 'X', fg: [255, 255, 255], bg: [0, 0, 0] }); // active layer

    // A layer ABOVE the active one shadows (1,1) with different content.
    state.addLayer('Top'); // becomes active layer 2
    state.setCell(1, 1, { char: 'Z', fg: [255, 255, 255], bg: [0, 0, 0] });
    // Make layer 1 (with 'X') active again.
    state.activeLayerIndex = 1;

    // Composite shows the upper layer's 'Z', but the active layer holds 'X'.
    expect(state.getCompositeCell(1, 1)!.char).toBe('Z');
    expect(state.getCell(1, 1)!.char).toBe('X');

    const ctx = makeCtx(state);

    // Select (1,1) on the active layer.
    const tool = new SelectionTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    expect(ctx.renderer.getSelectedCells().has('1,1')).toBe(true);

    tool.onKeyDown(ctx, 'ctrl+c');
    tool.onKeyDown(ctx, 'ctrl+v');

    // The pasted content must be the active layer's 'X', not the upper 'Z'.
    expect(ctx.state.getCompositeCell(1, 1)!.char).toBe('X');
  });
});
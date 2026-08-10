import { describe, it, expect } from 'vitest';
import { BrushTool } from '../src/tools/BrushTool';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { ToolContext } from '../src/tools/Tool';
import { AppState } from '../src/types';
import { GridRenderer } from '../src/canvas/GridRenderer';

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

describe('undo entries are only recorded for real changes', () => {
  it('does not push an undo entry when the canvas is unchanged', () => {
    const state = new CanvasState(3, 3);
    // Pre-fill the target cell so clicking it does not actually change anything.
    state.setCell(1, 1, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });

    const undoStack = new UndoStack();
    undoStack.setCurrentState(state);
    const renderer = { setPreview: () => {}, clearPreview: () => {} } as unknown as GridRenderer;

    const ctx: ToolContext = {
      state,
      undoStack,
      renderer,
      appState: makeAppState(),
      modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
    };

    const tool = new BrushTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });

    // Clicking a cell that already holds exactly the brush's output changes
    // nothing, so it must not record a no-op undo step.
    expect(undoStack.canUndo()).toBe(false);
  });
});
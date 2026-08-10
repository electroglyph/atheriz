// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { EraserTool } from '../src/tools/EraserTool';
import { RectangleTool } from '../src/tools/RectangleTool';
import { OvalTool } from '../src/tools/OvalTool';
import { GradientTool } from '../src/tools/GradientTool';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { ToolContext } from '../src/tools/Tool';
import { AppState } from '../src/types';
import { GridRenderer } from '../src/canvas/GridRenderer';

function makeAppState(overrides: Partial<AppState> = {}): AppState {
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
    ...overrides,
  };
}

function makeCtx(state: CanvasState, overrides: Partial<AppState> = {}): ToolContext {
  const renderer = { setPreview: () => {}, clearPreview: () => {} } as unknown as GridRenderer;
  return {
    state,
    undoStack: new UndoStack(),
    renderer,
    appState: makeAppState(overrides),
    modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
  };
}

describe('no-op undo entries are skipped', () => {
  it('eraser does not push undo when erasing an already-empty cell', () => {
    const state = new CanvasState(3, 3);
    const ctx = makeCtx(state);
    const tool = new EraserTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('eraser pushes undo when erasing a filled cell', () => {
    const state = new CanvasState(3, 3);
    state.setCell(1, 1, { char: 'A', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state);
    const tool = new EraserTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });

  it('rectangle single-click does not push undo when the cell is unchanged', () => {
    const state = new CanvasState(3, 3);
    // rect mode 'light', single point is a horizontal box-drawing piece.
    state.setCell(1, 1, { char: '─', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state);
    const tool = new RectangleTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('rectangle pushes undo when drawing a real change', () => {
    const state = new CanvasState(3, 3);
    const ctx = makeCtx(state);
    // Foreground color differs from the empty cell default fg -> real change.
    ctx.appState.fgColor = [255, 0, 0];
    const tool = new RectangleTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });

  it('oval single-click does not push undo when the cell is unchanged', () => {
    const state = new CanvasState(3, 3);
    // 'custom' oval draws the selected char at a single point.
    state.setCell(1, 1, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state, { ovalMode: 'custom' as const, selectedChar: 'x' });
    const tool = new OvalTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('oval pushes undo when drawing a real change', () => {
    const state = new CanvasState(3, 3);
    const ctx = makeCtx(state, { ovalMode: 'custom', selectedChar: 'x', fgColor: [255, 0, 0] });
    const tool = new OvalTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });

  it('gradient does not push undo when nothing changes', () => {
    // A truly empty canvas (no char, transparent bg) yields no gradient updates.
    const state = new CanvasState(3, 3, false);
    const ctx = makeCtx(state, { gradientStops: [[255, 0, 0], [0, 0, 255]] });
    const tool = new GradientTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    // An empty canvas yields no gradient updates, so no undo entry.
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('gradient pushes undo when it changes a cell', () => {
    const state = new CanvasState(3, 3);
    state.setCell(1, 1, { char: ' ', fg: [0, 0, 0], bg: [0, 0, 0] });
    const ctx = makeCtx(state, { gradientStops: [[255, 0, 0], [0, 0, 255]], gradientTarget: 'foreground' });
    const tool = new GradientTool();
    tool.onMouseDown(ctx, { x: 1, y: 1 });
    tool.onMouseUp(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });
});
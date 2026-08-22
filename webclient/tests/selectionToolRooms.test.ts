// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { SelectionTool } from '../src/tools/SelectionTool';
import { CanvasState } from '../src/state/CanvasState';
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
    selectMode: 'rectangle',
    rotateMode: 'cw90',
    fillMode: 'brush',
    lineDiagonal: false,
    eyedropperTarget: 'fg-fg',
  };
}

describe('SelectionTool keeps room cells in rectangle selections', () => {
  it('retains glyph-less room cells that filterNonEmpty would drop', () => {
    const state = new CanvasState(4, 4);
    // every cell is empty; only (1,1) is a room
    const roomCells = new Set(['1,1']);
    let selection: Set<string> = new Set();
    const renderer = {
      getSelectedCells: () => selection,
      setSelection: (s: Set<string>) => { selection = s; },
      clearSelection: () => { selection = new Set(); },
      setPreview: () => {},
      clearPreview: () => {},
      getRoomCells: () => roomCells,
    } as unknown as GridRenderer;

    const ctx: ToolContext = {
      state,
      undoStack: null as never,
      renderer,
      appState: makeAppState(),
      modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
    };

    const tool = new SelectionTool();
    tool.onMouseDown(ctx, { x: 0, y: 0 });
    tool.onMouseUp(ctx, { x: 2, y: 2 });

    expect(selection).toEqual(new Set(['1,1']));
  });

  it('still drops plain empty cells that are not rooms', () => {
    const state = new CanvasState(4, 4);
    const roomCells = new Set<string>();
    let selection: Set<string> = new Set();
    const renderer = {
      getSelectedCells: () => selection,
      setSelection: (s: Set<string>) => { selection = s; },
      clearSelection: () => { selection = new Set(); },
      setPreview: () => {},
      clearPreview: () => {},
      getRoomCells: () => roomCells,
    } as unknown as GridRenderer;

    const ctx: ToolContext = {
      state,
      undoStack: null as never,
      renderer,
      appState: makeAppState(),
      modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
    };

    const tool = new SelectionTool();
    tool.onMouseDown(ctx, { x: 0, y: 0 });
    tool.onMouseUp(ctx, { x: 2, y: 2 });

    expect(selection.size).toBe(0);
  });
});

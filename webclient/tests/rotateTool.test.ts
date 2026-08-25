// @ts-nocheck
import { describe, it, expect } from 'vitest';
import { RotateTool } from '../src/tools/RotateTool';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { ToolContext } from '../src/tools/Tool';
import { AppState } from '../src/types';

function makeState() {
  const state = new CanvasState(6, 6);
  // 2-cell-wide selection on the background layer
  state.setCell(0, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
  state.setCell(1, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
  return state;
}

function makeCtx(state: CanvasState, selectedCells: string[] = ['0,0', '1,0']) {
  let selection = new Set(selectedCells);
  const renderer = {
    getSelectedCells: () => selection,
    setSelection: (s: Set<string>) => {
      selection = s;
    },
    clearSelection: () => {
      selection = new Set();
    },
    setPreview: () => {},
    clearPreview: () => {},
  };
  const appState: AppState = {
    activeToolId: 'rotate',
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
  const ctx: ToolContext = {
    state,
    undoStack: new UndoStack(),
    renderer,
    appState,
    modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
  };
  return ctx;
}

function nonEmptyCells(state: CanvasState): string[] {
  const keys: string[] = [];
  const layer = state.getActiveLayer();
  for (let r = 0; r < state.height; r++) {
    for (let c = 0; c < state.width; c++) {
      const cell = layer.cells[r][c];
      if (cell.char && cell.char.trim() !== '') {
        keys.push(`${c},${r}`);
      }
    }
  }
  return keys.sort();
}

describe('RotateTool even-size selections rotate in place', () => {
  it('returns cells to their original positions after four 90° rotations', () => {
    const state = makeState();
    const ctx = makeCtx(state);
    const tool = new RotateTool();

    const original = nonEmptyCells(state);

    for (let i = 0; i < 4; i++) {
      tool.applyTransform(ctx, 'cw90');
    }

    // Proper behavior: 4x90° == 360°; the even-width selection must land back
    // exactly where it started. Rounding around a half-cell center causes drift.
    expect(nonEmptyCells(state)).toEqual(original);
  });
});

describe('RotateTool cw90 anchors to the bounding-box top-left', () => {
  it('rotates a 2x1 selection in place after a single step', () => {
    const state = makeState();
    const ctx = makeCtx(state);
    const tool = new RotateTool();

    tool.applyTransform(ctx, 'cw90');

    expect(nonEmptyCells(state)).toEqual(['0,0', '0,1']);
  });

  it('returns an asymmetric L-shape to its original position after four 90° rotations', () => {
    const state = new CanvasState(6, 6);
    state.setCell(0, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.setCell(1, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.setCell(0, 1, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state, ['0,0', '1,0', '0,1']);
    const tool = new RotateTool();

    const original = nonEmptyCells(state);
    for (let i = 0; i < 4; i++) {
      tool.applyTransform(ctx, 'cw90');
    }
    expect(nonEmptyCells(state)).toEqual(original);
  });

  it('flips horizontally within the bounding box without drifting', () => {
    const state = new CanvasState(6, 6);
    state.setCell(0, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.setCell(1, 0, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.setCell(0, 1, { char: 'x', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state, ['0,0', '1,0', '0,1']);
    const tool = new RotateTool();

    tool.applyTransform(ctx, 'flip-h');

    expect(nonEmptyCells(state)).toEqual(['0,0', '1,0', '1,1']);
  });
});
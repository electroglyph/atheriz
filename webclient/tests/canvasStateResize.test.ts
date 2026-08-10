import { describe, it, expect } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';

describe('CanvasState.resize keeps a consistent cell shape', () => {
  it('resized cells expose the full Cell shape including styling flags', () => {
    const s = new CanvasState(2, 2);
    s.setCell(0, 0, {
      char: 'x',
      fg: [255, 0, 0],
      bg: [0, 0, 255],
      bold: true,
      italic: true,
      underline: true,
    });

    // Grow the canvas; every cell must carry bold/italic/underline so the
    // object literal type-checks and runtime rendering is consistent.
    s.resize(4, 4);

    for (const layer of s.layers) {
      for (let r = 0; r < 4; r++) {
        for (let c = 0; c < 4; c++) {
          const cell: any = layer.cells[r][c];
          expect('bold' in cell).toBe(true);
          expect('italic' in cell).toBe(true);
          expect('underline' in cell).toBe(true);
        }
      }
    }
  });
});
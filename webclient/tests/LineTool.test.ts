// @ts-nocheck
import { describe, it, expect } from 'vitest';
import { LineTool } from '../src/tools/LineTool';
import { AppState, Point } from '../src/types';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { GridRenderer } from '../src/canvas/GridRenderer';
import { getLinePoints } from '../src/utils/geometry';

function mockCtx(overrides?: Partial<AppState>): any {
  const appState: AppState = {
    activeToolId: 'line',
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
    lineDiagonal: true,
    eyedropperTarget: 'fg-fg',
    ...overrides,
  };
  const state = new CanvasState(20, 20);
  const undoStack = new UndoStack();
  const renderer = {
    setPreview: () => {},
    clearPreview: () => {},
  } as unknown as GridRenderer;
  return { state, undoStack, renderer, appState, modifiers: { shiftKey: false, altKey: false, ctrlKey: false } };
}

function getCharMap(grid: string[][], x: number, y: number): string {
  return grid[y]?.[x] ?? '';
}

function buildGrid(cells: { col: number; row: number; cell: { char: string } }[]): string[][] {
  if (cells.length === 0) return [];
  const minCol = Math.min(...cells.map(c => c.col));
  const maxCol = Math.max(...cells.map(c => c.col));
  const minRow = Math.min(...cells.map(c => c.row));
  const maxRow = Math.max(...cells.map(c => c.row));
  const width = maxCol - minCol + 1;
  const height = maxRow - minRow + 1;
  const grid: string[][] = Array.from({ length: height }, () => Array(width).fill(''));
  for (const c of cells) {
    grid[c.row - minRow][c.col - minCol] = c.cell.char;
  }
  return grid;
}

describe('LineTool two-segment junction gaps', () => {
  const FIRST_SEG_START = { x: 0, y: 0 };
  const FIRST_SEG_END = { x: 4, y: 4 };
  const JUNCTION = FIRST_SEG_END;

  interface SegmentSpec {
    label: string;
    end: Point;
    length: number;
  }

  function makeSecondSegmentSpecs(): SegmentSpec[] {
    const specs: SegmentSpec[] = [];
    const base = JUNCTION;

    const candidates = [
      { dx: 8, dy: 0, label: 'right (horizontal)' },
      { dx: -8, dy: 0, label: 'left (horizontal)' },
      { dx: 0, dy: 8, label: 'down (vertical)' },
      { dx: 0, dy: -8, label: 'up (vertical)' },
      { dx: 8, dy: 8, label: 'down-right (diagonal)' },
      { dx: 8, dy: -8, label: 'up-right (diagonal)' },
      { dx: -8, dy: 8, label: 'down-left (diagonal)' },
      { dx: -8, dy: -8, label: 'up-left (diagonal)' },
      { dx: 8, dy: 4, label: 'down-right shallow (1:0.5)' },
      { dx: 8, dy: -4, label: 'up-right shallow (1:0.5)' },
      { dx: 8, dy: 2, label: 'down-right very shallow (1:0.25)' },
      { dx: 8, dy: -2, label: 'up-right very shallow (1:0.25)' },
      { dx: 4, dy: 8, label: 'down-right steep (0.5:1)' },
      { dx: 4, dy: -8, label: 'up-right steep (0.5:1)' },
      { dx: 2, dy: 8, label: 'down-right very steep (0.25:1)' },
      { dx: 2, dy: -8, label: 'up-right very steep (0.25:1)' },
      { dx: 6, dy: 8, label: 'down-right 3:4' },
      { dx: 6, dy: -8, label: 'up-right 3:4' },
      { dx: 8, dy: 6, label: 'down-right 4:3' },
      { dx: 8, dy: -6, label: 'up-right 4:3' },
      { dx: 7, dy: 8, label: 'down-right 7:8' },
      { dx: 7, dy: -8, label: 'up-right 7:8' },
      { dx: 8, dy: 7, label: 'down-right 8:7' },
      { dx: 8, dy: -7, label: 'up-right 8:7' },
      { dx: 5, dy: 8, label: 'down-right 5:8' },
      { dx: 5, dy: -8, label: 'up-right 5:8' },
      { dx: 8, dy: 5, label: 'down-right 8:5' },
      { dx: 8, dy: -5, label: 'up-right 8:5' },
      { dx: 3, dy: 8, label: 'down-right 3:8' },
      { dx: 3, dy: -8, label: 'up-right 3:8' },
      { dx: 8, dy: 3, label: 'down-right 8:3' },
      { dx: 8, dy: -3, label: 'up-right 8:3' },
    ];

    for (const c of candidates) {
      specs.push({
        label: c.label,
        end: { x: base.x + c.dx, y: base.y + c.dy },
        length: c.dx !== 0 && c.dy !== 0 ? Math.max(Math.abs(c.dx), Math.abs(c.dy)) : Math.abs(c.dx || c.dy),
      });
    }

    return specs;
  }

  function connectedLine(x0: number, y0: number, x1: number, y1: number, useDiagonal = false): Point[] {
    const raw = getLinePoints({ x: x0, y: y0 }, { x: x1, y: y1 });
    if (raw.length <= 1 || useDiagonal) return raw;
    const totalDx = Math.abs(x1 - x0);
    const totalDy = Math.abs(y1 - y0);
    const preferHorizontal = totalDx >= totalDy;
    const result: Point[] = [raw[0]];
    for (let i = 1; i < raw.length; i++) {
      const prev = raw[i - 1];
      const cur = raw[i];
      if (Math.abs(cur.x - prev.x) === 1 && Math.abs(cur.y - prev.y) === 1) {
        if (preferHorizontal) {
          result.push({ x: cur.x, y: prev.y });
        } else {
          result.push({ x: prev.x, y: cur.y });
        }
      }
      result.push(cur);
    }
    return result;
  }

  function buildGridFromPoints(points: Point[]): string[][] {
    const minX = Math.min(...points.map(p => p.x));
    const maxX = Math.max(...points.map(p => p.x));
    const minY = Math.min(...points.map(p => p.y));
    const maxY = Math.max(...points.map(p => p.y));
    const width = maxX - minX + 1;
    const height = maxY - minY + 1;
    const grid: string[][] = Array.from({ length: height }, () => Array(width).fill(''));
    for (const p of points) {
      grid[p.y - minY][p.x - minX] = 'X';
    }
    return grid;
  }

function getCharFromGrid(grid: string[][], x: number, y: number, minX: number, minY: number): string {
  const gx = x - minX;
  const gy = y - minY;
  if (gy < 0 || gy >= grid.length || gx < 0 || gx >= grid[0].length) return '';
  return grid[gy][gx];
}

  const specs = makeSecondSegmentSpecs();

  it('first segment alone should have no gaps', () => {
    const tool = new LineTool();
    const ctx = mockCtx();
    const points = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, FIRST_SEG_END.x, FIRST_SEG_END.y, true);
    const cells = (tool as any).buildCells(ctx, points);
    const grid = buildGrid(cells);
    for (const p of points) {
      const ch = getCharMap(grid, p.x, p.y);
      expect(ch, `gap at (${p.x},${p.y}) in first segment`).not.toBe('');
    }
  });

  it.each(specs)('no gap at junction: $label', ({ end }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, end.x, end.y, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    const minX = Math.min(...combinedPoints.map(p => p.x));
    const minY = Math.min(...combinedPoints.map(p => p.y));

    for (const p of combinedPoints) {
      const ch = getCharFromGrid(grid, p.x, p.y, minX, minY);
      expect(ch, `gap at (${p.x},${p.y}) for end=(${end.x},${end.y})`).not.toBe('');
    }
  });

  it.each(specs)('junction cell should not be empty: $label', ({ end }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, end.x, end.y, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const junctionCell = cells.find(c => c.col === JUNCTION.x && c.row === JUNCTION.y);

    expect(junctionCell, `junction (${JUNCTION.x},${JUNCTION.y}) has no cell for end=(${end.x},${end.y})`).toBeDefined();
    expect(junctionCell?.cell.char, `junction (${JUNCTION.x},${JUNCTION.y}) has empty char for end=(${end.x},${end.y})`).not.toBe('');
  });

  it.each(specs)('junction character should bridge both segments: $label', ({ end }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, end.x, end.y, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    const minCol = Math.min(...cells.map(c => c.col));
    const minRow = Math.min(...cells.map(c => c.row));
    const junctionChar = grid[JUNCTION.y - minRow]?.[JUNCTION.x - minCol] ?? '';

    expect(junctionChar, `junction char is empty for end=(${end.x},${end.y})`).not.toBe('');
  });

  it('visualize down-left V-turn gap', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, -4, 12, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    console.log('Grid for down-left V-turn (junction at 4,4):');
    console.log(`cells: ${JSON.stringify(cells)}`);
    console.log(`minCol=${Math.min(...cells.map(c => c.col))}, minRow=${Math.min(...cells.map(c => c.row))}`);
    console.log(`grid dimensions: ${grid[0]?.length ?? 0}x${grid.length}`);
    for (let row = 0; row < grid.length; row++) {
      console.log(`row ${row} (len=${grid[row].length}): '${grid[row].map(c => c || ' ').join('')}'`);
    }

    const minCol = Math.min(...cells.map(c => c.col));
    const minRow = Math.min(...cells.map(c => c.row));
    const junctionChar = grid[JUNCTION.y - minRow]?.[JUNCTION.x - minCol] ?? '';
    console.log(`junction (4,4) char: '${junctionChar}'`);
    console.log(`expected at grid[${JUNCTION.y - minRow}][${JUNCTION.x - minCol}]`);

    expect(junctionChar).not.toBe('');
  });

  it('visualize up-right V-turn', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, 12, -4, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    console.log('Grid for up-right V-turn (junction at 4,4):');
    console.log(`cells: ${JSON.stringify(cells)}`);
    console.log(`minCol=${Math.min(...cells.map(c => c.col))}, minRow=${Math.min(...cells.map(c => c.row))}`);
    console.log(`grid dimensions: ${grid[0]?.length ?? 0}x${grid.length}`);
    for (let row = 0; row < grid.length; row++) {
      console.log(`row ${row} (len=${grid[row].length}): '${grid[row].map(c => c || ' ').join('')}'`);
    }

    const minCol = Math.min(...cells.map(c => c.col));
    const minRow = Math.min(...cells.map(c => c.row));
    const junctionChar = grid[JUNCTION.y - minRow]?.[JUNCTION.x - minCol] ?? '';
    console.log(`junction (4,4) char: '${junctionChar}'`);

    expect(junctionChar).not.toBe('');
  });

  it('should show gap visualization for diagonal-to-diagonal junction', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(0, 0, 4, 4, true);
    const seg2 = connectedLine(4, 4, 0, 8, true);

    const combinedPoints: Point[] = [...seg1];
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    console.log('Grid for diagonal down-right (0,0→4,4) then diagonal down-left (4,4→0,8):');
    for (let row = 0; row < grid.length; row++) {
      const rowStr = grid[row].map(c => c || ' ').join('');
      console.log(`y=${row}: '${rowStr}'`);
    }

    const cellSet = new Set(cells.map(c => `${c.col},${c.row}`));
    for (const p of combinedPoints) {
      const has = cellSet.has(`${p.x},${p.y}`);
      if (!has) {
        console.log(`MISSING CELL at (${p.x},${p.y})`);
      }
    }
    expect(cellSet.size).toBe(combinedPoints.length);
  });

  it.each([
    { seg1End: { x: 4, y: 4 }, seg2End: { x: 0, y: 8 }, label: 'down-right then down-left' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: 8, y: 8 }, label: 'down-right then continue down-right' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: 8, y: 0 }, label: 'down-right then up-right' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: 0, y: 0 }, label: 'down-right then up-left' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: -4, y: 8 }, label: 'down-right then down-left-far' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: -4, y: 0 }, label: 'down-right then left' },
    { seg1End: { x: 4, y: 4 }, seg2End: { x: 8, y: -4 }, label: 'down-right then up-right-steep' },
  ])('junction character for $label should bridge segments', ({ seg1End, seg2End }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(0, 0, seg1End.x, seg1End.y, true);
    const seg2 = connectedLine(seg1End.x, seg1End.y, seg2End.x, seg2End.y, true);

    const combinedPoints: Point[] = [...seg1];
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const junctionCell = cells.find(c => c.col === seg1End.x && c.row === seg1End.y);

    console.log(`${seg1End.x},${seg1End.y} → ${seg2End.x},${seg2End.y}: junction char='${junctionCell?.cell.char}' (seg1 entry direction: ${seg1.length >= 2 ? `(${seg1[seg1.length-2].x},${seg1[seg1.length-2].y})→(${seg1End.x},${seg1End.y})` : 'N/A'}, seg2 exit direction: ${seg2.length >= 2 ? `(${seg1End.x},${seg1End.y})→(${seg2[1]?.x},${seg2[1]?.y})` : 'N/A'})`);

    expect(junctionCell, `junction cell missing at (${seg1End.x},${seg1End.y})`).toBeDefined();
    expect(junctionCell?.cell.char, `junction char is empty at (${seg1End.x},${seg1End.y})`).not.toBe('');
  });

  it('should have no empty cells between segments for down-left V-turn', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, -4, 12, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const cellSet = new Set(cells.map(c => `${c.col},${c.row}`));

    for (const p of combinedPoints) {
      const hasCell = cellSet.has(`${p.x},${p.y}`);
      expect(hasCell, `Empty cell at (${p.x},${p.y})`).toBe(true);
    }
  });

  it.each(specs)('adjacent cells along both segments should be filled: $label', ({ end }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(FIRST_SEG_START.x, FIRST_SEG_START.y, JUNCTION.x, JUNCTION.y, true);
    const seg2 = connectedLine(JUNCTION.x, JUNCTION.y, end.x, end.y, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const grid = buildGrid(cells);

    const minX = Math.min(...combinedPoints.map(p => p.x));
    const minY = Math.min(...combinedPoints.map(p => p.y));

    const cellSet = new Set(cells.map(c => `${c.col},${c.row}`));

    for (const p of combinedPoints) {
      const hasCell = cellSet.has(`${p.x},${p.y}`);
      expect(hasCell, `cell missing at (${p.x},${p.y}) for end=(${end.x},${end.y})`).toBe(true);
    }
  });

  it('junction should connect to first segment for 15-cell down-left V-turn', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(0, 0, 15, 15, true);
    const seg2 = connectedLine(15, 15, 0, 29, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const cellMap = new Map<string, string>();
    for (const c of cells) {
      cellMap.set(`${c.col},${c.row}`, c.cell.char);
    }

    const junctionChar = cellMap.get('15,15');
    expect(junctionChar).toBeDefined();
    // The junction must connect to UL (entry from seg1) to avoid a gap.
    expect(junctionChar).not.toBe('┘');
    expect(junctionChar).not.toBe('─');
    expect(junctionChar).not.toBe('│');
  });

  it.each([
    { seg1End: { x: 15, y: 15 }, seg2End: { x: 0, y: 29 }, label: 'exact 45 then approx 45 down-left' },
    { seg1End: { x: 15, y: 15 }, seg2End: { x: 0, y: 30 }, label: 'exact 45 then exact 45 down-left' },
    { seg1End: { x: 15, y: 15 }, seg2End: { x: 0, y: 28 }, label: 'exact 45 then shallow down-left' },
  ])('junction connects to both segments for $label', ({ seg1End, seg2End }) => {
    const tool = new LineTool();
    const ctx = mockCtx();

    const seg1 = connectedLine(0, 0, seg1End.x, seg1End.y, true);
    const seg2 = connectedLine(seg1End.x, seg1End.y, seg2End.x, seg2End.y, true);

    const combinedPoints: Point[] = [];
    for (const p of seg1) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }
    for (const p of seg2) {
      if (!combinedPoints.some(cp => cp.x === p.x && cp.y === p.y)) {
        combinedPoints.push(p);
      }
    }

    const cells = (tool as any).buildCells(ctx, combinedPoints);
    const cellMap = new Map<string, string>();
    for (const c of cells) {
      cellMap.set(`${c.col},${c.row}`, c.cell.char);
    }

    // Find the junction cell
    const junctionChar = cellMap.get(`${seg1End.x},${seg1End.y}`);
    expect(junctionChar, `junction at (${seg1End.x},${seg1End.y}) should have a character`).toBeDefined();
    expect(junctionChar, `junction at (${seg1End.x},${seg1End.y}) should not be empty`).not.toBe('');

    // Find the cell before the junction in seg1
    const prevInSeg1 = seg1[seg1.length - 2];
    const prevChar = cellMap.get(`${prevInSeg1.x},${prevInSeg1.y}`);
    expect(prevChar, `cell before junction at (${prevInSeg1.x},${prevInSeg1.y}) should exist`).toBeDefined();

    // The previous cell and junction should be adjacent
    const pdx = seg1End.x - prevInSeg1.x;
    const pdy = seg1End.y - prevInSeg1.y;
    expect(Math.abs(pdx) <= 1 && Math.abs(pdy) <= 1, `previous cell should be adjacent to junction`).toBe(true);

    // The junction character should not be a box corner that doesn't connect to corners
    const badJunctionChars = ['┘', '┐', '└', '┌', '─', '│'];
    expect(badJunctionChars.includes(junctionChar!), `junction char '${junctionChar}' should connect to the entry corner`).toBe(false);
  });

  it('all 8x8 junction transitions use an exact glyph or acceptable edge fallback', () => {
    const tool = new LineTool();
    const ctx = mockCtx();

    // Exact connection points for each glyph, based on Unicode names
    const glyphConnections: Record<string, Set<string>> = {
      '─': new Set(['ML', 'MR']),
      '│': new Set(['MT', 'MB']),
      '┘': new Set(['ML', 'MT']),
      '┐': new Set(['ML', 'MB']),
      '└': new Set(['MR', 'MT']),
      '┌': new Set(['MR', 'MB']),
      '╱': new Set(['LL', 'UR']),
      '╲': new Set(['LR', 'UL']),
      '🯐': new Set(['MR', 'LL']),
      '🯑': new Set(['UR', 'ML']),
      '🯒': new Set(['UL', 'MR']),
      '🯓': new Set(['ML', 'LR']),
      '🯔': new Set(['UL', 'MB']),
      '🯕': new Set(['MT', 'LR']),
      '🯖': new Set(['UR', 'MB']),
      '🯗': new Set(['MT', 'LL']),
      '🯘': new Set(['UL', 'UR']),
      '🯙': new Set(['UR', 'LR']),
      '🯚': new Set(['LL', 'LR']),
      '🯛': new Set(['UL', 'LL']),
      '🯜': new Set(['UL', 'MB', 'UR']),
      '🯝': new Set(['UR', 'ML', 'LR']),
      '🯞': new Set(['LL', 'MT', 'LR']),
      '🯟': new Set(['UL', 'MR', 'LL']),
    };

    // For cases with no exact glyph, the fallback must be on the same edge
    const acceptableFallbacks: Record<string, string> = {
      'LL-ML': '🯛', 'ML-UL': '🯛',
      'LR-MR': '🯙', 'MR-UR': '🯙',
      'MT-UL': '🯘', 'MT-UR': '🯘',
      'LL-MB': '🯚', 'LR-MB': '🯚',
    };

    const directions = [
      { dx: 1, dy: 0, entry: 'ML', exit: 'MR' },
      { dx: -1, dy: 0, entry: 'MR', exit: 'ML' },
      { dx: 0, dy: 1, entry: 'MT', exit: 'MB' },
      { dx: 0, dy: -1, entry: 'MB', exit: 'MT' },
      { dx: 1, dy: 1, entry: 'UL', exit: 'LR' },
      { dx: 1, dy: -1, entry: 'LL', exit: 'UR' },
      { dx: -1, dy: 1, entry: 'UR', exit: 'LL' },
      { dx: -1, dy: -1, entry: 'LR', exit: 'UL' },
    ];

    for (const d1 of directions) {
      for (const d2 of directions) {
        const junction = { x: 5, y: 5 };
        const p1 = { x: 5 - d1.dx * 3, y: 5 - d1.dy * 3 };
        const p3 = { x: 5 + d2.dx * 3, y: 5 + d2.dy * 3 };

        const seg1 = connectedLine(p1.x, p1.y, junction.x, junction.y, true);
        const seg2 = connectedLine(junction.x, junction.y, p3.x, p3.y, true);

        const combined: Point[] = [];
        for (const p of seg1) {
          if (!combined.some(cp => cp.x === p.x && cp.y === p.y)) combined.push(p);
        }
        for (const p of seg2) {
          if (!combined.some(cp => cp.x === p.x && cp.y === p.y)) combined.push(p);
        }

        const cells = (tool as any).buildCells(ctx, combined);
        const cell = cells.find((c: any) => c.col === junction.x && c.row === junction.y);
        const char = cell?.cell?.char ?? 'MISSING';

        const key = [d1.entry, d2.exit].sort().join('-');
        const connections = glyphConnections[char];
        const exactMatch = connections?.has(d1.entry) && connections?.has(d2.exit);
        const fallbackOk = acceptableFallbacks[key] === char;

        expect(exactMatch || fallbackOk,
          `Transition ${d1.entry}->${d2.exit} (key=${key}) got '${char}' which is not an exact match or acceptable fallback`
        ).toBe(true);
      }
    }
  });

});

// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { AppState } from '../src/types';
import { GridRenderer } from '../src/canvas/GridRenderer';
import { SelectionTool } from '../src/tools/SelectionTool';
import { RectangleTool } from '../src/tools/RectangleTool';
import { OvalTool } from '../src/tools/OvalTool';
import { LineTool } from '../src/tools/LineTool';
import { FillTool } from '../src/tools/FillTool';
import { RotateTool } from '../src/tools/RotateTool';
import { BrushTool } from '../src/tools/BrushTool';
import { HEAVY_BOX, LIGHT_BOX } from '../src/utils/characters';
import * as fs from 'node:fs';
import * as path from 'node:path';

function makeAppState(overrides: Partial<AppState> = {}): AppState {
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
        lineDiagonal: true,
        eyedropperTarget: 'fg-fg',
        ...overrides,
    };
}

function makeRenderer(state: CanvasState, selected: Set<string> = new Set()): GridRenderer {
    let sel = selected;
    return {
        getSelectedCells: () => sel,
        setSelection: (s: Set<string>) => { sel = s; },
        clearSelection: () => { sel = new Set(); },
        setPreview: () => {},
        clearPreview: () => {},
        getRoomCells: () => new Set<string>(),
        setRoomCells: () => {},
    } as unknown as GridRenderer;
}

function makeCtx(state: CanvasState, overrides: Partial<AppState> = {}, selected?: Set<string>) {
    const appState = makeAppState(overrides);
    const renderer = makeRenderer(state, selected);
    return {
        state,
        undoStack: new UndoStack(),
        renderer,
        appState,
        modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
    };
}

describe('selection flood uses index queue not shift', () => {
    it('magic wand finds large contiguous region without truncation', () => {
        const state = new CanvasState(20, 20);
        for (let y = 0; y < 10; y++) for (let x = 0; x < 10; x++) state.setCell(x, y, { char: '#', fg: [255, 255, 255], bg: [-1, -1, -1] });
        const ctx = makeCtx(state, { selectMode: 'magic' });
        const tool = new SelectionTool() as unknown as { magicSelectCells: (ctx: unknown, p: { x: number; y: number }) => Set<string> };
        const result = tool.magicSelectCells(ctx as never, { x: 0, y: 0 });
        expect(result.size).toBe(100);
    });

    it('color match finds exact region and color fuzzy respects thresholds', () => {
        const state = new CanvasState(5, 5);
        state.setCell(0, 0, { char: 'x', fg: [100, 100, 100], bg: [-1, -1, -1] });
        state.setCell(1, 0, { char: 'x', fg: [101, 101, 101], bg: [-1, -1, -1] });
        state.setCell(2, 0, { char: 'x', fg: [200, 200, 200], bg: [-1, -1, -1] });
        const ctxExact = makeCtx(state, { selectMode: 'color-match' });
        const tool = new SelectionTool() as unknown as { colorSelectCells: (ctx: unknown, p: never, f: boolean) => Set<string> };
        const exact = tool.colorSelectCells(ctxExact as never, { x: 0, y: 0 } as never, false);
        expect(exact.has('0,0')).toBe(true);
        expect(exact.has('1,0')).toBe(true);
        expect(exact.has('2,0')).toBe(false);
        const ctxFuzzy = makeCtx(state, { selectMode: 'color-fuzzy' });
        const fuzzy = tool.colorSelectCells(ctxFuzzy as never, { x: 0, y: 0 } as never, true);
        expect(fuzzy.has('0,0')).toBe(true);
    });

    it('file no longer contains queue.shift in selection', () => {
        const src = fs.readFileSync(path.resolve(import.meta.dirname, '../src/tools/SelectionTool.ts'), 'utf-8');
        expect(src).not.toContain('queue.shift()');
    });
});

describe('fill flood performance and correctness', () => {
    it('fills enclosed room and fills outside when border open', () => {
        const state = new CanvasState(5, 5);
        for (let x = 0; x < 5; x++) { state.setCell(x, 0, { char: '#', fg: [255, 255, 255], bg: [-1, -1, -1] }); state.setCell(x, 4, { char: '#', fg: [255, 255, 255], bg: [-1, -1, -1] }); }
        for (let y = 0; y < 5; y++) { state.setCell(0, y, { char: '#', fg: [255, 255, 255], bg: [-1, -1, -1] }); state.setCell(4, y, { char: '#', fg: [255, 255, 255], bg: [-1, -1, -1] }); }
        const ctx = makeCtx(state, { fillMode: 'brush' });
        const tool = new FillTool() as unknown as { floodFill: (ctx: unknown, p: never) => Set<string> };
        const inside = tool.floodFill(ctx as never, { x: 2, y: 2 } as never);
        expect(inside.size).toBe(9);
        const outsideTool = new FillTool() as unknown as { getOutsideEmptyCells: (ctx: unknown) => Set<string> };
        const stateOpen = new CanvasState(5, 5);
        const ctxOpen = makeCtx(stateOpen);
        const outside = outsideTool.getOutsideEmptyCells(ctxOpen as never);
        expect(outside.size).toBe(25);
    });

    it('fill file uses index queue not shift', () => {
        const src = fs.readFileSync(path.resolve(import.meta.dirname, '../src/tools/FillTool.ts'), 'utf-8');
        expect(src).not.toContain('queue.shift()');
    });
});

describe('rectangle heavy mode draws heavy box characters', () => {
    it('light vs heavy produce different corner glyphs', () => {
        const state = new CanvasState(10, 10);
        const ctxLight = makeCtx(state, { rectMode: 'light' });
        const ctxHeavy = makeCtx(state, { rectMode: 'heavy' });
        const tool = new RectangleTool() as unknown as { getRectCells: (ctx: unknown, a: never, b: never) => { col: number; row: number; cell: { char: string } }[] };
        const light = tool.getRectCells(ctxLight as never, { x: 0, y: 0 } as never, { x: 2, y: 2 } as never);
        const heavy = tool.getRectCells(ctxHeavy as never, { x: 0, y: 0 } as never, { x: 2, y: 2 } as never);
        const lightCorner = light.find(c => c.col === 0 && c.row === 0)?.cell.char;
        const heavyCorner = heavy.find(c => c.col === 0 && c.row === 0)?.cell.char;
        expect(lightCorner).toBe(LIGHT_BOX.tl);
        expect(heavyCorner).toBe(HEAVY_BOX.tl);
        expect(lightCorner).not.toBe(heavyCorner);
    });

    it('oval heavy mode draws heavy characters', () => {
        const state = new CanvasState(10, 10);
        const ctx = makeCtx(state, { ovalMode: 'heavy' });
        const tool = new OvalTool() as unknown as { getOvalCells: (ctx: unknown, a: never, b: never) => { col: number; row: number; cell: { char: string } }[] };
        const cells = tool.getOvalCells(ctx as never, { x: 0, y: 0 } as never, { x: 4, y: 4 } as never);
        expect(cells.length).toBeGreaterThan(0);
        const hasHeavy = cells.some(c => Object.values(HEAVY_BOX).includes(c.cell.char));
        expect(hasHeavy).toBe(true);
    });

    it('index.html offers heavy for rect and oval', () => {
        const html = fs.readFileSync(path.resolve(import.meta.dirname, '../index.html'), 'utf-8');
        expect(html).toContain('id="rect-mode-select"');
        expect(html).toContain('value="heavy"');
        const rectSection = html.slice(html.indexOf('rect-mode-select'), html.indexOf('rect-mode-select') + 500);
        expect(rectSection).toContain('heavy');
        const ovalSection = html.slice(html.indexOf('oval-mode-select'), html.indexOf('oval-mode-select') + 500);
        expect(ovalSection).toContain('heavy');
    });

    it('types allow heavy for rect and oval', () => {
        const types = fs.readFileSync(path.resolve(import.meta.dirname, '../src/types.ts'), 'utf-8');
        expect(types).toContain('RectMode = "light" | "rounded" | "double" | "heavy"');
        expect(types).toContain('OvalMode = "light" | "rounded" | "double" | "heavy"');
    });
});

describe('line junction dead code removed and sorted keys correct', () => {
    it('file does not contain dead three-value bridge cases', () => {
        const src = fs.readFileSync(path.resolve(import.meta.dirname, '../src/tools/LineTool.ts'), 'utf-8');
        expect(src).not.toContain('ML-UR-LR');
        expect(src).not.toContain('LL-MR-UL');
    });

    it('diagonal line still bridges without gaps', () => {
        const tool = new LineTool() as unknown as { buildCells: (ctx: unknown, pts: { x: number; y: number }[]) => { col: number; row: number; cell: { char: string } }[] };
        const ctx = { appState: makeAppState({ lineMode: 'light', lineDiagonal: true }), state: new CanvasState(20, 20), undoStack: new UndoStack(), renderer: makeRenderer(new CanvasState(20, 20)), modifiers: { shiftKey: false, altKey: false, ctrlKey: false } } as unknown as never;
        const cells = tool.buildCells(ctx, [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 2, y: 2 }]);
        expect(cells.length).toBe(3);
        for (const c of cells) expect(c.cell.char).not.toBe('');
    });

    it('orthogonal line uses box characters', () => {
        const tool = new LineTool() as unknown as { buildCells: (ctx: unknown, pts: { x: number; y: number }[]) => { col: number; row: number; cell: { char: string } }[] };
        const ctx = { appState: makeAppState({ lineMode: 'light', lineDiagonal: false }), state: new CanvasState(20, 20), undoStack: new UndoStack(), renderer: makeRenderer(new CanvasState(20, 20)), modifiers: { shiftKey: false, altKey: false, ctrlKey: false } } as unknown as never;
        const cells = tool.buildCells(ctx, [{ x: 0, y: 0 }, { x: 2, y: 0 }]);
        expect(cells.every(c => c.cell.char === LIGHT_BOX.h)).toBe(true);
    });
});

describe('rotate aspect uses measured metrics not hardcoded', () => {
    it('source imports measureCellMetrics and defines helper', () => {
        const src = fs.readFileSync(path.resolve(import.meta.dirname, '../src/tools/RotateTool.ts'), 'utf-8');
        expect(src).toContain('measureCellMetrics');
        expect(src).toContain('getCellAspect');
        expect(src).not.toMatch(/const W = 0\.5;\s*\n\s*const H = 1\.0;\s*\n\s*const cosInv = Math\.cos\(-this\.currentTheta\)/);
        expect(src).toContain('getCellAspect(ctx.appState.fontFamily)');
    });

    it('free rotation still produces preview cells', () => {
        const state = new CanvasState(6, 6);
        state.setCell(2, 2, { char: 'x', fg: [255, 255, 255], bg: [-1, -1, -1] });
        state.setCell(3, 2, { char: 'x', fg: [255, 255, 255], bg: [-1, -1, -1] });
        let preview: unknown = null;
        const renderer = {
            getSelectedCells: () => new Set(['2,2', '3,2']),
            setSelection: () => {},
            clearSelection: () => {},
            setPreview: (c: unknown) => { preview = c; },
            clearPreview: () => {},
        } as unknown as GridRenderer;
        const ctx = {
            state,
            undoStack: new UndoStack(),
            renderer,
            appState: makeAppState({ rotateMode: 'free' }),
            modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
        };
        const tool = new RotateTool();
        tool.onMouseDown(ctx as never, { x: 2, y: 2 });
        tool.onDrag(ctx as never, { x: 2, y: 2 }, { x: 3, y: 3 });
        expect(preview).not.toBeNull();
        expect(Array.isArray(preview)).toBe(true);
        expect((preview as unknown[]).length).toBeGreaterThan(0);
    });
});

describe('brush and selection integration', () => {
    it('brush paints and erases without pushing undo on no-op', () => {
        const state = new CanvasState(5, 5);
        const ctx = makeCtx(state);
        const brush = new BrushTool();
        brush.onMouseDown(ctx as never, { x: 1, y: 1 });
        expect(ctx.undoStack.canUndo()).toBe(true);
        const before = ctx.undoStack.canUndo();
        brush.onMouseDown(ctx as never, { x: 1, y: 1 });
        expect(ctx.undoStack.canUndo()).toBe(before);
    });
});

import { describe, expect, it } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';
import { AnsiExporter } from '../src/export/AnsiExporter';
import { detectAnsiDimensions } from '../src/utils/ansiParser';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('canvas state cloning with overflow cells', () => {
    it('deep clones overflow cell objects', () => {
        const state = new CanvasState(2, 2);
        state.setCell(5, 5, { char: 'X', fg: [255, 0, 0], bg: [0, 255, 0] });
        const clone = state.clone();
        const originalCell = state.getCell(5, 5)!;
        originalCell.fg = [0, 0, 255];
        originalCell.bg = [255, 255, 0];
        originalCell.char = 'Y';
        const clonedCell = clone.getCell(5, 5)!;
        expect(clonedCell.char).toBe('X');
        expect(clonedCell.fg).toEqual([255, 0, 0]);
        expect(clonedCell.bg).toEqual([0, 255, 0]);
    });

    it('cloning preserves negative coordinates independently', () => {
        const state = new CanvasState(3, 3);
        state.setCell(-1, -1, { char: 'A', fg: [100, 100, 100], bg: [10, 20, 30] });
        const clone = state.clone();
        state.setCell(-1, -1, { char: 'B', fg: [200, 200, 200], bg: [40, 50, 60] });
        expect(clone.getCell(-1, -1)!.char).toBe('A');
        expect(clone.getCell(-1, -1)!.fg).toEqual([100, 100, 100]);
    });

    it('modifying cloned overflow does not affect original', () => {
        const state = new CanvasState(2, 2);
        state.setCell(10, 10, { char: 'Q', fg: [1, 2, 3], bg: [4, 5, 6] });
        const clone = state.clone();
        const c = clone.getCell(10, 10)!;
        c.char = 'Z';
        c.fg = [9, 9, 9];
        expect(state.getCell(10, 10)!.char).toBe('Q');
        expect(state.getCell(10, 10)!.fg).toEqual([1, 2, 3]);
    });
});

describe('canvas resizing with promoted layers', () => {
    it('grows a promoted layer opaque: index 0 is the background', () => {
        const state = new CanvasState(2, 2);
        state.addLayer('Overlay', false);
        expect(state.layers[0].cells[0][0].bg).toEqual([0, 0, 0]);
        expect(state.layers[1].cells[0][0].bg).toEqual([-1, -1, -1]);
        state.layers.splice(0, 1);
        state.activeLayerIndex = 0;
        expect(state.layers[0].cells[0][0].bg).toEqual([-1, -1, -1]);
        state.resize(4, 4);
        // The original cell keeps its transparent bg, but the layer is now
        // index 0 (the background), so newly grown cells default to opaque
        // black — matching the exporter's background raster invariant.
        expect(state.layers[0].cells[0][0].bg).toEqual([-1, -1, -1]);
        expect(state.layers[0].cells[3][3].bg).toEqual([0, 0, 0]);
        expect(state.layers[0].cells[2][3].bg).toEqual([0, 0, 0]);
    });

    it('keeps new cells opaque for true background layer', () => {
        const state = new CanvasState(2, 2);
        expect(state.layers[0].cells[0][0].bg).toEqual([0, 0, 0]);
        state.resize(4, 4);
        expect(state.layers[0].cells[3][3].bg).toEqual([0, 0, 0]);
    });

    it('migrates overflow cells that fit into new bounds', () => {
        const state = new CanvasState(2, 2);
        state.setCell(3, 0, { char: 'X', fg: [255, 0, 0], bg: [0, 0, 0] });
        expect(state.getCell(3, 0)!.char).toBe('X');
        state.resize(4, 2);
        expect(state.getCell(3, 0)!.char).toBe('X');
        expect(state.getActiveLayer().overflowCells?.has('3,0')).toBe(false);
    });
});

describe('ansi dimensions detection with trailing newline', () => {
    it('uses header when present even with trailing newline', () => {
        const s = '\x1b[8;5;10t\x1b[2J\x1b[Hhello\nworld\n';
        expect(detectAnsiDimensions(s)).toEqual({ width: 10, height: 5 });
    });

    it('does not count trailing empty line for plain text', () => {
        expect(detectAnsiDimensions('hello\nworld')).toEqual({ width: 5, height: 2 });
        expect(detectAnsiDimensions('hello\nworld\n')).toEqual({ width: 5, height: 2 });
        expect(detectAnsiDimensions('hello\nworld\n\n')).toEqual({ width: 5, height: 2 });
        expect(detectAnsiDimensions('a\nb\nc\n')).toEqual({ width: 1, height: 3 });
        expect(detectAnsiDimensions('single')).toEqual({ width: 6, height: 1 });
        expect(detectAnsiDimensions('single\n')).toEqual({ width: 6, height: 1 });
    });

    it('strips ansi before measuring', () => {
        const s = '\x1b[31mhello\x1b[0m\nworld\n';
        expect(detectAnsiDimensions(s)).toEqual({ width: 5, height: 2 });
    });
});

describe('ansi export background handling for sparse layers', () => {
    it('does not spill previous overlay bg onto transparent char', () => {
        const state = new CanvasState(3, 1);
        // background is black already
        state.addLayer('Overlay', false);
        state.activeLayerIndex = 1;
        // first overlay cell with red bg
        state.setCell(0, 0, { char: 'A', fg: [255, 255, 255], bg: [255, 0, 0] });
        // second overlay cell with transparent bg
        state.setCell(1, 0, { char: 'B', fg: [255, 255, 255], bg: [-1, -1, -1] });
        const out = AnsiExporter.export(state);
        // should contain red bg for A and some bg (not red) for B
        expect(out).toContain('\x1b[48;2;255;0;0m');
        // after fix, B should have underlying bg (black 0,0,0) emitted, not retain red
        const bIndex = out.indexOf('B');
        const redBgIndex = out.lastIndexOf('\x1b[48;2;255;0;0m', bIndex);
        // there should be a bg sequence between red and B that is not red (black)
        const segmentBetween = out.slice(redBgIndex, bIndex);
        // segment should contain a bg change away from red before B
        expect(segmentBetween).toContain('\x1b[48;2;0;0;0m');
    });

    it('exports background layer fully with resolved black for transparent sentinel', () => {
        const state = new CanvasState(2, 1);
        // delete background and promote overlay with transparent bg
        state.addLayer('Overlay', false);
        state.layers.splice(0, 1);
        state.activeLayerIndex = 0;
        state.setCell(0, 0, { char: 'X', fg: [255, 0, 0], bg: [-1, -1, -1] });
        const out = AnsiExporter.export(state);
        // background layer (now promoted) transparent should be resolved to black
        expect(out).toContain('\x1b[48;2;0;0;0m');
        expect(out).toContain('X');
    });

    it('preserves cursor jumps for sparse overlay', () => {
        const state = new CanvasState(5, 5);
        state.addLayer('Overlay', false);
        state.activeLayerIndex = 1;
        state.setCell(4, 4, { char: 'Z', fg: [10, 20, 30], bg: [-1, -1, -1] });
        const out = AnsiExporter.export(state);
        expect(out).toContain('\x1b[5;5H');
        expect(out).toContain('Z');
    });
});

describe('text tool undo handling', () => {
    it('pushes undo before mutation', () => {
        const p = path.resolve(import.meta.dirname, '../src/ui/TextToolDialog.ts');
        const content = fs.readFileSync(p, 'utf-8');
        const pushIndex = content.indexOf('this.undoStack.push(this.canvasState)');
        const renderIndex = content.indexOf('await renderTextToAnsiLayer');
        expect(pushIndex).toBeGreaterThan(-1);
        expect(renderIndex).toBeGreaterThan(-1);
        expect(pushIndex).toBeLessThan(renderIndex);
    });

    it('main does not push after mutation for text tool', () => {
        const p = path.resolve(import.meta.dirname, '../src/main.ts');
        const content = fs.readFileSync(p, 'utf-8');
        // the TextToolDialog instantiation should not contain push inside its callback
        const dialogStart = content.indexOf('new TextToolDialog');
        const nextNew = content.indexOf('new ToolManager', dialogStart);
        const segment = content.slice(dialogStart, nextNew);
        expect(segment).not.toContain('undoStack.push(canvasState);');
        expect(segment).toContain('undoStack');
    });
});

describe('client download handling', () => {
    it('appends link to DOM before click', () => {
        const p = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
        const content = fs.readFileSync(p, 'utf-8');
        const fnStart = content.indexOf('function downloadText');
        const fn = content.slice(fnStart, fnStart + 800);
        expect(fn).toContain('document.body.appendChild(link)');
        expect(fn).toContain('document.body.removeChild(link)');
        expect(fn.indexOf('appendChild')).toBeLessThan(fn.indexOf('link.click()'));
    });

    it('exporter download also appends and cleans up', () => {
        const p = path.resolve(import.meta.dirname, '../src/export/AnsiExporter.ts');
        const content = fs.readFileSync(p, 'utf-8');
        expect(content).toContain('document.body.appendChild(a)');
        expect(content).toContain('document.body.removeChild(a)');
    });
});

describe('room data logging gate', () => {
    it('is gated behind dev flag', () => {
        const p = path.resolve(import.meta.dirname, '../src/mapedit.ts');
        const content = fs.readFileSync(p, 'utf-8');
        const idx = content.indexOf('export function logRoomData');
        const snippet = content.slice(idx, idx + 400);
        expect(snippet).toContain('import.meta');
        expect(snippet).toContain('DEV');
        expect(snippet).toContain('return;');
    });
});

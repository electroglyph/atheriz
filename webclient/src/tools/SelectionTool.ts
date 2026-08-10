import { Tool, ToolContext } from './Tool';
import { Point, Cell, Color } from '../types';
import { LIGHT_CHARS, ROUNDED_CHARS, DOUBLE_CHARS, HEAVY_CHARS } from '../utils/characters';
import { GridRenderer } from '../canvas/GridRenderer';
import { getLinePoints } from '../utils/geometry';

function luminance(c: Color): number {
    return (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) / 255;
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0;
    const l = (max + min) / 2;
    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        else if (max === g) h = ((b - r) / d + 2) / 6;
        else h = ((r - g) / d + 4) / 6;
    }
    return [h * 360, s, l];
}

function hueDistance(h1: number, h2: number): number {
    const d = Math.abs(h1 - h2);
    return Math.min(d, 360 - d);
}

function key(col: number, row: number): string {
    return `${col},${row}`;
}

const LIGHT_ROUNDED_CHARS = new Set([...LIGHT_CHARS, ...ROUNDED_CHARS]);

let selectionEscapeBound = false;
let activeSelection: SelectionTool | null = null;

function bindSelectionEscapeHandler(): void {
    if (selectionEscapeBound) return;
    selectionEscapeBound = true;
    window.addEventListener('keydown', (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
            const tool = activeSelection;
            if (tool && tool.hasSelection) {
                tool.clearSelection();
                e.preventDefault();
                e.stopPropagation();
            }
        }
    });
}

export class SelectionTool implements Tool {
    private selectedCells: Set<string> = new Set();
    private clipboard: {
        cells: { col: number; row: number; cell: Cell }[];
        minCol: number;
        minRow: number;
        maxCol: number;
        maxRow: number;
    } | null = null;
    private anchor: Point | null = null;
    private lassoPath: Point[] = [];
    private lastRenderer: GridRenderer | null = null;

    constructor() {
        activeSelection = this;
        bindSelectionEscapeHandler();
    }

    public get hasSelection(): boolean {
        return this.selectedCells.size > 0;
    }

    private getInkColor(cell: Cell): Color {
        const hasBg = cell.bg[0] !== -1;
        if (!cell.char || cell.char.trim() === '') {
            return hasBg ? [...cell.bg] as Color : [0, 0, 0];
        }
        const fgLum = luminance(cell.fg);
        const bgLum = hasBg ? luminance(cell.bg) : -1;
        return (hasBg && bgLum > fgLum) ? [...cell.bg] as Color : [...cell.fg] as Color;
    }

    private applyModifiers(ctx: ToolContext, newCells: Set<string>): void {
        if (ctx.modifiers.altKey) {
            for (const k of newCells) {
                this.selectedCells.delete(k);
            }
        } else if (ctx.modifiers.ctrlKey) {
            for (const k of newCells) {
                this.selectedCells.add(k);
            }
        } else {
            this.selectedCells = newCells;
        }
        ctx.renderer.setSelection(this.selectedCells);
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.lastRenderer = ctx.renderer;
        const mode = ctx.appState.selectMode;

        if (mode === 'single') {
            this.applyModifiers(ctx, new Set([key(cell.x, cell.y)]));
            return;
        }

        if (mode === 'magic') {
            const cells = this.magicSelectCells(ctx, cell);
            this.applyModifiers(ctx, cells);
            return;
        }

        if (mode === 'color-match') {
            const cells = this.colorSelectCells(ctx, cell, false);
            this.applyModifiers(ctx, cells);
            return;
        }

        if (mode === 'color-fuzzy') {
            const cells = this.colorSelectCells(ctx, cell, true);
            this.applyModifiers(ctx, cells);
            return;
        }

        if (!ctx.modifiers.ctrlKey && !ctx.modifiers.altKey) {
            this.clearSelection(ctx);
        }

        if (mode === 'rectangle') {
            this.anchor = cell;
        } else if (mode === 'lasso') {
            this.anchor = cell;
            this.lassoPath = [cell];
        }
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point): void {
        const mode = ctx.appState.selectMode;
        if (!this.anchor) return;

        if (mode === 'rectangle') {
            const cells = this.getRectCells(this.anchor, to);
            ctx.renderer.setSelection(cells);
        } else if (mode === 'lasso') {
            const last = this.lassoPath[this.lassoPath.length - 1];
            if (to.x !== last.x || to.y !== last.y) {
                const seg = getLinePoints(last, to);
                for (let i = 1; i < seg.length; i++) {
                    this.lassoPath.push(seg[i]);
                }
            }
            const outline = new Set<string>();
            for (const p of this.lassoPath) {
                outline.add(key(p.x, p.y));
            }
            ctx.renderer.setSelection(outline);
        }
    }

    onMouseUp(ctx: ToolContext, cell: Point): void {
        const mode = ctx.appState.selectMode;
        if (!this.anchor) return;

        if (mode === 'rectangle') {
            if (cell.x === this.anchor.x && cell.y === this.anchor.y) {
                if (!ctx.modifiers.ctrlKey && !ctx.modifiers.altKey) {
                    this.clearSelection(ctx);
                }
            } else {
                const raw = this.getRectCells(this.anchor, cell);
                const filtered = this.filterNonEmpty(ctx, raw);
                this.applyModifiers(ctx, filtered);
            }
            this.anchor = null;
        } else if (mode === 'lasso') {
            const last = this.lassoPath[this.lassoPath.length - 1];
            if (cell.x !== last.x || cell.y !== last.y) {
                const seg = getLinePoints(last, cell);
                for (let i = 1; i < seg.length; i++) {
                    this.lassoPath.push(seg[i]);
                }
            }
            const first = this.lassoPath[0];
            const end = this.lassoPath[this.lassoPath.length - 1];
            if (first.x !== end.x || first.y !== end.y) {
                const closing = getLinePoints(end, first);
                for (let i = 1; i < closing.length; i++) {
                    this.lassoPath.push(closing[i]);
                }
            }
            const raw = this.scanlineFill(this.lassoPath);
            const filtered = this.filterNonEmpty(ctx, raw);
            this.applyModifiers(ctx, filtered);
            this.anchor = null;
            this.lassoPath = [];
        }
    }

    onHover(_ctx: ToolContext, _cell: Point): void {}

    onMouseLeave(_ctx: ToolContext): void {}

    onKeyDown(ctx: ToolContext, keyStr: string): boolean {
        if (keyStr === 'Escape') {
            this.clearSelection(ctx);
            return true;
        }
        if (keyStr === 'Delete') {
            return this.deleteSelected(ctx);
        }
        if (keyStr === 'ctrl+c') {
            return this.copySelected(ctx);
        }
        if (keyStr === 'ctrl+v') {
            return this.pasteClipboard(ctx);
        }
        return false;
    }

    private filterNonEmpty(ctx: ToolContext, cells: Set<string>): Set<string> {
        const result = new Set<string>();
        for (const k of cells) {
            const [col, row] = k.split(',').map(Number);
            const cell = ctx.state.getCell(col, row);
            if (cell && ((cell.char && cell.char.trim() !== '') || (cell.bg[0] !== -1 && !(cell.bg[0] === 0 && cell.bg[1] === 0 && cell.bg[2] === 0)))) {
                result.add(k);
            }
        }
        return result;
    }

    public clearSelection(ctx?: ToolContext): void {
        this.selectedCells = new Set();
        const renderer = ctx?.renderer ?? this.lastRenderer;
        if (renderer) {
            renderer.clearSelection();
        }
    }

    private getRectCells(from: Point, to: Point): Set<string> {
        const cells = new Set<string>();
        const minX = Math.min(from.x, to.x);
        const maxX = Math.max(from.x, to.x);
        const minY = Math.min(from.y, to.y);
        const maxY = Math.max(from.y, to.y);
        for (let y = minY; y <= maxY; y++) {
            for (let x = minX; x <= maxX; x++) {
                cells.add(key(x, y));
            }
        }
        return cells;
    }

    /**
     * Executes a polygon scanline fill algorithm using the Ray Casting method.
     * It scans the bounding box row by row, toggling whether cells are "inside" 
     * or "outside" the polygon based on segment intersections.
     */
    private scanlineFill(path: Point[]): Set<string> {
        const result = new Set<string>();

        if (path.length < 3) {
            for (const p of path) result.add(key(p.x, p.y));
            return result;
        }

        let minRow = Infinity, maxRow = -Infinity;
        let minCol = Infinity, maxCol = -Infinity;
        for (const p of path) {
            if (p.y < minRow) minRow = p.y;
            if (p.y > maxRow) maxRow = p.y;
            if (p.x < minCol) minCol = p.x;
            if (p.x > maxCol) maxCol = p.x;
        }

        const n = path.length;
        for (let row = minRow; row <= maxRow; row++) {
            for (let col = minCol; col <= maxCol; col++) {
                let inside = false;
                for (let i = 0, j = n - 1; i < n; j = i++) {
                    const yi = path[i].y, yj = path[j].y;
                    const xi = path[i].x, xj = path[j].x;
                    if ((yi > row) !== (yj > row)) {
                        const xIntersect = xi + (row - yi) / (yj - yi) * (xj - xi);
                        if (col > xIntersect) {
                            inside = !inside;
                        }
                    }
                }
                if (inside) {
                    result.add(key(col, row));
                }
            }
        }

        for (const p of path) {
            result.add(key(p.x, p.y));
        }

        return result;
    }

    /**
     * Floods contiguous, matching characters or colors acting as a "Magic Wand".
     */
    private magicSelectCells(ctx: ToolContext, cell: Point): Set<string> {
        const composite = ctx.state.getCell(cell.x, cell.y);
        if (!composite) return new Set([key(cell.x, cell.y)]);

        const ch = composite.char || ' ';
        const isSpace = ch.trim() === '';

        let category: string | null = null;
        if (!isSpace) {
            if (LIGHT_ROUNDED_CHARS.has(ch)) {
                category = 'light-rounded';
            } else if (DOUBLE_CHARS.has(ch)) {
                category = 'double';
            } else if (HEAVY_CHARS.has(ch)) {
                category = 'heavy';
            }
        }

        const inkColor = this.getInkColor(composite);

        const visited = new Set<string>();
        const queue: Point[] = [{ x: cell.x, y: cell.y }];
        visited.add(key(cell.x, cell.y));

        const match = (c: number, r: number): boolean => {
            const comp = ctx.state.getCell(c, r);
            if (!comp) return false;
            
            const compCh = comp.char || ' ';
            const compIsSpace = compCh.trim() === '';

            if (isSpace) {
                if (!compIsSpace) return false;
            } else {
                if (compIsSpace) return false;
                if (category) {
                    if (category === 'light-rounded') return LIGHT_ROUNDED_CHARS.has(compCh);
                    if (category === 'double') return DOUBLE_CHARS.has(compCh);
                    if (category === 'heavy') return HEAVY_CHARS.has(compCh);
                    return false;
                }
                if (compCh !== ch) return false;
            }

            const cInkColor = this.getInkColor(comp);
            return cInkColor[0] === inkColor[0] && cInkColor[1] === inkColor[1] && cInkColor[2] === inkColor[2];
        };

        while (queue.length > 0) {
            const p = queue.shift()!;
            for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
                const nx = p.x + dx;
                const ny = p.y + dy;
                const nk = key(nx, ny);
                if (visited.has(nk)) continue;
                if (nx < 0 || nx >= ctx.state.width || ny < 0 || ny >= ctx.state.height) continue;
                if (match(nx, ny)) {
                    visited.add(nk);
                    queue.push({ x: nx, y: ny });
                }
            }
        }

        return this.filterNonEmpty(ctx, visited);
    }

    private colorSelectCells(ctx: ToolContext, cell: Point, fuzzy: boolean): Set<string> {
        const composite = ctx.state.getCell(cell.x, cell.y);
        if (!composite) return new Set([key(cell.x, cell.y)]);

        const inkColor = this.getInkColor(composite);
        const inkHsl = rgbToHsl(inkColor[0], inkColor[1], inkColor[2]);

        const FUZZY_HUE_THRESHOLD = 45;
        const FUZZY_SAT_THRESHOLD = 0.3;
        const FUZZY_LUM_THRESHOLD = 0.35;
        const EXACT_THRESHOLD = 3;

        const match = (c: number, r: number): boolean => {
            const comp = ctx.state.getCell(c, r);
            if (!comp) return false;

            const compInk = this.getInkColor(comp);

            if (!fuzzy) {
                return Math.abs(compInk[0] - inkColor[0]) <= EXACT_THRESHOLD &&
                       Math.abs(compInk[1] - inkColor[1]) <= EXACT_THRESHOLD &&
                       Math.abs(compInk[2] - inkColor[2]) <= EXACT_THRESHOLD;
            }

            const compHsl = rgbToHsl(compInk[0], compInk[1], compInk[2]);

            if (inkHsl[1] < 0.08 && compHsl[1] < 0.08) {
                return Math.abs(compHsl[2] - inkHsl[2]) <= FUZZY_LUM_THRESHOLD;
            }

            return hueDistance(compHsl[0], inkHsl[0]) <= FUZZY_HUE_THRESHOLD &&
                   Math.abs(compHsl[1] - inkHsl[1]) <= FUZZY_SAT_THRESHOLD;
        };

        const visited = new Set<string>();
        const queue: Point[] = [{ x: cell.x, y: cell.y }];
        visited.add(key(cell.x, cell.y));

        while (queue.length > 0) {
            const p = queue.shift()!;
            for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
                const nx = p.x + dx;
                const ny = p.y + dy;
                const nk = key(nx, ny);
                if (visited.has(nk)) continue;
                if (nx < 0 || nx >= ctx.state.width || ny < 0 || ny >= ctx.state.height) continue;
                if (match(nx, ny)) {
                    visited.add(nk);
                    queue.push({ x: nx, y: ny });
                }
            }
        }

        visited.add(key(cell.x, cell.y));
        return visited;
    }

    private deleteSelected(ctx: ToolContext): boolean {
        if (this.selectedCells.size === 0) return false;
        ctx.undoStack.push(ctx.state);
        const layer = ctx.state.getActiveLayer();
        for (const k of this.selectedCells) {
            const [col, row] = k.split(',').map(Number);
            if (col >= 0 && col < ctx.state.width && row >= 0 && row < ctx.state.height) {
                layer.cells[row][col] = {
                    char: '',
                    fg: [204, 204, 204] as Color,
                    bg: [-1, -1, -1] as Color
                };
            }
        }
        this.clearSelection(ctx);
        ctx.state.notify();
        return true;
    }

    private copySelected(_ctx: ToolContext): boolean {
        if (this.selectedCells.size === 0) return false;

        let minCol = Infinity, minRow = Infinity;
        let maxCol = -Infinity, maxRow = -Infinity;
        for (const k of this.selectedCells) {
            const [col, row] = k.split(',').map(Number);
            if (col < minCol) minCol = col;
            if (col > maxCol) maxCol = col;
            if (row < minRow) minRow = row;
            if (row > maxRow) maxRow = row;
        }

        const cells: { col: number; row: number; cell: Cell }[] = [];
        for (const k of this.selectedCells) {
            const [col, row] = k.split(',').map(Number);
            const composite = _ctx.state.getCell(col, row);
            if (composite) {
                cells.push({
                    col,
                    row,
                    cell: {
                        char: composite.char,
                        fg: [...composite.fg] as Color,
                        bg: [...composite.bg] as Color,
                        bold: composite.bold,
                        italic: composite.italic,
                        underline: composite.underline
                    }
                });
            }
        }

        this.clipboard = { cells, minCol, minRow, maxCol, maxRow };
        return true;
    }

    private pasteClipboard(ctx: ToolContext): boolean {
        if (!this.clipboard) return false;
        ctx.undoStack.push(ctx.state);

        ctx.state.addLayer('Pasted');
        const layer = ctx.state.getActiveLayer();

        for (const item of this.clipboard.cells) {
            const col = item.col;
            const row = item.row;
            if (col >= 0 && col < ctx.state.width && row >= 0 && row < ctx.state.height) {
                layer.cells[row][col] = {
                    char: item.cell.char,
                    fg: [...item.cell.fg] as Color,
                    bg: [...item.cell.bg] as Color,
                    bold: item.cell.bold,
                    italic: item.cell.italic,
                    underline: item.cell.underline
                };
            }
        }

        this.clearSelection(ctx);
        ctx.state.notify();
        return true;
    }
}

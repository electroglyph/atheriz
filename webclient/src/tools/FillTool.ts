import { Tool, ToolContext } from './Tool';
import { Point, Cell, Color } from '../types';
import { sampleGradient, lerpColor } from '../utils/colors';

function luminance(c: Color): number {
    return (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) / 255;
}

export class FillTool implements Tool {
    private anchor: Point | null = null;
    private currentTarget: Point | null = null;
    private fillCells: Set<string> = new Set();

    private isEmptyCell(cell: Cell): boolean {
        const hasChar = cell.char && cell.char.trim() !== '';
        const hasBg = cell.bg[0] !== -1 && !(cell.bg[0] === 0 && cell.bg[1] === 0 && cell.bg[2] === 0);
        return !hasChar && !hasBg;
    }

    private floodFill(ctx: ToolContext, start: Point): Set<string> {
        const layer = ctx.state.getActiveLayer();
        const w = ctx.state.width;
        const h = ctx.state.height;
        const visited = new Set<string>();
        const queue: Point[] = [start];
        let qIdx = 0;
        let reachedBorder = false;

        while (qIdx < queue.length) {
            const p = queue[qIdx++]!;
            const k = `${p.x},${p.y}`;

            if (visited.has(k)) continue;
            if (p.x < 0 || p.x >= w || p.y < 0 || p.y >= h) {
                reachedBorder = true;
                continue;
            }

            const cell = layer.cells[p.y][p.x];
            if (!this.isEmptyCell(cell)) continue;

            visited.add(k);

            queue.push({ x: p.x - 1, y: p.y });
            queue.push({ x: p.x + 1, y: p.y });
            queue.push({ x: p.x, y: p.y - 1 });
            queue.push({ x: p.x, y: p.y + 1 });
        }

        if (reachedBorder) {
            return this.getOutsideEmptyCells(ctx);
        }

        return visited;
    }

    private getOutsideEmptyCells(ctx: ToolContext): Set<string> {
        const layer = ctx.state.getActiveLayer();
        const w = ctx.state.width;
        const h = ctx.state.height;
        const outside = new Set<string>();
        const visited = new Set<string>();
        const queue: Point[] = [];
        let qIdx = 0;

        for (let x = 0; x < w; x++) {
            queue.push({ x, y: 0 });
            queue.push({ x, y: h - 1 });
        }
        for (let y = 1; y < h - 1; y++) {
            queue.push({ x: 0, y });
            queue.push({ x: w - 1, y });
        }

        while (qIdx < queue.length) {
            const p = queue[qIdx++]!;
            const k = `${p.x},${p.y}`;

            if (visited.has(k)) continue;
            if (p.x < 0 || p.x >= w || p.y < 0 || p.y >= h) continue;

            visited.add(k);

            const cell = layer.cells[p.y][p.x];
            if (!this.isEmptyCell(cell)) continue;

            outside.add(k);

            queue.push({ x: p.x - 1, y: p.y });
            queue.push({ x: p.x + 1, y: p.y });
            queue.push({ x: p.x, y: p.y - 1 });
            queue.push({ x: p.x, y: p.y + 1 });
        }

        return outside;
    }

    private computeFillCells(ctx: ToolContext, start: Point): Set<string> {
        const selected = ctx.renderer.getSelectedCells();
        if (selected.size > 0) return selected;
        return this.floodFill(ctx, start);
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.anchor = cell;
        this.currentTarget = cell;

        if (ctx.appState.fillMode === 'gradient') {
            this.fillCells = this.computeFillCells(ctx, cell);
            ctx.undoStack.push(ctx.state);
            this.renderPreview(ctx);
        } else {
            ctx.undoStack.push(ctx.state);
            const targets = this.computeFillCells(ctx, cell);
            const updates = this.applyFill(ctx, targets);
            if (updates.length > 0) {
                ctx.state.applyBatch(updates);
            }
            this.anchor = null;
            this.fillCells = new Set();
        }
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point): void {
        if (ctx.appState.fillMode !== 'gradient' || !this.anchor) return;
        this.currentTarget = to;
        this.renderPreview(ctx);
    }

    onMouseUp(ctx: ToolContext, cell: Point): void {
        if (ctx.appState.fillMode !== 'gradient' || !this.anchor) return;
        this.currentTarget = cell;

        ctx.renderer.clearPreview();

        const updates = this.applyGradientFill(ctx, this.anchor, this.currentTarget);
        if (updates.length > 0) {
            ctx.state.applyBatch(updates);
        }

        this.anchor = null;
        this.currentTarget = null;
        this.fillCells = new Set();
    }

    onHover(_ctx: ToolContext, _cell: Point): void {}

    onMouseLeave(ctx: ToolContext): void {
        if (!this.anchor) {
            ctx.renderer.clearPreview();
        }
    }

    private renderPreview(ctx: ToolContext) {
        if (!this.anchor || !this.currentTarget || this.fillCells.size === 0) return;
        const updates = this.applyGradientFill(ctx, this.anchor, this.currentTarget);
        ctx.renderer.setPreview(updates);
    }

    private applyFill(ctx: ToolContext, targets: Set<string>): { col: number, row: number, cell: Cell }[] {
        const mode = ctx.appState.fillMode;
        const layer = ctx.state.getActiveLayer();
        const updates: { col: number, row: number, cell: Cell }[] = [];

        for (const k of targets) {
            const [cs, rs] = k.split(',');
            const col = parseInt(cs);
            const row = parseInt(rs);
            if (col < 0 || col >= ctx.state.width || row < 0 || row >= ctx.state.height) continue;

            const existing = layer.cells[row][col];
            const newCell: Cell = {
                char: existing.char,
                fg: [...existing.fg] as Color,
                bg: [...existing.bg] as Color,
            };

            if (mode === 'brush') {
                newCell.char = ctx.appState.selectedChar;
                newCell.fg = [...ctx.appState.fgColor] as Color;
                newCell.bg = [...ctx.appState.bgColor] as Color;
            } else if (mode === 'foreground') {
                newCell.fg = [...ctx.appState.fgColor] as Color;
            } else if (mode === 'background') {
                newCell.bg = [...ctx.appState.bgColor] as Color;
            }

            updates.push({ col, row, cell: newCell });
        }

        return updates;
    }

    private applyGradientFill(ctx: ToolContext, start: Point, end: Point): { col: number, row: number, cell: Cell }[] {
        const layer = ctx.state.getActiveLayer();
        const updates: { col: number, row: number, cell: Cell }[] = [];

        const vx = end.x - start.x;
        const vy = end.y - start.y;
        const lenSq = vx * vx + vy * vy;

        const target = ctx.appState.gradientTarget;
        const stops = ctx.appState.gradientStops || [[0, 0, 0], [255, 255, 255]];

        for (const k of this.fillCells) {
            const [cs, rs] = k.split(',');
            const col = parseInt(cs);
            const row = parseInt(rs);
            if (col < 0 || col >= ctx.state.width || row < 0 || row >= ctx.state.height) continue;

            const existing = layer.cells[row][col];

            let t = 0;
            if (lenSq !== 0) {
                const wx = col - start.x;
                const wy = row - start.y;
                t = (wx * vx + wy * vy) / lenSq;
                t = Math.max(0, Math.min(1, t));
            }

            const gColor = sampleGradient(stops, t);
            const newCell: Cell = {
                char: existing.char,
                fg: [...existing.fg] as Color,
                bg: [...existing.bg] as Color,
            };

            const hasChar = existing.char && existing.char.trim() !== '';
            const hasBg = existing.bg[0] !== -1;
            const fgLum = luminance(existing.fg);
            const bgLum = hasBg ? luminance(existing.bg) : -1;
            const inkIsBg = hasBg && (!hasChar || bgLum > fgLum);
            const inkLum = inkIsBg ? bgLum : fgLum;

            if (target === 'foreground' || target === 'both') {
                if (inkIsBg) {
                    newCell.bg = gColor;
                } else {
                    newCell.fg = gColor;
                }
            }
            if (target === 'background' || target === 'both') {
                if (!inkIsBg) {
                    newCell.bg = gColor;
                }
            }

            if (target === 'luminance' || target === 'inverse-luminance') {
                const factor = target === 'luminance' ? inkLum * inkLum : (1 - inkLum) * (1 - inkLum);
                if (inkIsBg) {
                    newCell.bg = lerpColor(existing.bg, gColor, factor);
                } else {
                    newCell.fg = lerpColor(existing.fg, gColor, factor);
                }
            }

            updates.push({ col, row, cell: newCell });
        }

        return updates;
    }
}

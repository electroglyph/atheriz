import { Tool, ToolContext } from './Tool';
import { Point, Cell, Color } from '../types';
import { sampleGradient, lerpColor, cellEquals } from '../utils/colors';

function luminance(c: Color): number {
    return (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) / 255;
}

export class GradientTool implements Tool {
    private anchor: Point | null = null;
    private currentTarget: Point | null = null;

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.anchor = cell;
        this.currentTarget = cell;
        this.renderPreview(ctx);
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point): void {
        if (!this.anchor) return;
        this.currentTarget = to;
        this.renderPreview(ctx);
    }

    onMouseUp(ctx: ToolContext, cell: Point): void {
        if (!this.anchor) return;
        this.currentTarget = cell;
        
        ctx.renderer.clearPreview();
        
        const updates = this.getGradientUpdates(ctx, this.anchor, this.currentTarget);
        // Only record undo when at least one cell actually changes.
        if (updates.some(u => {
            const current = ctx.state.getCell(u.col, u.row);
            return !current || !cellEquals(current, u.cell);
        })) {
            ctx.undoStack.push(ctx.state);
            ctx.state.applyBatch(updates);
        }
        
        this.anchor = null;
        this.currentTarget = null;
    }

    onHover(_ctx: ToolContext, _cell: Point): void {
        // We don't render a hover symbol for the gradient tool unless dragging
    }

    onMouseLeave(ctx: ToolContext): void {
        if (!this.anchor) {
            ctx.renderer.clearPreview();
        }
    }

    private renderPreview(ctx: ToolContext) {
        if (!this.anchor || !this.currentTarget) return;
        const updates = this.getGradientUpdates(ctx, this.anchor, this.currentTarget);
        ctx.renderer.setPreview(updates);
    }

    private getGradientUpdates(ctx: ToolContext, start: Point, end: Point): {col: number, row: number, cell: Cell}[] {
        const updates: {col: number, row: number, cell: Cell}[] = [];
        
        const vx = end.x - start.x;
        const vy = end.y - start.y;
        const lenSq = vx * vx + vy * vy;
        
        const activeLayer = ctx.state.getActiveLayer();
        const width = ctx.state.width;
        const height = ctx.state.height;
        const target = ctx.appState.gradientTarget;
        const stops = ctx.appState.gradientStops || [[0,0,0], [255,255,255]];
        
        for (let r = 0; r < height; r++) {
            for (let c = 0; c < width; c++) {
                const existingCell = activeLayer.cells[r][c];
                
                const hasChar = existingCell.char && existingCell.char.trim() !== '';
                const hasBg = existingCell.bg && existingCell.bg[0] !== -1;
                
                if (!hasChar && !hasBg) {
                    continue;
                }
                
                let t = 0;
                if (lenSq !== 0) {
                    const wx = c - start.x;
                    const wy = r - start.y;
                    t = (wx * vx + wy * vy) / lenSq;
                    t = Math.max(0, Math.min(1, t)); // clamp
                }
                
                const gColor = sampleGradient(stops, t);
                
                const fgLum = luminance(existingCell.fg);
                const bgLum = hasBg ? luminance(existingCell.bg) : -1;
                const inkIsBg = hasBg && (!hasChar || bgLum > fgLum);
                const inkLum = inkIsBg ? bgLum : fgLum;
                
                const newCell: Cell = {
                    char: existingCell.char,
                    fg: existingCell.fg,
                    bg: existingCell.bg
                };
                
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
                        newCell.bg = lerpColor(existingCell.bg, gColor, factor);
                    } else {
                        newCell.fg = lerpColor(existingCell.fg, gColor, factor);
                    }
                }
                
                updates.push({
                    col: c,
                    row: r,
                    cell: newCell
                });
            }
        }
        
        return updates;
    }
}

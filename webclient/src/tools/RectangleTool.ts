import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';
import { LIGHT_BOX, ROUNDED_BOX, DOUBLE_BOX } from '../utils/characters';
import { cellEquals } from '../utils/colors';

export class RectangleTool implements Tool {
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
        
        const cells = this.getRectCells(ctx, this.anchor, this.currentTarget);

        // Only record undo when at least one cell actually changes.
        if (cells.some(u => {
            const current = ctx.state.getCell(u.col, u.row);
            return !current || !cellEquals(current, u.cell);
        })) {
            ctx.undoStack.push(ctx.state);
            ctx.state.applyBatch(cells);
        }

        ctx.renderer.clearPreview();
        this.anchor = null;
        this.currentTarget = null;
        
        // Fall back to hover
        this.onHover(ctx, cell);
    }

    onHover(ctx: ToolContext, cell: Point): void {
        ctx.renderer.setPreview([{
            col: cell.x,
            row: cell.y,
            cell: {
                char: ctx.appState.selectedChar,
                fg: ctx.appState.fgColor,
                bg: ctx.appState.bgColor
            }
        }]);
    }

    onMouseLeave(ctx: ToolContext): void {
        if (!this.anchor) {
            ctx.renderer.clearPreview();
        }
    }

    private renderPreview(ctx: ToolContext) {
        if (!this.anchor || !this.currentTarget) return;
        const cells = this.getRectCells(ctx, this.anchor, this.currentTarget);
        ctx.renderer.setPreview(cells);
    }

    private getRectCells(ctx: ToolContext, from: Point, to: Point): {col: number, row: number, cell: Cell}[] {
        let x0 = from.x;
        let y0 = from.y;
        let x1 = to.x;
        let y1 = to.y;

        if (ctx.modifiers.altKey) {
            // Draw from center
            const dx = Math.abs(x1 - x0);
            const dy = Math.abs(y1 - y0);
            x0 = x0 - dx;
            x1 = x0 + 2 * dx;
            y0 = y0 - dy;
            y1 = y0 + 2 * dy;
        }

        if (ctx.modifiers.shiftKey) {
            // Constrain to square
            const size = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
            x1 = x0 + (x1 >= x0 ? size : -size);
            y1 = y0 + (y1 >= y0 ? size : -size);
        }

        const minX = Math.min(x0, x1);
        const maxX = Math.max(x0, x1);
        const minY = Math.min(y0, y1);
        const maxY = Math.max(y0, y1);

        const updates: {col: number, row: number, cell: Cell}[] = [];
        const mode = ctx.appState.rectMode;
        const fg = ctx.appState.fgColor;
        const bg = ctx.appState.bgColor;
        const selected = ctx.appState.selectedChar;

        const charMap = mode === 'double' ? DOUBLE_BOX : 
                        mode === 'rounded' ? ROUNDED_BOX : 
                        LIGHT_BOX;

        // If regular mode, just draw the selected char around perimeter
        for (let y = minY; y <= maxY; y++) {
            for (let x = minX; x <= maxX; x++) {
                if (x === minX || x === maxX || y === minY || y === maxY) {
                    let charToDraw = selected;

                    if (mode !== 'custom') {
                        // Figure out which piece we are
                        const isTop = y === minY;
                        const isBottom = y === maxY;
                        const isLeft = x === minX;
                        const isRight = x === maxX;

                        // Edges connect along their own axis
                        // A top/bottom edge connects E and W. A left/right edge connects N and S.
                        let n = isLeft || isRight;
                        let s = isLeft || isRight;
                        let e = isTop || isBottom;
                        let w = isTop || isBottom;

                        // Corners and ends lose outward connections
                        if (isTop) n = false;
                        if (isBottom) s = false;
                        if (isRight) e = false;
                        if (isLeft) w = false;

                        // Single points are horizontal by default visually
                        if (minX === maxX && minY === maxY) {
                            n=false; e=true; s=false; w=true;
                        } else if (minX === maxX) {
                            n=true; s=true; e=false; w=false;
                        } else if (minY === maxY) {
                            e=true; w=true; n=false; s=false;
                        }



                        // Map using charMap
                        
                        if (n&&e&&s&&w) charToDraw = charMap.c;
                        else if (n&&s&&e) charToDraw = charMap.l;
                        else if (n&&s&&w) charToDraw = charMap.r;
                        else if (n&&e&&w) charToDraw = charMap.b;
                        else if (s&&e&&w) charToDraw = charMap.t;
                        else if (n&&e) charToDraw = charMap.bl;
                        else if (n&&w) charToDraw = charMap.br;
                        else if (s&&e) charToDraw = charMap.tl;
                        else if (s&&w) charToDraw = charMap.tr;
                        else if (n||s) charToDraw = charMap.v;
                        else charToDraw = charMap.h;
                    }

                    updates.push({ col: x, row: y, cell: { char: charToDraw, fg, bg } });
                }
            }
        }

        return updates;
    }

}

import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';
import { getEllipsePerimeter } from '../utils/geometry';
import { LIGHT_BOX, ROUNDED_BOX, DOUBLE_BOX } from '../utils/characters';
import { cellEquals } from '../utils/colors';

export class OvalTool implements Tool {
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

        const cells = this.getOvalCells(ctx, this.anchor, this.currentTarget);

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
        const cells = this.getOvalCells(ctx, this.anchor, this.currentTarget);
        ctx.renderer.setPreview(cells);
    }

    private getOvalCells(ctx: ToolContext, from: Point, to: Point): {col: number, row: number, cell: Cell}[] {
        let x0 = from.x;
        let y0 = from.y;
        let x1 = to.x;
        let y1 = to.y;

        if (ctx.modifiers.altKey) {
            const dx = Math.abs(x1 - x0);
            const dy = Math.abs(y1 - y0);
            x0 = x0 - dx;
            x1 = x0 + 2 * dx;
            y0 = y0 - dy;
            y1 = y0 + 2 * dy;
        }

        if (ctx.modifiers.shiftKey) {
            const size = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
            x1 = x0 + (x1 >= x0 ? size : -size);
            y1 = y0 + (y1 >= y0 ? size : -size);
        }

        const mode = ctx.appState.ovalMode;
        const fg = ctx.appState.fgColor;
        const bg = ctx.appState.bgColor;
        const selected = ctx.appState.selectedChar;

        const points = getEllipsePerimeter(
            Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1), 
            mode !== 'custom' && mode !== 'circle'
        );
        const updates: {col: number, row: number, cell: Cell}[] = [];

        if (mode === 'circle') {
            const minX = Math.min(x0, x1);
            const maxX = Math.max(x0, x1);
            const minY = Math.min(y0, y1);
            const maxY = Math.max(y0, y1);
            const w = maxX - minX + 1;
            const h = maxY - minY + 1;

            if (w < 4 || h < 4) {
                // Use Quarters
                updates.push({ col: minX, row: minY, cell: { char: "𜰵", fg, bg }});
                if (maxX !== minX) updates.push({ col: maxX, row: minY, cell: { char: "𜰶", fg, bg }});
                if (maxY !== minY) updates.push({ col: minX, row: maxY, cell: { char: "𜰹", fg, bg }});
                if (maxX !== minX && maxY !== minY) updates.push({ col: maxX, row: maxY, cell: { char: "𜰺", fg, bg }});
                
                for (let x = minX + 1; x < maxX; x++) {
                    updates.push({ col: x, row: minY, cell: { char: "▔", fg, bg }});
                    if (minY !== maxY) updates.push({ col: x, row: maxY, cell: { char: "▁", fg, bg }});
                }
                for (let y = minY + 1; y < maxY; y++) {
                    updates.push({ col: minX, row: y, cell: { char: "▏", fg, bg }});
                    if (minX !== maxX) updates.push({ col: maxX, row: y, cell: { char: "▕", fg, bg }});
                }
                return updates;
            } else {
                // Use Twelfths
                updates.push({ col: minX, row: minY, cell: { char: "𜰰", fg, bg }});
                updates.push({ col: minX + 1, row: minY, cell: { char: "𜰱", fg, bg }});
                updates.push({ col: maxX - 1, row: minY, cell: { char: "𜰲", fg, bg }});
                updates.push({ col: maxX, row: minY, cell: { char: "𜰳", fg, bg }});

                updates.push({ col: minX, row: minY + 1, cell: { char: "𜰴", fg, bg }});
                updates.push({ col: maxX, row: minY + 1, cell: { char: "𜰷", fg, bg }});

                updates.push({ col: minX, row: maxY - 1, cell: { char: "𜰸", fg, bg }});
                updates.push({ col: maxX, row: maxY - 1, cell: { char: "𜰻", fg, bg }});

                updates.push({ col: minX, row: maxY, cell: { char: "𜰼", fg, bg }});
                updates.push({ col: minX + 1, row: maxY, cell: { char: "𜰽", fg, bg }});
                updates.push({ col: maxX - 1, row: maxY, cell: { char: "𜰾", fg, bg }});
                updates.push({ col: maxX, row: maxY, cell: { char: "𜰿", fg, bg }});

                for (let x = minX + 2; x < maxX - 1; x++) {
                    updates.push({ col: x, row: minY, cell: { char: "▔", fg, bg }});
                    updates.push({ col: x, row: maxY, cell: { char: "▁", fg, bg }});
                }
                for (let y = minY + 2; y < maxY - 1; y++) {
                    updates.push({ col: minX, row: y, cell: { char: "▏", fg, bg }});
                    updates.push({ col: maxX, row: y, cell: { char: "▕", fg, bg }});
                }
                return updates;
            }
        }

        if (mode === 'custom') {
            for (const p of points) {
                updates.push({ col: p.x, row: p.y, cell: { char: selected, fg, bg }});
            }
            return updates;
        }

        const charMap = mode === 'double' ? DOUBLE_BOX : 
                        mode === 'rounded' ? ROUNDED_BOX : 
                        LIGHT_BOX;

        // First map all points for quick neighbor lookups
        const pMap = new Set<string>();
        for (const p of points) pMap.add(`${p.x},${p.y}`);

        for (const p of points) {
            let charToDraw = selected;

            const n = pMap.has(`${p.x},${p.y - 1}`);
            const s = pMap.has(`${p.x},${p.y + 1}`);
            const e = pMap.has(`${p.x + 1},${p.y}`);
            const w = pMap.has(`${p.x - 1},${p.y}`);

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

            updates.push({ col: p.x, row: p.y, cell: { char: charToDraw, fg, bg }});
        }

        return updates;
    }
}

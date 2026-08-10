import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';
import { getLinePoints } from '../utils/geometry';
import { cellEquals } from '../utils/colors';

export class BrushTool implements Tool {
    private paintedCells: Set<string> = new Set();
    private undoPushed = false;
    
    private getPreviewCell(ctx: ToolContext): Cell {
        return {
            char: ctx.appState.selectedChar,
            fg: ctx.appState.fgColor,
            bg: ctx.appState.bgColor
        };
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.paintedCells.clear();
        this.undoPushed = false;

        const cellData = this.getPreviewCell(ctx);
        const current = ctx.state.getCell(cell.x, cell.y);
        if (!current || !cellEquals(current, cellData)) {
            ctx.undoStack.push(ctx.state);
            this.undoPushed = true;
            ctx.state.setCell(cell.x, cell.y, cellData);
        }
        this.paintedCells.add(`${cell.x},${cell.y}`);
    }

    onDrag(ctx: ToolContext, from: Point, to: Point): void {
        const points = getLinePoints(from, to);
        const cellData = this.getPreviewCell(ctx);
        const updates: {col: number, row: number, cell: Cell}[] = [];
        
        for (const p of points) {
            const key = `${p.x},${p.y}`;
            if (this.paintedCells.has(key)) continue;
            this.paintedCells.add(key);

            const current = ctx.state.getCell(p.x, p.y);
            if (!current || !cellEquals(current, cellData)) {
                updates.push({ col: p.x, row: p.y, cell: cellData });
            }
        }
        
        if (updates.length > 0) {
            if (!this.undoPushed) {
                ctx.undoStack.push(ctx.state);
                this.undoPushed = true;
            }
            ctx.state.applyBatch(updates);
        }
    }

    onMouseUp(_ctx: ToolContext, _cell: Point): void {
        this.paintedCells.clear();
    }

    onHover(ctx: ToolContext, cell: Point): void {
        // Show what we're about to paint
        ctx.renderer.setPreview([{
            col: cell.x,
            row: cell.y,
            cell: this.getPreviewCell(ctx)
        }]);
    }

    onMouseLeave(ctx: ToolContext): void {
        ctx.renderer.clearPreview();
    }
}

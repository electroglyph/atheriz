import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';
import { getLinePoints } from '../utils/geometry';
import { cellEquals } from '../utils/colors';

export class EraserTool implements Tool {
    private erasedCells: Set<string> = new Set();
    private undoPushed = false;
    
    private getEraserCell(ctx: ToolContext): Cell {
        const isBackgroundLayer = ctx.state.activeLayerIndex === 0;
        return {
            char: '',
            fg: [204, 204, 204], // default fg
            bg: isBackgroundLayer ? [0, 0, 0] : [-1, -1, -1]
        };
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.erasedCells.clear();
        this.undoPushed = false;

        const eraserCell = this.getEraserCell(ctx);
        const current = ctx.state.getCell(cell.x, cell.y);
        if (!current || !cellEquals(current, eraserCell)) {
            ctx.undoStack.push(ctx.state);
            this.undoPushed = true;
            ctx.state.setCell(cell.x, cell.y, eraserCell);
        }
        this.erasedCells.add(`${cell.x},${cell.y}`);
    }

    onDrag(ctx: ToolContext, from: Point, to: Point): void {
        const points = getLinePoints(from, to);
        const cellData = this.getEraserCell(ctx);
        const updates: {col: number, row: number, cell: Cell}[] = [];
        
        for (const p of points) {
            const key = `${p.x},${p.y}`;
            if (this.erasedCells.has(key)) continue;
            this.erasedCells.add(key);

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
        this.erasedCells.clear();
    }

    onHover(ctx: ToolContext, cell: Point): void {
        // Preview cell will be drawn black
        ctx.renderer.setPreview([{
            col: cell.x,
            row: cell.y,
            cell: this.getEraserCell(ctx)
        }]);
    }

    onMouseLeave(ctx: ToolContext): void {
        ctx.renderer.clearPreview();
    }
}

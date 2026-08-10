import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';

export class MoveTool implements Tool {
    private anchor: Point | null = null;
    private movingCells: { col: number, row: number, originCell: Cell }[] = [];

    onMouseDown(ctx: ToolContext, cell: Point) {
        this.anchor = cell;
        
        const selected = ctx.renderer.getSelectedCells();
        const activeLayer = ctx.state.getActiveLayer();

        this.movingCells = [];

        if (selected && selected.size > 0) {
            // Move only the cells within selection on the active layer
            for (const key of selected) {
                const [col, row] = key.split(',').map(Number);
                const cell = ctx.state.getCell(col, row);
                if (cell) {
                    const originCell = { 
                        char: cell.char, 
                        fg: [...cell.fg] as [number, number, number], 
                        bg: [...cell.bg] as [number, number, number],
                        bold: cell.bold,
                        italic: cell.italic,
                        underline: cell.underline
                    };
                    this.movingCells.push({ col, row, originCell });
                }
            }
        } else {
            // Move everything on the active layer that is non-empty
            for (let row = 0; row < ctx.state.height; row++) {
                for (let col = 0; col < ctx.state.width; col++) {
                    const c = activeLayer.cells[row][col];
                    const isEmpty = (!c.char || c.char.trim() === '') && c.bg[0] === -1;
                    if (!isEmpty) {
                        const originCell = { 
                            char: c.char, fg: [...c.fg] as [number, number, number], bg: [...c.bg] as [number, number, number],
                            bold: c.bold, italic: c.italic, underline: c.underline
                        };
                        this.movingCells.push({ col, row, originCell });
                    }
                }
            }
            if (activeLayer.overflowCells) {
                 for (const [key, c] of activeLayer.overflowCells.entries()) {
                     const [col, row] = key.split(',').map(Number);
                     const originCell = { 
                         char: c.char, fg: [...c.fg] as [number, number, number], bg: [...c.bg] as [number, number, number],
                         bold: c.bold, italic: c.italic, underline: c.underline
                     };
                     this.movingCells.push({ col, row, originCell });
                 }
            }
        }
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point) {
        if (!this.anchor) return;
        const dx = to.x - this.anchor.x;
        const dy = to.y - this.anchor.y;

        const previewMap = new Map<string, { col: number, row: number, cell: Cell }>();

        // 1. Hide the original positions by placing transparent replacement cells
        for (const mc of this.movingCells) {
            previewMap.set(`${mc.col},${mc.row}`, {
                col: mc.col,
                row: mc.row,
                cell: { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] }
            });
        }

        // 2. Draw the cells at the new positions
        for (const mc of this.movingCells) {
            const newCol = mc.col + dx;
            const newRow = mc.row + dy;
            
            previewMap.set(`${newCol},${newRow}`, {
                col: newCol,
                row: newRow,
                cell: mc.originCell
            });
        }

        ctx.renderer.setPreview(Array.from(previewMap.values()));
    }

    onMouseUp(ctx: ToolContext, cell: Point) {
        if (!this.anchor) return;
        
        const dx = cell.x - this.anchor.x;
        const dy = cell.y - this.anchor.y;
        
        ctx.renderer.clearPreview();

        if (dx === 0 && dy === 0) {
            // No movement occurred
            this.anchor = null;
            this.movingCells = [];
            return;
        }

        // Push state for undo
        ctx.undoStack.push(ctx.state);
        
        // 1. & 2. Apply clear and place in a single batch
        const clearUpdates = this.movingCells.map(mc => ({ 
            col: mc.col, row: mc.row, cell: { char: '', fg: [204, 204, 204] as [number, number, number], bg: [-1, -1, -1] as [number, number, number] }
        }));
        
        const placeUpdates = this.movingCells.map(mc => ({
            col: mc.col + dx, row: mc.row + dy, cell: mc.originCell
        }));

        ctx.state.applyBatch([...clearUpdates, ...placeUpdates]);

        // 3. Move the selection outline if any
        let selected = ctx.renderer.getSelectedCells();
        if (selected && selected.size > 0) {
            const newSel = new Set<string>();
            for (const key of selected) {
                const [c, r] = key.split(',').map(Number);
                newSel.add(`${c + dx},${r + dy}`);
            }
            ctx.renderer.setSelection(newSel);
        }

        this.anchor = null;
        this.movingCells = [];
    }

    onHover(_ctx: ToolContext, _cell: Point) {}
    onMouseLeave(_ctx: ToolContext) {}
}

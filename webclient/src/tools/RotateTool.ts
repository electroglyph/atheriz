import { Tool, ToolContext } from './Tool';
import { Point, Cell, RotateMode } from '../types';

import { transformCharacter } from '../utils/transformMappings';

export class RotateTool implements Tool {
    private anchor: Point | null = null;
    private movingCells: { col: number, row: number, originCell: Cell }[] = [];
    private startAngle: number = 0;
    private currentTheta: number = 0;

    // Center used for rotation
    private cx: number = 0;
    private cy: number = 0;

    public applyTransform(ctx: ToolContext, mode: Exclude<RotateMode, 'free'>) {
        const selected = ctx.renderer.getSelectedCells();
        const activeLayer = ctx.state.getActiveLayer();
        
        let targetCells: { col: number, row: number, originCell: Cell }[] = [];

        if (selected && selected.size > 0) {
            for (const key of selected) {
                const [col, row] = key.split(',').map(Number);
                const cell = ctx.state.getCell(col, row);
                if (cell) {
                    targetCells.push({ col, row, originCell: cell });
                }
            }
        } else {
            for (let row = 0; row < ctx.state.height; row++) {
                for (let col = 0; col < ctx.state.width; col++) {
                    const c = activeLayer.cells[row][col];
                    const isEmpty = (!c.char || c.char.trim() === '') && c.bg[0] === -1;
                    if (!isEmpty) {
                        targetCells.push({ col, row, originCell: c });
                    }
                }
            }
            if (activeLayer.overflowCells) {
                for (const [key, c] of activeLayer.overflowCells.entries()) {
                    const [col, row] = key.split(',').map(Number);
                    targetCells.push({ col, row, originCell: c });
                }
            }
        }

        if (targetCells.length === 0) return;

        // Compute Bounding Box
        let minCol = Infinity, maxCol = -Infinity;
        let minRow = Infinity, maxRow = -Infinity;
        for (const tc of targetCells) {
            if (tc.col < minCol) minCol = tc.col;
            if (tc.col > maxCol) maxCol = tc.col;
            if (tc.row < minRow) minRow = tc.row;
            if (tc.row > maxRow) maxRow = tc.row;
        }

        const width = maxCol - minCol + 1;
        const height = maxRow - minRow + 1;

        ctx.undoStack.push(ctx.state);

        const clearUpdates = targetCells.map(tc => ({
            col: tc.col, row: tc.row, 
            cell: { char: '', fg: [204, 204, 204] as [number, number, number], bg: [-1, -1, -1] as [number, number, number] }
        }));

        const newTargetCells: { col: number, row: number, originCell: Cell }[] = [];
        const mappedSelection = new Set<string>();

        // 2. Transform positions and characters (in-place, anchored to bbox top-left)
        for (const tc of targetCells) {
            const i = tc.col - minCol;
            const j = tc.row - minRow;
            let ni = i, nj = j;
            let newChar = tc.originCell.char;

            switch (mode) {
                case 'cw90':
                    ni = height - 1 - j;
                    nj = i;
                    break;
                case 'ccw90':
                    ni = j;
                    nj = width - 1 - i;
                    break;
                case 'flip-h':
                    ni = width - 1 - i;
                    break;
                case 'flip-v':
                    nj = height - 1 - j;
                    break;
            }
            newChar = transformCharacter(newChar, mode);

            const finalCol = minCol + ni;
            const finalRow = minRow + nj;

            newTargetCells.push({
                col: finalCol,
                row: finalRow,
                originCell: { ...tc.originCell, char: newChar }
            });
            if (selected && selected.size > 0) {
                mappedSelection.add(`${finalCol},${finalRow}`);
            }
        }

        const placeUpdates = newTargetCells.map(ntc => ({
            col: ntc.col, row: ntc.row, cell: ntc.originCell
        }));

        ctx.state.applyBatch([...clearUpdates, ...placeUpdates]);

        if (mappedSelection.size > 0) {
            ctx.renderer.setSelection(mappedSelection);
        } else if (selected && selected.size > 0) {
             // they all fell out of bounds
             ctx.renderer.clearSelection();
        }

    }

    onMouseDown(ctx: ToolContext, cell: Point) {
        if (ctx.appState.rotateMode !== 'free') return;
        this.anchor = cell;
        
        const selected = ctx.renderer.getSelectedCells();
        const activeLayer = ctx.state.getActiveLayer();
        this.movingCells = [];

        if (selected && selected.size > 0) {
            for (const key of selected) {
                const [col, row] = key.split(',').map(Number);
                const cell = ctx.state.getCell(col, row);
                if (cell) {
                    this.movingCells.push({ col, row, originCell: cell });
                }
            }
        } else {
            for (let row = 0; row < ctx.state.height; row++) {
                for (let col = 0; col < ctx.state.width; col++) {
                    const c = activeLayer.cells[row][col];
                    const isEmpty = (!c.char || c.char.trim() === '') && c.bg[0] === -1;
                    if (!isEmpty) {
                        this.movingCells.push({ col, row, originCell: c });
                    }
                }
            }
            if (activeLayer.overflowCells) {
                for (const [key, c] of activeLayer.overflowCells.entries()) {
                    const [col, row] = key.split(',').map(Number);
                    this.movingCells.push({ col, row, originCell: c });
                }
            }
        }

        if (this.movingCells.length === 0) return;

        let minCol = Infinity, maxCol = -Infinity;
        let minRow = Infinity, maxRow = -Infinity;
        for (const tc of this.movingCells) {
            if (tc.col < minCol) minCol = tc.col;
            if (tc.col > maxCol) maxCol = tc.col;
            if (tc.row < minRow) minRow = tc.row;
            if (tc.row > maxRow) maxRow = tc.row;
        }

        this.cx = (minCol + maxCol) / 2;
        this.cy = (minRow + maxRow) / 2;

        const dy = cell.y - this.cy;
        const dx = cell.x - this.cx;
        this.startAngle = Math.atan2(dy, dx);
        this.currentTheta = 0;
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point) {
        if (!this.anchor || ctx.appState.rotateMode !== 'free' || this.movingCells.length === 0) return;
        
        const dy = to.y - this.cy;
        const dx = to.x - this.cx;
        const currentAngle = Math.atan2(dy, dx);
        this.currentTheta = currentAngle - this.startAngle;

        this.updateFreeHover(ctx, this.currentTheta);
    }

    private updateFreeHover(ctx: ToolContext, theta: number) {
        const previewMap = new Map<string, { col: number, row: number, cell: Cell }>();

        // To prevent extreme skewing during free rotation, we apply a 1:2 aspect ratio scaling, 
        // as standard text monospace grids (e.g. 9x18) are rarely square. 
        // While retrieving exact metrics would be perfect, W/H = 0.5 is a standard approximation.
        const W = 0.5;
        const H = 1.0;

        // 1. Hide original positions
        for (const mc of this.movingCells) {
            previewMap.set(`${mc.col},${mc.row}`, {
                col: mc.col,
                row: mc.row,
                cell: { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] }
            });
        }

        const cosInv = Math.cos(-theta);
        const sinInv = Math.sin(-theta);

        // We use Reverse Mapping (target to source) instead of a Forward Pass (source to target) 
        // to prevent sparse "holes" between characters at large angles. By scanning a conservatively 
        // scaled bounding box in the destination space and computing where each cell originated, 
        // we guarantee contiguous coverage.
        
        let Rmax = 0;
        for (const mc of this.movingCells) {
             const dx = (mc.col - this.cx) * W;
             const dy = (mc.row - this.cy) * H;
             const r = Math.sqrt(dx*dx + dy*dy);
             if (r > Rmax) Rmax = r;
        }

        const RmaxCol = Math.ceil(Rmax / W);
        const RmaxRow = Math.ceil(Rmax / H);
        
        const minC = Math.floor(this.cx - RmaxCol);
        const maxC = Math.ceil(this.cx + RmaxCol);
        const minR = Math.floor(this.cy - RmaxRow);
        const maxR = Math.ceil(this.cy + RmaxRow);

        // Put originals in a map for quick lookup
        const originHash = new Map<string, Cell>();
        for (const mc of this.movingCells) originHash.set(`${mc.col},${mc.row}`, mc.originCell);

        for (let r = minR - 1; r <= maxR + 1; r++) {
            for (let c = minC - 1; c <= maxC + 1; c++) {
                const px = (c - this.cx) * W;
                const py = (r - this.cy) * H;

                const ox = px * cosInv - py * sinInv;
                const oy = px * sinInv + py * cosInv;
                
                const sc = Math.round((ox / W) + this.cx);
                const sr = Math.round((oy / H) + this.cy);
                
                const oCell = originHash.get(`${sc},${sr}`);
                if (oCell) {
                    previewMap.set(`${c},${r}`, {
                        col: c,
                        row: r,
                        cell: oCell
                    });
                }
            }
        }

        ctx.renderer.setPreview(Array.from(previewMap.values()));
    }

    onMouseUp(ctx: ToolContext, cell: Point) {
        if (!this.anchor || ctx.appState.rotateMode !== 'free' || this.movingCells.length === 0) return;
        
        const dy = cell.y - this.cy;
        const dx = cell.x - this.cx;
        const currentAngle = Math.atan2(dy, dx);
        this.currentTheta = currentAngle - this.startAngle;

        ctx.renderer.clearPreview();

        if (this.currentTheta === 0) {
            this.anchor = null;
            return;
        }

        ctx.undoStack.push(ctx.state);

        // Regenerate reverse mapped output internally
        const W = 0.5;
        const H = 1.0;
        const cosInv = Math.cos(-this.currentTheta);
        const sinInv = Math.sin(-this.currentTheta);
        
        let Rmax = 0;
        for (const mc of this.movingCells) {
             const distx = (mc.col - this.cx) * W;
             const disty = (mc.row - this.cy) * H;
             const r = Math.sqrt(distx*distx + disty*disty);
             if (r > Rmax) Rmax = r;
        }

        const RmaxCol = Math.ceil(Rmax / W);
        const RmaxRow = Math.ceil(Rmax / H);
        const minC = Math.floor(this.cx - RmaxCol);
        const maxC = Math.ceil(this.cx + RmaxCol);
        const minR = Math.floor(this.cy - RmaxRow);
        const maxR = Math.ceil(this.cy + RmaxRow);

        const originHash = new Map<string, Cell>();
        for (const mc of this.movingCells) originHash.set(`${mc.col},${mc.row}`, mc.originCell);

        const newTargetCells: { col: number, row: number, originCell: Cell }[] = [];
        const mappedSelection = new Set<string>();
        const wasSelected = ctx.renderer.getSelectedCells().size > 0;

        for (let r = minR - 1; r <= maxR + 1; r++) {
            for (let c = minC - 1; c <= maxC + 1; c++) {
                const px = (c - this.cx) * W;
                const py = (r - this.cy) * H;
                const ox = px * cosInv - py * sinInv;
                const oy = px * sinInv + py * cosInv;
                const sc = Math.round((ox / W) + this.cx);
                const sr = Math.round((oy / H) + this.cy);
                
                const oCell = originHash.get(`${sc},${sr}`);
                if (oCell) {
                    newTargetCells.push({ col: c, row: r, originCell: oCell });
                    if (wasSelected) mappedSelection.add(`${c},${r}`);
                }
            }
        }

        const clearUpdates = this.movingCells.map(mc => ({
            col: mc.col, row: mc.row, cell: { char: '', fg: [204, 204, 204] as [number, number, number], bg: [-1, -1, -1] as [number, number, number] }
        }));

        const placeUpdates = newTargetCells.map(ntc => ({
            col: ntc.col, row: ntc.row, cell: ntc.originCell
        }));

        ctx.state.applyBatch([...clearUpdates, ...placeUpdates]);

        if (mappedSelection.size > 0) {
            ctx.renderer.setSelection(mappedSelection);
        } else if (wasSelected) {
            ctx.renderer.clearSelection();
        }

        this.anchor = null;
        this.movingCells = [];
    }

    onHover(_ctx: ToolContext, _cell: Point) {}
    onMouseLeave(_ctx: ToolContext) {}
}

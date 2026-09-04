import { Tool, ToolContext } from './Tool';
import { Point, Cell } from '../types';
import { LIGHT_BOX, ROUNDED_BOX, DOUBLE_BOX, HEAVY_BOX } from '../utils/characters';
import { getLinePoints } from '../utils/geometry';

function connectedLine(x0: number, y0: number, x1: number, y1: number, useDiagonal = false): Point[] {
    const raw = getLinePoints({ x: x0, y: y0 }, { x: x1, y: y1 });
    if (raw.length <= 1 || useDiagonal) return raw;

    const totalDx = Math.abs(x1 - x0);
    const totalDy = Math.abs(y1 - y0);
    const preferHorizontal = totalDx >= totalDy;

    const result: Point[] = [raw[0]];
    for (let i = 1; i < raw.length; i++) {
        const prev = raw[i - 1];
        const cur = raw[i];
        if (Math.abs(cur.x - prev.x) === 1 && Math.abs(cur.y - prev.y) === 1) {
            if (preferHorizontal) {
                result.push({ x: cur.x, y: prev.y });
            } else {
                result.push({ x: prev.x, y: cur.y });
            }
        }
        result.push(cur);
    }
    return result;
}

export class LineTool implements Tool {
    private anchor: Point | null = null;
    private currentEnd: Point | null = null;
    private isFirstClick = true;
    private pushedForStroke = false;
    private toastEl: HTMLDivElement | null = null;
    private committedPoints: Point[] = [];

    private showToast() {
        if (!this.toastEl) {
            this.toastEl = document.createElement('div');
            this.toastEl.className = 'line-tool-toast';
            this.toastEl.textContent = 'ESC: cancel';
            document.body.appendChild(this.toastEl);
        }
        this.toastEl.classList.add('visible');
    }

    private hideToast() {
        if (this.toastEl) {
            this.toastEl.classList.remove('visible');
        }
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        if (this.isFirstClick) {
            this.isFirstClick = false;
            this.pushedForStroke = false;
            this.committedPoints = [];
            this.anchor = cell;
            this.currentEnd = cell;
            this.showToast();
            this.renderPreview(ctx);
            return;
        }

        if (this.anchor && (cell.x !== this.anchor.x || cell.y !== this.anchor.y)) {
            this.commitSegment(ctx, this.anchor, cell);
        }
        this.anchor = cell;
        this.currentEnd = cell;
        this.renderPreview(ctx);
    }

    onDrag(ctx: ToolContext, _from: Point, to: Point): void {
        if (this.isFirstClick) return;
        this.currentEnd = to;
        this.renderPreview(ctx);
    }

    onMouseUp(_ctx: ToolContext, _cell: Point): void {
    }

    onHover(ctx: ToolContext, cell: Point): void {
        if (this.isFirstClick) {
            ctx.renderer.setPreview([{
                col: cell.x,
                row: cell.y,
                cell: {
                    char: ctx.appState.selectedChar,
                    fg: ctx.appState.fgColor,
                    bg: ctx.appState.bgColor
                }
            }]);
            return;
        }
        this.currentEnd = cell;
        this.renderPreview(ctx);
    }

    onMouseLeave(ctx: ToolContext): void {
        if (this.isFirstClick) {
            ctx.renderer.clearPreview();
        }
    }

    onKeyDown(ctx: ToolContext, key: string): boolean {
        if (key === 'Escape') {
            if (this.isFirstClick) return false;
            this.anchor = null;
            this.currentEnd = null;
            this.isFirstClick = true;
            this.pushedForStroke = false;
            this.committedPoints = [];
            this.hideToast();
            ctx.renderer.clearPreview();
            return true;
        }
        return false;
    }

    private commitSegment(ctx: ToolContext, from: Point, to: Point): void {
        const useDiagonal = ctx.appState.lineDiagonal;
        const newPoints = connectedLine(from.x, from.y, to.x, to.y, useDiagonal);
        const allPoints = [...this.committedPoints, ...newPoints];
        const cells = this.buildCells(ctx, allPoints);
        if (cells.length > 0) {
            if (!this.pushedForStroke) {
                ctx.undoStack.push(ctx.state);
                this.pushedForStroke = true;
            }
            ctx.state.applyBatch(cells);
        }
        this.committedPoints = allPoints;
    }

    private renderPreview(ctx: ToolContext) {
        if (!this.anchor || !this.currentEnd) return;
        if (this.anchor.x === this.currentEnd.x && this.anchor.y === this.currentEnd.y) {
            const mode = ctx.appState.lineMode;
            if (mode === 'custom') {
                ctx.renderer.setPreview([{
                    col: this.anchor.x,
                    row: this.anchor.y,
                    cell: { char: ctx.appState.selectedChar, fg: ctx.appState.fgColor, bg: ctx.appState.bgColor }
                }]);
            } else {
                ctx.renderer.setPreview([{
                    col: this.anchor.x,
                    row: this.anchor.y,
                    cell: { char: this.getCharMap(mode).v, fg: ctx.appState.fgColor, bg: ctx.appState.bgColor }
                }]);
            }
            return;
        }
        const useDiagonal = ctx.appState.lineDiagonal;
        const newPoints = connectedLine(this.anchor.x, this.anchor.y, this.currentEnd.x, this.currentEnd.y, useDiagonal);
        const allPoints = [...this.committedPoints, ...newPoints];
        const cells = this.buildCells(ctx, allPoints);
        ctx.renderer.setPreview(cells);
    }

    private getCharMap(mode: string) {
        return mode === 'double' ? DOUBLE_BOX :
               mode === 'rounded' ? ROUNDED_BOX :
               mode === 'heavy' ? HEAVY_BOX :
               LIGHT_BOX;
    }

    private buildCells(ctx: ToolContext, points: Point[]): { col: number; row: number; cell: Cell }[] {
        const mode = ctx.appState.lineMode;
        const fg = ctx.appState.fgColor;
        const bg = ctx.appState.bgColor;
        const selected = ctx.appState.selectedChar;

        if (points.length === 0) return [];

        if (mode === 'custom') {
            const seen = new Set<string>();
            return points.filter(p => {
                const k = `${p.x},${p.y}`;
                if (seen.has(k)) return false;
                seen.add(k);
                return true;
            }).map(p => ({ col: p.x, row: p.y, cell: { char: selected, fg, bg } }));
        }

        const charMap = this.getCharMap(mode);

        // --- NON-DIAGONAL MODE: adjacency-based character selection ---
        // We look at the immediate 4-way neighbors (N, S, E, W) in the drawn points set 
        // to determine if the current cell should be a straight line, a corner, or an intersection piece.
        if (!ctx.appState.lineDiagonal) {
            const pSet = new Set<string>();
            for (const p of points) pSet.add(`${p.x},${p.y}`);
            const seen = new Set<string>();
            const updates: { col: number; row: number; cell: Cell }[] = [];
            for (const p of points) {
                const key = `${p.x},${p.y}`;
                if (seen.has(key)) continue;
                seen.add(key);
                const n = pSet.has(`${p.x},${p.y - 1}`);
                const s = pSet.has(`${p.x},${p.y + 1}`);
                const e = pSet.has(`${p.x + 1},${p.y}`);
                const w = pSet.has(`${p.x - 1},${p.y}`);
                let charToDraw: string;
                if (n && e && s && w) charToDraw = charMap.c;
                else if (n && s && e) charToDraw = charMap.l;
                else if (n && s && w) charToDraw = charMap.r;
                else if (n && e && w) charToDraw = charMap.b;
                else if (s && e && w) charToDraw = charMap.t;
                else if (n && e) charToDraw = charMap.bl;
                else if (n && w) charToDraw = charMap.br;
                else if (s && e) charToDraw = charMap.tl;
                else if (s && w) charToDraw = charMap.tr;
                else if (n || s) charToDraw = charMap.v;
                else charToDraw = charMap.h;
                updates.push({ col: p.x, row: p.y, cell: { char: charToDraw, fg, bg } });
            }
            return updates;
        }

        // --- DIAGONAL MODE: sequence-based character selection ---
        // Each cell character is chosen based on the DIRECTION VECTORS from the previous and
        // next point in the sequence, not a neighbor-set lookup. This ensures contiguous lines.

        // Deduplicate while preserving traversal order
        const seenKeys = new Set<string>();
        const seq: Point[] = [];
        for (const p of points) {
            const k = `${p.x},${p.y}`;
            if (!seenKeys.has(k)) { seenKeys.add(k); seq.push(p); }
        }

        // Cell boundary connection points:
        //   ML=middle-left  MR=middle-right  MT=middle-top  MB=middle-bottom
        //   UL=upper-left   UR=upper-right   LL=lower-left  LR=lower-right
        type CP = 'ML'|'MR'|'MT'|'MB'|'UL'|'UR'|'LL'|'LR';

        // Entry point: where the line enters this cell, given direction (dx,dy) from prev->curr
        // Handles any step size (including non-adjacent points after deduplication).
        function entry(dx: number, dy: number): CP {
            const sx = Math.sign(dx);
            const sy = Math.sign(dy);
            if (sx ===  1 && sy ===  0) return 'ML'; // came from west
            if (sx === -1 && sy ===  0) return 'MR'; // came from east
            if (sx ===  0 && sy ===  1) return 'MT'; // came from north
            if (sx ===  0 && sy === -1) return 'MB'; // came from south
            if (sx ===  1 && sy ===  1) return 'UL'; // came from NW (SE direction)
            if (sx ===  1 && sy === -1) return 'LL'; // came from SW (NE direction)
            if (sx === -1 && sy ===  1) return 'UR'; // came from NE (SW direction)
            if (sx === -1 && sy === -1) return 'LR'; // came from SE (NW direction)
            return 'ML';
        }

        // Exit point: where the line exits this cell, given direction (dx,dy) from curr->next
        // Handles any step size (including non-adjacent points after deduplication).
        function exit_(dx: number, dy: number): CP {
            const sx = Math.sign(dx);
            const sy = Math.sign(dy);
            if (sx ===  1 && sy ===  0) return 'MR'; // going east
            if (sx === -1 && sy ===  0) return 'ML'; // going west
            if (sx ===  0 && sy === -1) return 'MT'; // going north
            if (sx ===  0 && sy ===  1) return 'MB'; // going south
            if (sx ===  1 && sy === -1) return 'UR'; // going NE
            if (sx ===  1 && sy ===  1) return 'LR'; // going SE
            if (sx === -1 && sy === -1) return 'UL'; // going NW
            if (sx === -1 && sy ===  1) return 'LL'; // going SW
            return 'MR';
        }

        // Map a pair of connection points → Unicode character (order-independent)
        function connChar(a: CP | null, b: CP | null): string {
            const key = (a && b) ? [a, b].sort().join('-') : (a ?? b ?? '');
            switch (key) {
                // Orthogonal straights (Middle-to-Middle)
                case 'ML-MR': return charMap.h;
                case 'MB-MT': return charMap.v;

                // Box corners (Middle-to-Middle)
                case 'ML-MT': return charMap.br; // ┘
                case 'MB-ML': return charMap.tr; // ┐  (was 'ML-MB' — wrong sorted key)
                case 'MR-MT': return charMap.bl; // └
                case 'MB-MR': return charMap.tl; // ┌  (was 'MR-MB' — wrong sorted key)

                // Perfect 45° diagonals (Corner-to-Corner)
                case 'LL-UR': return '╱';
                case 'LR-UL': return '╲';

                // Off-angle Corner-to-Middle (Long/Transitions)
                case 'LL-MR': return '🯐';
                case 'ML-UR': return '🯑';
                case 'MR-UL': return '🯒';
                case 'LR-ML': return '🯓';
                case 'MB-UL': return '🯔';
                case 'LR-MT': return '🯕';
                case 'MB-UR': return '🯖';
                case 'LL-MT': return '🯗';

                // Off-angle Corner-to-Corner (3-point bridge characters from U+1FBD8)
                // These eliminate the 0.5-cell gap in sharp "V" or ">" turns.
                case 'UL-UR': return '🯘'; // Upper-Left to Upper-Right via Center
                case 'LR-UR': return '🯙'; // Upper-Right to Lower-Right via Center (was 'UR-LR' — wrong sorted key)
                case 'LL-LR': return '🯚'; // Lower-Left to Lower-Right via Center
                case 'LL-UL': return '🯛'; // Lower-Left to Upper-Left via Center

                // Off-angle Corner-to-Middle (Short/Adjacent)
                // Fallbacks prioritise the corner connection so the line never
                // appears to stop short at a junction or turn.
                case 'LL-ML': return '🯛'; // connects LL (and UL)
                case 'LL-MB': return '🯚'; // bottom-edge fallback for LL-MB (was 🯛)
                case 'LR-MR': return '🯙'; // connects LR (and UR)
                case 'LR-MB': return '🯚'; // connects LR (and LL)
                case 'ML-UL': return '🯛'; // connects UL (and LL)
                case 'MT-UL': return '🯘'; // top-edge fallback for MT-UL (was 🯜 — does not reach MT)
                case 'MR-UR': return '🯙'; // connects UR (and LR)
                case 'MT-UR': return '🯘'; // top-edge fallback for MT-UR (was 🯜 — does not reach MT)

                // Endpoints — pick based on single connection direction
                case 'ML': case 'MR': return charMap.h;
                case 'MT': case 'MB': return charMap.v;
                case 'LL': case 'UR': return '╱';
                case 'UL': case 'LR': return '╲';

                default: return charMap.h;
            }
        }

        const updates: { col: number; row: number; cell: Cell }[] = [];

        for (let i = 0; i < seq.length; i++) {
            const p = seq[i];
            const prev = i > 0 ? seq[i - 1] : null;
            const next = i < seq.length - 1 ? seq[i + 1] : null;

            const entryPt = prev ? entry(p.x - prev.x, p.y - prev.y) : null;
            const exitPt  = next ? exit_(next.x - p.x,  next.y - p.y)  : null;

            updates.push({ col: p.x, row: p.y, cell: { char: connChar(entryPt, exitPt), fg, bg } });
        }

        return updates;
    }
}

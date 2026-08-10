import { CanvasState } from '../state/CanvasState';
import { Color } from '../types';

// This sequence is used as a layer boundary marker in .ans files.
// Save-cursor x3 + Restore-cursor x3 is a no-op in any standard terminal,
// but is distinctive enough for our parser to detect.
export const LAYER_BOUNDARY_MARKER = '\x1b[s\x1b[u\x1b[s\x1b[u\x1b[s\x1b[u';

export class AnsiExporter {
    public static export(state: CanvasState): string {
        const { width, height, layers } = state;

        let out = `\x1b[8;${height};${width}t\x1b[2J\x1b[H`;

        const emitStyle = (cell: { bold?: boolean; italic?: boolean; underline?: boolean }, current: { bold: boolean; italic: boolean; underline: boolean }): { bold: boolean; italic: boolean; underline: boolean } => {
            const bold = !!cell.bold;
            const italic = !!cell.italic;
            const underline = !!cell.underline;
            if (bold !== current.bold || italic !== current.italic || underline !== current.underline) {
                const codes: number[] = [];
                if (bold !== current.bold) codes.push(bold ? 1 : 22);
                if (italic !== current.italic) codes.push(italic ? 3 : 23);
                if (underline !== current.underline) codes.push(underline ? 4 : 24);
                out += `\x1b[${codes.join(';')}m`;
            }
            return { bold, italic, underline };
        };

        // Background Layer: Exported as a full raster sequence. 
        // We emit every cell to guarantee a solid base, avoiding transparent holes during rendering.
        const bgLayer = layers[0];
        let currentFg: Color | null = null;
        let currentBg: Color | null = null;
        let currentStyle = { bold: false, italic: false, underline: false };

        for (let r = 0; r < height; r++) {
            out += `\x1b[${r + 1};1H`;
            for (let c = 0; c < width; c++) {
                const cell = bgLayer.cells[r][c];
                const char = cell.char || ' ';

                // A layer promoted to index 0 (after the original bg was deleted) may still
                // carry transparent bg sentinel values [-1,-1,-1]. Resolve to black here so
                // we never emit invalid negative color components into the escape sequence.
                const bg: Color = cell.bg[0] === -1 ? [0, 0, 0] : cell.bg;

                const bgChanged = !currentBg || currentBg[0] !== bg[0] || currentBg[1] !== bg[1] || currentBg[2] !== bg[2];
                const fgChanged = !currentFg || currentFg[0] !== cell.fg[0] || currentFg[1] !== cell.fg[1] || currentFg[2] !== cell.fg[2];

                if (bgChanged) {
                    out += `\x1b[48;2;${bg[0]};${bg[1]};${bg[2]}m`;
                    currentBg = bg;
                }
                if (char !== ' ' && fgChanged) {
                    out += `\x1b[38;2;${cell.fg[0]};${cell.fg[1]};${cell.fg[2]}m`;
                    currentFg = cell.fg;
                }
                currentStyle = emitStyle(cell, currentStyle);

                out += char;
            }
        }

        // Overlay Layers: Exported sparsely. 
        // To minimize file size and avoid overwriting lower layers unnecessarily, 
        // we only emit cursor jumps and ANSI sequences for non-transparent cells.
        for (let li = 1; li < layers.length; li++) {
            out += LAYER_BOUNDARY_MARKER;

            const layer = layers[li];
            currentFg = null;
            currentBg = null;
            currentStyle = { bold: false, italic: false, underline: false };

            for (let r = 0; r < height; r++) {
                for (let c = 0; c < width; c++) {
                    const cell = layer.cells[r][c];

                    const hasChar = cell.char && cell.char.trim() !== '';
                    const hasBg = cell.bg[0] !== -1;
                    if (!hasChar && !hasBg) continue;

                    out += `\x1b[${r + 1};${c + 1}H`;

                    if (hasBg) {
                        out += `\x1b[48;2;${cell.bg[0]};${cell.bg[1]};${cell.bg[2]}m`;
                        currentBg = cell.bg;
                    }

                    const char = cell.char || ' ';
                    if (char !== ' ') {
                        out += `\x1b[38;2;${cell.fg[0]};${cell.fg[1]};${cell.fg[2]}m`;
                        currentFg = cell.fg;
                    }
                    currentStyle = emitStyle(cell, currentStyle);

                    out += char;
                }
            }
        }

        out += `\x1b[0m\n`;
        return out;
    }

    public static download(state: CanvasState, filename: string = 'drawing.ans') {
        const data = this.export(state);
        const blob = new Blob([data], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
    }
}

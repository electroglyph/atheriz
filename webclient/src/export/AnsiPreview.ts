import { CanvasState } from '../state/CanvasState';
import { Color } from '../types';

/**
 * Generates a flat ANSI/VT100 string that represents the *composited* view of the canvas
 * (all visible layers merged), suitable for feeding into xterm.js.
 */
export function buildCompositeAnsiPreview(state: CanvasState): string {
    const { width, height } = state;
    let out = '';

    let currentFg: Color | null = null;
    let currentBg: Color | null = null;
    let currentStyle = { bold: false, italic: false, underline: false };

    const emitStyle = (cell: { bold?: boolean; italic?: boolean; underline?: boolean }, cur: { bold: boolean; italic: boolean; underline: boolean }): { bold: boolean; italic: boolean; underline: boolean } => {
        const bold = !!cell.bold;
        const italic = !!cell.italic;
        const underline = !!cell.underline;
        if (bold !== cur.bold || italic !== cur.italic || underline !== cur.underline) {
            const codes: number[] = [];
            if (bold !== cur.bold) codes.push(bold ? 1 : 22);
            if (italic !== cur.italic) codes.push(italic ? 3 : 23);
            if (underline !== cur.underline) codes.push(underline ? 4 : 24);
            out += `\x1b[${codes.join(';')}m`;
        }
        return { bold, italic, underline };
    };

    for (let r = 0; r < height; r++) {
        out += `\x1b[${r + 1};1H`;

        for (let c = 0; c < width; c++) {
            const cell = state.getCompositeCell(c, r);
            if (!cell) { out += ' '; continue; }

            const char = cell.char && cell.char.trim() !== '' ? cell.char : ' ';
            const bg = cell.bg[0] === -1 ? [0, 0, 0] as Color : cell.bg;
            const fg = cell.fg;

            const bgChanged = !currentBg ||
                currentBg[0] !== bg[0] || currentBg[1] !== bg[1] || currentBg[2] !== bg[2];
            const fgChanged = !currentFg ||
                currentFg[0] !== fg[0] || currentFg[1] !== fg[1] || currentFg[2] !== fg[2];

            if (bgChanged) {
                out += `\x1b[48;2;${bg[0]};${bg[1]};${bg[2]}m`;
                currentBg = bg;
            }
            if (char !== ' ' && fgChanged) {
                out += `\x1b[38;2;${fg[0]};${fg[1]};${fg[2]}m`;
                currentFg = fg;
            }
            currentStyle = emitStyle(cell, currentStyle);

            out += char;
        }
    }

    out += '\x1b[0m';
    return out;
}

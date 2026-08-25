import { Cell, Color } from '../types';
import { CanvasState } from '../state/CanvasState';
import { Terminal } from '@xterm/headless';
import { LAYER_BOUNDARY_MARKER } from '../export/AnsiExporter';

interface XtermCell {
    isFgRGB(): boolean;
    isBgRGB(): boolean;
    getFgColor(): number;
    getBgColor(): number;
    isFgPalette(): boolean;
    isBgPalette(): boolean;
    isInverse(): number;
    isBold(): number;
    isItalic(): number;
    isUnderline(): number;
    isBgDefault(): boolean;
    getChars(): string;
}

function colorFromXterm(cell: XtermCell, isFg: boolean): Color {
    if (isFg ? cell.isFgRGB() : cell.isBgRGB()) {
        const raw = isFg ? cell.getFgColor() : cell.getBgColor();
        return [(raw >> 16) & 0xff, (raw >> 8) & 0xff, raw & 0xff];
    }
    if (isFg ? cell.isFgPalette() : cell.isBgPalette()) {
        const idx = isFg ? cell.getFgColor() : cell.getBgColor();
        return ansi256ToRgb(idx);
    }
    return isFg ? [204, 204, 204] : [0, 0, 0];
}

function extractCellColors(c: XtermCell): { fg: Color; bg: Color } {
    let fg = colorFromXterm(c, true);
    let bg = colorFromXterm(c, false);
    if (c.isInverse()) {
        [fg, bg] = [bg, fg];
    }
    return { fg, bg };
}

function ansi256ToRgb(idx: number): Color {
    if (idx < 16) {
        const table: Color[] = [
            [0, 0, 0], [128, 0, 0], [0, 128, 0], [128, 128, 0],
            [0, 0, 128], [128, 0, 128], [0, 128, 128], [192, 192, 192],
            [128, 128, 128], [255, 0, 0], [0, 255, 0], [255, 255, 0],
            [0, 0, 255], [255, 0, 255], [0, 255, 255], [255, 255, 255],
        ];
        return table[idx] ?? [204, 204, 204];
    }
    if (idx < 232) {
        const i = idx - 16;
        const b = i % 6;
        const g = Math.floor(i / 6) % 6;
        const r = Math.floor(i / 36);
        const c = (v: number) => v === 0 ? 0 : 55 + v * 40;
        return [c(r), c(g), c(b)];
    }
    const v = Math.min(255, Math.round((idx - 232) * (255 / 23)));
    return [v, v, v];
}

function writeSync(term: Terminal, data: string): Promise<void> {
    return new Promise(resolve => term.write(data, resolve));
}

/**
 * Reads the xterm window-resize escape `\x1b[8;rows;colst` written by AnsiExporter
 * to recover the exact canvas dimensions. Falls back to counting visible rows/cols
 * for ANSI files produced by other tools.
 */
export function detectAnsiDimensions(ansiString: string): { width: number; height: number } {
    // Our exporter always starts with \x1b[8;<rows>;<cols>t
    const sizeMatch = ansiString.match(/^\x1b\[8;(\d+);(\d+)t/);
    if (sizeMatch) {
        return { width: parseInt(sizeMatch[2], 10), height: parseInt(sizeMatch[1], 10) };
    }

    // Fallback: strip ANSI escapes and measure the plain-text content
    const stripped = ansiString.replace(/\x1b\[[\d;]*[a-zA-Z]/g, '');
    const rawLines = stripped.split(/\r?\n/);
    while (rawLines.length > 1 && rawLines[rawLines.length - 1] === '') rawLines.pop();
    const lines = rawLines;
    const height = Math.max(1, lines.length);
    const width = Math.max(1, ...lines.map(l => l.length));
    return { width, height };
}

const DEFAULT_FG: Color = [204, 204, 204];
const TRANSPARENT: Color = [-1, -1, -1];

/**
 * Parses a single ANSI-wrapped symbol (one map-editor cell) into a Cell.
 * Handles the engine's wrap_truecolor() output: always a background
 * (`48;2;r;g;b`, black `0;0;0` when unset), always a truecolor foreground,
 * optional style SGRs, and a final reset. Inverse (`7`) and strikethrough
 * (`9`) are parsed and dropped — the editor Cell model has no fields for
 * them, so those attributes cannot round-trip.
 */
export function parseAnsiSymbol(symbol: string): Cell {
    let fg: Color = [...DEFAULT_FG];
    let bg: Color = [...TRANSPARENT];
    let bold: boolean | undefined;
    let italic: boolean | undefined;
    let underline: boolean | undefined;
    let char = '';
    let cellFg: Color = [...DEFAULT_FG];
    let cellBg: Color = [...TRANSPARENT];
    let cellBold: boolean | undefined;
    let cellItalic: boolean | undefined;
    let cellUnderline: boolean | undefined;

    // Walk the string in order: SGR sequences update the running state; the
    // first visible character snapshots it. The engine's wrap_* output places
    // the reset AFTER the glyph, so a naive last-wins scan would wipe the
    // cell's colors; capturing at the char avoids that.
    const re = /\x1b\[[0-9;]*m|[^\x1b]/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(symbol)) !== null) {
        const token = m[0];
        if (token.startsWith('\x1b')) {
            const raw = token.slice(2, -1);
            const parts = raw ? raw.split(';') : ['0'];
            let i = 0;
            while (i < parts.length) {
                const code = Number(parts[i]);
                if (code === 0) {
                    fg = [...DEFAULT_FG];
                    bg = [...TRANSPARENT];
                    bold = undefined;
                    italic = undefined;
                    underline = undefined;
                    i += 1;
                } else if (code === 1) {
                    bold = true;
                    i += 1;
                } else if (code === 22) {
                    bold = false;
                    i += 1;
                } else if (code === 3) {
                    italic = true;
                    i += 1;
                } else if (code === 23) {
                    italic = false;
                    i += 1;
                } else if (code === 4) {
                    underline = true;
                    i += 1;
                } else if (code === 24) {
                    underline = false;
                    i += 1;
                } else if (code === 38 || code === 48) {
                    const isFg = code === 38;
                    const mode = Number(parts[i + 1]);
                    if (mode === 2 && i + 4 < parts.length) {
                        const rgb: Color = [Number(parts[i + 2]), Number(parts[i + 3]), Number(parts[i + 4])];
                        if (isFg) {
                            fg = rgb;
                        } else {
                            // Engine convention: black background == unset/transparent.
                            bg = rgb[0] === 0 && rgb[1] === 0 && rgb[2] === 0 ? [...TRANSPARENT] : rgb;
                        }
                        i += 5;
                    } else if (mode === 5 && i + 2 < parts.length) {
                        const rgb = ansi256ToRgb(Number(parts[i + 2]));
                        if (isFg) {
                            fg = rgb;
                        } else {
                            bg = rgb[0] === 0 && rgb[1] === 0 && rgb[2] === 0 ? [...TRANSPARENT] : rgb;
                        }
                        i += 3;
                    } else {
                        i += 2;
                    }
                } else {
                    // 7 (inverse) and 9 (strikethrough) deliberately ignored.
                    i += 1;
                }
            }
        } else if (!char) {
            char = token;
            cellFg = [...fg];
            cellBg = [...bg];
            cellBold = bold;
            cellItalic = italic;
            cellUnderline = underline;
        } else {
            char += token;
        }
    }

    return { char, fg: cellFg, bg: cellBg, bold: cellBold, italic: cellItalic, underline: cellUnderline };
}

export async function parseAnsiToCells(ansiString: string, canvasWidth: number, canvasHeight?: number): Promise<Cell[]> {
    const rows = canvasHeight ?? Math.max(1, Math.ceil(ansiString.length / canvasWidth));
    const term = new Terminal({ cols: canvasWidth, rows, scrollback: 0, allowProposedApi: true });
    const normalized = ansiString.replace(/(?<!\r)\n/g, '\r\n');
    await writeSync(term, normalized);

    const buf = term.buffer.active;
    const cells: Cell[] = [];
    const nullCell = buf.getNullCell();

    for (let y = 0; y < rows; y++) {
        const line = buf.getLine(y);
        for (let x = 0; x < canvasWidth; x++) {
            const c = line?.getCell(x, nullCell);
            if (!c) {
                cells.push({ char: '', fg: [204, 204, 204], bg: [0, 0, 0] });
                continue;
            }
            const ch = c.getChars();
            const { fg, bg } = extractCellColors(c);
            cells.push({
                char: ch === ' ' ? '' : ch,
                fg,
                bg,
                bold: !!c.isBold() || undefined,
                italic: !!c.isItalic() || undefined,
                underline: !!c.isUnderline() || undefined,
            });
        }
    }

    term.dispose();
    return cells;
}

export async function parseAnsiToState(ansiString: string, width: number, height: number): Promise<CanvasState> {
    const state = new CanvasState(width, height, false);
    state.layers = [];
    state.layerIdCounter = 0;
    state.addLayer('Background', true);
    state.activeLayerIndex = 0;

    const layerChunks = ansiString.split(LAYER_BOUNDARY_MARKER);

    for (let li = 0; li < layerChunks.length; li++) {
        if (li > 0) {
            state.addLayer(`Layer ${li + 1}`, false);
            state.activeLayerIndex = state.layers.length - 1;
        }

        const chunk = layerChunks[li];
        const normalizedChunk = chunk.replace(/(?<!\r)\n/g, '\r\n');
        const term = new Terminal({ cols: width, rows: height, scrollback: 0, allowProposedApi: true });
        await writeSync(term, normalizedChunk);

        const buf = term.buffer.active;
        const layer = state.layers[li];
        const nullCell = buf.getNullCell();
        const defaultBg: Color = li === 0 ? [0, 0, 0] : [-1, -1, -1];

        for (let y = 0; y < height; y++) {
            const line = buf.getLine(y);
            for (let x = 0; x < width; x++) {
                const c = line?.getCell(x, nullCell);
                if (!c) continue;
                const ch = c.getChars();
                const { fg, bg: rawBg } = extractCellColors(c);
                const bg = c.isBgDefault() ? [...defaultBg] as Color : rawBg;
                layer.cells[y][x] = {
                    char: ch === ' ' ? '' : ch,
                    fg,
                    bg,
                    bold: !!c.isBold() || undefined,
                    italic: !!c.isItalic() || undefined,
                    underline: !!c.isUnderline() || undefined,
                };
            }
        }

        term.dispose();
    }

    state.activeLayerIndex = 0;
    return state;
}

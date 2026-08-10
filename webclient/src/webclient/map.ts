import { MapBackground, MapLegendEntry, MapPayload } from './types';

const ANSI = /\x1b\[[0-?]*[ -/]*[@-~]/g;
const RESET = '\x1b[0m';
export const MAP_CLEAR_SEQUENCE = '\x1b[2J\x1b[3J\x1b[H';

export function renderMap(payload: MapPayload, columns: number, rows: number): string {
    let lines = payload.map.split(/\r?\n/);
    applyBackground(lines, payload);

    const processedLegend = processLegend(payload.legend ?? []);
    for (const entry of processedLegend) {
        if (entry.coords) placeVisual(lines, relativePosition(entry.coords, payload), withReset(entry.symbol));
    }
    if (payload.pos && payload.symbol) {
        placeVisual(lines, relativePosition(payload.pos, payload), withReset(payload.symbol));
    }

    const legend = payload.show_legend === false ? [] : buildLegend(payload, processedLegend, columns, rows);
    const availableRows = Math.max(1, rows - (legend.length > 0 ? legend.length + 1 : 0));
    const mapWidth = Math.max(0, ...lines.map(visibleLength));
    const mapHeight = lines.length;
    const player = payload.pos ? relativePosition(payload.pos, payload) : undefined;
    const xStart = player && mapWidth > columns
        ? clamp(player[0] - Math.floor(columns / 2), 0, mapWidth - columns)
        : 0;
    const yStart = player && mapHeight > availableRows
        ? clamp(player[1] - Math.floor(availableRows / 2), 0, mapHeight - availableRows)
        : 0;
    const visible = lines.slice(yStart, yStart + availableRows).map((line) => {
        const sliced = ansiSubstring(line, xStart, xStart + columns);
        return sliced;
    });

    const mapStartRow = Math.max(1, Math.floor((rows - visible.length - (legend.length > 0 ? legend.length + 1 : 0)) / 2) + 1);
    const mapStartColumn = Math.max(1, Math.floor((columns - Math.min(columns, mapWidth)) / 2) + 1);
    const output: string[] = [];
    visible.forEach((line, index) => {
        output.push(`\x1b[${mapStartRow + index};${mapStartColumn}H${line}`);
    });
    if (legend.length > 0) {
        const legendStartRow = mapStartRow + visible.length + 1;
        legend.forEach((line, index) => {
            const column = Math.max(1, Math.floor((columns - visibleLength(line)) / 2) + 1);
            output.push(`\x1b[${legendStartRow + index};${column}H${line}`);
        });
    }
    return output.join('');
}

function applyBackground(lines: string[], payload: MapPayload): void {
    const backgrounds = payload.background
        ? Array.isArray(payload.background) ? payload.background : [payload.background]
        : [];
    for (const background of backgrounds) {
        const [r, g, b] = background.color;
        for (const [worldX, worldY] of background.coords) {
            const [x, y] = relativePosition([worldX, worldY], payload);
            if (y < 0 || y >= lines.length || x < 0) continue;
            const line = lines[y] ?? '';
            const color = `\x1b[48;2;${r};${g};${b}m`;
            const start = visualRawIndex(line, x, true);
            const end = visualRawIndex(line, x + 1, false);
            if (x >= visibleLength(line)) {
                lines[y] = `${line}${' '.repeat(x - visibleLength(line))}${color} ${RESET}`;
            } else {
                lines[y] = `${line.slice(0, start)}${color}${line.slice(start, end)}${RESET}${line.slice(end)}`;
            }
        }
    }
}

function buildLegend(payload: MapPayload, entries: MapLegendEntry[], columns: number, rows: number): string[] {
    const values = payload.symbol
        ? [{ symbol: stylePlayerSymbol(payload.symbol), desc: 'You' }, ...entries]
        : entries;
    if (values.length === 0) return [];
    const availableHeight = Math.max(5, Math.floor(rows / 3));
    const minColumns = Math.min(values.length, Math.max(1, Math.ceil(values.length / Math.max(1, availableHeight - 2))));
    let chosenColumns = minColumns;
    let columnWidths = calculateLegendWidths(values, chosenColumns);
    for (let candidate = minColumns; candidate >= 1; candidate -= 1) {
        const widths = calculateLegendWidths(values, candidate);
        if (legendWidth(widths, candidate) <= columns) {
            chosenColumns = candidate;
            columnWidths = widths;
            break;
        }
    }

    const rowCount = Math.ceil(values.length / chosenColumns);
    const totalWidth = legendWidth(columnWidths, chosenColumns);
    const title = payload.area ?? 'Legend';
    const headerText = `╭─ ${title} `;
    const header = `${headerText}${'─'.repeat(Math.max(1, totalWidth - visibleLength(headerText) - 1))}╮`;
    const output = [header];
    for (let row = 0; row < rowCount; row += 1) {
        let line = '│';
        for (let column = 0; column < chosenColumns; column += 1) {
            const item = values[column * rowCount + row];
            const width = columnWidths[column];
            const text = item ? `${item.symbol} = ${item.desc}` : '';
            line += ` ${text}${' '.repeat(Math.max(0, width - visibleLength(text)))} │`;
        }
        output.push(line);
    }
    let footer = '╰';
    for (let column = 0; column < chosenColumns; column += 1) {
        footer += `${'─'.repeat(columnWidths[column] + 2)}${column === chosenColumns - 1 ? '╯' : '┴'}`;
    }
    output.push(footer);
    return output;
}

function processLegend(entries: MapLegendEntry[]): MapLegendEntry[] {
    const seen = new Map<string, number>();
    const colorized = entries.flatMap((entry) => {
        if (!entry.symbol) return [];
        const stripped = stripAnsi(entry.symbol);
        const color = extractTrueColor(entry.symbol);
        const key = `${stripped}|${color ? color.join(',') : 'none'}`;
        const hue = seen.get(key);
        if (hue === undefined) {
            seen.set(key, 131);
            return [{ ...entry, symbol: withReset(entry.symbol) }];
        }
        seen.set(key, (hue + 57) % 360);
        const [r, g, b] = hslToRgb(hue / 360, 1, 0.5);
        return [{ ...entry, symbol: `\x1b[38;2;${r};${g};${b}m${stripped}${RESET}` }];
    });

    const grouped = new Map<string, MapLegendEntry>();
    const result: MapLegendEntry[] = [];
    for (const entry of colorized) {
        if (!entry.coords) {
            result.push(entry);
            continue;
        }
        const key = `${entry.coords[0]},${entry.coords[1]}`;
        const existing = grouped.get(key);
        if (!existing) {
            grouped.set(key, entry);
            result.push(entry);
            continue;
        }
        const descriptions = `${existing.desc}, ${entry.desc}`;
        existing.desc = descriptions;
        const firstColor = extractTrueColor(existing.symbol) ?? [190, 190, 190];
        const secondColor = extractTrueColor(entry.symbol) ?? [190, 190, 190];
        existing.symbol = `\x1b[38;2;${secondColor[0]};${secondColor[1]};${secondColor[2]}m\x1b[48;2;${firstColor[0]};${firstColor[1]};${firstColor[2]}m${stripAnsi(existing.symbol)}${RESET}`;
    }
    return result;
}

function calculateLegendWidths(entries: MapLegendEntry[], columns: number): number[] {
    const rows = Math.ceil(entries.length / columns);
    return Array.from({ length: columns }, (_, column) => {
        let width = 0;
        for (let row = 0; row < rows; row += 1) {
            const item = entries[column * rows + row];
            if (item) width = Math.max(width, visibleLength(`${item.symbol} = ${item.desc}`));
        }
        return width;
    });
}

function legendWidth(widths: number[], columns: number): number {
    return widths.reduce((total, width) => total + width, 0) + columns * 3 + 1;
}

function stylePlayerSymbol(symbol: string): string {
    if (extractTrueColor(symbol) || /\x1b\[[0-9;]+m/.test(symbol)) return withReset(symbol);
    return `\x1b[38;2;255;255;255m${symbol}${RESET}`;
}

function stripAnsi(value: string): string {
    return value.replace(ANSI, '');
}

function extractTrueColor(value: string): [number, number, number] | undefined {
    const match = value.match(/\x1b\[38;2;(\d+);(\d+);(\d+)m/);
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : undefined;
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
    if (s === 0) return [l, l, l].map((value) => Math.round(value * 255)) as [number, number, number];
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    const channel = (part: number) => {
        if (part < 0) part += 1;
        if (part > 1) part -= 1;
        if (part < 1 / 6) return p + (q - p) * 6 * part;
        if (part < 1 / 2) return q;
        if (part < 2 / 3) return p + (q - p) * (2 / 3 - part) * 6;
        return p;
    };
    return [channel(h + 1 / 3), channel(h), channel(h - 1 / 3)].map((value) => Math.round(value * 255)) as [number, number, number];
}

export function mergeBackgrounds(
    current: MapPayload['background'],
    next: Exclude<MapPayload['background'], undefined>,
): MapPayload['background'] {
    const entries = new Map<string, { color: [number, number, number]; coord: [number, number] }>();
    const existing = current ? Array.isArray(current) ? current : [current] : [];
    for (const item of existing) {
        for (const coord of item.coords) entries.set(`${coord[0]},${coord[1]}`, { color: item.color, coord });
    }
    const incoming = Array.isArray(next) ? next : [next];
    for (const item of incoming) {
        for (const coord of item.coords) entries.set(`${coord[0]},${coord[1]}`, { color: item.color, coord });
    }
    const groups: MapBackground[] = [];
    for (const { color, coord } of entries.values()) {
        const group = groups.find((candidate) => candidate.color.every((part, index) => part === color[index]));
        if (group) group.coords.push(coord);
        else groups.push({ color, coords: [coord] });
    }
    return groups.length === 1 ? groups[0] : groups;
}

export function parseBackground(value: unknown): MapPayload['background'] | undefined {
    const values = Array.isArray(value) ? value : [value];
    const backgrounds: MapBackground[] = [];
    for (const entry of values) {
        if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) continue;
        const data = entry as { color?: unknown; coords?: unknown };
        if (!Array.isArray(data.color) || data.color.length !== 3 || !data.color.every((part) => typeof part === 'number')) continue;
        if (!Array.isArray(data.coords)) continue;
        const coords = data.coords.filter((coord): coord is [number, number] => {
            return Array.isArray(coord) && coord.length === 2 && typeof coord[0] === 'number' && typeof coord[1] === 'number';
        });
        backgrounds.push({ color: [data.color[0], data.color[1], data.color[2]], coords });
    }
    return backgrounds.length === 1 ? backgrounds[0] : backgrounds.length > 1 ? backgrounds : undefined;
}

function relativePosition(position: [number, number], payload: MapPayload): [number, number] {
    return [position[0] - (payload.min_x ?? 0), (payload.max_y ?? 0) - position[1]];
}

function placeVisual(lines: string[], position: [number, number], value: string): void {
    const [x, y] = position;
    if (y < 0 || y >= lines.length || x < 0) return;
    const line = lines[y] ?? '';
    if (x >= visibleLength(line)) return;
    const start = visualRawIndex(line, x, true);
    const end = visualRawIndex(line, x + 1, false);
    lines[y] = `${line.slice(0, start)}${value}${line.slice(end)}`;
}

function ansiSubstring(value: string, start: number, end: number): string {
    const rawStart = visualRawIndex(value, start, true);
    const rawEnd = visualRawIndex(value, end, false);
    return rawStart < rawEnd ? `${ansiStateAt(value, rawStart)}${value.slice(rawStart, rawEnd)}${RESET}` : '';
}

function ansiStateAt(value: string, rawEnd: number): string {
    let state = '';
    for (const match of value.matchAll(ANSI)) {
        if ((match.index ?? 0) >= rawEnd) break;
        const code = match[0];
        state = code === RESET ? '' : `${state}${code}`;
    }
    return state;
}

function visualRawIndex(value: string, target: number, skipLeadingCodes: boolean): number {
    let visible = 0;
    let index = 0;
    while (index < value.length && visible < target) {
        if (value[index] === '\x1b') {
            index = ansiEnd(value, index);
        } else {
            visible += 1;
            index += 1;
        }
    }
    if (skipLeadingCodes) {
        while (index < value.length && value[index] === '\x1b') index = ansiEnd(value, index);
    }
    return index;
}

function ansiEnd(value: string, start: number): number {
    const match = value.slice(start).match(/^\x1b\[[0-?]*[ -/]*[@-~]/);
    return match ? start + match[0].length : value.length;
}

function visibleLength(value: string): number {
    return value.replace(ANSI, '').length;
}

function withReset(value: string): string {
    return value.endsWith(RESET) ? value : `${value}${RESET}`;
}

function clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(value, max));
}

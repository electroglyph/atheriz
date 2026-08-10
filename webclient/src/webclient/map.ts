import { MapPayload } from './types';

const ANSI = /\x1b\[[0-?]*[ -/]*[@-~]/g;
const RESET = '\x1b[0m';

export function renderMap(payload: MapPayload, columns: number, rows: number): string {
    let lines = payload.map.split(/\r?\n/);
    applyBackground(lines, payload);

    for (const entry of payload.legend ?? []) {
        if (entry.coords) placeVisual(lines, relativePosition(entry.coords, payload), withReset(entry.symbol));
    }
    if (payload.pos && payload.symbol) {
        placeVisual(lines, relativePosition(payload.pos, payload), withReset(payload.symbol));
    }

    const legend = payload.show_legend === false ? [] : buildLegend(payload);
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
        return ' '.repeat(Math.max(0, Math.floor((columns - visibleLength(sliced)) / 2))) + sliced;
    });

    if (legend.length > 0) visible.push('', ...legend);
    return visible.join('\r\n');
}

function applyBackground(lines: string[], payload: MapPayload): void {
    const background = payload.background;
    if (!background) return;
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

function buildLegend(payload: MapPayload): string[] {
    const entries = payload.legend ?? [];
    if (entries.length === 0 && !payload.symbol) return [];
    const title = payload.area ?? 'Legend';
    const values = payload.symbol ? [{ symbol: payload.symbol, desc: 'You' }, ...entries] : entries;
    return [`${title}:`, ...values.map((entry) => `${entry.symbol} = ${entry.desc}`)];
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
    return rawStart < rawEnd ? `${value.slice(rawStart, rawEnd)}${RESET}` : '';
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

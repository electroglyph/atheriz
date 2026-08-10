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

    const legend = payload.show_legend === false ? [] : buildLegend(payload, columns);
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

function buildLegend(payload: MapPayload, columns: number): string[] {
    const entries = payload.legend ?? [];
    if (entries.length === 0 && !payload.symbol) return [];
    const title = payload.area ?? 'Legend';
    const values = payload.symbol ? [{ symbol: payload.symbol, desc: 'You' }, ...entries] : entries;
    const cells = values.map((entry) => {
        const value = `${withReset(entry.symbol)} = ${entry.desc}`;
        return visibleLength(value) > columns ? ansiSubstring(value, 0, columns) : value;
    });
    const cellWidth = Math.max(1, ...cells.map(visibleLength));
    const columnCount = Math.max(1, Math.min(3, Math.floor(columns / Math.max(1, cellWidth + 2))));
    const rowCount = Math.ceil(cells.length / columnCount);
    const output = [title.length + 1 > columns ? `${title.slice(0, Math.max(0, columns - 1))}:` : `${title}:`];
    for (let row = 0; row < rowCount; row += 1) {
        const rowCells: string[] = [];
        for (let column = 0; column < columnCount; column += 1) {
            const cell = cells[row + column * rowCount];
            if (cell) rowCells.push(cell);
        }
        output.push(rowCells.join('  '));
    }
    return output;
}

export function mergeBackgrounds(
    current: MapPayload['background'],
    next: Exclude<MapPayload['background'], undefined>,
): MapPayload['background'] {
    const groups = current
        ? Array.isArray(current)
            ? current.map((item) => ({ color: item.color, coords: [...item.coords] }))
            : [{ color: current.color, coords: [...current.coords] }]
        : [];
    const incoming = Array.isArray(next) ? next : [next];
    for (const item of incoming) {
        const group = groups.find((candidate) => candidate.color.every((part, index) => part === item.color[index]));
        if (group) {
            for (const coord of item.coords) {
                if (!group.coords.some((existing) => existing[0] === coord[0] && existing[1] === coord[1])) group.coords.push(coord);
            }
        } else {
            groups.push({ color: item.color, coords: [...item.coords] });
        }
    }
    return groups.length === 1 ? groups[0] : groups;
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

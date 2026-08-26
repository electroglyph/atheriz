import { MapPayload } from './types';
import { parseBackground } from './map';

export function asString(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

export function asBoolean(value: unknown): boolean {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        return normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'on';
    }
    return false;
}

export function asPosition(value: unknown): [number, number] | undefined {
    return Array.isArray(value) && typeof value[0] === 'number' && typeof value[1] === 'number' ? [value[0], value[1]] : undefined;
}

export function asLegend(value: unknown): MapPayload['legend'] {
    if (!Array.isArray(value)) return [];
    return value.flatMap((entry) => {
        if (Array.isArray(entry) && typeof entry[0] === 'string') {
            const rawDesc = entry[1];
            const desc = typeof rawDesc === 'string' ? rawDesc : rawDesc == null ? '' : null;
            if (desc === null) return [];
            const coords = asPosition(entry[2]);
            return [{ symbol: entry[0], desc, coords }];
        }
        if (typeof entry === 'object' && entry !== null &&
            typeof (entry as { symbol?: unknown }).symbol === 'string') {
            const raw = entry as { symbol: string; desc?: unknown; coords?: unknown };
            const rawDesc = raw.desc;
            let desc: string | null;
            if (typeof rawDesc === 'string') desc = rawDesc;
            else if (rawDesc == null) desc = '';
            else return [];
            return [{ symbol: raw.symbol, desc, coords: asPosition(raw.coords) }];
        }
        return [];
    });
}

export function normalizeShowLegend(value: unknown): boolean {
    if (value === undefined) return true;
    if (value === false || value === 0 || value === '' || value === null) return false;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (normalized === 'false' || normalized === '0' || normalized === 'no' || normalized === 'off') return false;
        if (normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'on') return true;
        return normalized.length > 0;
    }
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'boolean') return value;
    return Boolean(value);
}

export function asMapPayload(value: unknown): MapPayload {
    if (typeof value !== 'object' || value === null) return { map: '' };
    const data = value as Partial<MapPayload>;
    return {
        map: typeof data.map === 'string' ? data.map : '',
        pos: asPosition(data.pos),
        symbol: typeof data.symbol === 'string' ? data.symbol : undefined,
        legend: asLegend(data.legend),
        min_x: typeof data.min_x === 'number' ? data.min_x : 0,
        max_y: typeof data.max_y === 'number' ? data.max_y : 0,
        area: typeof data.area === 'string' ? data.area : undefined,
        show_legend: normalizeShowLegend(data.show_legend),
        background: parseBackground(data.background),
    };
}

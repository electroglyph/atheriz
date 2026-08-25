import { describe, expect, it } from 'vitest';
import { renderMap } from '../src/webclient/map';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('map pane zero size handling', () => {
    it('returns empty string when columns or rows are zero', () => {
        const payload = { map: 'ab\ncd', max_y: 1 } as unknown as Parameters<typeof renderMap>[0];
        expect(renderMap(payload, 0, 10)).toBe('');
        expect(renderMap(payload, 10, 0)).toBe('');
        expect(renderMap(payload, 0, 0)).toBe('');
        expect(renderMap(payload, -1, 10)).toBe('');
        expect(renderMap(payload, 10, -1)).toBe('');
    });

    it('renders normally when dimensions are valid', () => {
        const payload = { map: 'ab\ncd', max_y: 1 } as unknown as Parameters<typeof renderMap>[0];
        const out = renderMap(payload, 10, 5);
        expect(out).toContain('\x1b[');
        expect(out.length).toBeGreaterThan(0);
    });
});

describe('map centering around player', () => {
    it('centers small map in larger pane', () => {
        const payload = {
            map: ['#####', '#...#', '#.@.#', '#...#', '#####'].join('\n'),
            max_y: 4,
            pos: [2, 2] as [number, number],
            symbol: '@',
            show_legend: false,
        } as unknown as Parameters<typeof renderMap>[0];
        const output = renderMap(payload, 20, 10);
        const rows = [...output.matchAll(/\x1b\[(\d+);(\d+)H/g)].map((m) => Number(m[1]));
        const cols = [...output.matchAll(/\x1b\[(\d+);(\d+)H/g)].map((m) => Number(m[2]));
        expect(Math.min(...rows)).toBeGreaterThan(1);
        expect(Math.min(...cols)).toBeGreaterThan(1);
        const expectedRow = Math.floor((10 - 5) / 2) + 1;
        expect(Math.min(...rows)).toBe(expectedRow);
    });

    it('crops large map around player position', () => {
        const map = Array.from({ length: 20 }, (_, y) => Array.from({ length: 20 }, (_, x) => (x === 10 && y === 10 ? '@' : '.')).join('')).join('\n');
        const payload = {
            map,
            max_y: 19,
            pos: [10, 10] as [number, number],
            symbol: '@',
            show_legend: false,
        } as unknown as Parameters<typeof renderMap>[0];
        const output = renderMap(payload, 10, 10);
        expect(output).toContain('@');
        const visibleRows = [...output.matchAll(/\x1b\[\d+;\d+H([^\x1b]*)/g)].map((m) => m[1]);
        expect(visibleRows.length).toBe(10);
    });

    it('falls back to top-left when player position is missing', () => {
        const payload = {
            map: 'abc\ndef\nghi',
            max_y: 2,
            show_legend: false,
        } as unknown as Parameters<typeof renderMap>[0];
        const output = renderMap(payload, 10, 10);
        expect(output).toContain('abc');
        const rows = [...output.matchAll(/\x1b\[(\d+);\d+H/g)].map((m) => Number(m[1]));
        expect(Math.min(...rows)).toBeGreaterThanOrEqual(1);
    });

    it('keeps legend inside pane and clamps legend row', () => {
        const legend = Array.from({ length: 5 }, (_, i) => ({ symbol: 'x', desc: `Exit ${i}` }));
        const payload = { map: 'ab\ncd\nef\ngh', max_y: 3, legend } as unknown as Parameters<typeof renderMap>[0];
        const output = renderMap(payload, 20, 6);
        const rows = [...output.matchAll(/\x1b\[(\d+);\d+H/g)].map((m) => Number(m[1]));
        expect(Math.max(...rows)).toBeLessThanOrEqual(6);
    });
});

describe('map client integration for first draw', () => {
    it('defers rendering when pane has no size', () => {
        const mapPath = path.resolve(import.meta.dirname, '../src/webclient/map.ts');
        const mapContent = fs.readFileSync(mapPath, 'utf-8');
        expect(mapContent).toContain('if (columns <= 0 || rows <= 0) return');
    });

    it('schedules fitting on map pane visibility and defers first map until sized', () => {
        const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
        const content = fs.readFileSync(mainPath, 'utf-8');
        expect(content).toContain('requestAnimationFrame(() => fitAndReportSize())');
        expect(content).toContain('right.cols <= 0 || right.rows <= 0');
        expect(content).toContain("fonts.status !== 'loaded'");
        expect(content).toContain('if (mapEnabled && mapPayload) renderMap()');
    });

    it('does not refit on every text message', () => {
        const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
        const content = fs.readFileSync(mainPath, 'utf-8');
        const textCase = content.match(/case 'text':[\s\S]*?break;/);
        expect(textCase).not.toBeNull();
        expect(textCase![0]).not.toContain('fitAndReportSize');
        expect(textCase![0]).not.toContain('requestAnimationFrame');
    });
});

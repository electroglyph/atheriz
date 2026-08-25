import { describe, expect, it } from 'vitest';
import { mergeBackgrounds, parseBackground, renderMap } from '../src/webclient/map';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('map background parsing', () => {
    it('rejects entries with no valid coordinates', () => {
        expect(parseBackground({ color: [1, 2, 3], coords: [] })).toBeUndefined();
        expect(parseBackground({ color: [10, 20, 30], coords: [[0, 0], ['a', 'b']] })).toEqual({ color: [10, 20, 30], coords: [[0, 0]] });
        expect(parseBackground({ color: [1, 2, 3], coords: [[0, 0]] })).toEqual({ color: [1, 2, 3], coords: [[0, 0]] });
        expect(parseBackground([{ color: [1, 2, 3], coords: [] }, { color: [4, 5, 6], coords: [[1, 0]] }])).toEqual({ color: [4, 5, 6], coords: [[1, 0]] });
    });

    it('rejects invalid or out-of-range colors', () => {
        expect(parseBackground({ color: [300, 0, 0], coords: [[0, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [-1, 0, 0], coords: [[0, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [NaN, 0, 0], coords: [[0, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [1, 2, 3, 4], coords: [[0, 0]] })).toBeUndefined();
        expect(parseBackground({ color: 'red' as unknown as number[], coords: [[0, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [1, 2, 3], coords: [[0, 0]] })).toEqual({ color: [1, 2, 3], coords: [[0, 0]] });
    });

    it('filters non-finite coordinates', () => {
        expect(parseBackground({ color: [1, 2, 3], coords: [[NaN, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [1, 2, 3], coords: [[Infinity, 0]] })).toBeUndefined();
        expect(parseBackground({ color: [1, 2, 3], coords: [[0, 0], [NaN, 1]] })).toEqual({ color: [1, 2, 3], coords: [[0, 0]] });
    });

    it('handles single and array payloads consistently', () => {
        expect(parseBackground({ color: [1, 2, 3], coords: [[0, 0]] })).toEqual({ color: [1, 2, 3], coords: [[0, 0]] });
        expect(parseBackground([{ color: [1, 2, 3], coords: [[0, 0]] }])).toEqual({ color: [1, 2, 3], coords: [[0, 0]] });
        expect(parseBackground([])).toBeUndefined();
        expect(parseBackground(null as unknown as object)).toBeUndefined();
    });
});

describe('map background merging', () => {
    it('groups by color deterministically', () => {
        const a = { color: [1, 2, 3] as [number, number, number], coords: [[0, 0]] as [number, number][] };
        const b = { color: [4, 5, 6] as [number, number, number], coords: [[1, 0]] as [number, number][] };
        const c = { color: [1, 2, 3] as [number, number, number], coords: [[2, 0]] as [number, number][] };
        const merged = mergeBackgrounds([a, b], c);
        expect(Array.isArray(merged)).toBe(true);
        if (Array.isArray(merged)) {
            expect(merged).toHaveLength(2);
            const first = merged.find((g) => g.color[0] === 1);
            const second = merged.find((g) => g.color[0] === 4);
            expect(first?.coords).toEqual(expect.arrayContaining([[0, 0], [2, 0]]));
            expect(second?.coords).toEqual([[1, 0]]);
            expect(merged[0].color).toEqual([1, 2, 3]);
        }
    });

    it('deduplicates per-coordinate with last write wins', () => {
        const merged = mergeBackgrounds(
            { color: [1, 2, 3], coords: [[0, 0]] },
            { color: [9, 9, 9], coords: [[0, 0]] },
        );
        expect(merged).toEqual({ color: [9, 9, 9], coords: [[0, 0]] });
    });

    it('merges arrays and single entries', () => {
        const merged = mergeBackgrounds(
            { color: [1, 2, 3], coords: [[0, 0]] },
            [{ color: [1, 2, 3], coords: [[1, 0]] }, { color: [2, 2, 2], coords: [[2, 0]] }],
        );
        expect(Array.isArray(merged)).toBe(true);
    });
});

describe('map legend sizing and placement', () => {
    it('limits legend height on small terminals', () => {
        const legend = Array.from({ length: 30 }, (_, i) => ({ symbol: String.fromCharCode(97 + (i % 26)), desc: `Exit ${i}` }));
        const output = renderMap({ map: 'ab', max_y: 0, legend } as unknown as Parameters<typeof renderMap>[0], 40, 10);
        const rowNumbers = [...output.matchAll(/\x1b\[(\d+);\d+H/g)].map((m) => Number(m[1]));
        expect(Math.max(...rowNumbers)).toBeLessThanOrEqual(10);
        const legendLines = output.split(/\x1b\[\d+;\d+H/).filter((l) => l.includes('╭') || l.includes('│') || l.includes('╰'));
        const availableHeight = Math.max(5, Math.floor(10 / 3));
        expect(legendLines.length).toBeLessThanOrEqual(availableHeight);
    });

    it('keeps legend inside terminal width', () => {
        const legend = Array.from({ length: 14 }, (_, i) => ({ symbol: String.fromCharCode(97 + i), desc: `A dusty trail leading ${['north', 'south', 'east', 'west'][i % 4]}ward` }));
        const output = renderMap(
            { map: Array.from({ length: 27 }, () => '#'.repeat(62)).join('\n'), max_y: 26, pos: [31, 13], symbol: '@', area: 'The Western Reaches of Eldermoor', legend } as unknown as Parameters<typeof renderMap>[0],
            62, 28,
        );
        const lines = output.split(/\x1b\[\d+;\d+H/).map((l) => l.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, ''));
        const maxLine = Math.max(...lines.map((l) => l.length));
        expect(maxLine).toBeLessThanOrEqual(62);
    });

    it('clamps legend start row to stay visible', () => {
        const legend = Array.from({ length: 5 }, (_, i) => ({ symbol: 'x', desc: `Exit ${i}` }));
        const output = renderMap({ map: 'ab\ncd\nef\ngh', max_y: 3, legend } as unknown as Parameters<typeof renderMap>[0], 20, 6);
        const rows = [...output.matchAll(/\x1b\[(\d+);\d+H/g)].map((m) => Number(m[1]));
        expect(Math.max(...rows)).toBeLessThanOrEqual(6);
        expect(Math.min(...rows)).toBeGreaterThanOrEqual(1);
    });

    it('truncates legend entries when height would overflow', () => {
        const many = Array.from({ length: 50 }, (_, i) => ({ symbol: 'x', desc: `Desc ${i}` }));
        const small = renderMap({ map: 'ab', max_y: 0, legend: many } as unknown as Parameters<typeof renderMap>[0], 20, 10);
        const large = renderMap({ map: 'ab', max_y: 0, legend: many } as unknown as Parameters<typeof renderMap>[0], 20, 30);
        const smallLegendCount = small.split('│').length;
        const largeLegendCount = large.split('│').length;
        expect(smallLegendCount).toBeLessThan(largeLegendCount);
    });
});

describe('map legend duplicate handling', () => {
    it('assigns distinct colors to many duplicates without early collision', () => {
        const dup = Array.from({ length: 10 }, () => ({ symbol: 'x', desc: 'Door' }));
        const output = renderMap({ map: 'x', max_y: 0, legend: dup } as unknown as Parameters<typeof renderMap>[0], 60, 20);
        const colors = [...output.matchAll(/\x1b\[38;2;(\d+);(\d+);(\d+)m/g)].map((m) => m[0]);
        const unique = new Set(colors);
        expect(unique.size).toBeGreaterThanOrEqual(2);
        const early = colors.slice(0, 7);
        expect(new Set(early).size).toBe(early.length);
    });

    it('uses golden-angle increment for hue distribution', () => {
        const file = fs.readFileSync(path.resolve(import.meta.dirname, '../src/webclient/map.ts'), 'utf-8');
        expect(file).toContain('(hue + 137) % 360');
        expect(file).not.toContain('(hue + 57) % 360');
    });

    it('combines same-coordinate entries with counts', () => {
        const output = renderMap(
            { map: 'x', max_y: 0, legend: [{ symbol: 'x', desc: 'Door', coords: [0, 0] }, { symbol: 'x', desc: 'Door', coords: [0, 0] }] } as unknown as Parameters<typeof renderMap>[0],
            30, 12,
        );
        expect(output).toContain('Door (2)');
    });
});

describe('map background and wide character handling', () => {
    it('renders background at correct visual column for astral symbols', () => {
        const output = renderMap(
            { map: 'ab🯅cd', max_y: 0, background: { color: [10, 20, 30], coords: [[2, 0]] } as unknown as Parameters<typeof renderMap>[0]['background'], show_legend: false } as unknown as Parameters<typeof renderMap>[0],
            20, 5,
        );
        expect(output).toContain('\x1b[48;2;10;20;30m');
    });

    it('keeps astral symbols rectangular in legend', () => {
        const output = renderMap(
            { map: '#'.repeat(30) + '\n' + '#'.repeat(30), max_y: 1, pos: [1, 1], symbol: '🯅', area: 'Town', legend: [{ symbol: '𜸂', desc: 'shrine of light' }, { symbol: '󿀎', desc: 'shadow guild' }] } as unknown as Parameters<typeof renderMap>[0],
            40, 12,
        );
        const lines = output.split(/\x1b\[\d+;\d+H/).map((l) => l.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, ''));
        const legendLines = lines.filter((l) => l.includes('╭') || l.includes('│') || l.includes('╰'));
        const widths = [...new Set(legendLines.map((l) => [...l.trimEnd()].length))];
        expect(widths).toHaveLength(1);
    });

    it('places player correctly after astral symbols', () => {
        const output = renderMap({ map: 'ab🯅cd', max_y: 0, pos: [3, 0], symbol: '@', show_legend: false } as unknown as Parameters<typeof renderMap>[0], 20, 5);
        expect(output).toContain('🯅\x1b[38;2;255;255;255m@');
    });

    it('ignores empty background payloads', () => {
        const output = renderMap({ map: 'ab', max_y: 0, background: { color: [1, 2, 3], coords: [] } as unknown as Parameters<typeof renderMap>[0]['background'], show_legend: false } as unknown as Parameters<typeof renderMap>[0], 10, 4);
        expect(output).not.toContain('\x1b[48;2;1;2;3m');
    });
});

import { describe, expect, it } from 'vitest';
import { asLegend, asMapPayload } from '../src/webclient/payload';
import { renderMap } from '../src/webclient/map';

describe('asLegend tolerates missing/empty descriptions', () => {
    it('keeps an object entry where desc is null by coercing to empty string', () => {
        expect(asLegend([{ symbol: 'X', desc: null }])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
        expect(asLegend([{ symbol: 'X', desc: '' }])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
        expect(asLegend([{ symbol: 'X' }])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
    });

    it('keeps an array entry where desc is null by coercing to empty string', () => {
        expect(asLegend([['X', null]])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
        expect(asLegend([['X', '']])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
        expect(asLegend([['X']])).toEqual([
            { symbol: 'X', desc: '', coords: undefined },
        ]);
    });

    it('drops entries where desc is a non-string non-null type', () => {
        expect(asLegend([{ symbol: 'X', desc: 123 as unknown as string }])).toEqual([]);
        expect(asLegend([['X', 123 as unknown as string]])).toEqual([]);
        expect(asLegend([{ symbol: 'X', desc: {} as unknown as string }])).toEqual([]);
    });

    it('preserves a valid string desc and coords in both object and array forms', () => {
        expect(asLegend([{ symbol: 'A', desc: 'shrine', coords: [1, 2] }])).toEqual([
            { symbol: 'A', desc: 'shrine', coords: [1, 2] },
        ]);
        expect(asLegend([['A', 'shrine', [1, 2]]])).toEqual([
            { symbol: 'A', desc: 'shrine', coords: [1, 2] },
        ]);
    });

    it('drops entries missing symbol and ignores non-array non-object input', () => {
        expect(asLegend([{ desc: 'no symbol' } as unknown as { symbol: string; desc: string }])).toEqual([]);
        expect(asLegend([{ symbol: '', desc: 'empty symbol ok?' }])).toEqual([
            { symbol: '', desc: 'empty symbol ok?', coords: undefined },
        ]);
        expect(asLegend(null as unknown as unknown[])).toEqual([]);
        expect(asLegend('not an array' as unknown as unknown[])).toEqual([]);
    });

    it('normalizes coords via asPosition and drops malformed coords', () => {
        expect(asLegend([{ symbol: 'X', desc: 'd', coords: [1] as unknown as [number, number] }])).toEqual([
            { symbol: 'X', desc: 'd', coords: undefined },
        ]);
        expect(asLegend([['X', 'd', [1, 2]]])).toEqual([
            { symbol: 'X', desc: 'd', coords: [1, 2] },
        ]);
        expect(asLegend([['X', 'd', 'bad' as unknown as [number, number]]])).toEqual([
            { symbol: 'X', desc: 'd', coords: undefined },
        ]);
    });

    it('asMapPayload forwards the normalized legend', () => {
        const payload = asMapPayload({ map: 'ab', legend: [{ symbol: 'X', desc: null as unknown as string }] });
        expect(payload.legend).toEqual([{ symbol: 'X', desc: '', coords: undefined }]);
        expect(asMapPayload({ map: 'ab', legend: 'nope' as unknown as [] }).legend).toEqual([]);
    });

    it('renderMap still shows a legend box when desc is empty (not dropped)', () => {
        const output = renderMap(
            { map: 'x', max_y: 0, legend: [{ symbol: 'X', desc: '' }] } as unknown as Parameters<typeof renderMap>[0],
            20, 10
        );
        // Box is still drawn even though desc is empty – verifies the entry was not filtered away.
        expect(output).toContain('╭');
        expect(output).toContain('│');
        expect(output).toContain('X');
    });
});

import { describe, expect, it } from 'vitest';
import { MAP_CLEAR_SEQUENCE, mergeBackgrounds, parseBackground, renderMap } from '../src/webclient/map';

describe('webclient map renderer', () => {
    it('renders the map, player, and legend in the map pane', () => {
        const output = renderMap({
            map: 'abc\ndef',
            min_x: 0,
            max_y: 1,
            pos: [1, 1],
            symbol: '@',
            area: 'Room',
            legend: [{ symbol: 'x', desc: 'Exit' }],
        }, 20, 10);

        expect(output).toContain('a@');
        expect(output).toContain('c');
        expect(output).toContain('Room');
        expect(output).toContain('╭');
        expect(output).toContain('x');
        expect(output).toContain('Exit');
        expect(output).toContain('\x1b[');
    });

    it('crops a large map around the player without dropping ANSI state', () => {
        const output = renderMap({
            map: '\x1b[31m0123456789\x1b[0m',
            min_x: 0,
            max_y: 0,
            pos: [8, 0],
            symbol: '@',
        }, 5, 3);

        expect(output).toContain('@');
        expect(output).toContain('\x1b[0m');
    });

    it('accumulates background updates with the same color', () => {
        const merged = mergeBackgrounds(
            { color: [1, 2, 3], coords: [[0, 0]] },
            { color: [1, 2, 3], coords: [[1, 0]] },
        );
        expect(merged).toEqual({ color: [1, 2, 3], coords: [[0, 0], [1, 0]] });
    });

    it('replaces the color at a coordinate when it is updated', () => {
        const merged = mergeBackgrounds(
            { color: [1, 2, 3], coords: [[0, 0]] },
            { color: [4, 5, 6], coords: [[0, 0]] },
        );
        expect(merged).toEqual({ color: [4, 5, 6], coords: [[0, 0]] });
    });

    it('exposes the legacy map clear sequence for recording', () => {
        expect(MAP_CLEAR_SEQUENCE).toBe('\x1b[2J\x1b[3J\x1b[H');
    });

    it('parses both single and array background payloads', () => {
        expect(parseBackground([
            { color: [1, 2, 3], coords: [[0, 0]] },
            { color: [4, 5, 6], coords: [[1, 0]] },
        ])).toEqual([
            { color: [1, 2, 3], coords: [[0, 0]] },
            { color: [4, 5, 6], coords: [[1, 0]] },
        ]);
    });

    it('renders accumulated backgrounds with distinct colors', () => {
        const output = renderMap({
            map: 'ab',
            max_y: 0,
            background: [
                { color: [1, 2, 3], coords: [[0, 0]] },
                { color: [4, 5, 6], coords: [[1, 0]] },
            ],
        }, 10, 4);
        expect(output).toContain('\x1b[48;2;1;2;3m');
        expect(output).toContain('\x1b[48;2;4;5;6m');
    });

    it('renders map rows with cursor positioning and bounds legend width', () => {
        const output = renderMap({
            map: 'abc\ndef',
            max_y: 1,
            legend: [
                { symbol: 'x', desc: 'A very long description' },
                { symbol: 'y', desc: 'Exit' },
            ],
        }, 12, 8);
        expect(output).toMatch(/\x1b\[\d+;\d+H/);
        expect(output.split('\r\n')).toHaveLength(1);
    });

    it('recolors duplicate legend symbols and combines same-coordinate descriptions', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'x', desc: 'Exit', coords: [0, 0] },
            ],
        }, 30, 12);
        expect(output).toContain('Door, Exit');
        expect(output).toContain('\x1b[48;2;');
    });
});

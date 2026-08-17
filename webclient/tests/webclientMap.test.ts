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

        expect(output).toContain('d\x1b[38;2;255;255;255m@');
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

    it('keeps every legend line inside the terminal width with a rectangular box', () => {
        const output = renderMap({
            map: Array.from({ length: 27 }, () => '#'.repeat(62)).join('\n'),
            max_y: 26,
            pos: [31, 13],
            symbol: '@',
            area: 'The Western Reaches of Eldermoor',
            legend: Array.from({ length: 14 }, (_, index) => ({
                symbol: String.fromCharCode(97 + index),
                desc: `A dusty trail leading ${['north', 'south', 'east', 'west'][index % 4]}ward`,
            })),
        }, 62, 28);
        const lines = output.split(/\x1b\[\d+;\d+H/).map((line) => line.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, ''));
        const maxLine = Math.max(...lines.map((line) => line.length));
        expect(maxLine).toBeLessThanOrEqual(62);
        const legendLines = lines.filter((line) => line.includes('╭') || line.includes('│') || line.includes('╰'));
        const widths = [...new Set(legendLines.map((line) => line.trimEnd().length))];
        expect(widths).toHaveLength(1);
        const rowNumbers = [...output.matchAll(/\x1b\[(\d+);\d+H/g)].map((match) => Number(match[1]));
        expect(Math.max(...rowNumbers)).toBeLessThanOrEqual(28);
    });

    it('treats the player position as already relative to the map string', () => {
        const output = renderMap({
            map: 'abc\ndef\nghi',
            pos: [1, 2],
            symbol: '@',
            min_x: 10,
            max_y: 20,
            show_legend: false,
        }, 20, 10);
        expect(output).toContain('g\x1b[38;2;255;255;255m@');
        expect(output).toContain('i');
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

    it('counts duplicate descriptions at the same coordinate', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
            ],
        }, 30, 12);
        expect(output).toContain('Door (2)');
        expect(output).not.toContain('Door, Door');
    });

    it('counts only the duplicate descriptions in a combined legend entry', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'x', desc: 'Exit', coords: [0, 0] },
            ],
        }, 30, 12);
        expect(output).toContain('Door (2), Exit');
    });

    it('truncates a combined legend description at half the terminal width', () => {
        const longDesc = 'The quick brown fox jumps over the lazy dog';
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'x', desc: longDesc, coords: [0, 0] },
                { symbol: 'x', desc: longDesc, coords: [0, 0] },
                { symbol: 'x', desc: 'Backdoor', coords: [0, 0] },
            ],
        }, 100, 12);
        expect(output).toContain(`${longDesc} (2)...`);
        expect(output).not.toContain('Backdoor');
    });

    it('places grouped legend entries before entries without coordinates', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'z', desc: 'Exit' },
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'p', desc: 'Portal' },
            ],
        }, 30, 12);
        expect(output.indexOf('Door (2)')).toBeGreaterThan(-1);
        expect(output.indexOf('Door (2)')).toBeLessThan(output.indexOf('Exit'));
        expect(output.indexOf('Exit')).toBeLessThan(output.indexOf('Portal'));
    });

    it('keeps the first two entry colors when merging three duplicates', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: '\x1b[38;2;255;0;0mX\x1b[0m', desc: 'Door', coords: [0, 0] },
                { symbol: '\x1b[38;2;0;255;0mX\x1b[0m', desc: 'Door', coords: [0, 0] },
                { symbol: '\x1b[38;2;0;0;255mX\x1b[0m', desc: 'Door', coords: [0, 0] },
            ],
        }, 30, 12);
        expect(output).toContain('Door (3)');
        expect(output).toContain('\x1b[48;2;255;0;0m');
        expect(output).not.toContain('\x1b[38;2;0;0;255m');
    });

    it('uses the legacy dark blue background for uncolored merged symbols', () => {
        const output = renderMap({
            map: 'x',
            max_y: 0,
            legend: [
                { symbol: 'x', desc: 'Door', coords: [0, 0] },
                { symbol: 'y', desc: 'Exit', coords: [0, 0] },
            ],
        }, 30, 12);
        expect(output).toContain('\x1b[48;2;30;60;120m');
        expect(output).toContain('\x1b[38;2;190;190;190m\x1b[48;2;30;60;120m');
    });

    it('truncates a legend entry wider than the terminal', () => {
        const output = renderMap({
            map: 'x',
            legend: [{ symbol: 'x', desc: 'This description is much too long' }],
        }, 12, 10);
        expect(output).not.toContain('This description is much too long');
    });
});

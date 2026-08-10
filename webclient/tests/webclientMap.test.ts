import { describe, expect, it } from 'vitest';
import { renderMap } from '../src/webclient/map';

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
        expect(output).toContain('Room:');
        expect(output).toContain('x = Exit');
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
});

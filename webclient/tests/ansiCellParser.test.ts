import { describe, expect, it } from 'vitest';
import { parseAnsiSymbol } from '../src/utils/ansiParser';

describe('parseAnsiSymbol', () => {
    it('parses exact truecolor fg and treats the engine black bg as transparent', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;0;0;0m\x1b[38;2;255;0;0mX\x1b[0m');
        expect(cell.char).toBe('X');
        expect(cell.fg).toEqual([255, 0, 0]);
        expect(cell.bg).toEqual([-1, -1, -1]);
    });

    it('keeps a real background color', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;10;20;30m\x1b[38;2;255;255;255m#\x1b[0m');
        expect(cell.bg).toEqual([10, 20, 30]);
        expect(cell.fg).toEqual([255, 255, 255]);
        expect(cell.char).toBe('#');
    });

    it('maps 256-color fg through ansi256ToRgb', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;0;0;0m\x1b[38;5;9mQ\x1b[0m');
        expect(cell.fg).toEqual([255, 0, 0]);
    });

    it('sets style flags', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;0;0;0m\x1b[38;2;0;255;0m\x1b[1m\x1b[3m\x1b[4mS\x1b[0m');
        expect(cell.bold).toBe(true);
        expect(cell.italic).toBe(true);
        expect(cell.underline).toBe(true);
        expect(cell.char).toBe('S');
    });

    it('ignores inverse and strikethrough', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;0;0;0m\x1b[38;2;0;0;255m\x1b[7m\x1b[9mR\x1b[0m');
        expect(cell.fg).toEqual([0, 0, 255]);
        expect(cell.char).toBe('R');
    });

    it('returns defaults for a plain symbol', () => {
        const cell = parseAnsiSymbol('W');
        expect(cell.char).toBe('W');
        expect(cell.fg).toEqual([204, 204, 204]);
        expect(cell.bg).toEqual([-1, -1, -1]);
        expect(cell.bold).toBeUndefined();
    });

    it('strips all escape sequences from the char', () => {
        const cell = parseAnsiSymbol('\x1b[48;2;1;2;3m\x1b[38;2;4;5;6m\x1b[1mY\x1b[22m\x1b[0m');
        expect(cell.char).toBe('Y');
        expect(cell.bold).toBe(true);
    });
});
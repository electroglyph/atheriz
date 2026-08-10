import { describe, expect, it } from 'vitest';
import {
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_RESET,
    formatPrompt,
    formatTextOutput,
    normalizeServerText,
    wrapText,
} from '../src/webclient/text';

describe('webclient text rendering', () => {
    it('applies the legacy gray default to plain text', () => {
        expect(normalizeServerText('hello', 80, false)).toBe(`${DEFAULT_TEXT_COLOR}hello`);
    });

    it('preserves explicit colors and restores gray after reset or white', () => {
        const red = '\x1b[38;2;255;0;0m';
        expect(normalizeServerText(`${red}red\x1b[0m white\x1b[37mwhite`, 80, false)).toBe(
            `${red}red${DEFAULT_TEXT_RESET} white${DEFAULT_TEXT_COLOR}white`,
        );
    });

    it('does not inject color in screen-reader mode', () => {
        expect(normalizeServerText('plain', 80, true)).toBe('plain');
    });

    it('wraps visible text without counting ANSI sequences', () => {
        const red = '\x1b[31m';
        expect(wrapText(`${red}one two`, 5)).toContain(`${red}one \x1b[0m\n${red}two`);
    });

    it('clears the old prompt and restores terminal state', () => {
        expect(formatTextOutput('hello', 80, false, '> ', true)).toBe(
            `\r  \r\x1b[0m${DEFAULT_TEXT_COLOR}hello\x1b[0m> `,
        );
        expect(formatPrompt('new> ', 'old> ', true)).toBe('\r     \r\x1b[0mnew> \x1b[0m');
    });
});

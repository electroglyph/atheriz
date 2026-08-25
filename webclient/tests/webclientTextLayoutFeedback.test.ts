import { describe, expect, it } from 'vitest';
import { BUFFER_FINAL_SEQUENCE } from '../src/webclient/buffer';
import { settingFeedback, screenReaderFeedback } from '../src/webclient/feedback';
import { mapLayout, recordingDividerPct, resizeWidth } from '../src/webclient/layout';
import { DEFAULT_TEXT_COLOR, normalizeServerText, wrapText } from '../src/webclient/text';

describe('text wrapping with newlines and ANSI', () => {
    it('preserves hard newlines and resets line length after each', () => {
        const input = 'aa bb\ncc dd';
        const out = wrapText(input, 5);
        expect(out).toBe('aa bb\ncc dd');
        const tight = wrapText('12345 67890\nabc', 5);
        expect(tight).toContain('abc');
        expect(tight.split('\n').pop()).toBe('abc');
    });

    it('handles multiple consecutive newlines', () => {
        expect(wrapText('a\n\nb', 10)).toBe('a\n\nb');
        expect(wrapText('a \n \n b', 10)).toContain('\n');
        expect(wrapText('x\n\n\n y', 10).split('\n')).toHaveLength(4);
    });

    it('counts surrogate pairs as single visible cells', () => {
        const surrogate = '𜰵';
        expect(surrogate.length).toBe(2);
        expect([...surrogate].length).toBe(1);
        expect(wrapText(`${surrogate} ${surrogate}`, 3)).toBe(`${surrogate} ${surrogate}`);
        expect(wrapText(`${surrogate} ${surrogate}`, 2)).toContain('\n');
        expect(wrapText(`a${surrogate}b c`, 5)).not.toContain('\n');
        expect(wrapText(`a${surrogate}b c`, 4)).toContain('\n');
        const tight = wrapText(`${surrogate} ${surrogate} ${surrogate}`, 3);
        expect(tight.split('\n')).toHaveLength(2);
        expect(tight).toContain(`${surrogate} ${surrogate}\x1b[0m\n${surrogate}`);
        const afterNewline = wrapText(`hi\n${surrogate} ${surrogate}`, 3);
        expect(afterNewline).toContain(`${surrogate} ${surrogate}`);
    });

    it('does not count ANSI sequences toward visible length', () => {
        const red = '\x1b[31m';
        const reset = '\x1b[0m';
        expect(wrapText(`${red}one two`, 5)).toContain(`${red}one ${reset}\n${red}two`);
        expect(wrapText(`${red}hello world`, 5)).toContain(`${reset}\n${red}world`);
        const longAnsi = `${red}one${reset} ${red}two`;
        expect(wrapText(longAnsi, 5)).toContain(`${reset}\n`);
    });

    it('whitespace wrap preserves ANSI color via nextColor', () => {
        const red = '\x1b[31m';
        const reset = '\x1b[0m';
        const out = wrapText(`${red}aaa bbb`, 5);
        expect(out).toContain(`${red}aaa`);
        expect(out).toContain(`${reset}\n${red}bbb`);
        const out2 = wrapText(`hello ${red}world`, 5);
        expect(out2).toContain(`${reset}\n`);
    });

    it('handles 200-char whitespace with embedded newline without bypassing width', () => {
        const spaces200 = ' '.repeat(200);
        const input = `hi${spaces200}\nworld`;
        const out = wrapText(input, 10);
        expect(out).toContain('\n');
        expect(out.split('\n').length).toBeGreaterThanOrEqual(2);
    });

    it('returns original text when width <=0', () => {
        expect(wrapText('hello world', 0)).toBe('hello world');
        expect(wrapText('hello world', -1)).toBe('hello world');
        expect(wrapText('', 10)).toBe('');
    });

    it('handles ANSI inside newline-containing whitespace token', () => {
        const red = '\x1b[31m';
        const input = `a${red}   \n   b`;
        const out = wrapText(input, 5);
        expect(out).toContain('\n');
        expect(out).toContain('a');
        expect(out).toContain('b');
    });
});

describe('server text normalization', () => {
    it('normalizeServerText maps all white variants to default gray', () => {
        for (const code of ['\x1b[37m', '\x1b[97m', '\x1b[90m']) {
            const normalized = normalizeServerText(`${code}text`, 80, false);
            expect(normalized).not.toContain(code);
            expect(normalized).toContain(DEFAULT_TEXT_COLOR);
        }
        const combined = `\x1b[38;2;255;0;0mred\x1b[0m white\x1b[37mwhite2\x1b[97mbright\x1b[90mgray`;
        const out = normalizeServerText(combined, 80, false);
        expect(out).toContain('\x1b[38;2;255;0;0m');
        expect(out).not.toContain('\x1b[37m');
        expect(out).not.toContain('\x1b[97m');
        expect(out).not.toContain('\x1b[90m');
    });

    it('normalizeServerText does not inject color in screenReader mode', () => {
        expect(normalizeServerText('plain', 80, true)).toBe('plain');
        expect(normalizeServerText('\x1b[31mred', 80, true)).toBe('\x1b[31mred');
    });
});

describe('buffer final sequence', () => {
    it('BUFFER_FINAL_SEQUENCE resets, shows cursor, and ends buffer', () => {
        expect(BUFFER_FINAL_SEQUENCE).toBe('\x1b[0m\x1b[?25h\n');
        expect(BUFFER_FINAL_SEQUENCE).toContain('\x1b[0m');
        expect(BUFFER_FINAL_SEQUENCE).toContain('\x1b[?25h');
        expect(BUFFER_FINAL_SEQUENCE.endsWith('\n')).toBe(true);
        expect(BUFFER_FINAL_SEQUENCE.indexOf('\x1b[0m')).toBeLessThan(BUFFER_FINAL_SEQUENCE.indexOf('\x1b[?25h'));
    });
});

describe('map layout and divider calculations', () => {
    it('mapLayout trims and rejects unsafe positions', () => {
        expect(mapLayout(true, '63.5')).toEqual({ leftWidth: '63.5%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, ' 63.5% ')).toEqual({ leftWidth: '63.5%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '5')).toEqual({ leftWidth: '50%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '95')).toEqual({ leftWidth: '50%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '6')).toEqual({ leftWidth: '6%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '94.9')).toEqual({ leftWidth: '94.9%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '99')).toEqual({ leftWidth: '50%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, 'abc')).toEqual({ leftWidth: '50%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(true, '')).toEqual({ leftWidth: '50%', rightHidden: false, dividerHidden: false });
        expect(mapLayout(false, '63.5')).toEqual({ leftWidth: '100%', rightHidden: true, dividerHidden: true });
    });

    it('resizeWidth clamps to minimum and maximum and handles invalid inputs', () => {
        expect(resizeWidth(200, 500, -300, 5)).toBe(50);
        expect(resizeWidth(200, 500, 400, 5)).toBe(445);
        expect(resizeWidth(200, 500, 20, 5)).toBe(220);
        expect(resizeWidth(200, 0, 10, 5)).toBe(50);
        expect(resizeWidth(200, -100, 10, 5)).toBe(50);
        expect(resizeWidth(Number.NaN, 500, 10, 5)).toBe(50);
        expect(resizeWidth(200, 500, Number.NaN, 5)).toBe(50);
        expect(resizeWidth(200, 500, 10, Number.NaN)).toBe(50);
        expect(resizeWidth(100, 120, 0, 5)).toBe(65);
    });

    it('recordingDividerPct returns 50 for disabled or invalid container', () => {
        expect(recordingDividerPct(false, 1200, 1200)).toBe(50);
        expect(recordingDividerPct(true, 0, 0)).toBe(50);
        expect(recordingDividerPct(true, -10, 100)).toBe(50);
        expect(recordingDividerPct(true, Number.NaN, 100)).toBe(50);
        expect(recordingDividerPct(true, 1000, Number.NaN)).toBe(50);
        expect(recordingDividerPct(true, Number.POSITIVE_INFINITY, 500)).toBe(50);
    });

    it('recordingDividerPct computes percentage with 2-decimal precision', () => {
        expect(recordingDividerPct(true, 1000, 700)).toBe(70);
        expect(recordingDividerPct(true, 1000, 333)).toBe(33.3);
        expect(recordingDividerPct(true, 1000, 333.333)).toBe(33.33);
        expect(recordingDividerPct(true, 1200, 600)).toBe(50);
        expect(recordingDividerPct(true, 300, 100)).toBe(33.33);
    });
});

describe('client setting feedback', () => {
    it('settingFeedback keeps legacy strings', () => {
        expect(settingFeedback('fontsize', '24')).toBe('\r\nFont size is: 24.\r\n');
        expect(settingFeedback('contrast', '3')).toBe('\r\nMinimum contrast ratio is: 3.\r\n');
        expect(settingFeedback('scrollback', '100')).toBe('\r\nScrollback is: 100.\r\n');
        expect(settingFeedback('fontfamily', 'Fira Custom')).toContain('Font changed to: Fira Custom.');
        expect(settingFeedback('fontfamily', 'Fira Custom')).toContain(':reset');
    });

    it('settingFeedback handles default case for unknown setting', () => {
        const unknown = settingFeedback('fontsize' as unknown as 'fontsize', '42');
        expect(unknown).toContain('42');
        const fallback = settingFeedback('unknown' as unknown as 'fontsize', 'val');
        expect(fallback).toContain('val');
    });

    it('screenReaderFeedback formats status', () => {
        expect(screenReaderFeedback(true)).toBe('\r\nScreen reader mode enabled.\r\n');
        expect(screenReaderFeedback(false)).toBe('\r\nScreen reader mode disabled.\r\n');
    });
});

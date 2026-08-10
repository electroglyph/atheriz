import { describe, expect, it } from 'vitest';
import { screenReaderFeedback, settingFeedback } from '../src/webclient/feedback';

describe('webclient feedback', () => {
    it('keeps setting confirmations compatible with the legacy client', () => {
        expect(settingFeedback('fontsize', '24')).toBe('\r\nFont size is: 24.\r\n');
        expect(settingFeedback('contrast', '3')).toBe('\r\nMinimum contrast ratio is: 3.\r\n');
        expect(settingFeedback('fontfamily', 'Fira Custom')).toContain('Font changed to: Fira Custom.');
    });

    it('formats screen-reader status feedback', () => {
        expect(screenReaderFeedback(true)).toBe('\r\nScreen reader mode enabled.\r\n');
        expect(screenReaderFeedback(false)).toBe('\r\nScreen reader mode disabled.\r\n');
    });
});

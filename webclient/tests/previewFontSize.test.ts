// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { pickPreviewFontSize } from '../src/ui/PreviewWindow';
import { CellMetrics } from '../src/utils/fontMetrics';

function fakeMetrics(advanceRatio: number, heightRatio: number): (fs: number) => CellMetrics {
    return (fs: number) => ({
        width: Math.max(1, Math.ceil(fs * advanceRatio)),
        height: Math.ceil(fs * heightRatio),
        font: `${fs}px TestFont`,
        advance: fs * advanceRatio,
    });
}

describe('pickPreviewFontSize', () => {
    it('uses the largest size whose real metrics fit, not a hardcoded ratio', () => {
        // Unifont-style: 0.5 advance ratio, 1.11 height ratio (18px -> 9x20)
        const measure = fakeMetrics(0.5, 1.11);
        // 100x36 canvas, viewport sized so 18px fits but 20px does not
        const availW = 9 * 100;
        const availH = 20 * 36;
        expect(pickPreviewFontSize(measure, 100, 36, availW, availH)).toBe(18);
        // old heuristic (0.6 width / 1.2 height) would have rejected 18px:
        // 0.6 * 18 * 100 = 1080 > 900
    });

    it('prefers sizes with integral advances over fractional ones', () => {
        // odd-advance font: fs=20 -> advance 10.5 (fractional), fs=18 -> 9.45,
        // fs=16 -> 8.4, fs=14 -> 7.35 ... only even multiples of fs*0.525 land on integers?
        const measure = (fs: number): CellMetrics => ({
            width: Math.max(1, Math.ceil(fs * 0.5)),
            height: Math.ceil(fs * 1.1),
            font: `${fs}px TestFont`,
            advance: fs === 16 ? 8 : fs * 0.51,
        });
        // everything fits
        expect(pickPreviewFontSize(measure, 10, 10, 10000, 10000)).toBe(16);
    });

    it('falls back to the largest fitting size when no advance is integral', () => {
        const measure = fakeMetrics(0.51, 1.1);
        expect(pickPreviewFontSize(measure, 10, 10, 10000, 10000)).toBe(20);
    });

    it('clamps to the smallest size when nothing fits', () => {
        const measure = fakeMetrics(0.6, 1.2);
        expect(pickPreviewFontSize(measure, 1000, 1000, 50, 50)).toBe(2);
    });
});

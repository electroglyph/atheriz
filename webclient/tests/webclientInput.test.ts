import { describe, expect, it } from 'vitest';
import { inputHeight, shouldClearSubmittedInput, shouldNavigateHistory } from '../src/webclient/input';

describe('webclient input behavior', () => {
    it('keeps arrow navigation inside multiline input', () => {
        expect(shouldNavigateHistory('ArrowDown', 'line one\nline two', 5, 5, false)).toBe(false);
    });

    it('allows history navigation from an empty input or at its start', () => {
        expect(shouldNavigateHistory('ArrowUp', '', 0, 0, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowUp', 'command', 0, 0, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowDown', 'command', 0, 0, false)).toBe(false);
    });

    it('keeps the input large enough for multiline content', () => {
        expect(inputHeight(80)).toBe(80);
        expect(inputHeight(10)).toBe(30);
    });

    it('clears a submitted command only after ordinary next-key input', () => {
        expect(shouldClearSubmittedInput('a', true, false, false, false)).toBe(true);
        expect(shouldClearSubmittedInput('Enter', true, false, false, false)).toBe(false);
        expect(shouldClearSubmittedInput('a', true, true, false, false)).toBe(false);
        expect(shouldClearSubmittedInput('a', false, false, false, false)).toBe(false);
    });
});

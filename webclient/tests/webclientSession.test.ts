import { describe, expect, it } from 'vitest';
import { shouldResetSession } from '../src/webclient/session';

describe('webclient session lifecycle', () => {
    it('resets authenticated state when an established connection closes', () => {
        expect(shouldResetSession(true, 'closed')).toBe(true);
        expect(shouldResetSession(true, 'connecting')).toBe(true);
    });

    it('does not reset state during the initial connection', () => {
        expect(shouldResetSession(false, 'connecting')).toBe(false);
        expect(shouldResetSession(false, 'closed')).toBe(false);
        expect(shouldResetSession(true, 'open')).toBe(false);
    });
});

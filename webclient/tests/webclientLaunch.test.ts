// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearDrawGrant, launchDraw, readDrawGrant } from '../src/webclient/launch';

describe('draw launch command', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="left-terminal"></div>';
        sessionStorage.clear();
        vi.restoreAllMocks();
        vi.useFakeTimers();
    });

    afterEach(() => vi.useRealTimers());

    it('opens the fixed draw route in a new tab', () => {
        vi.setSystemTime(1000);
        const opened = vi.spyOn(window, 'open').mockReturnValue({} as Window);
        expect(launchDraw()).toBe(true);
        expect(opened).toHaveBeenCalledWith(
            'http://localhost:3000/atheriz_draw/',
            '_blank',
            'noopener,noreferrer',
        );
    });

    it('shows a fallback link when the popup is blocked', () => {
        vi.setSystemTime(3000);
        vi.spyOn(window, 'open').mockReturnValue(null);
        expect(launchDraw()).toBe(false);
        expect(document.querySelector('a')?.href).toBe('http://localhost:3000/atheriz_draw/');
        expect(document.querySelector('.popup-fallback')).not.toBeNull();
    });

    it('stores a grant before opening and clears it after', () => {
        vi.setSystemTime(5000);
        const opened = vi.spyOn(window, 'open').mockReturnValue({} as Window);
        const payload = { area: 'TestArea', z: 0, grid: [] };
        expect(launchDraw('secret-key', payload)).toBe(true);
        expect(readDrawGrant()).toBeNull();
        expect(opened).toHaveBeenCalledWith(
            'http://localhost:3000/atheriz_draw/',
            '_blank',
            'noopener,noreferrer',
        );
    });

    it('keeps the grant when the popup is blocked', () => {
        vi.setSystemTime(7000);
        vi.spyOn(window, 'open').mockReturnValue(null);
        const payload = { area: 'TestArea', z: 0, grid: [] };
        expect(launchDraw('secret-key', payload)).toBe(false);
        expect(readDrawGrant()).toEqual({ key: 'secret-key', payload });
        expect(document.querySelector('.popup-fallback')).not.toBeNull();
    });

    it('does not store a grant without a key', () => {
        vi.setSystemTime(9000);
        vi.spyOn(window, 'open').mockReturnValue({} as Window);
        expect(launchDraw()).toBe(true);
        expect(readDrawGrant()).toBeNull();
    });

    it('throttles launches within one second', () => {
        vi.setSystemTime(11000);
        const opened = vi.spyOn(window, 'open').mockReturnValue({} as Window);
        expect(launchDraw()).toBe(true);
        vi.setSystemTime(11500);
        expect(launchDraw()).toBe(true);
        expect(opened).toHaveBeenCalledTimes(1);
    });

    it('round-trips grants and rejects malformed ones', () => {
        sessionStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: { area: 'a' } }));
        expect(readDrawGrant()).toEqual({ key: 'k', payload: { area: 'a' } });
        sessionStorage.setItem('atheriz_draw_grant', 'not json');
        expect(readDrawGrant()).toBeNull();
        sessionStorage.setItem('atheriz_draw_grant', JSON.stringify({ payload: { area: 'a' } }));
        expect(readDrawGrant()).toBeNull();
        sessionStorage.setItem('atheriz_draw_grant', JSON.stringify({ key: 'k', payload: null }));
        expect(readDrawGrant()).toBeNull();
        clearDrawGrant();
        expect(readDrawGrant()).toBeNull();
    });
});

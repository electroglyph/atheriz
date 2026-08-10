// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { launchDraw } from '../src/webclient/launch';

describe('draw launch command', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="left-terminal"></div>';
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
    });
});

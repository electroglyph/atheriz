import { describe, expect, it } from 'vitest';
import { mapLayout, resizeWidth } from '../src/webclient/layout';

describe('webclient map layout', () => {
    it('expands the main terminal when the map is hidden', () => {
        expect(mapLayout(false, '50')).toEqual({
            leftWidth: '100%',
            rightHidden: true,
            dividerHidden: true,
        });
    });

    it('restores a valid saved divider position', () => {
        expect(mapLayout(true, '63.5')).toEqual({
            leftWidth: '63.5%',
            rightHidden: false,
            dividerHidden: false,
        });
    });

    it('rejects unsafe saved divider positions', () => {
        expect(mapLayout(true, '99')).toEqual({
            leftWidth: '50%',
            rightHidden: false,
            dividerHidden: false,
        });
    });

    it('keeps both panes at least 50px wide while dragging', () => {
        expect(resizeWidth(200, 500, -300, 5)).toBe(50);
        expect(resizeWidth(200, 500, 400, 5)).toBe(445);
        expect(resizeWidth(200, 500, 20, 5)).toBe(220);
    });
});

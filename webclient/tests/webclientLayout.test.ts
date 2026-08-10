import { describe, expect, it } from 'vitest';
import { mapLayout } from '../src/webclient/layout';

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
});

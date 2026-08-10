import { describe, expect, it } from 'vitest';
import { BUFFER_FINAL_SEQUENCE } from '../src/webclient/buffer';

describe('webclient buffered output', () => {
    it('restores ANSI state, shows the cursor, and ends the buffer', () => {
        expect(BUFFER_FINAL_SEQUENCE).toBe('\x1b[0m\x1b[?25h\n');
    });
});

import { describe, expect, it } from 'vitest';
import { encodeWireMessage, parseWireMessage } from '../src/webclient/types';

describe('webclient wire protocol', () => {
    it('parses the standard command tuple', () => {
        expect(parseWireMessage('["text", ["hello"], {"safe": true}]')).toEqual({
            command: 'text',
            args: ['hello'],
            kwargs: { safe: true },
        });
    });

    it('rejects malformed command tuples', () => {
        expect(parseWireMessage('{"command":"text"}')).toBeNull();
        expect(parseWireMessage('[42, [], {}]')).toBeNull();
        expect(parseWireMessage('["text", "not-an-array", {}]')).toBeNull();
        expect(parseWireMessage('["text", [], []]')).toBeNull();
        expect(parseWireMessage('not json')).toBeNull();
    });

    it('encodes the standard command tuple', () => {
        expect(encodeWireMessage('launch_draw')).toBe('["launch_draw",[],{}]');
    });
});

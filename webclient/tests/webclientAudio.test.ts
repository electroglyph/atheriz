import { describe, expect, it, vi } from 'vitest';
import { playAudio } from '../src/webclient/audio';

describe('webclient audio playback', () => {
    it('does not surface autoplay rejection as terminal output', async () => {
        const audio = {
            src: '',
            pause: vi.fn(),
            play: vi.fn().mockRejectedValue(new Error('blocked')),
        };
        await expect(playAudio(audio, '/sound.mp3')).resolves.toBeUndefined();
        expect(audio.pause).toHaveBeenCalledOnce();
        expect(audio.src).toBe('/sound.mp3');
    });
});

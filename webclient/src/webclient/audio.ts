export interface AudioLike {
    src: string;
    pause(): void;
    play(): Promise<unknown>;
}

export async function playAudio(audio: AudioLike, source: string): Promise<void> {
    if (!source) return;
    audio.pause();
    audio.src = source;
    try {
        await audio.play();
    } catch {
        return;
    }
}

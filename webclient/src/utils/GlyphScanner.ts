export class GlyphScanner {
    private static cache: Map<string, number[]> = new Map();

    // Only scan ranges that are actually useful for a drawing app.
    // This avoids all the obscure historical scripts, unassigned blocks, and speeds up scanning 100x.
    private static readonly VALID_RANGES: [number, number][] = [
        [0x0020, 0x007E], // Basic Latin
        [0x00A0, 0x02AF], // Latin-1 Supplement, Latin Extended-A & B, IPA Extensions
        [0x0370, 0x04FF], // Greek and Coptic, Cyrillic
        [0x2000, 0x206F], // General Punctuation
        [0x20A0, 0x20CF], // Currency Symbols
        [0x2100, 0x214F], // Letterlike Symbols
        [0x2150, 0x218F], // Number Forms
        [0x2190, 0x21FF], // Arrows
        [0x2200, 0x22FF], // Mathematical Operators
        [0x2300, 0x23FF], // Miscellaneous Technical
        [0x2400, 0x243F], // Control Pictures
        [0x2460, 0x24FF], // Enclosed Alphanumerics
        [0x2500, 0x257F], // Box Drawing
        [0x2580, 0x259F], // Block Elements
        [0x25A0, 0x25FF], // Geometric Shapes
        [0x2600, 0x26FF], // Miscellaneous Symbols
        [0x2700, 0x27BF], // Dingbats
        [0x2800, 0x28FF], // Braille Patterns
        [0x2B00, 0x2BFF], // Miscellaneous Symbols and Arrows
        [0x1CC00, 0x1CEAF], // Legacy Computing Supplement (Atheriz Circles)
        [0x1F300, 0x1FAFF], // Miscellaneous Symbols and Pictographs, Emoticons, Transport, Supplemental Symbols
        [0x1FB00, 0x1FBFF], // Symbols for Legacy Computing
    ];

    static async scanFont(fontFamily: string, onProgress: (pct: number) => void): Promise<number[]> {
        if (this.cache.has(fontFamily)) {
            return this.cache.get(fontFamily)!;
        }

        // Wait for the real webfont before measuring. Without this, the scan
        // measures the fallback font and caches those metrics permanently
        // under the real family name.
        const fonts = (document as Document & { fonts?: { load(font: string): Promise<unknown> } }).fonts;
        let fontReady = !fonts;
        if (fonts) {
            try {
                await fonts.load(`16px ${fontFamily}`);
                fontReady = true;
            } catch {
                fontReady = false;
            }
        }

        const canvas = document.createElement('canvas');
        canvas.width = 16;
        canvas.height = 16;
        const ctx = canvas.getContext('2d');
        if (!ctx) return [];

        ctx.font = `16px ${fontFamily}`;
        ctx.textBaseline = 'middle';

        // Find reference "missing glyph" metrics for fallback elimination within these blocks
        const refM4 = ctx.measureText(String.fromCodePoint(0xFFFF));
        const refM5 = ctx.measureText(String.fromCodePoint(0x1FFFF));
        const refM6 = ctx.measureText(String.fromCodePoint(0x10FFFF));

        const validGlyphs: number[] = [];
        const CHUNK_SIZE = 5000; 

        // Flatten ranges into an array of start/end boundaries we can iterate easily
        let rangeIdx = 0;
        let cp = this.VALID_RANGES[0][0];

        // Total codepoints we will scan (for progress bar)
        const totalCodes = this.VALID_RANGES.reduce((acc, [start, end]) => acc + (end - start + 1), 0);
        let codesProcessed = 0;

        return new Promise((resolve) => {
            const processChunk = () => {
                let chunkProcessed = 0;

                while (chunkProcessed < CHUNK_SIZE && rangeIdx < this.VALID_RANGES.length) {
                    const [_start, end] = this.VALID_RANGES[rangeIdx];
                    
                    if (cp > end) {
                        rangeIdx++;
                        if (rangeIdx < this.VALID_RANGES.length) {
                            cp = this.VALID_RANGES[rangeIdx][0];
                        }
                        continue;
                    }

                    for (; cp <= end && chunkProcessed < CHUNK_SIZE; cp++, chunkProcessed++) {
                        if (cp >= 0xD800 && cp <= 0xDFFF) continue; // Skip surrogates

                        const char = String.fromCodePoint(cp);
                        const m = ctx.measureText(char);

                        if (m.width === 0 && cp !== 0x20 && cp !== 0xA0) {
                            continue;
                        }

                        // Robust heuristic to catch any hex-boxes that might fall in unassigned spots within ranges
                        const isSameAsMissing4 = 
                            m.width === refM4.width &&
                            Math.abs(m.actualBoundingBoxLeft - refM4.actualBoundingBoxLeft) <= 1 &&
                            Math.abs(m.actualBoundingBoxRight - refM4.actualBoundingBoxRight) <= 1;
                            
                        const isSameAsMissing5 = 
                            m.width === refM5.width &&
                            Math.abs(m.actualBoundingBoxLeft - refM5.actualBoundingBoxLeft) <= 1 &&
                            Math.abs(m.actualBoundingBoxRight - refM5.actualBoundingBoxRight) <= 1;
                            
                        const isSameAsMissing6 = 
                            m.width === refM6.width &&
                            Math.abs(m.actualBoundingBoxLeft - refM6.actualBoundingBoxLeft) <= 1 &&
                            Math.abs(m.actualBoundingBoxRight - refM6.actualBoundingBoxRight) <= 1;

                        if (!isSameAsMissing4 && !isSameAsMissing5 && !isSameAsMissing6) {
                            validGlyphs.push(cp);
                        }
                    }
                }

                codesProcessed += chunkProcessed;

                if (rangeIdx >= this.VALID_RANGES.length) {
                    // Never cache fallback-font metrics under the real name;
                    // a later open (once the font loads) rescans correctly.
                    if (fontReady) this.cache.set(fontFamily, validGlyphs);
                    resolve(validGlyphs);
                } else {
                    onProgress(Math.floor((codesProcessed / totalCodes) * 100));
                    requestAnimationFrame(processChunk);
                }
            };
            
            requestAnimationFrame(processChunk);
        });
    }
}

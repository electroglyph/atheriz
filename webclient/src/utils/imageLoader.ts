import Chafa from 'chafa-wasm';
import { ChafaConfig } from './chafaDefaults';

const chafaWasmUrl = import.meta.env.BASE_URL + 'chafa.wasm';

export async function convertImageToAnsi(
    buffer: ArrayBuffer, 
    width: number, 
    height: number, 
    options: ChafaConfig,
    pixelsWidth?: number,
    pixelsHeight?: number
): Promise<string> {
    // Note: Chafa-wasm's default export resolves to the emscripten module wrapper
    const chafa = await (Chafa as any)({
        locateFile: (path: string) => {
            if (path.endsWith('.wasm')) return chafaWasmUrl;
            return path;
        }
    });
    
    return new Promise((resolve, reject) => {
        chafa.imageToAnsi(buffer, {
            ...options,
            pixelsWidth,
            pixelsHeight,
            width: width,
            height: height || Number(options.height),
        }, (err: any, result: any) => {
            if (err) reject(err);
            else resolve(result.ansi);
        });
    });
}

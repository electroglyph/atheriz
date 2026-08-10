const ANSI_COLOR = /\x1B\[[0-9;]+m/g;
const ESC = '\x1B';
const RESET = `${ESC}[0m`;
const WHITE = `${ESC}[37m`;

export const DEFAULT_TEXT_COLOR = `${ESC}[38;2;190;190;190m`;
export const DEFAULT_TEXT_RESET = `${RESET}${DEFAULT_TEXT_COLOR}`;

export function normalizeServerText(input: string, width: number, screenReader: boolean): string {
    if (screenReader) return input;
    let output = input;
    if (output.charAt(0) !== ESC) output = DEFAULT_TEXT_COLOR + output;
    output = wrapText(output, width);
    return output.replaceAll(RESET, DEFAULT_TEXT_RESET).replaceAll(WHITE, DEFAULT_TEXT_COLOR);
}

export function formatTextOutput(
    input: string,
    width: number,
    screenReader: boolean,
    prompt: string,
    promptPrinted: boolean,
): string {
    const output = normalizeServerText(input, width, screenReader);
    if (promptPrinted) {
        return `\r${' '.repeat(stripAnsi(prompt).length)}\r${RESET}${output}${RESET}${prompt}`;
    }
    return `${RESET}${output}${RESET}${prompt}`;
}

export function formatPrompt(prompt: string, oldPrompt: string, promptPrinted: boolean): string {
    const clear = promptPrinted ? `\r${' '.repeat(stripAnsi(oldPrompt).length)}\r` : '';
    return `${clear}${RESET}${prompt}${RESET}`;
}

export function wrapText(text: string, width: number): string {
    if (!text || width <= 0) return text;
    let result = '';
    let currentLineLength = 0;
    let currentColor = '';
    const words = text.split(/(\s+)/);

    for (const word of words) {
        if (!word) continue;
        let nextColor = currentColor;
        const codes = word.match(ANSI_COLOR);
        if (codes) {
            for (const code of codes) nextColor = code === RESET ? '' : code;
        }

        if (word.includes('\n')) {
            result += word;
            const afterNewline = word.slice(word.lastIndexOf('\n') + 1).replace(ANSI_COLOR, '');
            currentLineLength = afterNewline.length;
            currentColor = nextColor;
            continue;
        }

        const visibleWord = word.replace(ANSI_COLOR, '');
        const wordLength = visibleWord.length;
        if (currentLineLength + wordLength > width) {
            if (/^\s+$/.test(word)) {
                if (currentLineLength > 0) {
                    result += `${RESET}\n${currentColor}`;
                    currentLineLength = 0;
                }
            } else {
                if (currentLineLength > 0) {
                    result += `${RESET}\n${currentColor}`;
                    currentLineLength = 0;
                }
                result += word;
                currentLineLength += wordLength;
            }
        } else {
            result += word;
            currentLineLength += wordLength;
        }
        currentColor = nextColor;
    }
    return result;
}

function stripAnsi(value: string): string {
    return value.replace(ANSI_COLOR, '');
}

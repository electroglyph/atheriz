export function shouldNavigateHistory(
    key: 'ArrowUp' | 'ArrowDown',
    value: string,
    selectionStart: number | null,
    selectionEnd: number | null,
    navigating: boolean,
): boolean {
    if (value === '' || navigating) return true;
    const fullSelection = selectionStart === 0 && selectionEnd === value.length;
    const atStart = selectionStart === 0 && selectionEnd === 0;
    return fullSelection || (key === 'ArrowUp' && atStart);
}

export function inputHeight(scrollHeight: number, minimum = 30): number {
    return Math.max(scrollHeight, minimum);
}

export function shouldNavigateHistory(
    _key: 'ArrowUp' | 'ArrowDown',
    value: string,
    selectionStart: number | null,
    selectionEnd: number | null,
    navigating: boolean,
): boolean {
    if (value === '' || navigating) return true;
    const fullSelection = selectionStart === 0 && selectionEnd === value.length;
    const atStart = selectionStart === 0 && selectionEnd === 0;
    return fullSelection || atStart;
}

export function inputHeight(scrollHeight: number, minimum = 30): number {
    return Math.max(scrollHeight, minimum);
}

export function shouldClearSubmittedInput(
    key: string,
    submitted: boolean,
    controlKey: boolean,
    altKey: boolean,
    metaKey: boolean,
): boolean {
    return submitted && key.length === 1 && !controlKey && !altKey && !metaKey;
}

export function submissionFeedback(sent: boolean): string | null {
    return sent ? null : '\r\nNot connected to server.\r\n';
}

// @vitest-environment jsdom
import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { CommandHistory } from '../src/webclient/history';
import { shouldNavigateHistory, shouldClearSubmittedInput } from '../src/webclient/input';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('command history player commands capping', () => {
    beforeEach(() => localStorage.clear());
    afterEach(() => localStorage.clear());

    it('caps playerCommands at maxSize', () => {
        const hist = new CommandHistory('test-history-cap', 10);
        const many = Array.from({ length: 30 }, (_, i) => `cmd${i}`);
        hist.setPlayerCommands(many);
        // @ts-ignore access private for verification
        const stored = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored.length).toBeLessThanOrEqual(10);
        expect(stored.length).toBe(10);
    });

    it('caps incrementally across multiple setPlayerCommands calls', () => {
        const hist = new CommandHistory('test-history-inc', 5);
        hist.setPlayerCommands(['a', 'b', 'c']);
        hist.setPlayerCommands(['d', 'e', 'f', 'g', 'h', 'i']);
        const stored = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored.length).toBe(5);
    });

    it('deduplicates playerCommands', () => {
        const hist = new CommandHistory('test-history-dedup', 100);
        hist.setPlayerCommands(['look', 'go', 'look', 'go', 'say']);
        hist.setPlayerCommands(['look', 'say', 'new']);
        const stored = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored.filter(c => c === 'look').length).toBe(1);
        expect(stored.filter(c => c === 'go').length).toBe(1);
        expect(stored).toContain('new');
    });

    it('filters non-string and empty playerCommands', () => {
        const hist = new CommandHistory('test-history-filter', 100);
        // @ts-ignore testing runtime filtering
        hist.setPlayerCommands(['valid', '', 42 as unknown as string, null as unknown as string, 'alsoValid']);
        const stored = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored).toContain('valid');
        expect(stored).toContain('alsoValid');
        expect(stored).not.toContain('');
        expect(stored).not.toContain(42 as unknown as string);
    });

    it('rejects malicious growth from large server payload', () => {
        const hist = new CommandHistory('test-history-malicious', 2048);
        const huge = Array.from({ length: 5000 }, (_, i) => `evil${i}`);
        hist.setPlayerCommands(huge);
        const stored = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored.length).toBe(2048);
        hist.setPlayerCommands(Array.from({ length: 5000 }, (_, i) => `evil2_${i}`));
        const stored2 = (hist as unknown as { playerCommands: string[] }).playerCommands;
        expect(stored2.length).toBe(2048);
    });
});

describe('command history add and navigation', () => {
    beforeEach(() => localStorage.clear());

    it('does not add empty strings', () => {
        const hist = new CommandHistory('test-history-empty', 10);
        hist.add('');
        // @ts-ignore
        expect((hist as unknown as { history: string[] }).history.length).toBe(0);
    });

    it('adds most recent at front and dedupes', () => {
        const hist = new CommandHistory('test-history-order', 10);
        hist.add('first');
        hist.add('second');
        hist.add('first');
        const h = (hist as unknown as { history: string[] }).history;
        expect(h[0]).toBe('first');
        expect(h.filter(x => x === 'first').length).toBe(1);
    });

    it('respects maxSize for history', () => {
        const hist = new CommandHistory('test-history-max', 3);
        hist.add('a');
        hist.add('b');
        hist.add('c');
        hist.add('d');
        const h = (hist as unknown as { history: string[] }).history;
        expect(h.length).toBe(3);
        expect(h).not.toContain('a');
    });
});

describe('input history navigation at boundaries', () => {
    it('navigates when at start for both arrow keys', () => {
        expect(shouldNavigateHistory('ArrowUp', 'command', 0, 0, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowDown', 'command', 0, 0, false)).toBe(true);
    });

    it('navigates when full selection regardless of key', () => {
        expect(shouldNavigateHistory('ArrowUp', 'hello', 0, 5, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowDown', 'hello', 0, 5, false)).toBe(true);
    });

    it('does not navigate inside multiline when not at start or full selection', () => {
        expect(shouldNavigateHistory('ArrowUp', 'line one\nline two', 5, 5, false)).toBe(false);
        expect(shouldNavigateHistory('ArrowDown', 'line one\nline two', 5, 5, false)).toBe(false);
        expect(shouldNavigateHistory('ArrowUp', 'hello', 2, 2, false)).toBe(false);
        expect(shouldNavigateHistory('ArrowDown', 'hello', 2, 2, false)).toBe(false);
    });

    it('always navigates when already navigating or input empty', () => {
        expect(shouldNavigateHistory('ArrowUp', '', 0, 0, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowDown', '', 0, 0, false)).toBe(true);
        expect(shouldNavigateHistory('ArrowUp', 'cmd', 2, 2, true)).toBe(true);
        expect(shouldNavigateHistory('ArrowDown', 'cmd', 2, 2, true)).toBe(true);
    });

    it('does not navigate when selection is partial at start', () => {
        expect(shouldNavigateHistory('ArrowUp', 'hello', 0, 2, false)).toBe(false);
        expect(shouldNavigateHistory('ArrowDown', 'hello', 0, 2, false)).toBe(false);
    });
});

describe('input submitted clearing', () => {
    it('clears on ordinary typing after submit', () => {
        expect(shouldClearSubmittedInput('a', true, false, false, false)).toBe(true);
        expect(shouldClearSubmittedInput('A', true, false, false, false)).toBe(true);
        expect(shouldClearSubmittedInput('1', true, false, false, false)).toBe(true);
    });

    it('does not clear on control keys after submit', () => {
        expect(shouldClearSubmittedInput('Enter', true, false, false, false)).toBe(false);
        expect(shouldClearSubmittedInput('ArrowUp', true, false, false, false)).toBe(false);
        expect(shouldClearSubmittedInput('a', true, true, false, false)).toBe(false);
        expect(shouldClearSubmittedInput('a', true, false, true, false)).toBe(false);
        expect(shouldClearSubmittedInput('a', true, false, false, true)).toBe(false);
        expect(shouldClearSubmittedInput('a', false, false, false, false)).toBe(false);
    });
});

describe('command handling file integrity', () => {
    const mainPath = path.resolve(import.meta.dirname, '../src/webclient/main.ts');
    const content = fs.readFileSync(mainPath, 'utf-8');

    it('trims input and treats whitespace as empty', () => {
        expect(content).toContain('const trimmed = command.trim()');
        expect(content).toContain("if (!trimmed)");
        expect(content).toContain("connection.send('text', ['\\n'])");
        // trimmed should be sent, not raw command
        expect(content).toContain("connection.send('text', [trimmed])");
        expect(content).toContain("writeSelf(trimmed)");
    });

    it('does not pollute history with internal colon commands', () => {
        expect(content).toContain("if (trimmed.startsWith(':'))");
        // history.add should appear after the colon handling, not before
        const colonIndex = content.indexOf("if (trimmed.startsWith(':'))");
        const addIndex = content.indexOf("history.add(trimmed)");
        expect(addIndex).toBeGreaterThan(colonIndex);
        // old pattern should not exist
        expect(content).not.toContain("history.add(command)");
        expect(content).not.toMatch(/history\.add\(command\)/);
    });

    it('shows usage hint for unknown colon commands instead of forwarding to server', () => {
        expect(content).toContain('Unknown command:');
        expect(content).toContain('Enter :help for a list of commands');
        // the unknown handler should return without sending to server after the hint
        expect(content).toContain("write(`\\r\\nUnknown command:");
        // ensure the colon block returns after handling
        const unknownBlock = content.slice(content.indexOf('Unknown command:'), content.indexOf('Unknown command:') + 500);
        expect(unknownBlock).toContain('return;');
    });

    it('history ghost scroll is synced on resize', () => {
        expect(content).toContain('hint.scrollTop = elements.input.scrollTop');
        expect(content).toContain('hint.scrollLeft = elements.input.scrollLeft');
        // should be inside resizeInput
        const resizeIndex = content.indexOf('const resizeInput');
        const hintSyncIndex = content.indexOf('hint.scrollTop = elements.input.scrollTop');
        expect(hintSyncIndex).toBeGreaterThan(resizeIndex);
        expect(content).toContain("hint.scrollTop = elements.input.scrollTop;");
        expect(content).toContain("elements.input.addEventListener('scroll'");
    });

    it('findCompletions uses capped playerCommands', () => {
        const historyPath = path.resolve(import.meta.dirname, '../src/webclient/history.ts');
        const histContent = fs.readFileSync(historyPath, 'utf-8');
        expect(histContent).toContain('.slice(0, this.maxSize)');
        expect(histContent).toContain('filter((c)');
    });
});

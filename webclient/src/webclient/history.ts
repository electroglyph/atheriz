export class CommandHistory {
    private readonly storageKey: string;
    private readonly maxSize: number;
    private history: string[];
    private index = -1;
    private currentInput = '';
    private playerCommands: string[] = [];
    private completionMatches: string[] = [];

    constructor(storageKey = 'xtermia2CommandHistory', maxSize = 2048) {
        this.storageKey = storageKey;
        this.maxSize = maxSize;
        this.history = this.load();
    }

    add(value: string): void {
        if (!value) return;
        this.history = [value, ...this.history.filter((item) => item !== value)].slice(0, this.maxSize);
        this.save();
        this.reset();
    }

    navigate(direction: 'up' | 'down', currentValue: string): string {
        if (this.index === -1) this.currentInput = currentValue;
        if (direction === 'up') this.index = Math.min(this.index + 1, this.history.length - 1);
        else this.index = Math.max(this.index - 1, -1);
        return this.index === -1 ? this.currentInput : (this.history[this.index] ?? this.currentInput);
    }

    reset(): void {
        this.index = -1;
        this.currentInput = '';
        this.completionMatches = [];
    }

    setPlayerCommands(commands: string[]): void {
        this.playerCommands = [...new Set([...this.playerCommands, ...commands])];
    }

    findCompletions(value: string): void {
        if (!value) {
            this.completionMatches = [];
            return;
        }
        const candidates = [...new Set([...this.history, ...this.playerCommands])];
        this.completionMatches = candidates.filter((candidate) => {
            return candidate.startsWith(value) && candidate.length > value.length;
        });
    }

    getSuggestion(): string {
        return this.completionMatches[0] ?? '';
    }

    save(): void {
        try {
            window.localStorage.setItem(this.storageKey, JSON.stringify(this.history));
        } catch {
            // Storage can be disabled or full; history must never block input.
        }
    }

    clear(): void {
        this.history = [];
        this.reset();
        this.save();
    }

    private load(): string[] {
        try {
            const saved = window.localStorage.getItem(this.storageKey);
            const parsed: unknown = saved ? JSON.parse(saved) : [];
            return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
        } catch {
            return [];
        }
    }
}

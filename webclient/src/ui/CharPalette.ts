import { CHAR_GROUPS, CHAR_NAMES } from '../utils/characters';
import { AppState } from '../types';

export class CharPalette {
    private container: HTMLElement;
    private appState: AppState;
    private charCells: Map<string, HTMLElement> = new Map();
    private onChangeAction: () => void;
    private onAddCustomChar?: () => void;
    private groups: { name: string; chars: string[] }[] = CHAR_GROUPS.map((group) => ({ name: group.name, chars: [...group.chars] }));

    constructor(containerId: string, appState: AppState, onChange: () => void, onAddCustomChar?: () => void) {
        this.container = document.getElementById(containerId)!;
        this.appState = appState;
        this.onChangeAction = onChange;
        this.onAddCustomChar = onAddCustomChar;
        try {
            const stored = localStorage.getItem('atheriz_custom_chars');
            if (stored) {
                const parsed = JSON.parse(stored);
                if (Array.isArray(parsed)) {
                    const customGroup = this.groups.find((group) => group.name === 'Custom');
                    if (customGroup) {
                        for (const char of parsed) {
                            if (typeof char === 'string' && char.length > 0 && !customGroup.chars.includes(char)) {
                                customGroup.chars.push(char);
                            }
                        }
                    }
                }
            }
        } catch {}
        this.render();
    }

    public addCustomChars(chars: string[]): void {
        const customGroup = this.groups.find((group) => group.name === 'Custom');
        if (!customGroup) return;
        let added = false;
        for (const char of chars) {
            if (!customGroup.chars.includes(char)) {
                customGroup.chars.push(char);
                added = true;
            }
        }
        if (added) {
            try {
                localStorage.setItem('atheriz_custom_chars', JSON.stringify(customGroup.chars));
            } catch {}
            this.reRender();
        }
    }

    private render() {
        this.container.innerHTML = '';
        
        for (const group of this.groups) {
            const label = document.createElement('div');
            label.className = 'palette-group-label';
            label.textContent = group.name;
            this.container.appendChild(label);
            
            for (const char of group.chars) {
                const cell = document.createElement('div');
                cell.className = 'char-cell';
                cell.textContent = char;
                cell.title = CHAR_NAMES[char] || char;
                if (char === this.appState.selectedChar) {
                    cell.classList.add('active');
                }
                
                cell.addEventListener('click', () => {
                    this.selectChar(char);
                });

                if (group.name === "Custom") {
                    cell.addEventListener('contextmenu', (e) => {
                        e.preventDefault();
                        this.removeCustomChar(char);
                    });
                }
                
                this.charCells.set(char, cell);
                this.container.appendChild(cell);
            }

            if (group.name === "Custom") {
                const addBtn = document.createElement('div');
                addBtn.className = 'char-cell add-btn';
                addBtn.textContent = '+';
                addBtn.title = 'Add Custom Character';
                addBtn.addEventListener('click', () => {
                    if (this.onAddCustomChar) {
                        this.onAddCustomChar();
                    }
                });
                this.container.appendChild(addBtn);
            }
        }
    }

    public selectChar(char: string) {
        // Remove active class from old
        const oldCell = this.charCells.get(this.appState.selectedChar);
        if (oldCell) oldCell.classList.remove('active');
        
        this.appState.selectedChar = char;
        
        // Add active class to new
        const newCell = this.charCells.get(char);
        if (newCell) newCell.classList.add('active');
        
        this.onChangeAction();
    }

    private removeCustomChar(char: string) {
        const customGroup = this.groups.find((group) => group.name === 'Custom');
        if (!customGroup) return;
        const idx = customGroup.chars.indexOf(char);
        if (idx === -1) return;
        customGroup.chars.splice(idx, 1);
        try {
            localStorage.setItem('atheriz_custom_chars', JSON.stringify(customGroup.chars));
        } catch {}
        if (this.appState.selectedChar === char) {
            this.appState.selectedChar = customGroup.chars[0] || this.groups[0].chars[0];
        }
        this.reRender();
    }

    public reRender() {
        this.charCells.clear();
        this.render();
    }
}

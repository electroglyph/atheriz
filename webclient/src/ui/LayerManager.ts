import { CanvasState } from '../state/CanvasState';
import { UndoStack } from '../state/UndoStack';

export class LayerManager {
    private container: HTMLElement;
    private state!: CanvasState;
    private undoStack: UndoStack;

    private renderBound = () => this.render();

    constructor(containerId: string, state: CanvasState, undoStack: UndoStack) {
        this.container = document.getElementById(containerId)!;
        this.undoStack = undoStack;
        this.updateState(state);
    }

    public updateState(newState: CanvasState) {
        if (this.state) {
            this.state.offChange(this.renderBound);
        }
        this.state = newState;
        this.state.onChange(this.renderBound);
        this.render();
    }

    private render() {
        this.container.innerHTML = '';
        
        // Render from top down (last layer in array is top visually)
        for (let i = this.state.layers.length - 1; i >= 0; i--) {
            const layer = this.state.layers[i];
            const item = document.createElement('div');
            item.className = 'layer-item';
            if (i === this.state.activeLayerIndex) {
                item.classList.add('active');
            }

            // Click anywhere to select
            item.addEventListener('click', (e) => {
                if ((e.target as HTMLElement).tagName.toLowerCase() !== 'button') {
                    this.state.activeLayerIndex = i;
                    this.state.notify();
                }
            });

            // Visibility toggle
            const visBtn = document.createElement('button');
            visBtn.className = 'icon-btn';
            visBtn.title = 'Toggle Visibility';
            visBtn.innerHTML = layer.visible
                ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`
                : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
            visBtn.style.opacity = layer.visible ? '1' : '0.4';
            visBtn.addEventListener('click', () => {
                layer.visible = !layer.visible;
                this.state.notify();
            });
            item.appendChild(visBtn);

            // Layer Name
            const nameEl = document.createElement('div');
            nameEl.className = 'layer-name';
            nameEl.textContent = layer.name;
            item.appendChild(nameEl);

            const controls = document.createElement('div');
            controls.className = 'layer-controls';

            // Merge down
            const mergeBtn = document.createElement('button');
            mergeBtn.className = 'icon-btn';
            mergeBtn.title = 'Merge Down';
            mergeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="3" x2="12" y2="14"/><polyline points="8 10 12 14 16 10"/><line x1="4" y1="19" x2="20" y2="19"/></svg>`;
            mergeBtn.disabled = i === 0;
            mergeBtn.addEventListener('click', () => {
                this.mergeDown(i);
            });
            controls.appendChild(mergeBtn);

            // Up arrow
            const upBtn = document.createElement('button');
            upBtn.className = 'icon-btn';
            upBtn.title = 'Move Up';
            upBtn.innerHTML = '&#9650;';
            upBtn.disabled = i === this.state.layers.length - 1;
            upBtn.addEventListener('click', () => {
                this.moveLayer(i, i + 1);
            });
            controls.appendChild(upBtn);

            // Down arrow
            const downBtn = document.createElement('button');
            downBtn.className = 'icon-btn';
            downBtn.title = 'Move Down';
            downBtn.innerHTML = '&#9660;';
            downBtn.disabled = i === 0;
            downBtn.addEventListener('click', () => {
                this.moveLayer(i, i - 1);
            });
            controls.appendChild(downBtn);

            // Delete (red ×)
            const trashBtn = document.createElement('button');
            trashBtn.className = 'icon-btn delete-btn';
            trashBtn.title = 'Delete Layer';
            trashBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
            trashBtn.disabled = this.state.layers.length <= 1;
            trashBtn.addEventListener('click', () => {
                if (confirm(`Delete "${layer.name}"?`)) {
                    this.deleteLayer(i);
                }
            });
            controls.appendChild(trashBtn);

            item.appendChild(controls);
            this.container.appendChild(item);
        }

        // Add layer button
        const addBtn = document.createElement('div');
        addBtn.className = 'add-layer-btn';
        addBtn.innerHTML = '+ Add Layer';
        addBtn.addEventListener('click', () => {
            this.undoStack.push(this.state);
            this.state.addLayer();
        });
        this.container.appendChild(addBtn);
    }

    private moveLayer(fromIndex: number, toIndex: number) {
        if (toIndex < 0 || toIndex >= this.state.layers.length) return;
        this.undoStack.push(this.state);
        
        const layer = this.state.layers.splice(fromIndex, 1)[0];
        this.state.layers.splice(toIndex, 0, layer);
        
        if (this.state.activeLayerIndex === fromIndex) {
            this.state.activeLayerIndex = toIndex;
        } else if (this.state.activeLayerIndex === toIndex) {
            this.state.activeLayerIndex = fromIndex;
        }
        
        this.state.notify();
    }

    private deleteLayer(index: number) {
        if (this.state.layers.length <= 1) return;
        this.undoStack.push(this.state);
        
        this.state.layers.splice(index, 1);
        
        if (this.state.activeLayerIndex >= index) {
            this.state.activeLayerIndex = Math.max(0, this.state.activeLayerIndex - 1);
        }
        
        this.state.notify();
    }

    private mergeDown(index: number) {
        if (index <= 0) return;
        this.undoStack.push(this.state);

        const upper = this.state.layers[index];
        const lower = this.state.layers[index - 1];

        for (let r = 0; r < this.state.height; r++) {
            for (let c = 0; c < this.state.width; c++) {
                const src = upper.cells[r][c];
                const dst = lower.cells[r][c];
                if (src.char && src.char.trim() !== '') {
                    dst.char = src.char;
                    dst.fg = [...src.fg] as [number, number, number];
                    dst.bold = src.bold;
                    dst.italic = src.italic;
                    dst.underline = src.underline;
                }
                if (src.bg[0] !== -1) {
                    dst.bg = [...src.bg] as [number, number, number];
                }
            }
        }

        if (upper.overflowCells && upper.overflowCells.size > 0) {
            if (!lower.overflowCells) lower.overflowCells = new Map();
            for (const [key, src] of upper.overflowCells.entries()) {
                const existing = lower.overflowCells.get(key);
                if (src.char && src.char.trim() !== '') {
                    if (existing) {
                        existing.char = src.char;
                        existing.fg = [...src.fg] as [number, number, number];
                        existing.bold = src.bold;
                        existing.italic = src.italic;
                        existing.underline = src.underline;
                        if (src.bg[0] !== -1) existing.bg = [...src.bg] as [number, number, number];
                    } else {
                        lower.overflowCells.set(key, {
                            char: src.char,
                            fg: [...src.fg] as [number, number, number],
                            bg: src.bg[0] === -1 ? ([-1, -1, -1] as [number, number, number]) : ([...src.bg] as [number, number, number]),
                            bold: src.bold,
                            italic: src.italic,
                            underline: src.underline,
                        });
                    }
                } else if (src.bg[0] !== -1) {
                    if (existing) {
                        existing.bg = [...src.bg] as [number, number, number];
                    } else {
                        lower.overflowCells.set(key, {
                            char: '',
                            fg: [...src.fg] as [number, number, number],
                            bg: [...src.bg] as [number, number, number],
                            bold: src.bold,
                            italic: src.italic,
                            underline: src.underline,
                        });
                    }
                }
            }
        }

        this.state.layers.splice(index, 1);
        if (this.state.activeLayerIndex === index) {
            this.state.activeLayerIndex = index - 1;
        } else if (this.state.activeLayerIndex > index) {
            this.state.activeLayerIndex--;
        }

        this.state.notify();
    }
}

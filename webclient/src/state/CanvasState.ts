import { Cell, Layer } from '../types';

export class CanvasState {
    width: number;
    height: number;
    layers: Layer[];
    activeLayerIndex: number;
    private changeListeners: Set<() => void> = new Set();
    layerIdCounter: number = 0;

    constructor(width: number, height: number, initializeBlack: boolean = true) {
        this.width = width;
        this.height = height;
        this.layers = [];
        this.activeLayerIndex = 0;
        this.addLayer("Background", initializeBlack);
    }

    public createEmptyCells(initializeBlack: boolean = false): Cell[][] {
        return Array.from({ length: this.height }, () =>
            Array.from({ length: this.width }, () => ({
                char: '',
                fg: [204, 204, 204] as [number, number, number],
                // Use [-1,-1,-1] to represent transparent background for layers above background
                bg: initializeBlack ? [0, 0, 0] as [number, number, number] : [-1, -1, -1] as [number, number, number]
            }))
        );
    }

    public addLayer(name?: string, initializeBlack: boolean = false) {
        this.layerIdCounter++;
        this.layers.push({
            id: `layer-${this.layerIdCounter}`,
            name: name || `Layer ${this.layers.length + 1}`,
            visible: true,
            cells: this.createEmptyCells(initializeBlack),
            overflowCells: new Map()
        });
        this.activeLayerIndex = this.layers.length - 1;
        this.notify();
    }

    public getActiveLayer(): Layer {
        return this.layers[this.activeLayerIndex];
    }

    /**
     * Resolves the final visible cell at (col, row) by blending layers from the top (foreground) 
     * to the bottom (background). Once an opaque background is found, lower layers are obscured.
     */
    public getCompositeCell(col: number, row: number): Cell | null {
        if (col < 0 || col >= this.width || row < 0 || row >= this.height) return null;
        
        let finalChar = '';
        let finalFg: [number, number, number] = [204, 204, 204];
        let finalBg: [number, number, number] = [-1, -1, -1];
        let finalBold: boolean | undefined;
        let finalItalic: boolean | undefined;
        let finalUnderline: boolean | undefined;
        let charFound = false;
        let bgFound = false;

        for (let i = this.layers.length - 1; i >= 0; i--) {
            const layer = this.layers[i];
            if (!layer.visible) continue;
            
            const cell = layer.cells[row][col];
            
            if (!charFound && cell.char && cell.char.trim() !== '') {
                finalChar = cell.char;
                finalFg = [...cell.fg] as [number, number, number];
                finalBold = cell.bold;
                finalItalic = cell.italic;
                finalUnderline = cell.underline;
                charFound = true;
            }
            
            if (!bgFound && cell.bg[0] !== -1) {
                finalBg = [...cell.bg] as [number, number, number];
                bgFound = true;
            }

            if (charFound && bgFound) break;
        }

        if (!bgFound) finalBg = [0, 0, 0];
        
        return { char: finalChar, fg: finalFg, bg: finalBg, bold: finalBold, italic: finalItalic, underline: finalUnderline };
    }

    public getCell(col: number, row: number): Cell | null {
        const layer = this.getActiveLayer();
        if (col < 0 || col >= this.width || row < 0 || row >= this.height) {
            return layer.overflowCells?.get(`${col},${row}`) || null;
        }
        return layer.cells[row][col];
    }

    public setCell(col: number, row: number, cell: Cell, triggerChange: boolean = true) {
        const layer = this.getActiveLayer();
        if (col < 0 || col >= this.width || row < 0 || row >= this.height) {
            if (!layer.overflowCells) layer.overflowCells = new Map();
            const isEmpty = (!cell.char || cell.char.trim() === '') && cell.bg[0] === -1;
            if (isEmpty) {
                layer.overflowCells.delete(`${col},${row}`);
            } else {
                layer.overflowCells.set(`${col},${row}`, { char: cell.char, fg: [...cell.fg] as [number, number, number], bg: [...cell.bg] as [number, number, number], bold: cell.bold, italic: cell.italic, underline: cell.underline });
            }
        } else {
            layer.cells[row][col] = { char: cell.char, fg: [...cell.fg] as [number, number, number], bg: [...cell.bg] as [number, number, number], bold: cell.bold, italic: cell.italic, underline: cell.underline };
        }
        if (triggerChange) {
            this.notify();
        }
    }

    public applyBatch(updates: { col: number, row: number, cell: Cell }[]) {
        let changed = false;
        const layer = this.getActiveLayer();
        for (const u of updates) {
            if (u.col >= 0 && u.col < this.width && u.row >= 0 && u.row < this.height) {
                layer.cells[u.row][u.col] = { char: u.cell.char, fg: [...u.cell.fg] as [number, number, number], bg: [...u.cell.bg] as [number, number, number], bold: u.cell.bold, italic: u.cell.italic, underline: u.cell.underline };
                changed = true;
            } else {
                if (!layer.overflowCells) layer.overflowCells = new Map();
                const isEmpty = (!u.cell.char || u.cell.char.trim() === '') && u.cell.bg[0] === -1;
                if (isEmpty) {
                    if (layer.overflowCells.has(`${u.col},${u.row}`)) {
                         layer.overflowCells.delete(`${u.col},${u.row}`);
                         changed = true;
                    }
                } else {
                    layer.overflowCells.set(`${u.col},${u.row}`, { char: u.cell.char, fg: [...u.cell.fg] as [number, number, number], bg: [...u.cell.bg] as [number, number, number], bold: u.cell.bold, italic: u.cell.italic, underline: u.cell.underline });
                    changed = true;
                }
            }
        }
        if (changed) this.notify();
    }

    public fill(cell: Cell) {
        const layer = this.getActiveLayer();
        for (let row = 0; row < this.height; row++) {
            for (let col = 0; col < this.width; col++) {
                layer.cells[row][col] = {
                    char: cell.char,
                    fg: [...cell.fg] as [number, number, number],
                    bg: [...cell.bg] as [number, number, number],
                    bold: cell.bold,
                    italic: cell.italic,
                    underline: cell.underline
                };
            }
        }
        this.notify();
    }

    public clone(): CanvasState {
        const copy = new CanvasState(this.width, this.height, false);
        copy.layers = [];
        copy.layerIdCounter = this.layerIdCounter;
        copy.activeLayerIndex = this.activeLayerIndex;
        
        for (const layer of this.layers) {
            const newCells = this.createEmptyCells();
            for (let r = 0; r < this.height; r++) {
                for (let c = 0; c < this.width; c++) {
                    const src = layer.cells[r][c];
                    newCells[r][c] = {
                        char: src.char,
                        fg: [...src.fg] as [number, number, number],
                        bg: [...src.bg] as [number, number, number],
                        bold: src.bold,
                        italic: src.italic,
                        underline: src.underline
                    };
                }
            }
            copy.layers.push({
                id: layer.id,
                name: layer.name,
                visible: layer.visible,
                cells: newCells,
                overflowCells: layer.overflowCells ? new Map(Array.from(layer.overflowCells.entries()).map(([k, cell]) => [k, { char: cell.char, fg: [...cell.fg] as [number, number, number], bg: [...cell.bg] as [number, number, number], bold: cell.bold, italic: cell.italic, underline: cell.underline }])) : new Map()
            });
        }
        return copy;
    }

    public onChange(listener: () => void) {
        this.changeListeners.add(listener);
    }

    public offChange(listener: () => void) {
        this.changeListeners.delete(listener);
    }

    public notify() {
        for (const listener of this.changeListeners) {
            listener();
        }
    }

    public resize(newWidth: number, newHeight: number) {
        if (newWidth === this.width && newHeight === this.height) return;

        for (let i = 0; i < this.layers.length; i++) {
            const layer = this.layers[i];
            const isOpaqueBgLayer = i === 0;
            const defaultBg = isOpaqueBgLayer ? [0, 0, 0] : [-1, -1, -1];

            const newCells: Cell[][] = Array.from({ length: newHeight }, () =>
                Array.from({ length: newWidth }, () => ({
                    char: '',
                    fg: [204, 204, 204] as [number, number, number],
                    bg: defaultBg as [number, number, number],
                    bold: false,
                    italic: false,
                    underline: false
                }))
            );

            for (let r = 0; r < newHeight; r++) {
                for (let c = 0; c < newWidth; c++) {
                    if (r < this.height && c < this.width) {
                        const src = layer.cells[r][c];
                        newCells[r][c] = {
                            char: src.char,
                            fg: [...src.fg] as [number, number, number],
                            bg: [...src.bg] as [number, number, number],
                            bold: src.bold,
                            italic: src.italic,
                            underline: src.underline
                        };
                    }
                }
            }

            if (layer.overflowCells) {
                for (const [key, cell] of layer.overflowCells.entries()) {
                    const [cStr, rStr] = key.split(',');
                    const c = Number(cStr);
                    const r = Number(rStr);
                    if (c >= 0 && c < newWidth && r >= 0 && r < newHeight) {
                        newCells[r][c] = {
                            char: cell.char,
                            fg: [...cell.fg] as [number, number, number],
                            bg: [...cell.bg] as [number, number, number],
                            bold: cell.bold,
                            italic: cell.italic,
                            underline: cell.underline
                        };
                        layer.overflowCells.delete(key);
                    }
                }
            }

            layer.cells = newCells;
        }

        this.width = newWidth;
        this.height = newHeight;
        this.notify();
    }
}

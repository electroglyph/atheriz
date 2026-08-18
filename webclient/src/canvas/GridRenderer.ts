import { CanvasState } from '../state/CanvasState';
import { CellMetrics } from '../utils/fontMetrics';
import { Cell } from '../types';

export class GridRenderer {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private state: CanvasState;
    private metrics: CellMetrics;

    // Optional overlays for previewing tool actions
    private previewCells: Map<string, Cell> = new Map();
    private selectedCells: Set<string> = new Set();
    private roomCells: Set<string> = new Set();
    private roomColor: string = '#00CCCC';
    private roomVisible: boolean = true;

    private renderBound = () => this.render();

    constructor(canvas: HTMLCanvasElement, state: CanvasState, metrics: CellMetrics) {
        this.canvas = canvas;
        const ctx = canvas.getContext('2d', { alpha: false }); // Optimize for no transparency
        if (!ctx) throw new Error("Could not get 2D context");
        this.ctx = ctx;
        this.state = state;
        this.metrics = metrics;

        // Resize the actual canvas element based on state * metrics
        this.resize();
        this.state.onChange(this.renderBound);
    }

    public resize() {
        this.canvas.width = this.state.width * this.metrics.width;
        this.canvas.height = this.state.height * this.metrics.height;
        this.canvas.style.width = `${this.canvas.width}px`;
        this.canvas.style.height = `${this.canvas.height}px`;

        // Setting width/height resets context state, so re-apply font
        this.ctx.font = this.metrics.font;
        this.ctx.textBaseline = "middle";
        this.ctx.textAlign = "center";
        
        this.render();
    }

    public updateState(newState: CanvasState) {
        this.state.offChange(this.renderBound);
        this.state = newState;
        this.state.onChange(this.renderBound);
        this.resize();
    }

    public updateMetrics(metrics: CellMetrics) {
        this.metrics = metrics;
        this.resize();
    }

    public setPreview(cells: {col: number, row: number, cell: Cell}[]) {
        this.previewCells.clear();
        for (const c of cells) {
            this.previewCells.set(`${c.col},${c.row}`, c.cell);
        }
        this.render();
    }

    public clearPreview() {
        if (this.previewCells.size > 0) {
            this.previewCells.clear();
            this.render();
        }
    }

    public setSelection(cells: Set<string>) {
        this.selectedCells = cells;
        this.render();
    }

    public getSelectedCells(): Set<string> {
        return this.selectedCells;
    }

    public clearSelection() {
        if (this.selectedCells.size > 0) {
            this.selectedCells = new Set();
            this.render();
        }
    }

    public setRoomCells(cells: Set<string>) {
        this.roomCells = cells;
        this.render();
    }

    public setRoomColor(color: string) {
        this.roomColor = color;
        this.render();
    }

    public setRoomVisible(visible: boolean) {
        this.roomVisible = visible;
        this.render();
    }

    public render() {
        const { width, height } = this.metrics;

        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        const bgColors = new Map<string, Path2D>();
        const chars = new Map<string, {text: string, x: number, y: number}[]>();
        const underlines: {x: number, y: number, w: number, color: string}[] = [];

        const addBg = (col: number, row: number, r: number, g: number, b: number) => {
            if (r === 0 && g === 0 && b === 0) return;
            const key = `rgb(${r},${g},${b})`;
            let path = bgColors.get(key);
            if (!path) {
                path = new Path2D();
                bgColors.set(key, path);
            }
            path.rect(col * width, row * height, width, height);
        };

        const fontKey = (r: number, g: number, b: number, opacity: number, bold: boolean, italic: boolean) => {
            const colorKey = opacity === 1.0 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${opacity})`;
            return `${colorKey}|${bold?'b':''}${italic?'i':''}`;
        };

        const addChar = (col: number, row: number, char: string, r: number, g: number, b: number, opacity: number = 1.0, bold?: boolean, italic?: boolean, underline?: boolean) => {
            if (!char || char === ' ') return;
            const key = fontKey(r, g, b, opacity, !!bold, !!italic);
            let list = chars.get(key);
            if (!list) {
                list = [];
                chars.set(key, list);
            }
            list.push({ text: char, x: col * width + width / 2, y: row * height + height / 2 });

            if (underline) {
                const colorKey = opacity === 1.0 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${opacity})`;
                underlines.push({ x: col * width, y: row * height + height - 2, w: width, color: colorKey });
            }
        };

        for (let row = 0; row < this.state.height; row++) {
            for (let col = 0; col < this.state.width; col++) {
                const previewCell = this.previewCells.get(`${col},${row}`);
                const baseCell = this.state.getCompositeCell(col, row) || { char: '', fg: [204, 204, 204] as [number, number, number], bg: [0, 0, 0] as [number, number, number] };
                const cell = previewCell ?? baseCell;
                const opacity = previewCell ? 0.7 : 1.0;

                addBg(col, row, cell.bg[0], cell.bg[1], cell.bg[2]);
                addChar(col, row, cell.char, cell.fg[0], cell.fg[1], cell.fg[2], opacity, cell.bold, cell.italic, cell.underline);
            }
        }

        for (const [color, path] of bgColors.entries()) {
            this.ctx.fillStyle = color;
            this.ctx.fill(path);
        }

        // Enhance grid lines over everything but text
        this.ctx.strokeStyle = '#222';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        for (let col = 1; col < this.state.width; col++) {
            this.ctx.moveTo(col * width, 0);
            this.ctx.lineTo(col * width, this.canvas.height);
        }
        for (let row = 1; row < this.state.height; row++) {
            this.ctx.moveTo(0, row * height);
            this.ctx.lineTo(this.canvas.width, row * height);
        }
        this.ctx.stroke();

        const strokeCellOutlines = (cells: Set<string>) => {
            this.ctx.beginPath();
            for (const key of cells) {
                const parts = key.split(',');
                const col = parseInt(parts[0]);
                const row = parseInt(parts[1]);
                const x = col * width;
                const y = row * height;
                this.ctx.moveTo(x, y);
                this.ctx.lineTo(x + width, y);
                this.ctx.moveTo(x + width, y);
                this.ctx.lineTo(x + width, y + height);
                this.ctx.moveTo(x + width, y + height);
                this.ctx.lineTo(x, y + height);
                this.ctx.moveTo(x, y + height);
                this.ctx.lineTo(x, y);
            }
            this.ctx.stroke();
        };

        if (this.roomVisible && this.roomCells.size > 0) {
            this.ctx.strokeStyle = this.roomColor;
            this.ctx.lineWidth = 2;
            strokeCellOutlines(this.roomCells);
        }

        if (this.selectedCells.size > 0) {
            this.ctx.strokeStyle = '#FFCC00';
            this.ctx.lineWidth = 2;
            strokeCellOutlines(this.selectedCells);
        }

        const baseFont = this.metrics.font;

        for (const [key, list] of chars.entries()) {
            const [colorKey] = key.split('|');
            const hasBold = key.includes('|b');
            const hasItalic = key.includes('i');
            let fontStr = '';
            if (hasBold && hasItalic) fontStr = `bold italic ${baseFont}`;
            else if (hasBold) fontStr = `bold ${baseFont}`;
            else if (hasItalic) fontStr = `italic ${baseFont}`;
            else fontStr = baseFont;

            this.ctx.font = fontStr;
            this.ctx.fillStyle = colorKey;
            for (const item of list) {
                this.ctx.fillText(item.text, item.x, item.y);
            }
        }

        if (underlines.length > 0) {
            this.ctx.lineWidth = 1;
            this.ctx.beginPath();
            for (const ul of underlines) {
                this.ctx.strokeStyle = ul.color;
                this.ctx.moveTo(ul.x, ul.y);
                this.ctx.lineTo(ul.x + ul.w, ul.y);
            }
            this.ctx.stroke();
        }

        this.ctx.font = baseFont;
    }
}

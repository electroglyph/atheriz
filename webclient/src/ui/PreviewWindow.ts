import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { CanvasState } from '../state/CanvasState';
import { buildCompositeAnsiPreview } from '../export/AnsiPreview';
import { measureCellMetrics, CellMetrics } from '../utils/fontMetrics';
import { closeOtherModals } from './modalHelper';

const PREVIEW_MAX_FONT_SIZE = 20;
const PREVIEW_MIN_FONT_SIZE = 2;

export function pickPreviewFontSize(
    measure: (fontSize: number) => CellMetrics,
    width: number,
    height: number,
    availW: number,
    availH: number,
): number {
    let firstFit = -1;
    for (let fs = PREVIEW_MAX_FONT_SIZE; fs >= PREVIEW_MIN_FONT_SIZE; fs--) {
        const m = measure(fs);
        if (m.width * width > availW || m.height * height > availH) continue;
        if (Number.isInteger(m.advance)) return fs;
        if (firstFit === -1) firstFit = fs;
    }
    return firstFit === -1 ? PREVIEW_MIN_FONT_SIZE : firstFit;
}

export class PreviewWindow {
    private modal: HTMLElement;
    private termContainer: HTMLElement = document.createElement('div');
    private terminal: Terminal | null = null;
    private getState: () => CanvasState;
    private getFont: () => string;

    private win!: HTMLElement;
    private titleBar!: HTMLElement;
    private dragging = false;
    private dragStartX = 0;
    private dragStartY = 0;
    private winStartLeft = 0;
    private winStartTop = 0;
    private winW = 0;
    private winH = 0;

    private boundWindowMouseMove = (e: MouseEvent) => {
        if (!this.dragging) return;

        let newLeft = this.winStartLeft + e.clientX - this.dragStartX;
        let newTop = this.winStartTop + e.clientY - this.dragStartY;

        // Simple boundary clamping to keep it on screen
        const maxX = window.innerWidth - this.winW;
        const maxY = window.innerHeight - this.winH;

        newLeft = Math.max(0, Math.min(newLeft, maxX));
        newTop = Math.max(0, Math.min(newTop, maxY));

        this.win.style.left = newLeft + 'px';
        this.win.style.top = newTop + 'px';
    };

    private boundWindowMouseUp = () => {
        if (this.dragging) {
            this.dragging = false;
            this.titleBar.style.cursor = 'grab';
        }
    };

    private boundWindowKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && this.isOpen()) this.close();
    };

    constructor(getState: () => CanvasState, getFont: () => string) {
        this.getState = getState;
        this.getFont = getFont;
        this.modal = this.buildModal();
        document.body.appendChild(this.modal);
    }

    public destroy() {
        window.removeEventListener('mousemove', this.boundWindowMouseMove);
        window.removeEventListener('mouseup', this.boundWindowMouseUp);
        window.removeEventListener('keydown', this.boundWindowKeyDown);
    }

    private buildModal(): HTMLElement {
        const modal = document.createElement('div');
        modal.id = 'preview-window';
        modal.style.cssText = `
            display: none;
            position: fixed;
            inset: 0;
            z-index: 9999;
            background: rgba(0,0,0,0.85);
            align-items: center;
            justify-content: center;
        `;

        const win = document.createElement('div');
        win.style.cssText = `
            display: flex;
            flex-direction: column;
            background: #1a1a1a;
            border: 1px solid #444;
            border-radius: 8px;
            box-shadow: 0 8px 40px rgba(0,0,0,0.8);
            overflow: hidden;
            max-width: 96vw;
            max-height: 96vh;
        `;

        // Title bar
        const titleBar = document.createElement('div');
        titleBar.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 14px;
            background: #111;
            border-bottom: 1px solid #333;
            user-select: none;
            cursor: grab;
            height: 34px;
            box-sizing: border-box;
        `;
        const title = document.createElement('span');
        title.textContent = 'Preview';
        title.style.cssText = 'color:#ccc; font-family: sans-serif; font-size: 13px; font-weight: 600;';

        const closeBtn = document.createElement('button');
        closeBtn.textContent = '✕';
        closeBtn.title = 'Close';
        closeBtn.style.cssText = `
            background: none; border: none; color: #888; font-size: 16px;
            cursor: pointer; padding: 2px 6px; border-radius: 4px; line-height: 1;
        `;
        closeBtn.onmouseenter = () => closeBtn.style.color = '#fff';
        closeBtn.onmouseleave = () => closeBtn.style.color = '#888';
        closeBtn.addEventListener('click', () => this.close());

        titleBar.appendChild(title);
        titleBar.appendChild(closeBtn);

        // Drag-to-move
        titleBar.addEventListener('mousedown', (e) => {
            if (e.target === closeBtn) return;
            this.dragging = true;

            // 1. Capture the current rendered position FIRST
            const rect = win.getBoundingClientRect();
            this.winW = rect.width;
            this.winH = rect.height;
            this.winStartLeft = rect.left;
            this.winStartTop = rect.top;

            // 2. Now switch to absolute positioning and remove flex centering.
            // This prevents the window from jumping to the top-left before we capture it.
            modal.style.alignItems = 'flex-start';
            modal.style.justifyContent = 'flex-start';

            win.style.position = 'absolute';
            win.style.left = this.winStartLeft + 'px';
            win.style.top = this.winStartTop + 'px';
            win.style.margin = '0';

            this.dragStartX = e.clientX;
            this.dragStartY = e.clientY;

            titleBar.style.cursor = 'grabbing';
            e.preventDefault();
        });

        this.win = win;
        this.titleBar = titleBar;

        window.addEventListener('mousemove', this.boundWindowMouseMove);
        window.addEventListener('mouseup', this.boundWindowMouseUp);

        // Terminal container
        this.termContainer = document.createElement('div');
        this.termContainer.style.cssText = 'overflow: hidden; padding: 10px;';

        win.appendChild(titleBar);
        win.appendChild(this.termContainer);
        modal.appendChild(win);

        // Close on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.close();
        });

        // Close on Escape
        window.addEventListener('keydown', this.boundWindowKeyDown);

        return modal;
    }

    private isOpen(): boolean {
        return this.modal.style.display !== 'none';
    }

    public open() {
        closeOtherModals('preview-window');
        const state = this.getState();
        const fontFamily = this.getFont();

        // Ensure we reset styles to default for centering calculation
        const win = this.modal.firstElementChild as HTMLElement;
        if (win) {
            win.style.position = '';
            win.style.left = '';
            win.style.top = '';
            win.style.margin = '';
        }
        this.modal.style.alignItems = 'center';
        this.modal.style.justifyContent = 'center';

        // Calculate the best font size that fits 90% of the viewport accurately
        // Padding: window padding (20) + win padding (20)
        const availW = window.innerWidth  * 0.90 - 40; 
        // Title bar (34) + win padding (20) + modal padding/buffer
        const availH = window.innerHeight * 0.90 - 70; 

        // Use the same font metrics as the editor grid so the preview renders
        // at an integral pixel scale; fractional advances anti-alias bitmap
        // fonts into mush and the preview colors no longer match the editor.
        const fontSize = pickPreviewFontSize((fs) => measureCellMetrics(fontFamily, fs), state.width, state.height, availW, availH);

        if (this.terminal) {
            this.terminal.dispose();
            this.terminal = null;
        } else {
            this.termContainer.innerHTML = '';
        }

        const term = new Terminal({
            cols: state.width,
            rows: state.height,
            fontSize,
            fontFamily: `${fontFamily}, monospace`,
            theme: {
                background: '#000000',
                foreground: '#cccccc',
            },
            allowTransparency: false,
            scrollback: 0,
            cursorStyle: 'bar',
            cursorBlink: false,
            disableStdin: true,
        });

        term.open(this.termContainer);

        // Write the composited canvas
        const ansi = buildCompositeAnsiPreview(state);
        term.write(ansi);

        this.terminal = term;

        // Show the modal
        this.modal.style.display = 'flex';
    }

    public close() {
        this.modal.style.display = 'none';
        if (this.terminal) {
            this.terminal.dispose();
            this.terminal = null;
        }
    }
}

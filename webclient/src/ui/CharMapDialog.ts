import { GlyphScanner } from '../utils/GlyphScanner';
import { closeOtherModals } from './modalHelper';

function escapeCss(value: string): string {
    if (typeof CSS !== 'undefined' && typeof (CSS as unknown as { escape?: (s: string) => string }).escape === 'function') {
        return (CSS as unknown as { escape: (s: string) => string }).escape(value);
    }
    return value.replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`);
}

export class CharMapDialog {
    private modal: HTMLElement;
    private scrollContainer: HTMLElement;
    private innerContainer: HTMLElement;
    private selectedPreview: HTMLElement;
    private cancelBtn: HTMLElement;
    private confirmBtn: HTMLElement;
    
    private selectedChars: Set<string> = new Set();
    private onConfirm: (chars: string[]) => void;
    
    private readonly COLS = 16;
    private readonly ROW_HEIGHT = 32;
    private totalRows: number = 0;
    private validGlyphs: number[] = [];
    
    // A cache of currently rendered row elements to recycle or replace
    private activeRows: Map<number, HTMLElement> = new Map();

    constructor(onConfirm: (chars: string[]) => void) {
        this.onConfirm = onConfirm;
        
        this.modal = document.getElementById('char-map-modal')!;
        this.scrollContainer = document.getElementById('char-map-scroll-container')!;
        this.innerContainer = document.getElementById('char-map-inner')!;
        this.selectedPreview = document.getElementById('char-map-selection')!;
        this.cancelBtn = document.getElementById('btn-char-cancel')!;
        this.confirmBtn = document.getElementById('btn-char-confirm')!;
        
        this.scrollContainer.addEventListener('scroll', () => this.handleScroll());
        this.cancelBtn.addEventListener('click', () => this.close());
        this.confirmBtn.addEventListener('click', () => {
            this.onConfirm(Array.from(this.selectedChars));
            this.close();
        });
        
        // Close on clicking outside
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.close();
        });
    }

    public async open(fontFamily: string) {
        closeOtherModals('char-map-modal');
        this.selectedChars.clear();
        this.updatePreview();
        this.modal.classList.remove('hidden');

        // Show scanning UI
        const scanStatus = document.getElementById('char-scan-status');
        if (scanStatus) {
            scanStatus.style.display = 'block';
            scanStatus.textContent = `Scanning for characters...`;
        }

        this.validGlyphs = [];
        this.totalRows = 0;
        this.innerContainer.style.height = '0px';
        this.innerContainer.innerHTML = '';
        this.activeRows.clear();
        
        try {
            this.validGlyphs = await GlyphScanner.scanFont(fontFamily, (pct) => {
                if (scanStatus) scanStatus.textContent = `Scanning... ${pct}%`;
            });
            
            this.totalRows = Math.ceil(this.validGlyphs.length / this.COLS);
            this.innerContainer.style.height = `${this.totalRows * this.ROW_HEIGHT}px`;
            this.handleScroll(); // Trigger initial render
        } finally {
            if (scanStatus) scanStatus.style.display = 'none';
        }
    }

    public close() {
        this.modal.classList.add('hidden');
    }

    private handleScroll() {
        const scrollTop = this.scrollContainer.scrollTop;
        const viewportHeight = this.scrollContainer.clientHeight;
        
        const startRow = Math.max(0, Math.floor(scrollTop / this.ROW_HEIGHT) - 2);
        const endRow = Math.min(this.totalRows - 1, Math.ceil((scrollTop + viewportHeight) / this.ROW_HEIGHT) + 2);
        
        // Remove out of bounds rows
        for (const [rowIndex, el] of this.activeRows.entries()) {
            if (rowIndex < startRow || rowIndex > endRow) {
                el.remove();
                this.activeRows.delete(rowIndex);
            }
        }
        
        // Add visible rows that aren't rendered yet
        for (let r = startRow; r <= endRow; r++) {
            if (!this.activeRows.has(r)) {
                this.renderRow(r);
            }
        }
    }

    private renderRow(rowIndex: number) {
        const rowEl = document.createElement('div');
        rowEl.className = 'char-map-row';
        rowEl.style.top = `${rowIndex * this.ROW_HEIGHT}px`;
        
        const startIdx = rowIndex * this.COLS;
        
        for (let c = 0; c < this.COLS; c++) {
            const arrIdx = startIdx + c;
            
            const cellEl = document.createElement('div');
            cellEl.className = 'char-map-cell';
            
            if (arrIdx < this.validGlyphs.length) {
                const codePoint = this.validGlyphs[arrIdx];
                try {
                    const char = String.fromCodePoint(codePoint);
                    cellEl.textContent = char;
                    cellEl.dataset.char = char;
                    
                    if (this.selectedChars.has(char)) {
                        cellEl.classList.add('selected');
                    }
                    
                    cellEl.addEventListener('click', () => {
                        if (this.selectedChars.has(char)) {
                            this.selectedChars.delete(char);
                            cellEl.classList.remove('selected');
                        } else {
                            this.selectedChars.add(char);
                            cellEl.classList.add('selected');
                        }
                        this.updatePreview();
                    });
                    
                    cellEl.title = `U+${codePoint.toString(16).toUpperCase().padStart(4, '0')}`;
                } catch (e) {
                     cellEl.classList.add('empty');
                }
            } else {
                cellEl.classList.add('empty');
            }
            
            rowEl.appendChild(cellEl);
        }
        
        this.innerContainer.appendChild(rowEl);
        this.activeRows.set(rowIndex, rowEl);
    }
    
    private updatePreview() {
        this.selectedPreview.innerHTML = '';
        if (this.selectedChars.size === 0) {
            this.selectedPreview.textContent = 'Select characters to add...';
            this.selectedPreview.style.color = '#777';
            return;
        }
        
        this.selectedPreview.style.color = '#fff';
        for (const char of this.selectedChars) {
            const badge = document.createElement('span');
            badge.className = 'selected-char-badge';
            badge.textContent = char;
            badge.title = 'Click to remove';
            badge.addEventListener('click', () => {
                this.selectedChars.delete(char);
                this.updatePreview();
                const escaped = escapeCss(char);
                for (const rowEl of this.activeRows.values()) {
                    const cell = rowEl.querySelector(`[data-char="${escaped}"]`);
                    if (cell) cell.classList.remove('selected');
                }
            });
            this.selectedPreview.appendChild(badge);
        }
    }
}

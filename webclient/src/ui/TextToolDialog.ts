import { CanvasState } from '../state/CanvasState';
import { UndoStack } from '../state/UndoStack';
import { AppState } from '../types';
import { renderTextToAnsiLayer } from '../utils/TextToANSI';
import { ChafaConfig, DEFAULT_CHAFA_OPTIONS } from '../utils/chafaDefaults';
import { CellMetrics } from '../utils/fontMetrics';
import { GoogleFontPicker } from './GoogleFontPicker';
import { loadFontFull, fontNameToCSS } from '../utils/googleFontLoader';

export class TextToolDialog {
    private modal: HTMLElement;
    private input: HTMLTextAreaElement;
    private fontSelect: HTMLSelectElement;
    private styleSelect: HTMLSelectElement;
    private maxWidthInput: HTMLInputElement;
    private maxWidthVal: HTMLElement;
    private stretchInput: HTMLInputElement;
    private stretchVal: HTMLElement;
    private previewCanvas: HTMLCanvasElement;
    
    private btnCancel: HTMLButtonElement;
    private btnConfirm: HTMLButtonElement;
    private btnGoogleFonts: HTMLButtonElement;
    private alignSelect: HTMLSelectElement;
    private chafaOptionsContainer!: HTMLElement;

    private userConfig!: ChafaConfig;

    private systemFontsLoaded = false;
    private googleFontPicker: GoogleFontPicker;
    private onConfirm: (state: CanvasState) => void;
    private appState: AppState;
    private canvasState: CanvasState;
    private getCellMetrics: () => CellMetrics;
    private undoStack: UndoStack | null = null;

    constructor(appState: AppState, canvasState: CanvasState, onConfirm: (state: CanvasState) => void, getCellMetrics: () => CellMetrics, undoStack?: UndoStack) {
        this.appState = appState;
        this.canvasState = canvasState;
        this.onConfirm = onConfirm;
        this.getCellMetrics = getCellMetrics;
        this.undoStack = undoStack ?? null;

        this.modal = document.getElementById('text-tool-modal') as HTMLElement;
        this.input = document.getElementById('text-tool-input') as HTMLTextAreaElement;
        this.fontSelect = document.getElementById('text-tool-font') as HTMLSelectElement;
        this.styleSelect = document.getElementById('text-tool-style') as HTMLSelectElement;
        this.maxWidthInput = document.getElementById('text-tool-max-width') as HTMLInputElement;
        this.maxWidthVal = document.getElementById('text-tool-max-width-val') as HTMLElement;
        this.stretchInput = document.getElementById('text-tool-stretch') as HTMLInputElement;
        this.stretchVal = document.getElementById('text-tool-stretch-val') as HTMLElement;
        this.previewCanvas = document.getElementById('text-tool-preview') as HTMLCanvasElement;
        
        this.btnCancel = document.getElementById('btn-text-cancel') as HTMLButtonElement;
        this.btnConfirm = document.getElementById('btn-text-confirm') as HTMLButtonElement;
        this.btnGoogleFonts = document.getElementById('text-tool-google-fonts-btn') as HTMLButtonElement;
        this.alignSelect = document.getElementById('text-tool-align') as HTMLSelectElement;
        this.chafaOptionsContainer = document.getElementById('text-chafa-options-container')!;

        this.googleFontPicker = new GoogleFontPicker((family) => this.selectGoogleFont(family));

        this.userConfig = { ...DEFAULT_CHAFA_OPTIONS, symbols: 'block' };
        this.buildOptionsUI();
        this.bindEvents();
    }

    public updateCanvasState(state: CanvasState) {
        this.canvasState = state;
    }

    private bindEvents() {
        this.btnCancel.addEventListener('click', () => this.close());
        
        this.btnConfirm.addEventListener('click', async () => {
            const text = this.input.value;
            if (!text) {
                this.close();
                return;
            }
            let maxWidth = parseInt(this.maxWidthInput.value, 10);
            if (isNaN(maxWidth) || maxWidth < 1) maxWidth = 80;
            
            this.btnConfirm.disabled = true;
            this.btnConfirm.innerText = 'Converting...';

            
            try {
                if (this.undoStack) this.undoStack.push(this.canvasState);
                await renderTextToAnsiLayer(
                    text,
                    maxWidth,
                    this.canvasState,
                    this.userConfig,
                    this.previewCanvas,
                    this.getCellMetrics(),
                );
                this.onConfirm(this.canvasState);
                this.close();
            } catch (e) {
                console.error("Text conversion failed:", e);
                alert("Conversion failed. Check console.");
            } finally {
                this.btnConfirm.disabled = false;
                this.btnConfirm.innerText = 'Convert to ANSI Layer';
            }
        });

        this.input.addEventListener('input', () => this.schedulePreview());
        this.fontSelect.addEventListener('change', () => this.schedulePreview());
        this.styleSelect.addEventListener('change', () => this.schedulePreview());
        this.stretchInput.addEventListener('input', () => {
            this.stretchVal.innerText = `${this.stretchInput.value}%`;
            this.schedulePreview();
        });
        this.maxWidthInput.addEventListener('input', () => {
            this.maxWidthVal.innerText = this.maxWidthInput.value;
            this.schedulePreview();
        });

        this.fontSelect.addEventListener('focus', () => this.loadSystemFonts());
        this.btnGoogleFonts.addEventListener('click', () => this.googleFontPicker.open());
        this.alignSelect.addEventListener('change', () => this.schedulePreview());
    }

    private previewTimer: ReturnType<typeof setTimeout> | null = null;

    private schedulePreview() {
        if (this.previewTimer !== null) clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => {
            this.previewTimer = null;
            this.updatePreview();
        }, 80);
    }

    private async updatePreview() {
        try {
            const text = this.input.value;
            if (!text) {
                const ctx = this.previewCanvas.getContext('2d');
                if (ctx) {
                    this.previewCanvas.width = 100;
                    this.previewCanvas.height = 100;
                    ctx.clearRect(0, 0, 100, 100);
                }
                return;
            }

            const fontFamilies = this.fontSelect.value || 'Arial';
            const fontStyle = this.styleSelect.value || 'normal';
            const align = (this.alignSelect.value || 'left') as CanvasTextAlign;
            let stretch = parseInt(this.stretchInput.value, 10) / 100;
            if (isNaN(stretch) || stretch <= 0) stretch = 1;

            const fontSize = 96;
            const fontStr = fontStyle === 'normal'
                ? `${fontSize}px ${fontFamilies}`
                : `${fontStyle} ${fontSize}px ${fontFamilies}`;

            try { await document.fonts.load(fontStr, text); } catch (_) {}
            await document.fonts.ready;

            // Split into lines so multi-line input renders as stacked rows
            const lines = text.split('\n');
            const lineHeight = Math.round(fontSize * 1.2);
            const canvasW = 1200;
            const canvasH = Math.max(200, lineHeight * lines.length + 40);

            this.previewCanvas.width = canvasW;
            this.previewCanvas.height = canvasH;
            const ctx = this.previewCanvas.getContext('2d')!;

            const bgColor = `rgb(${this.appState.bgColor[0]},${this.appState.bgColor[1]},${this.appState.bgColor[2]})`;
            const fgColor = `rgb(${this.appState.fgColor[0]},${this.appState.fgColor[1]},${this.appState.fgColor[2]})`;
            ctx.fillStyle = bgColor;
            ctx.fillRect(0, 0, canvasW, canvasH);

            ctx.font = fontStr;
            ctx.fillStyle = fgColor;
            ctx.textBaseline = 'top';

            // Determine x anchor position based on alignment
            let anchorX: number;
            if (align === 'center') {
                anchorX = canvasW / 2;
            } else if (align === 'right') {
                anchorX = canvasW - 20;
            } else {
                anchorX = 20;
            }

            ctx.save();
            // Apply horizontal stretch around the anchor point
            ctx.translate(anchorX, 0);
            ctx.scale(stretch, 1);
            ctx.translate(-anchorX / stretch, 0);

            ctx.textAlign = align;

            for (let i = 0; i < lines.length; i++) {
                ctx.fillText(lines[i], anchorX / stretch, 20 + i * lineHeight);
            }
            ctx.restore();
        } catch (err) {
            console.error('Error drawing preview:', err);
        }
    }

    private initFonts() {
        if (this.fontSelect.options.length > 0) return;

        const localFonts = [
            { name: 'Unifont', val: 'Unifont' },
            { name: 'KreativeSquare', val: 'KreativeSquare' },
            { name: 'Fira Code', val: "'Fira Code', 'FiraCode'" },
            { name: 'Arial', val: 'Arial' },
            { name: 'Times New Roman', val: '"Times New Roman"' },
            { name: 'Impact', val: 'Impact' },
            { name: 'Courier New', val: '"Courier New"' }
        ];

        for (const f of localFonts) {
            const opt = document.createElement('option');
            opt.value = f.val;
            opt.textContent = f.name;
            this.fontSelect.appendChild(opt);
        }
        
        // Try to sync with app font
        const matchesApp = Array.from(this.fontSelect.options).find(o => o.value === this.appState.fontFamily);
        if (matchesApp) {
            this.fontSelect.value = this.appState.fontFamily;
        } else {
            this.fontSelect.value = 'Arial';
        }
    }

    private async loadSystemFonts() {
        if (this.systemFontsLoaded) return;
        this.systemFontsLoaded = true;

        try {
            if ('queryLocalFonts' in window) {
                // @ts-ignore
                const fonts = await window.queryLocalFonts();
                const familySet = new Set<string>();
                for (const f of fonts) {
                    familySet.add(f.family);
                }

                const sep = document.createElement('option');
                sep.disabled = true;
                sep.textContent = '── System Fonts ──';
                this.fontSelect.appendChild(sep);

                const sorted = Array.from(familySet).sort();
                for (const family of sorted) {
                    const opt = document.createElement('option');
                    opt.value = `"${family}"`;
                    opt.textContent = family;
                    this.fontSelect.appendChild(opt);
                }
            }
        } catch (e) {
            console.error('Failed to load system fonts for Text tool:', e);
            this.systemFontsLoaded = false;
        }
    }

    private async selectGoogleFont(family: string) {
        await loadFontFull(family);
        const cssVal = fontNameToCSS(family);

        const existing = Array.from(this.fontSelect.options).find(o => o.value === cssVal);
        if (existing) {
            this.fontSelect.value = cssVal;
        } else {
            const sep = document.createElement('option');
            sep.disabled = true;
            sep.textContent = '── Google Fonts ──';
            const hasGFSection = Array.from(this.fontSelect.options).some(o => o.textContent === '── Google Fonts ──');
            if (!hasGFSection) {
                this.fontSelect.appendChild(sep);
            }
            const opt = document.createElement('option');
            opt.value = cssVal;
            opt.textContent = family;
            this.fontSelect.appendChild(opt);
            this.fontSelect.value = cssVal;
        }
        this.schedulePreview();
    }

    public async open() {
        this.initFonts();
        this.input.value = '';
        this.maxWidthInput.max = this.canvasState.width.toString();
        this.maxWidthInput.value = this.canvasState.width.toString();
        this.maxWidthVal.innerText = this.canvasState.width.toString();
        this.stretchInput.value = '100';
        this.stretchVal.innerText = '100%';
        await this.updatePreview(); // Wait for initial blank preview to render
        this.modal.classList.remove('hidden');
        this.input.focus();
    }

    public close() {
        this.modal.classList.add('hidden');
    }

    private buildOptionsUI() {
        this.chafaOptionsContainer.innerHTML = '';
        const keys = Object.keys(DEFAULT_CHAFA_OPTIONS) as (keyof ChafaConfig)[];

        const enumMap: Record<string, string[]> = {
            format: ['CHAFA_PIXEL_MODE_SYMBOLS', 'CHAFA_PIXEL_MODE_SIXELS', 'CHAFA_PIXEL_MODE_KITTY', 'CHAFA_PIXEL_MODE_ITERM2'],
            colors: [
                'CHAFA_CANVAS_MODE_TRUECOLOR', 
                'CHAFA_CANVAS_MODE_INDEXED_256', 
                'CHAFA_CANVAS_MODE_INDEXED_240', 
                'CHAFA_CANVAS_MODE_INDEXED_16', 
                'CHAFA_CANVAS_MODE_INDEXED_16_8', 
                'CHAFA_CANVAS_MODE_INDEXED_8', 
                'CHAFA_CANVAS_MODE_FGBG_BGFG', 
                'CHAFA_CANVAS_MODE_FGBG'
            ],
            colorExtractor: ['CHAFA_COLOR_EXTRACTOR_AVERAGE', 'CHAFA_COLOR_EXTRACTOR_MEDIAN'],
            colorSpace: ['CHAFA_COLOR_SPACE_RGB', 'CHAFA_COLOR_SPACE_DIN99D'],
            dither: ['CHAFA_DITHER_MODE_NONE', 'CHAFA_DITHER_MODE_ORDERED', 'CHAFA_DITHER_MODE_DIFFUSION', 'CHAFA_DITHER_MODE_NOISE']
        };
        
        for (const key of keys) {
            // Lock format to Symbols by hiding the option entirely
            if (key === 'format') continue;

            const val = DEFAULT_CHAFA_OPTIONS[key];
            const div = document.createElement('div');
            const label = document.createElement('label');
            label.style.display = 'block';
            label.style.fontSize = '0.8em';
            label.style.color = '#ccc';
            label.style.marginBottom = '2px';
            label.innerText = key;
            
            let control: HTMLElement;
            
            if (enumMap[key]) {
                const select = document.createElement('select');
                select.style.width = '100%';
                select.style.padding = '4px';
                select.style.backgroundColor = '#333';
                select.style.color = '#fff';
                select.style.border = '1px solid #555';
                select.style.borderRadius = '4px';
                select.style.fontSize = '12px';

                for (const optVal of enumMap[key]) {
                    const opt = document.createElement('option');
                    opt.value = optVal;
                    // Prettify name: CHAFA_PIXEL_MODE_SYMBOLS -> Symbols
                    const parts = optVal.split('_');
                    opt.textContent = parts[parts.length - 1].toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
                    if (optVal === val) opt.selected = true;
                    select.appendChild(opt);
                }
                select.addEventListener('change', () => {
                    (this.userConfig[key] as any) = select.value;
                });
                control = select;
            } else if (typeof val === 'boolean') {
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = val;
                input.style.verticalAlign = 'middle';
                input.style.marginRight = '5px';
                input.addEventListener('change', () => {
                    (this.userConfig[key] as boolean) = input.checked;
                });
                label.prepend(input);
                control = document.createElement('span'); 
            } else if (typeof val === 'number') {
                const input = document.createElement('input');
                input.type = 'number';
                input.step = key.includes('threshold') || key.includes('Intensity') || key.includes('Ratio') ? "0.1" : "1";
                input.value = val.toString();
                input.style.width = '100%';
                input.style.padding = '4px';
                input.style.backgroundColor = '#333';
                input.style.color = '#fff';
                input.style.border = '1px solid #555';
                input.style.borderRadius = '4px';
                input.style.fontSize = '12px';
                input.addEventListener('change', () => {
                    (this.userConfig[key] as number) = parseFloat(input.value) || 0;
                });
                control = input;
            } else {
                const input = document.createElement('input');
                input.type = 'text';
                input.value = val as string;
                input.style.width = '100%';
                input.style.padding = '4px';
                input.style.backgroundColor = '#333';
                input.style.color = '#fff';
                input.style.border = '1px solid #555';
                input.style.borderRadius = '4px';
                input.style.fontSize = '12px';
                input.addEventListener('change', () => {
                    (this.userConfig[key] as string) = input.value;
                });
                control = input;
            }
            
            div.appendChild(label);
            if (control.tagName !== 'SPAN') {
                div.appendChild(control);
            }

            if (key === 'symbols') {
                const helpText = document.createElement('div');
                helpText.style.fontSize = '10px';
                helpText.style.color = '#8bb';
                helpText.style.marginTop = '4px';
                helpText.style.lineHeight = '1.3';
                helpText.innerText = 'Classes: all, none, space, solid, stipple, block, border, diagonal, dot, quad, half, hhalf, vhalf, inverted, braille, technical, geometric, ascii, legacy, sextant, wedge, wide, narrow.\nUse + to combine, - to subtract.';
                div.appendChild(helpText);
            }

            this.chafaOptionsContainer.appendChild(div);
        }
    }
}

import { ChafaConfig, DEFAULT_CHAFA_OPTIONS } from '../utils/chafaDefaults';
import { closeOtherModals } from './modalHelper';

export class ImageImportDialog {
    private modal: HTMLElement;
    private btnCancel: HTMLButtonElement;
    private btnConfirm: HTMLButtonElement;
    
    private fileInput: HTMLInputElement;
    private radios: NodeListOf<HTMLInputElement>;
    private inputW: HTMLInputElement;
    private inputH: HTMLInputElement;
    private optionsContainer: HTMLElement;
    
    private currentBuffer: ArrayBuffer | null = null;
    private origWidth: number = 1;
    private origHeight: number = 1;
    private userConfig: ChafaConfig;

    private onConfirmCallback: (buffer: ArrayBuffer, width: number, height: number, config: ChafaConfig) => void;

    constructor(onConfirm: (buffer: ArrayBuffer, width: number, height: number, config: ChafaConfig) => void) {
        this.onConfirmCallback = onConfirm;
        this.userConfig = { ...DEFAULT_CHAFA_OPTIONS };

        this.modal = document.getElementById('image-import-modal')!;
        this.btnCancel = document.getElementById('btn-import-cancel') as HTMLButtonElement;
        this.btnConfirm = document.getElementById('btn-import-confirm') as HTMLButtonElement;
        this.fileInput = document.getElementById('image-upload') as HTMLInputElement;
        
        this.radios = this.modal.querySelectorAll('input[name="import-mode"]');
        this.inputW = document.getElementById('import-width') as HTMLInputElement;
        this.inputH = document.getElementById('import-height') as HTMLInputElement;
        this.optionsContainer = document.getElementById('chafa-options-container')!;

        this.buildOptionsUI();
        this.bindEvents();
    }

    private buildOptionsUI() {
        this.optionsContainer.innerHTML = '';
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
                    const parts = optVal.split('_');
                    opt.textContent = parts[parts.length - 1].toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
                    if (optVal === val) opt.selected = true;
                    select.appendChild(opt);
                }
                select.addEventListener('change', () => {
                    (this.userConfig as unknown as Record<string, string>)[key] = select.value;
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

            this.optionsContainer.appendChild(div);
        }
    }

    private bindEvents() {
        this.fileInput.addEventListener('change', async () => {
            const file = this.fileInput.files?.[0];
            if (!file) return;

            this.currentBuffer = await file.arrayBuffer();
            this.fileInput.value = ''; // reset so we can load it again if needed
            
            const url = URL.createObjectURL(new Blob([this.currentBuffer]));
            const img = new Image();
            img.onload = () => {
                this.origWidth = img.naturalWidth || 1;
                this.origHeight = img.naturalHeight || 1;
                this.computeDims();
                closeOtherModals('image-import-modal');
                this.modal.classList.remove('hidden');
                URL.revokeObjectURL(url);
            };
            img.src = url;
            
        });

        this.btnCancel.addEventListener('click', () => {
            this.modal.classList.add('hidden');
            this.currentBuffer = null;
        });

        this.btnConfirm.addEventListener('click', () => {
            if (!this.currentBuffer) return;
            const w = parseInt(this.inputW.value) || 1;
            const h = parseInt(this.inputH.value) || 1;
            
            this.onConfirmCallback(this.currentBuffer, w, h, this.userConfig);
            this.modal.classList.add('hidden');
            this.currentBuffer = null;
        });

        this.inputW.addEventListener('input', () => this.handleDimensionChange('width'));
        this.inputH.addEventListener('input', () => this.handleDimensionChange('height'));

        for (const r of Array.from(this.radios)) {
            r.addEventListener('change', () => this.computeDims());
        }
    }
    
    private handleDimensionChange(source: 'width' | 'height') {
        const mode = Array.from(this.radios).find(r => r.checked)?.value || 'maxWidth';
        if (mode === 'custom') return;
        
        let w = parseInt(this.inputW.value) || 1;
        let h = parseInt(this.inputH.value) || 1;
        
        // Console aspects are typically 1 char wide, 2 chars tall (0.5 ratio)
        // To preserve image visually, `gridWidth / gridHeight` should approach `origW / (origH / 2)` = `(origW / origH) * 2`
        const targetVisualRatio = (this.origWidth / this.origHeight) * 2;
        
        if (source === 'width') {
            const predictedHeight = Math.max(1, Math.round(w / targetVisualRatio));
            this.inputH.value = predictedHeight.toString();
        } else {
            const predictedWidth = Math.max(1, Math.round(h * targetVisualRatio));
            this.inputW.value = predictedWidth.toString();
        }
    }

    private computeDims() {
        const mode = Array.from(this.radios).find(r => r.checked)?.value || 'maxWidth';
        if (mode === 'maxWidth') {
            this.inputW.disabled = false;
            this.inputH.disabled = true;
            this.handleDimensionChange('width');
        } else if (mode === 'maxHeight') {
            this.inputW.disabled = true;
            this.inputH.disabled = false;
            this.handleDimensionChange('height');
        } else {
            this.inputW.disabled = false;
            this.inputH.disabled = false;
        }
    }
}

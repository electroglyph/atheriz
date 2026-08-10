import { ColorAdjustOptions } from '../utils/colors';

export class ColorAdjustDialog {
    private modal: HTMLElement;
    
    private brightnessSlider: HTMLInputElement;
    private brightnessVal: HTMLElement;
    
    private contrastSlider: HTMLInputElement;
    private contrastVal: HTMLElement;
    
    private hueSlider: HTMLInputElement;
    private hueVal: HTMLElement;
    
    private saturationSlider: HTMLInputElement;
    private saturationVal: HTMLElement;
    
    private allLayersCheck: HTMLInputElement;
    
    private btnCancel: HTMLButtonElement;
    private btnApply: HTMLButtonElement;

    private onPreviewCallback: (options: ColorAdjustOptions, applyToAll: boolean) => void;
    private onApplyCallback: (options: ColorAdjustOptions, applyToAll: boolean) => void;
    private onCancelCallback: () => void;

    private isOpened: boolean = false;

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

    constructor(
        onPreview: (options: ColorAdjustOptions, applyToAll: boolean) => void,
        onApply: (options: ColorAdjustOptions, applyToAll: boolean) => void,
        onCancel: () => void
    ) {
        this.onPreviewCallback = onPreview;
        this.onApplyCallback = onApply;
        this.onCancelCallback = onCancel;

        this.modal = document.getElementById('color-adjust-modal') as HTMLElement;
        
        this.brightnessSlider = document.getElementById('color-adjust-brightness') as HTMLInputElement;
        this.brightnessVal = document.getElementById('color-adjust-brightness-val') as HTMLElement;
        
        this.contrastSlider = document.getElementById('color-adjust-contrast') as HTMLInputElement;
        this.contrastVal = document.getElementById('color-adjust-contrast-val') as HTMLElement;
        
        this.hueSlider = document.getElementById('color-adjust-hue') as HTMLInputElement;
        this.hueVal = document.getElementById('color-adjust-hue-val') as HTMLElement;
        
        this.saturationSlider = document.getElementById('color-adjust-saturation') as HTMLInputElement;
        this.saturationVal = document.getElementById('color-adjust-saturation-val') as HTMLElement;
        
        this.allLayersCheck = document.getElementById('color-adjust-all-layers') as HTMLInputElement;

        this.btnCancel = document.getElementById('color-adjust-cancel') as HTMLButtonElement;
        this.btnApply = document.getElementById('color-adjust-ok') as HTMLButtonElement;

        this.bindEvents();
    }

    private bindEvents() {
        const updatePreview = () => {
            if (!this.isOpened) return;
            
            this.brightnessVal.textContent = this.brightnessSlider.value;
            this.contrastVal.textContent = this.contrastSlider.value;
            this.hueVal.textContent = this.hueSlider.value + '°';
            this.saturationVal.textContent = this.saturationSlider.value;

            this.onPreviewCallback(this.getCurrentOptions(), this.allLayersCheck.checked);
        };

        this.brightnessSlider.addEventListener('input', updatePreview);
        this.contrastSlider.addEventListener('input', updatePreview);
        this.hueSlider.addEventListener('input', updatePreview);
        this.saturationSlider.addEventListener('input', updatePreview);
        this.allLayersCheck.addEventListener('change', updatePreview);

        this.btnCancel.addEventListener('click', () => {
            this.close();
            this.onCancelCallback();
        });

        this.btnApply.addEventListener('click', () => {
            const opts = this.getCurrentOptions();
            const all = this.allLayersCheck.checked;
            this.close();
            this.onApplyCallback(opts, all);
        });

        const win = this.modal.querySelector('.modal-content') as HTMLElement;
        const titleBar = win.querySelector('h2') as HTMLElement;
        if (titleBar) {
            titleBar.style.cursor = 'grab';
            titleBar.style.userSelect = 'none';
            this.win = win;
            this.titleBar = titleBar;

            titleBar.addEventListener('mousedown', (e) => {
                this.dragging = true;

                const rect = win.getBoundingClientRect();
                this.winW = rect.width;
                this.winH = rect.height;
                this.winStartLeft = rect.left;
                this.winStartTop = rect.top;

                this.modal.style.alignItems = 'flex-start';
                this.modal.style.justifyContent = 'flex-start';

                win.style.position = 'absolute';
                win.style.left = this.winStartLeft + 'px';
                win.style.top = this.winStartTop + 'px';
                win.style.margin = '0';
                // remove transform offset so it doesn't skew our left/top logic
                win.style.transform = 'none';

                this.dragStartX = e.clientX;
                this.dragStartY = e.clientY;

                titleBar.style.cursor = 'grabbing';
                e.preventDefault();
            });

            window.addEventListener('mousemove', this.boundWindowMouseMove);
            window.addEventListener('mouseup', this.boundWindowMouseUp);
        }
    }

    public destroy() {
        window.removeEventListener('mousemove', this.boundWindowMouseMove);
        window.removeEventListener('mouseup', this.boundWindowMouseUp);
    }

    private getCurrentOptions(): ColorAdjustOptions {
        return {
            brightness: parseInt(this.brightnessSlider.value, 10),
            contrast: parseInt(this.contrastSlider.value, 10),
            hue: parseInt(this.hueSlider.value, 10),
            saturation: parseInt(this.saturationSlider.value, 10),
        };
    }

    public open() {
        const win = this.modal.querySelector('.modal-content') as HTMLElement;
        if (win) {
            win.style.position = '';
            win.style.left = '';
            win.style.top = '';
            win.style.margin = '';
            win.style.transform = '';
        }
        this.modal.style.alignItems = 'center';
        this.modal.style.justifyContent = 'center';

        this.brightnessSlider.value = "0";
        this.contrastSlider.value = "0";
        this.hueSlider.value = "0";
        this.saturationSlider.value = "0";
        
        this.brightnessVal.textContent = "0";
        this.contrastVal.textContent = "0";
        this.hueVal.textContent = "0°";
        this.saturationVal.textContent = "0";
        
        this.allLayersCheck.checked = false;
        
        this.isOpened = true;
        this.modal.classList.remove('hidden');
    }

    public close() {
        this.isOpened = false;
        this.modal.classList.add('hidden');
    }
}

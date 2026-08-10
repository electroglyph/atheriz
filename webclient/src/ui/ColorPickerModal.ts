import { Color } from '../types';
import { rgbToHex, hexToRgb, cssColor } from '../utils/colors';

function hsvToRgb(h: number, s: number, v: number): Color {
    s /= 100;
    v /= 100;
    const c = v * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = v - c;
    let r1: number, g1: number, b1: number;
    if (h < 60) { r1 = c; g1 = x; b1 = 0; }
    else if (h < 120) { r1 = x; g1 = c; b1 = 0; }
    else if (h < 180) { r1 = 0; g1 = c; b1 = x; }
    else if (h < 240) { r1 = 0; g1 = x; b1 = c; }
    else if (h < 300) { r1 = x; g1 = 0; b1 = c; }
    else { r1 = c; g1 = 0; b1 = x; }
    return [
        Math.round((r1 + m) * 255),
        Math.round((g1 + m) * 255),
        Math.round((b1 + m) * 255),
    ];
}

function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const d = max - min;
    let h = 0;
    if (d !== 0) {
        if (max === r) h = 60 * (((g - b) / d) % 6);
        else if (max === g) h = 60 * ((b - r) / d + 2);
        else h = 60 * ((r - g) / d + 4);
    }
    if (h < 0) h += 360;
    const s = max === 0 ? 0 : (d / max) * 100;
    const v = max * 100;
    return [h, s, v];
}

export class ColorPickerModal {
    static instance: ColorPickerModal | null = null;

    static getInstance(): ColorPickerModal {
        if (!ColorPickerModal.instance) {
            ColorPickerModal.instance = new ColorPickerModal();
        }
        return ColorPickerModal.instance;
    }

    private modal: HTMLElement;
    private svCanvas: HTMLCanvasElement;
    private hueCanvas: HTMLCanvasElement;
    private preview: HTMLElement;
    private rInput: HTMLInputElement;
    private gInput: HTMLInputElement;
    private bInput: HTMLInputElement;
    private hexInput: HTMLInputElement;
    private okBtn: HTMLElement;
    private cancelBtn: HTMLElement;

    private hue = 0;
    private sat = 100;
    private val = 100;
    private dragging: 'sv' | 'hue' | null = null;

    private boundWindowMouseMove = (e: MouseEvent) => this.onMouseMove(e);
    private boundWindowMouseUp = () => this.onMouseUp();

    private resolve: ((color: Color | null) => void) | null = null;

    constructor() {
        this.modal = document.getElementById('color-picker-modal')!;
        this.svCanvas = document.getElementById('cp-sv-field') as HTMLCanvasElement;
        this.hueCanvas = document.getElementById('cp-hue-bar') as HTMLCanvasElement;
        this.preview = document.getElementById('cp-preview')!;
        this.rInput = document.getElementById('cp-r') as HTMLInputElement;
        this.gInput = document.getElementById('cp-g') as HTMLInputElement;
        this.bInput = document.getElementById('cp-b') as HTMLInputElement;
        this.hexInput = document.getElementById('cp-hex') as HTMLInputElement;
        this.okBtn = document.getElementById('cp-ok')!;
        this.cancelBtn = document.getElementById('cp-cancel')!;

        this.svCanvas.addEventListener('mousedown', (e) => this.onSvDown(e));
        this.hueCanvas.addEventListener('mousedown', (e) => this.onHueDown(e));
        window.addEventListener('mousemove', this.boundWindowMouseMove);
        window.addEventListener('mouseup', this.boundWindowMouseUp);

        this.rInput.addEventListener('change', () => this.updateFromRgb());
        this.gInput.addEventListener('change', () => this.updateFromRgb());
        this.bInput.addEventListener('change', () => this.updateFromRgb());
        this.hexInput.addEventListener('change', () => this.updateFromHex());

        this.okBtn.addEventListener('click', () => {
            this.close(hsvToRgb(this.hue, this.sat, this.val));
        });
        this.cancelBtn.addEventListener('click', () => this.close(null));
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.close(null);
        });
    }

    public destroy() {
        window.removeEventListener('mousemove', this.boundWindowMouseMove);
        window.removeEventListener('mouseup', this.boundWindowMouseUp);
    }

    open(initialColor: Color): Promise<Color | null> {
        return new Promise((resolve) => {
            this.resolve = resolve;
            const [h, s, v] = rgbToHsv(initialColor[0], initialColor[1], initialColor[2]);
            this.hue = h;
            this.sat = s;
            this.val = v;
            this.modal.classList.remove('hidden');
            this.drawAll();
            this.syncInputs();
        });
    }

    private close(result: Color | null) {
        if (!this.resolve) return;
        const r = this.resolve;
        this.resolve = null;
        this.modal.classList.add('hidden');
        r(result);
    }

    private drawAll() {
        this.drawHueBar();
        this.drawSvField();
        this.preview.style.backgroundColor = cssColor(hsvToRgb(this.hue, this.sat, this.val));
    }

    private drawSvField() {
        const ctx = this.svCanvas.getContext('2d')!;
        const w = this.svCanvas.width;
        const h = this.svCanvas.height;

        const hueColor = hsvToRgb(this.hue, 100, 100);
        ctx.fillStyle = cssColor(hueColor);
        ctx.fillRect(0, 0, w, h);

        const whiteGrad = ctx.createLinearGradient(0, 0, w, 0);
        whiteGrad.addColorStop(0, 'rgba(255,255,255,1)');
        whiteGrad.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = whiteGrad;
        ctx.fillRect(0, 0, w, h);

        const blackGrad = ctx.createLinearGradient(0, 0, 0, h);
        blackGrad.addColorStop(0, 'rgba(0,0,0,0)');
        blackGrad.addColorStop(1, 'rgba(0,0,0,1)');
        ctx.fillStyle = blackGrad;
        ctx.fillRect(0, 0, w, h);

        const px = (this.sat / 100) * w;
        const py = (1 - this.val / 100) * h;
        ctx.beginPath();
        ctx.arc(px, py, 7, 0, Math.PI * 2);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    private drawHueBar() {
        const ctx = this.hueCanvas.getContext('2d')!;
        const w = this.hueCanvas.width;
        const h = this.hueCanvas.height;
        const grad = ctx.createLinearGradient(0, 0, w, 0);
        for (let i = 0; i <= 6; i++) {
            grad.addColorStop(i / 6, cssColor(hsvToRgb(i * 60, 100, 100)));
        }
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);

        const px = (this.hue / 360) * w;
        ctx.beginPath();
        ctx.roundRect(px - 3, 0, 6, h, 2);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    private syncInputs() {
        const rgb = hsvToRgb(this.hue, this.sat, this.val);
        this.rInput.value = rgb[0].toString();
        this.gInput.value = rgb[1].toString();
        this.bInput.value = rgb[2].toString();
        this.hexInput.value = rgbToHex(rgb);
    }

    private updateFromRgb() {
        const r = parseInt(this.rInput.value) || 0;
        const g = parseInt(this.gInput.value) || 0;
        const b = parseInt(this.bInput.value) || 0;
        const [h, s, v] = rgbToHsv(r, g, b);
        this.hue = h;
        this.sat = s;
        this.val = v;
        this.drawAll();
        this.syncInputs();
    }

    private updateFromHex() {
        const c = hexToRgb(this.hexInput.value);
        const [h, s, v] = rgbToHsv(c[0], c[1], c[2]);
        this.hue = h;
        this.sat = s;
        this.val = v;
        this.drawAll();
        this.syncInputs();
    }

    private onSvDown(e: MouseEvent) {
        this.dragging = 'sv';
        this.pickSv(e);
    }

    private onHueDown(e: MouseEvent) {
        this.dragging = 'hue';
        this.pickHue(e);
    }

    private onMouseMove(e: MouseEvent) {
        if (!this.dragging) return;
        if (this.dragging === 'sv') this.pickSv(e);
        else this.pickHue(e);
    }

    private onMouseUp() {
        this.dragging = null;
    }

    private pickSv(e: MouseEvent) {
        const rect = this.svCanvas.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
        this.sat = (x / rect.width) * 100;
        this.val = (1 - y / rect.height) * 100;
        this.drawAll();
        this.syncInputs();
    }

    private pickHue(e: MouseEvent) {
        const rect = this.hueCanvas.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        this.hue = (x / rect.width) * 360;
        this.drawAll();
        this.syncInputs();
    }
}

import { Color, Cell } from '../types';

export function rgbToHex(color: Color): string {
    const [r, g, b] = color;
    const toHex = (c: number) => c.toString(16).padStart(2, '0');
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function hexToRgb(hex: string): Color {
    hex = hex.replace(/^#/, '');
    if (hex.length === 3) {
        hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    }
    const num = parseInt(hex, 16);
    return [num >> 16, (num >> 8) & 255, num & 255];
}

export function colorEquals(c1: Color, c2: Color): boolean {
    return c1[0] === c2[0] && c1[1] === c2[1] && c1[2] === c2[2];
}

export function cellEquals(a: Cell, b: Cell): boolean {
    return a.char === b.char
        && colorEquals(a.fg, b.fg)
        && colorEquals(a.bg, b.bg)
        && (a.bold ?? false) === (b.bold ?? false)
        && (a.italic ?? false) === (b.italic ?? false)
        && (a.underline ?? false) === (b.underline ?? false);
}

export function cssColor(color: Color): string {
    return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}

export function lerpColor(a: Color, b: Color, t: number): Color {
    return [
        Math.round(a[0] + (b[0] - a[0]) * t),
        Math.round(a[1] + (b[1] - a[1]) * t),
        Math.round(a[2] + (b[2] - a[2]) * t),
    ];
}

export function sampleGradient(stops: Color[], t: number): Color {
    if (stops.length === 0) return [0, 0, 0];
    if (stops.length === 1) return [...stops[0]];
    t = Math.max(0, Math.min(1, t));
    const segment = t * (stops.length - 1);
    const index = Math.min(Math.floor(segment), stops.length - 2);
    const localT = segment - index;
    return lerpColor(stops[index], stops[index + 1], localT);
}

export function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0, l = (max + min) / 2;

    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
    }
    return [h * 360, s, l];
}

export function hslToRgb(h: number, s: number, l: number): Color {
    let r, g, b;
    h /= 360;

    if (s === 0) {
        r = g = b = l; // achromatic
    } else {
        const hue2rgb = (p: number, q: number, t: number) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1 / 3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1 / 3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

export interface ColorAdjustOptions {
    brightness: number;  // -100 to 100
    contrast: number;    // -255 to 255
    hue: number;         // -180 to 180
    saturation: number;  // -100 to 100
}

export function applyColorAdjustments(color: Color, options: ColorAdjustOptions): Color {
    let [r, g, b] = color;

    // Contrast
    if (options.contrast !== 0) {
        const factor = (259 * (options.contrast + 255)) / (255 * (259 - options.contrast));
        r = Math.max(0, Math.min(255, factor * (r - 128) + 128));
        g = Math.max(0, Math.min(255, factor * (g - 128) + 128));
        b = Math.max(0, Math.min(255, factor * (b - 128) + 128));
    }

    // Convert to HSL
    let [h, s, l] = rgbToHsl(r, g, b);

    // Hue shift
    if (options.hue !== 0) {
        h = (h + options.hue) % 360;
        if (h < 0) h += 360;
    }

    // Saturation shift
    if (options.saturation !== 0) {
        const satShift = options.saturation / 100;
        if (satShift > 0) {
            s += (1 - s) * satShift;
        } else {
            s += s * satShift;
        }
        s = Math.max(0, Math.min(1, s));
    }

    // Brightness shift
    if (options.brightness !== 0) {
        const brightShift = options.brightness / 100;
        if (brightShift > 0) {
            l += (1 - l) * brightShift;
        } else {
            l += l * brightShift;
        }
        l = Math.max(0, Math.min(1, l));
    }

    return hslToRgb(h, s, l);
}

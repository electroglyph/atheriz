import { Color, AppState } from '../types';
import { cssColor, sampleGradient, colorEquals } from '../utils/colors';
import { ColorPickerModal } from './ColorPickerModal';

export class GradientPicker {
    private appState: AppState;
    private container: HTMLElement;
    private previewBar!: HTMLElement;
    private stopsContainer!: HTMLElement;

    constructor(containerId: string, appState: AppState) {
        this.container = document.getElementById(containerId)!;
        this.appState = appState;

        if (!this.appState.gradientStops || this.appState.gradientStops.length < 2) {
            this.appState.gradientStops = [
                [0, 0, 0] as Color,
                [255, 255, 255] as Color,
            ];
        }

        this.render();
        this.updateUI();
    }

    private get stops(): Color[] {
        return this.appState.gradientStops;
    }

    private render() {
        this.container.innerHTML = '';

        this.previewBar = document.createElement('div');
        this.previewBar.className = 'gradient-preview-bar';

        this.stopsContainer = document.createElement('div');
        this.stopsContainer.className = 'gradient-stops-row';

        this.previewBar.addEventListener('click', (e) => {
            this.onBarClick(e);
        });

        this.previewBar.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });

        this.container.appendChild(this.previewBar);
        this.container.appendChild(this.stopsContainer);
    }

    private updateUI() {
        const stops = this.stops;
        const colorStops = stops.map((c: Color, i: number) => {
            const pct = stops.length === 1 ? 0 : (i / (stops.length - 1)) * 100;
            return `${cssColor(c)} ${pct}%`;
        }).join(', ');
        this.previewBar.style.background = `linear-gradient(to right, ${colorStops})`;

        this.stopsContainer.innerHTML = '';
        for (let i = 0; i < stops.length; i++) {
            const marker = document.createElement('div');
            marker.className = 'gradient-stop-marker';
            marker.title = 'Left-click to change color, right-click to remove color';
            if (stops.length <= 2 && (i === 0 || i === stops.length - 1)) {
                marker.classList.add('permanent');
            }
            marker.style.backgroundColor = cssColor(stops[i]);

            const idx = i;
            marker.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.onStopClick(idx);
            });

            marker.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.onStopRightClick(idx);
            });

            this.stopsContainer.appendChild(marker);
        }
    }

    private onBarClick(e: MouseEvent) {
        const rect = this.previewBar.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const t = Math.max(0, Math.min(1, x / rect.width));

        const stops = this.stops;
        const newColor = sampleGradient(stops, t);

        const segment = t * (stops.length - 1);
        const insertIndex = Math.min(Math.floor(segment) + 1, stops.length);

        GradientPicker.getModal().open(newColor).then((result) => {
            if (result) {
                stops.splice(insertIndex, 0, [...result] as Color);
                this.updateUI();
            }
        });
    }

    private onStopClick(index: number) {
        const current = [...this.stops[index]] as Color;
        GradientPicker.getModal().open(current).then((result) => {
            if (result && !colorEquals(result, current)) {
                this.stops[index] = result;
                this.updateUI();
            }
        });
    }

    private onStopRightClick(index: number) {
        const stops = this.stops;
        if (stops.length <= 2) return;

        stops.splice(index, 1);
        this.updateUI();
    }

    private static getModal(): ColorPickerModal {
        return ColorPickerModal.getInstance();
    }
}

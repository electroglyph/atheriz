import { CanvasState } from '../state/CanvasState';
import { closeOtherModals } from './modalHelper';

export class ResizeCanvasDialog {
    private modal: HTMLElement;
    private btnResize: HTMLButtonElement;
    private btnCancel: HTMLButtonElement;
    private btnConfirm: HTMLButtonElement;
    private inputW: HTMLInputElement;
    private inputH: HTMLInputElement;
    
    private getStateCallback: () => CanvasState;
    private onConfirmCallback: (w: number, h: number) => void;

    constructor(getState: () => CanvasState, onConfirm: (w: number, h: number) => void) {
        this.getStateCallback = getState;
        this.onConfirmCallback = onConfirm;
        
        this.modal = document.getElementById('resize-canvas-modal')!;
        this.btnResize = document.getElementById('btn-resize') as HTMLButtonElement;
        this.btnCancel = document.getElementById('btn-resize-cancel') as HTMLButtonElement;
        this.btnConfirm = document.getElementById('btn-resize-confirm') as HTMLButtonElement;
        
        this.inputW = document.getElementById('resize-width') as HTMLInputElement;
        this.inputH = document.getElementById('resize-height') as HTMLInputElement;

        this.bindEvents();
    }

    private bindEvents() {
        this.btnResize.addEventListener('click', () => {
            closeOtherModals('resize-canvas-modal');
            const state = this.getStateCallback();
            if (state) {
                this.inputW.value = state.width.toString();
                this.inputH.value = state.height.toString();
            }
            this.modal.classList.remove('hidden');
        });

        this.btnCancel.addEventListener('click', () => {
            this.modal.classList.add('hidden');
        });

        this.btnConfirm.addEventListener('click', () => {
            const w = parseInt(this.inputW.value);
            const h = parseInt(this.inputH.value);
            if (w > 0 && h > 0) {
                this.onConfirmCallback(w, h);
                this.modal.classList.add('hidden');
            }
        });
    }
}

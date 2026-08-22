export class NewCanvasDialog {
    private modal: HTMLElement;
    private btnNew: HTMLButtonElement;
    private btnCancel: HTMLButtonElement;
    private btnConfirm: HTMLButtonElement;
    private inputs: NodeListOf<HTMLButtonElement>;
    private inputW: HTMLInputElement;
    private inputH: HTMLInputElement;
    
    private onConfirmCallback: (w: number, h: number) => void;

    constructor(onConfirm: (w: number, h: number) => void) {
        this.onConfirmCallback = onConfirm;
        
        this.modal = document.getElementById('new-canvas-modal')!;
        this.btnNew = document.getElementById('btn-new') as HTMLButtonElement;
        this.btnCancel = document.getElementById('btn-new-cancel') as HTMLButtonElement;
        this.btnConfirm = document.getElementById('btn-new-confirm') as HTMLButtonElement;
        
        this.inputs = this.modal.querySelectorAll('.preset-buttons button');
        this.inputW = document.getElementById('new-width') as HTMLInputElement;
        this.inputH = document.getElementById('new-height') as HTMLInputElement;

        this.bindEvents();
    }

    private bindEvents() {
        this.btnNew.addEventListener('click', () => {
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

        for (const preset of Array.from(this.inputs)) {
            preset.addEventListener('click', () => {
                this.inputW.value = preset.dataset['w'] || "24";
                this.inputH.value = preset.dataset['h'] || "24";
            });
        }
    }
}

import { closeOtherModals } from './modalHelper';

export class TypeToolModal {
    private modal: HTMLDivElement;
    private input: HTMLInputElement;
    private btnOk: HTMLButtonElement;
    private btnCancel: HTMLButtonElement;
    private resolve: ((value: string | null) => void) | null = null;

    constructor() {
        this.modal = document.getElementById('type-tool-modal') as HTMLDivElement;
        this.input = document.getElementById('type-tool-input') as HTMLInputElement;
        this.btnOk = document.getElementById('type-tool-ok') as HTMLButtonElement;
        this.btnCancel = document.getElementById('type-tool-cancel') as HTMLButtonElement;

        this.btnOk.addEventListener('click', () => {
            const text = this.input.value;
            this.close(text || null);
        });

        this.btnCancel.addEventListener('click', () => {
            this.close(null);
        });

        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.close(null);
        });

        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const text = this.input.value;
                this.close(text || null);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                this.close(null);
            }
        });
    }

    open(): Promise<string | null> {
        return new Promise((resolve) => {
            closeOtherModals('type-tool-modal');
            if (this.resolve) {
                const pending = this.resolve;
                this.resolve = null;
                pending(null);
            }
            this.resolve = resolve;
            this.input.value = '';
            this.modal.classList.remove('hidden');
            setTimeout(() => this.input.focus(), 50);
        });
    }

    private close(value: string | null) {
        this.modal.classList.add('hidden');
        if (this.resolve) {
            this.resolve(value);
            this.resolve = null;
        }
    }
}

import { closeOtherModals } from './modalHelper';

export class MessageDialog {
    private container: HTMLElement;
    private messageEl: HTMLElement;
    private okButton: HTMLButtonElement;
    private boundKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && this.isVisible()) this.hide();
    };
    private boundBackdropClick = (e: MouseEvent) => {
        if (e.target === this.container) this.hide();
    };

    constructor(containerId: string) {
        const container = document.getElementById(containerId);
        if (!container) throw new Error(`Missing dialog container #${containerId}`);
        this.container = container;
        const messageEl = document.getElementById(`${containerId}-message`);
        if (!messageEl) throw new Error(`Missing dialog message #${containerId}-message`);
        this.messageEl = messageEl;
        const okButton = document.getElementById(`${containerId}-ok`) as HTMLButtonElement | null;
        if (!okButton) throw new Error(`Missing dialog button #${containerId}-ok`);
        this.okButton = okButton;
        this.okButton.addEventListener('click', () => this.hide());
        this.container.addEventListener('click', this.boundBackdropClick);
        window.addEventListener('keydown', this.boundKeyDown);
    }

    public destroy(): void {
        this.container.removeEventListener('click', this.boundBackdropClick);
        window.removeEventListener('keydown', this.boundKeyDown);
    }

    public show(message: string): void {
        closeOtherModals(this.container.id);
        this.messageEl.textContent = message;
        this.container.classList.remove('hidden');
    }

    public hide(): void {
        this.container.classList.add('hidden');
    }

    public isVisible(): boolean {
        return !this.container.classList.contains('hidden');
    }
}

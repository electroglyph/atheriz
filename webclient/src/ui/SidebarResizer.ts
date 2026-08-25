export class SidebarResizer {
    private sidebar: HTMLElement;
    private resizer: HTMLElement;
    private isResizing: boolean = false;
    private startX: number = 0;
    private startWidth: number = 0;
    private inverted: boolean;

    private boundDocumentMouseMove = this.onMouseMove.bind(this);
    private boundDocumentMouseUp = this.onMouseUp.bind(this);
    private boundResizerMouseDown = this.onMouseDown.bind(this);

    constructor(sidebarId: string, resizerId: string, inverted: boolean = false) {
        this.sidebar = document.getElementById(sidebarId)!;
        this.resizer = document.getElementById(resizerId)!;
        this.inverted = inverted;

        this.init();
    }

    private init() {
        this.resizer.addEventListener('mousedown', this.boundResizerMouseDown);
        document.addEventListener('mousemove', this.boundDocumentMouseMove);
        document.addEventListener('mouseup', this.boundDocumentMouseUp);
        window.addEventListener('beforeunload', this.destroy.bind(this));
        window.addEventListener('pagehide', this.destroy.bind(this));
    }

    public destroy() {
        this.resizer.removeEventListener('mousedown', this.boundResizerMouseDown);
        document.removeEventListener('mousemove', this.boundDocumentMouseMove);
        document.removeEventListener('mouseup', this.boundDocumentMouseUp);
    }

    private onMouseDown(e: MouseEvent) {
        this.isResizing = true;
        this.startX = e.clientX;
        this.startWidth = this.sidebar.getBoundingClientRect().width;
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none'; // Prevent text selection during resize
    }

    private onMouseMove(e: MouseEvent) {
        if (!this.isResizing) return;
        // Inverted: dragging left makes right panel wider
        const dx = this.inverted ? this.startX - e.clientX : e.clientX - this.startX;
        const newWidth = Math.max(150, Math.min(800, this.startWidth + dx));
        this.sidebar.style.width = `${newWidth}px`;
    }

    private onMouseUp() {
        if (this.isResizing) {
            this.isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    }
}

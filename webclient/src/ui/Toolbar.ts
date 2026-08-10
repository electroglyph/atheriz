import { AppState, RectMode, OvalMode, LineMode, GradientTarget, TypeStyle, SelectMode, RotateMode, FillMode } from '../types';
import { UndoStack } from '../state/UndoStack';
import { CanvasState } from '../state/CanvasState';

export class Toolbar {
    private appState: AppState;
    private undoStack: UndoStack;
    
    private fontSelect: HTMLSelectElement;
    private systemFontsLoaded = false;
    
    private btnBrush: HTMLButtonElement;
    private btnErase: HTMLButtonElement;
    private btnType: HTMLButtonElement;
    private btnText: HTMLButtonElement;
    private btnRect: HTMLButtonElement;
    private btnOval: HTMLButtonElement;
    private btnLine: HTMLButtonElement;
    private btnGradient: HTMLButtonElement;
    private btnFill: HTMLButtonElement;
    private btnEyedropper: HTMLButtonElement;
    private btnSelect: HTMLButtonElement;
    private btnMove: HTMLButtonElement;
    private btnRotate: HTMLButtonElement;
    
    private typeStyleSel: HTMLSelectElement;
    private rectModeSel: HTMLSelectElement;
    private ovalModeSel: HTMLSelectElement;
    private lineModeSel: HTMLSelectElement;
    private gradientTargetSel: HTMLSelectElement;
    private fillModeSel: HTMLSelectElement;
    private eyedropperTargetSel: HTMLSelectElement;
    private selectModeSel: HTMLSelectElement;
    private rotateModeSel: HTMLSelectElement;

    private btnUndo: HTMLButtonElement;
    private btnRedo: HTMLButtonElement;
    private btnExport: HTMLButtonElement;

    private exportCallback: () => void;
    private stateRestoreCallback: (state: CanvasState) => void;
    private fontChangeCallback: (fontFamily: string) => void;
    private onTextAction?: () => void;
    public clearSelectionCallback: (() => void) | null = null;
    public onRotateAction?: (mode: Exclude<RotateMode, 'free'>) => void;

    private boundKeyDown = (e: KeyboardEvent) => {
        if (e.target instanceof HTMLInputElement ||
            e.target instanceof HTMLSelectElement ||
            e.target instanceof HTMLTextAreaElement) return;

        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'z') {
            const s = this.undoStack.undo();
            if (s) this.stateRestoreCallback(s);
            e.preventDefault();
        } else if ((e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'z') || (e.ctrlKey && e.key.toLowerCase() === 'y')) {
            const s = this.undoStack.redo();
            if (s) this.stateRestoreCallback(s);
            e.preventDefault();
        }
    };

    constructor(
        appState: AppState, 
        undoStack: UndoStack, 
        onExport: () => void, 
        onStateRestore: (state: CanvasState) => void,
        onFontChange: (fontFamily: string) => void,
        onTextAction?: () => void
    ) {
        this.appState = appState;
        this.undoStack = undoStack;
        this.exportCallback = onExport;
        this.stateRestoreCallback = onStateRestore;
        this.fontChangeCallback = onFontChange;
        this.onTextAction = onTextAction;

        this.btnBrush = document.getElementById('tool-brush') as HTMLButtonElement;
        this.btnErase = document.getElementById('tool-erase') as HTMLButtonElement;
        this.btnType = document.getElementById('tool-type') as HTMLButtonElement;
        this.btnText = document.getElementById('tool-text') as HTMLButtonElement;
        this.btnRect = document.getElementById('tool-rect') as HTMLButtonElement;
        this.btnOval = document.getElementById('tool-oval') as HTMLButtonElement;
        this.btnLine = document.getElementById('tool-line') as HTMLButtonElement;
        this.btnGradient = document.getElementById('tool-gradient') as HTMLButtonElement;
        this.btnFill = document.getElementById('tool-fill') as HTMLButtonElement;
        this.btnEyedropper = document.getElementById('tool-eyedropper') as HTMLButtonElement;
        this.btnSelect = document.getElementById('tool-select') as HTMLButtonElement;
        this.btnMove = document.getElementById('tool-move') as HTMLButtonElement;
        this.btnRotate = document.getElementById('tool-rotate') as HTMLButtonElement;

        this.typeStyleSel = document.getElementById('type-style-select') as HTMLSelectElement;
        this.typeStyleSel.value = this.appState.typeStyle;

        this.rectModeSel = document.getElementById('rect-mode-select') as HTMLSelectElement;
        this.rectModeSel.value = this.appState.rectMode;

        this.ovalModeSel = document.getElementById('oval-mode-select') as HTMLSelectElement;
        this.ovalModeSel.value = this.appState.ovalMode;

        this.lineModeSel = document.getElementById('line-mode-select') as HTMLSelectElement;
        this.lineModeSel.value = this.appState.lineMode;

        this.gradientTargetSel = document.getElementById('gradient-target-select') as HTMLSelectElement;
        this.gradientTargetSel.value = this.appState.gradientTarget;

        this.fillModeSel = document.getElementById('fill-mode-select') as HTMLSelectElement;
        this.fillModeSel.value = this.appState.fillMode;

        this.eyedropperTargetSel = document.getElementById('eyedropper-target-select') as HTMLSelectElement;
        this.eyedropperTargetSel.value = this.appState.eyedropperTarget;

        this.selectModeSel = document.getElementById('select-mode-select') as HTMLSelectElement;
        this.selectModeSel.value = this.appState.selectMode;

        this.rotateModeSel = document.getElementById('rotate-mode-select') as HTMLSelectElement;
        this.rotateModeSel.value = this.appState.rotateMode;

        this.btnUndo = document.getElementById('btn-undo') as HTMLButtonElement;
        this.btnRedo = document.getElementById('btn-redo') as HTMLButtonElement;
        this.btnExport = document.getElementById('btn-export') as HTMLButtonElement;

        this.fontSelect = document.getElementById('font-select') as HTMLSelectElement;
        this.initFonts();

        this.bindEvents();
        this.updateUndoRedoStates();
        this.undoStack.onChange(() => this.updateUndoRedoStates());
    }

    private bindEvents() {
        const tools = [
            { id: 'brush', btn: this.btnBrush },
            { id: 'erase', btn: this.btnErase },
            { id: 'type', btn: this.btnType },
            { id: 'text', btn: this.btnText },
            { id: 'rect', btn: this.btnRect },
            { id: 'oval', btn: this.btnOval },
            { id: 'line', btn: this.btnLine },
            { id: 'gradient', btn: this.btnGradient },
            { id: 'fill', btn: this.btnFill },
            { id: 'eyedropper', btn: this.btnEyedropper },
            { id: 'select', btn: this.btnSelect },
            { id: 'move', btn: this.btnMove },
            { id: 'rotate', btn: this.btnRotate }
        ];

        for (const t of tools) {
            // Except for rotate btn if mode isn't free
            t.btn.addEventListener('click', () => {
                if (t.id === 'rotate' && this.appState.rotateMode !== 'free') {
                    if (this.onRotateAction) {
                        this.onRotateAction(this.appState.rotateMode as Exclude<RotateMode, 'free'>);
                    }
                    return; // Don't activate tool
                }
                
                this.appState.activeToolId = t.id;
                this.updateToolButtons();
                if (t.id === 'text' && this.onTextAction) {
                    this.onTextAction();
                }
            });
        }

        this.rectModeSel.addEventListener('change', (e) => {
            this.appState.rectMode = (e.target as HTMLSelectElement).value as RectMode;
            this.appState.activeToolId = 'rect';
            this.updateToolButtons();
        });

        this.ovalModeSel.addEventListener('change', (e) => {
            this.appState.ovalMode = (e.target as HTMLSelectElement).value as OvalMode;
            this.appState.activeToolId = 'oval';
            this.updateToolButtons();
        });

        this.lineModeSel.addEventListener('change', (e) => {
            this.appState.lineMode = (e.target as HTMLSelectElement).value as LineMode;
            this.appState.activeToolId = 'line';
            this.updateToolButtons();
        });

        const diagonalCheckbox = document.getElementById('line-diagonal-checkbox') as HTMLInputElement;
        if (diagonalCheckbox) {
            diagonalCheckbox.checked = !!this.appState.lineDiagonal;
            diagonalCheckbox.addEventListener('change', (e) => {
                this.appState.lineDiagonal = (e.target as HTMLInputElement).checked;
                this.appState.activeToolId = 'line';
                this.updateToolButtons();
            });
        }

        this.gradientTargetSel.addEventListener('change', (e) => {
            this.appState.gradientTarget = (e.target as HTMLSelectElement).value as GradientTarget;
            this.appState.activeToolId = 'gradient';
            this.updateToolButtons();
        });

        this.fillModeSel.addEventListener('change', (e) => {
            this.appState.fillMode = (e.target as HTMLSelectElement).value as FillMode;
            this.appState.activeToolId = 'fill';
            this.updateToolButtons();
        });

        this.eyedropperTargetSel.addEventListener('change', (e) => {
            this.appState.eyedropperTarget = (e.target as HTMLSelectElement).value as any;
            this.appState.activeToolId = 'eyedropper';
            this.updateToolButtons();
        });

        this.selectModeSel.addEventListener('change', (e) => {
            this.appState.selectMode = (e.target as HTMLSelectElement).value as SelectMode;
            this.appState.activeToolId = 'select';
            this.updateToolButtons();
        });

        this.rotateModeSel.addEventListener('change', (e) => {
            this.appState.rotateMode = (e.target as HTMLSelectElement).value as RotateMode;
            if (this.appState.rotateMode === 'free') {
                this.appState.activeToolId = 'rotate';
                this.updateToolButtons();
            }
        });

        this.typeStyleSel.addEventListener('change', (e) => {
            this.appState.typeStyle = (e.target as HTMLSelectElement).value as TypeStyle;
            this.appState.activeToolId = 'type';
            this.updateToolButtons();
        });

        this.btnUndo.addEventListener('click', () => {
            const s = this.undoStack.undo();
            if (s) this.stateRestoreCallback(s);
        });
        this.btnRedo.addEventListener('click', () => {
            const s = this.undoStack.redo();
            if (s) this.stateRestoreCallback(s);
        });
        
        this.btnExport.addEventListener('click', () => this.exportCallback());

        this.fontSelect.addEventListener('change', (e) => {
            const family = (e.target as HTMLSelectElement).value;
            this.appState.fontFamily = family;
            this.fontChangeCallback(family);
        });

        this.fontSelect.addEventListener('click', () => {
            this.loadSystemFonts();
        });

        window.addEventListener('keydown', this.boundKeyDown);
    }

    public destroy() {
        window.removeEventListener('keydown', this.boundKeyDown);
    }

    private updateToolButtons() {
        this.btnBrush.classList.remove('active');
        this.btnErase.classList.remove('active');
        this.btnType.classList.remove('active');
        this.btnText.classList.remove('active');
        this.btnRect.classList.remove('active');
        this.btnOval.classList.remove('active');
        this.btnLine.classList.remove('active');
        this.btnGradient.classList.remove('active');
        this.btnFill.classList.remove('active');
        this.btnEyedropper.classList.remove('active');
        this.btnSelect.classList.remove('active');
        this.btnMove.classList.remove('active');
        this.btnRotate.classList.remove('active');

        switch (this.appState.activeToolId) {
            case 'brush': this.btnBrush.classList.add('active'); break;
            case 'erase': this.btnErase.classList.add('active'); break;
            case 'type': this.btnType.classList.add('active'); break;
            case 'text': this.btnText.classList.add('active'); break;
            case 'rect': this.btnRect.classList.add('active'); break;
            case 'oval': this.btnOval.classList.add('active'); break;
            case 'line': this.btnLine.classList.add('active'); break;
            case 'gradient': this.btnGradient.classList.add('active'); break;
            case 'fill': this.btnFill.classList.add('active'); break;
            case 'eyedropper': this.btnEyedropper.classList.add('active'); break;
            case 'select': this.btnSelect.classList.add('active'); break;
            case 'move': this.btnMove.classList.add('active'); break;
            case 'rotate': this.btnRotate.classList.add('active'); break;
        }

        if (this.appState.activeToolId !== 'select' && this.appState.activeToolId !== 'move' && this.appState.activeToolId !== 'rotate' && this.appState.activeToolId !== 'fill' && this.appState.activeToolId !== 'eyedropper' && this.clearSelectionCallback) {
            this.clearSelectionCallback();
        }

        if (this.appState.activeToolId === 'gradient' || this.appState.activeToolId === 'line') {
            document.body.classList.add('tool-gradient-active');
        } else {
            document.body.classList.remove('tool-gradient-active');
        }

        if (this.appState.activeToolId === 'fill') {
            document.body.classList.add('tool-fill-active');
        } else {
            document.body.classList.remove('tool-fill-active');
        }

        if (this.appState.activeToolId === 'move') {
            document.body.classList.add('tool-move-active');
        } else {
            document.body.classList.remove('tool-move-active');
        }

        if (this.appState.activeToolId === 'rotate') {
            document.body.classList.add('tool-rotate-active');
        } else {
            document.body.classList.remove('tool-rotate-active');
        }

        if (this.appState.activeToolId === 'eyedropper') {
            document.body.classList.add('tool-eyedropper-active');
        } else {
            document.body.classList.remove('tool-eyedropper-active');
        }
    }

    private updateUndoRedoStates() {
        this.btnUndo.disabled = !this.undoStack.canUndo();
        this.btnRedo.disabled = !this.undoStack.canRedo();
        this.btnUndo.style.opacity = this.btnUndo.disabled ? '0.5' : '1';
        this.btnRedo.style.opacity = this.btnRedo.disabled ? '0.5' : '1';
    }

    private initFonts() {
        const localFonts = [
            { name: 'Unifont', val: 'Unifont' },
            { name: 'KreativeSquare', val: 'KreativeSquare' },
            { name: 'Fira Code', val: "'Fira Code', 'FiraCode'" }
        ];

        for (const f of localFonts) {
            const opt = document.createElement('option');
            opt.value = f.val;
            opt.textContent = f.name;
            this.fontSelect.appendChild(opt);
        }

        this.fontSelect.value = this.appState.fontFamily;
    }

    private async loadSystemFonts() {
        if (this.systemFontsLoaded) return;
        this.systemFontsLoaded = true; // Mark as started

        try {
            if ('queryLocalFonts' in window) {
                // @ts-ignore - queryLocalFonts is not yet fully codified in standard TS DOM
                const fonts = await window.queryLocalFonts();
                // Deduplicate by family
                const familySet = new Set<string>();
                for (const f of fonts) {
                    familySet.add(f.family);
                }

                // Add separator
                const sep = document.createElement('option');
                sep.disabled = true;
                sep.textContent = '── System Fonts ──';
                this.fontSelect.appendChild(sep);

                // Sort and add
                const sorted = Array.from(familySet).sort();
                for (const family of sorted) {
                    const opt = document.createElement('option');
                    // quote it
                    opt.value = `"${family}"`;
                    opt.textContent = family;
                    this.fontSelect.appendChild(opt);
                }
            } else {
                // Fallback list
                const fallbackFonts = [
                    'Arial', 'Consolas', 'Courier New', 'Monaco', 'Segoe UI', 'sans-serif', 'monospace'
                ];
                const sep = document.createElement('option');
                sep.disabled = true;
                sep.textContent = '── Fallback Fonts ──';
                this.fontSelect.appendChild(sep);

                for (const family of fallbackFonts) {
                    const opt = document.createElement('option');
                    opt.value = family;
                    opt.textContent = family;
                    this.fontSelect.appendChild(opt);
                }
            }
        } catch (e) {
            console.error('Failed to load system fonts:', e);
            // Might have been denied permission
            this.systemFontsLoaded = false;
        }
    }
}

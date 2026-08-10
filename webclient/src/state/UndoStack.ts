import { CanvasState } from './CanvasState';

export class UndoStack {
    private maxCapacity = 128;
    private undoStack: CanvasState[] = [];
    private redoStack: CanvasState[] = [];
    private currentState: CanvasState | null = null;
    
    private listeners: Set<() => void> = new Set();

    public setCurrentState(state: CanvasState) {
        this.currentState = state;
    }

    /**
     * Should be called BEFORE a modification happens.
     */
    public push(state: CanvasState) {
        this.undoStack.push(state.clone());
        if (this.undoStack.length > this.maxCapacity) {
            this.undoStack.shift();
        }
        this.redoStack = []; // Clear redo stack on new action
        this.notify();
    }

    public canUndo(): boolean {
        return this.undoStack.length > 0;
    }

    public canRedo(): boolean {
        return this.redoStack.length > 0;
    }

    public undo(): CanvasState | null {
        if (!this.canUndo() || !this.currentState) return null;
        
        this.redoStack.push(this.currentState.clone());
        const state = this.undoStack.pop()!;
        this.currentState = state;
        
        this.notify();
        return state;
    }

    public redo(): CanvasState | null {
        if (!this.canRedo() || !this.currentState) return null;
        
        this.undoStack.push(this.currentState.clone());
        const state = this.redoStack.pop()!;
        this.currentState = state;
        
        this.notify();
        return state;
    }

    public reset() {
        this.undoStack = [];
        this.redoStack = [];
        this.notify();
    }

    public onChange(listener: () => void) {
        this.listeners.add(listener);
    }

    private notify() {
        for (const l of this.listeners) {
            l();
        }
    }
}

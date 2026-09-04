import { Point, AppState } from '../types';
import { CanvasState } from '../state/CanvasState';
import { UndoStack } from '../state/UndoStack';
import { GridRenderer } from '../canvas/GridRenderer';

export interface CellMove {
    fromCol: number;
    fromRow: number;
    toCol: number;
    toRow: number;
}

export interface ToolContext {
    state: CanvasState;
    undoStack: UndoStack;
    renderer: GridRenderer;
    appState: AppState;
    modifiers: {
        shiftKey: boolean;
        altKey: boolean;
        ctrlKey: boolean;
    };
    onCellsMoved?: (moves: CellMove[]) => void;
    /**
     * Owner of the authoritative selection set, if the host wires one.
     * Move/Rotate keep it in sync when they translate the renderer outline;
     * without it Delete/Copy would keep using stale coordinates.
     */
    selectionSync?: SelectionSync;
}

export interface SelectionSync {
    setSelection(cells: Set<string>): void;
    clearSelection(): void;
}

export interface Tool {
    onMouseDown(ctx: ToolContext, cell: Point): void;
    onDrag(ctx: ToolContext, from: Point, to: Point): void;
    onMouseUp(ctx: ToolContext, cell: Point): void;
    onHover(ctx: ToolContext, cell: Point): void;
    onMouseLeave(ctx: ToolContext): void;
    onKeyDown?(ctx: ToolContext, key: string): boolean;
}

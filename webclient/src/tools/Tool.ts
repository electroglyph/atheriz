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
}

export interface Tool {
    onMouseDown(ctx: ToolContext, cell: Point): void;
    onDrag(ctx: ToolContext, from: Point, to: Point): void;
    onMouseUp(ctx: ToolContext, cell: Point): void;
    onHover(ctx: ToolContext, cell: Point): void;
    onMouseLeave(ctx: ToolContext): void;
    onKeyDown?(ctx: ToolContext, key: string): boolean;
}

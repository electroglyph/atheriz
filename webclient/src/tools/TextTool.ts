import { Tool, ToolContext } from './Tool';
import { Point } from '../types';

export class TextTool implements Tool {
    private onActivate: () => void;
    
    constructor(onActivate: () => void) {
        this.onActivate = onActivate;
    }

    onMouseDown(_ctx: ToolContext, _cell: Point): void {
        // Trigger the dialog when the user clicks on the canvas
        // This is a simple implementation that ignores the 'cell' coordinate.
        // It always creates the text starting from top-left per the plan.
        this.onActivate();
    }

    onDrag(_ctx: ToolContext, _from: Point, _to: Point): void {
        // No drag action for text placement currently
    }

    onMouseUp(_ctx: ToolContext, _cell: Point): void {
        // No action on mouse up
    }

    onHover(_ctx: ToolContext, _cell: Point): void {}

    onMouseLeave(_ctx: ToolContext): void {}
}

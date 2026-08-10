import { Tool, ToolContext } from './Tool';
import { Point } from '../types';
import { BrushTool } from './BrushTool';
import { EraserTool } from './EraserTool';

export class ToolManager {
    private tools: Record<string, Tool> = {};
    private context: ToolContext;

    constructor(context: ToolContext) {
        this.context = context;
        
        // Register standard tools
        this.tools['brush'] = new BrushTool();
        this.tools['erase'] = new EraserTool();
        // Rect and Oval to be registered via addTool
    }

    public addTool(id: string, tool: Tool) {
        this.tools[id] = tool;
    }

    public updateModifiers(shift: boolean, alt: boolean, ctrl: boolean) {
        this.context.modifiers.shiftKey = shift;
        this.context.modifiers.altKey = alt;
        this.context.modifiers.ctrlKey = ctrl;
        
        // Let the active tool know state changed without pointer move, 
        // to update hover/drag previews immediately for shift/alt.
        // Usually we'd trigger a re-render here, but mousemove handles it.
    }

    private getActiveTool(): Tool | null {
        return this.tools[this.context.appState.activeToolId] || null;
    }

    public onMouseDown(cell: Point) {
        this.getActiveTool()?.onMouseDown(this.context, cell);
    }

    public onDrag(from: Point, to: Point) {
        this.getActiveTool()?.onDrag(this.context, from, to);
    }

    public onMouseUp(cell: Point) {
        this.getActiveTool()?.onMouseUp(this.context, cell);
    }

    public onHover(cell: Point) {
        this.getActiveTool()?.onHover(this.context, cell);
    }

    public onMouseLeave() {
        this.getActiveTool()?.onMouseLeave(this.context);
    }

    public onKeyDown(key: string): boolean {
        const tool = this.getActiveTool();
        if (tool?.onKeyDown) {
            return tool.onKeyDown(this.context, key);
        }
        return false;
    }
}

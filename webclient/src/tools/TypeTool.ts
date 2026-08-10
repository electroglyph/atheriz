import { Tool, ToolContext } from './Tool';
import { Point } from '../types';
import { TypeToolModal } from '../ui/TypeToolModal';

export class TypeTool implements Tool {
    private modal: TypeToolModal;

    constructor() {
        this.modal = new TypeToolModal();
    }

    onMouseDown(ctx: ToolContext, cell: Point): void {
        this.modal.open().then(text => {
            if (text === null || text.length === 0) return;

            ctx.undoStack.push(ctx.state);

            const style = ctx.appState.typeStyle;
            const updates: { col: number; row: number; cell: { char: string; fg: [number, number, number]; bg: [number, number, number]; bold?: boolean; italic?: boolean; underline?: boolean } }[] = [];

            for (let i = 0; i < text.length; i++) {
                const col = cell.x + i;
                if (col >= ctx.state.width) break;
                const cellData: { char: string; fg: [number, number, number]; bg: [number, number, number]; bold?: boolean; italic?: boolean; underline?: boolean } = {
                    char: text[i],
                    fg: [...ctx.appState.fgColor] as [number, number, number],
                    bg: [...ctx.appState.bgColor] as [number, number, number],
                };

                if (style === 'bold') cellData.bold = true;
                else if (style === 'italic') cellData.italic = true;
                else if (style === 'underline') cellData.underline = true;

                updates.push({ col, row: cell.y, cell: cellData });
            }

            if (updates.length > 0) {
                ctx.state.applyBatch(updates);
            }
        });
    }

    onDrag(_ctx: ToolContext, _from: Point, _to: Point): void {}
    onMouseUp(_ctx: ToolContext, _cell: Point): void {}

    onHover(ctx: ToolContext, cell: Point): void {
        ctx.renderer.setPreview([{
            col: cell.x,
            row: cell.y,
            cell: {
                char: ctx.appState.selectedChar,
                fg: ctx.appState.fgColor,
                bg: ctx.appState.bgColor,
            }
        }]);
    }

    onMouseLeave(ctx: ToolContext): void {
        ctx.renderer.clearPreview();
    }
}

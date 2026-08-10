import { describe, it, expect, vi } from 'vitest';
import { UndoStack } from '../src/state/UndoStack';
import { CanvasState } from '../src/state/CanvasState';

describe('UndoStack', () => {
    it('manages undo and redo correctly by returning the clone to the caller', () => {
        const stack = new UndoStack();
        const notifySpy = vi.fn();
        stack.onChange(notifySpy);

        // Intial state
        let currentState = new CanvasState(5, 5);
        stack.setCurrentState(currentState);

        // Before modification, we push to undo
        stack.push(currentState);
        
        // Modify
        currentState.setCell(0, 0, { char: 'A', fg: [255,255,255], bg: [0,0,0] });
        
        expect(stack.canUndo()).toBe(true);
        expect(stack.canRedo()).toBe(false);

        // Perform Undo
        const restoredState = stack.undo();
        
        expect(notifySpy).toHaveBeenCalled();
        expect(restoredState).toBeDefined();
        // The restored state should not have the 'A'
        expect(restoredState!.getCell(0, 0)?.char).toBe('');

        // Apply it back as the current simulation
        currentState = restoredState!;

        expect(stack.canUndo()).toBe(false);
        expect(stack.canRedo()).toBe(true);

        // Perform Redo
        const redoneState = stack.redo();
        expect(redoneState).toBeDefined();
        // The redone state should have the 'A' again
        expect(redoneState!.getCell(0, 0)?.char).toBe('A');
    });
});

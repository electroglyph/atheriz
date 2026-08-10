// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { LayerManager } from '../src/ui/LayerManager';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';

describe('LayerManager does not stack onChange listeners', () => {
  it('does not stack onChange listeners across repeated updateState calls', () => {
    const container = document.createElement('div');
    container.id = 'layers';
    document.body.appendChild(container);

    const state = new CanvasState(3, 3);
    const manager = new LayerManager('layers', state, new UndoStack());

    let renderCalls = 0;
    const originalRender = (manager as any).render.bind(manager);
    (manager as any).render = () => {
      renderCalls++;
      originalRender();
    };

    // Re-point to the same state repeatedly. Each call must detach the
    // previous listener rather than stacking an additional one.
    manager.updateState(state);
    manager.updateState(state);

    renderCalls = 0; // ignore renders from setup / updateState
    state.addLayer(); // triggers notify()

    // With stacked listeners, a single notify fires render() multiple times.
    expect(renderCalls).toBe(1);
  });

  it('renders exactly once when a re-pointed state notifies', () => {
    const container = document.createElement('div');
    container.id = 'layers';
    document.body.appendChild(container);

    const state = new CanvasState(3, 3);
    const manager = new LayerManager('layers', state, new UndoStack());

    let renderCalls = 0;
    const originalRender = (manager as any).render.bind(manager);
    (manager as any).render = () => {
      renderCalls++;
      originalRender();
    };

    manager.updateState(state);

    renderCalls = 0; // ignore renders from setup
    state.addLayer(); // triggers notify()

    // With stacked listeners, a single notify fires render() multiple times.
    expect(renderCalls).toBe(1);
  });
});
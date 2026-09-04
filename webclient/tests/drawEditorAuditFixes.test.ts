// @vitest-environment jsdom
// @ts-nocheck
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { cellEquals } from '../src/utils/colors';
import { LineTool } from '../src/tools/LineTool';
import { FillTool } from '../src/tools/FillTool';
import { MoveTool } from '../src/tools/MoveTool';
import { RotateTool } from '../src/tools/RotateTool';
import { ToolContext } from '../src/tools/Tool';
import { AppState } from '../src/types';
import { GridRenderer } from '../src/canvas/GridRenderer';
import { AnsiExporter } from '../src/export/AnsiExporter';
import { transformCharacter } from '../src/utils/transformMappings';
import { LayerManager } from '../src/ui/LayerManager';
import { TypeToolModal } from '../src/ui/TypeToolModal';
import { ImageImportDialog } from '../src/ui/ImageImportDialog';
import { SidebarResizer } from '../src/ui/SidebarResizer';
import { calculateGrid } from '../src/utils/TextToANSI';

function makeAppState(overrides: Partial<AppState> = {}): AppState {
  return {
    activeToolId: 'brush',
    rectMode: 'light',
    ovalMode: 'light',
    lineMode: 'light',
    gradientTarget: 'foreground',
    typeStyle: 'regular',
    selectedChar: 'x',
    fgColor: [255, 255, 255],
    bgColor: [0, 0, 0],
    fontFamily: 'monospace',
    gradientStops: [],
    selectMode: 'single',
    rotateMode: 'cw90',
    fillMode: 'brush',
    lineDiagonal: false,
    eyedropperTarget: 'fg-fg',
    ...overrides,
  };
}

function makeRenderer(selected: Set<string> = new Set()) {
  return {
    getSelectedCells: () => selected,
    setSelection: (s: Set<string>) => { selected = s; },
    clearSelection: () => { selected = new Set(); },
    setPreview: () => {},
    clearPreview: () => {},
  } as unknown as GridRenderer;
}

function makeCtx(state: CanvasState, overrides: Partial<AppState> = {}, selected?: Set<string>): ToolContext {
  return {
    state,
    undoStack: new UndoStack(),
    renderer: makeRenderer(selected),
    appState: makeAppState(overrides),
    modifiers: { shiftKey: false, altKey: false, ctrlKey: false },
  };
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('finding 17: undoTo(checkpoint) reverts to an earlier depth', () => {
  it('pops back to the checkpoint depth and restores that state', () => {
    const state = new CanvasState(2, 2);
    const undo = new UndoStack();
    undo.setCurrentState(state);
    undo.push(state);
    state.setCell(0, 0, { char: 'a', fg: [255, 255, 255], bg: [0, 0, 0] });
    undo.push(state);
    state.setCell(0, 0, { char: 'b', fg: [255, 255, 255], bg: [0, 0, 0] });
    undo.push(state);
    expect(undo.depth).toBe(3);

    const restored = undo.undoTo(1);
    expect(undo.depth).toBe(1);
    expect(restored!.getCell(0, 0)!.char).toBe('a');
  });
});

describe('finding 18: resize uses a per-layer bg default, not cell (0,0)', () => {
  it('grows overlays transparent and the background opaque regardless of (0,0)', () => {
    const state = new CanvasState(2, 2);
    state.addLayer(); // transparent overlay, now active
    state.setCell(0, 0, { char: 'X', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.activeLayerIndex = 0;
    state.setCell(0, 0, { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] });

    state.resize(4, 4);

    expect(state.layers[1].cells[0][0].char).toBe('X');
    expect(state.layers[1].cells[3][3].bg).toEqual([-1, -1, -1]);
    expect(state.layers[0].cells[3][3].bg).toEqual([0, 0, 0]);
  });
});

describe('finding 19: cellEquals treats missing flags as false', () => {
  it('considers undefined flags equal to explicit false', () => {
    const noFlags = { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] };
    const explicitFalse = {
      char: '', fg: [204, 204, 204], bg: [-1, -1, -1],
      bold: false, italic: false, underline: false,
    };
    expect(cellEquals(noFlags, explicitFalse)).toBe(true);
  });

  it('still distinguishes explicit true from missing flags', () => {
    const noFlags = { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] };
    const explicitTrue = {
      char: '', fg: [204, 204, 204], bg: [-1, -1, -1],
      bold: true, italic: false, underline: false,
    };
    expect(cellEquals(noFlags, explicitTrue)).toBe(false);
  });
});

describe('finding 20: Add Layer is undoable', () => {
  it('clicking .add-layer-btn adds a layer and pushes an undo entry', () => {
    const container = document.createElement('div');
    container.id = 'layers';
    document.body.appendChild(container);
    const state = new CanvasState(2, 2);
    const undo = new UndoStack();
    undo.setCurrentState(state);
    new LayerManager('layers', state, undo);

    (container.querySelector('.add-layer-btn') as HTMLElement).click();

    expect(state.layers.length).toBe(2);
    expect(undo.canUndo()).toBe(true);
  });
});

describe('finding 21: no-op strokes do not push undo', () => {
  it('LineTool click + Escape leaves no undo entry', () => {
    const state = new CanvasState(3, 3);
    const ctx = makeCtx(state);
    const tool = new LineTool();
    tool.onMouseDown(ctx, { x: 0, y: 0 });
    tool.onKeyDown(ctx, 'Escape');
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('LineTool click + second click commits and pushes undo', () => {
    const state = new CanvasState(3, 3);
    const ctx = makeCtx(state);
    const tool = new LineTool();
    tool.onMouseDown(ctx, { x: 0, y: 0 });
    tool.onMouseDown(ctx, { x: 2, y: 0 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });

  it('FillTool brush on a non-empty cell pushes no undo', () => {
    const state = new CanvasState(3, 3);
    state.setCell(1, 1, { char: 'A', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state, { fillMode: 'brush' });
    new FillTool().onMouseDown(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(false);
  });

  it('FillTool brush on an empty cell pushes undo', () => {
    const state = new CanvasState(3, 3, false);
    const ctx = makeCtx(state, { fillMode: 'brush' });
    new FillTool().onMouseDown(ctx, { x: 1, y: 1 });
    expect(ctx.undoStack.canUndo()).toBe(true);
  });
});

describe('finding 23: export skips hidden layers like the preview does', () => {
  it('omits a hidden overlay glyph from the export', () => {
    const state = new CanvasState(3, 1);
    state.addLayer();
    state.setCell(0, 0, { char: 'X', fg: [255, 255, 255], bg: [-1, -1, -1] });
    state.layers[1].visible = false;

    expect(AnsiExporter.export(state)).not.toContain('X');
  });

  it('emits a black raster for a hidden background instead of its glyphs', () => {
    const state = new CanvasState(3, 1);
    state.setCell(0, 0, { char: 'Z', fg: [255, 255, 255], bg: [0, 0, 0] });
    state.addLayer();
    state.setCell(1, 0, { char: 'Y', fg: [255, 255, 255], bg: [-1, -1, -1] });
    state.layers[0].visible = false;

    const out = AnsiExporter.export(state);
    expect(out).not.toContain('Z');
    expect(out).toContain('Y');
  });
});

describe('finding 24: 180-degree rotate works', () => {
  it('rotates an L-shape 180 degrees in place', () => {
    const state = new CanvasState(3, 3);
    for (const [c, r] of [[0, 0], [1, 0], [0, 1]]) {
      state.setCell(c, r, { char: 'L', fg: [255, 255, 255], bg: [0, 0, 0] });
    }
    const ctx = makeCtx(state, {}, new Set(['0,0', '1,0', '0,1']));
    new RotateTool().applyTransform(ctx, '180');

    const filled = new Set<string>();
    const layer = state.getActiveLayer();
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        if (layer.cells[r][c].char) filled.add(`${c},${r}`);
      }
    }
    expect([...filled].sort()).toEqual(['0,1', '1,0', '1,1']);
  });

  it('maps a single box corner through 180 degrees', () => {
    const state = new CanvasState(2, 2);
    state.setCell(0, 0, { char: '┌', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state);
    new RotateTool().applyTransform(ctx, '180');
    expect(state.getCell(0, 0)!.char).toBe('┘');
  });

  it('transformCharacter maps corners through 180 degrees directly', () => {
    expect(transformCharacter('┌', '180')).toBe('┘');
  });
});

describe('finding 25: whole-layer move/rotate ignores pure-black background cells', () => {
  it('MoveTool whole-layer drag leaves black and transparent cells behind', () => {
    const state = new CanvasState(5, 5);
    state.setCell(1, 1, { char: '', fg: [204, 204, 204], bg: [0, 0, 0] });
    state.setCell(2, 1, { char: '', fg: [204, 204, 204], bg: [-1, -1, -1] });
    state.setCell(2, 2, { char: 'A', fg: [255, 255, 255], bg: [0, 0, 0] });
    const syncCalls: Set<string>[] = [];
    const ctx = makeCtx(state);
    ctx.selectionSync = {
      setSelection: (s: Set<string>) => { syncCalls.push(new Set(s)); },
      clearSelection: () => {},
    };

    const tool = new MoveTool();
    tool.onMouseDown(ctx, { x: 0, y: 0 });
    tool.onMouseUp(ctx, { x: 1, y: 0 });

    expect(state.getCell(3, 2)!.char).toBe('A');
    expect(state.getCell(2, 2)!.char).toBe('');
    expect(state.getCell(1, 1)!.bg).toEqual([0, 0, 0]);
    expect(state.getCell(2, 1)!.bg).toEqual([-1, -1, -1]);
  });

  it('MoveTool syncs the moved selection through selectionSync', () => {
    const state = new CanvasState(5, 5);
    state.setCell(2, 2, { char: 'A', fg: [255, 255, 255], bg: [0, 0, 0] });
    const syncCalls: Set<string>[] = [];
    const ctx = makeCtx(state, {}, new Set(['2,2']));
    ctx.selectionSync = {
      setSelection: (s: Set<string>) => { syncCalls.push(new Set(s)); },
      clearSelection: () => {},
    };

    const tool = new MoveTool();
    tool.onMouseDown(ctx, { x: 2, y: 2 });
    tool.onMouseUp(ctx, { x: 3, y: 2 });

    expect(syncCalls.length).toBe(1);
    expect([...syncCalls[0]]).toEqual(['3,2']);
  });

  it('RotateTool whole-layer cw90 treats a lone glyph as a 1x1 box', () => {
    const state = new CanvasState(3, 3);
    state.setCell(2, 0, { char: 'A', fg: [255, 255, 255], bg: [0, 0, 0] });
    const ctx = makeCtx(state);
    new RotateTool().applyTransform(ctx, 'cw90');
    expect(state.getCell(2, 0)!.char).toBe('A');
    expect(state.getCell(2, 2)!.char).toBe('');
  });
});

describe('finding 26: re-entrant modal open resolves the pending promise', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="type-tool-modal" class="hidden">
        <input id="type-tool-input" />
        <button id="type-tool-ok">OK</button>
        <button id="type-tool-cancel">Cancel</button>
      </div>`;
  });

  it('second open() resolves the first caller with null', async () => {
    const modal = new TypeToolModal();
    const p1 = modal.open();
    const p2 = modal.open();
    await expect(p1).resolves.toBeNull();

    (document.getElementById('type-tool-input') as HTMLInputElement).value = 'hi';
    (document.getElementById('type-tool-ok') as HTMLButtonElement).click();
    await expect(p2).resolves.toBe('hi');
  });
});

describe('finding 28: image import failure revokes the blob URL and reports', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="image-import-modal" class="hidden">
        <input id="image-upload" type="file" />
        <input id="import-width" value="80" />
        <input id="import-height" value="40" />
        <div id="chafa-options-container"></div>
        <div id="import-error" style="display:none"></div>
        <button id="btn-import-cancel">Cancel</button>
        <button id="btn-import-confirm">OK</button>
      </div>`;
  });

  it('onerror revokes the blob URL, shows the error, and keeps the modal hidden', async () => {
    const instances: Array<{ onload: (() => void) | null; onerror: (() => void) | null; src: string }> = [];
    vi.stubGlobal('Image', class {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      src = '';
      naturalWidth = 0;
      naturalHeight = 0;
      constructor() { instances.push(this); }
    });
    const revoke = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:fake'), configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revoke, configurable: true });

    new ImageImportDialog(() => {});
    const fileInput = document.getElementById('image-upload') as HTMLInputElement;
    const file = new File(['not an image'], 'bad.png', { type: 'image/png' });
    vi.spyOn(file, 'arrayBuffer').mockResolvedValue(new ArrayBuffer(8));
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

    await new Promise((r) => setTimeout(r, 10));
    expect(instances.length).toBe(1);
    instances[0].onerror!();

    expect(revoke).toHaveBeenCalledWith('blob:fake');
    const errorEl = document.getElementById('import-error')!;
    expect(errorEl.style.display).toBe('block');
    expect(errorEl.textContent).toContain('bad.png');
    expect(document.getElementById('image-import-modal')!.classList.contains('hidden')).toBe(true);
  });
});

describe('finding 30: SidebarResizer destroy removes window unload listeners', () => {
  beforeEach(() => {
    const sidebar = document.createElement('div');
    sidebar.id = 'sidebar';
    const resizer = document.createElement('div');
    resizer.id = 'sidebar-resizer';
    document.body.appendChild(sidebar);
    document.body.appendChild(resizer);
  });

  it('removes the exact beforeunload/pagehide handlers it added', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const resizer = new SidebarResizer('sidebar', 'sidebar-resizer');
    const unloadAdded = addSpy.mock.calls.filter(
      (call) => call[0] === 'beforeunload' || call[0] === 'pagehide',
    );
    expect(unloadAdded.length).toBe(2);

    const removeSpy = vi.spyOn(window, 'removeEventListener');
    resizer.destroy();

    for (const [type, fn] of unloadAdded) {
      expect(removeSpy).toHaveBeenCalledWith(type, fn);
    }
  });
});

describe('finding 31: TextToANSI calculateGrid clamps rows on tiny canvases', () => {
  it('returns at least one row and a sane column count for height 2', () => {
    expect(calculateGrid(10, 10, 80, 2, 0.5)).toEqual({ cols: 2, rows: 1 });
  });
});

// @ts-nocheck
// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { CanvasState } from '../src/state/CanvasState';
import { UndoStack } from '../src/state/UndoStack';
import { LayerManager } from '../src/ui/LayerManager';
import { MessageDialog } from '../src/ui/MessageDialog';
import { CharPalette } from '../src/ui/CharPalette';
import { CHAR_GROUPS } from '../src/utils/characters';
import { closeOtherModals } from '../src/ui/modalHelper';

class MockIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
if (typeof window !== 'undefined') {
    (window as unknown as { IntersectionObserver: unknown }).IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
}

describe('toolbar font loading prevents concurrent requests', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <button id="tool-brush"></button><button id="tool-erase"></button><button id="tool-type"></button><button id="tool-text"></button><button id="tool-rect"></button><button id="tool-oval"></button><button id="tool-line"></button><button id="tool-gradient"></button><button id="tool-fill"></button><button id="tool-eyedropper"></button><button id="tool-select"></button><button id="tool-move"></button><button id="tool-rotate"></button>
            <select id="type-style-select"></select><select id="rect-mode-select"></select><select id="oval-mode-select"></select><select id="line-mode-select"></select><select id="gradient-target-select"></select><select id="fill-mode-select"></select><select id="eyedropper-target-select"></select><select id="select-mode-select"></select><select id="rotate-mode-select"></select>
            <button id="btn-undo"></button><button id="btn-redo"></button><button id="btn-export"></button>
            <select id="font-select"></select>
            <input type="checkbox" id="line-diagonal-checkbox" />
        `;
    });
    afterEach(() => {
        document.body.innerHTML = '';
        vi.restoreAllMocks();
        // @ts-ignore
        delete (window as unknown as { queryLocalFonts?: unknown }).queryLocalFonts;
    });

    it('marks loading and prevents duplicate requests', async () => {
        const { Toolbar } = await import('../src/ui/Toolbar');
        const appState: any = { activeToolId: 'brush', typeStyle: 'regular', rectMode: 'light', ovalMode: 'light', lineMode: 'light', gradientTarget: 'foreground', fillMode: 'brush', eyedropperTarget: 'fg-fg', selectMode: 'rectangle', rotateMode: 'cw90', fontFamily: 'Unifont' };
        const stack = new UndoStack();
        let callCount = 0;
        // @ts-ignore
        window.queryLocalFonts = async () => {
            callCount++;
            await new Promise((resolve) => setTimeout(resolve, 10));
            return [{ family: 'MockFont' } as unknown as FontData];
        };
        const toolbar: any = new Toolbar(appState, stack, () => {}, () => {}, () => {});
        const p1 = toolbar.loadSystemFonts();
        const p2 = toolbar.loadSystemFonts();
        await Promise.all([p1, p2]);
        expect(callCount).toBe(1);
        expect(toolbar.systemFontsLoading).toBe(false);
        expect(toolbar.systemFontsLoaded).toBe(true);
        const before = toolbar.fontSelect.querySelectorAll('option').length;
        await toolbar.loadSystemFonts();
        expect(toolbar.fontSelect.querySelectorAll('option').length).toBe(before);
    });
});

describe('color picker updates typed app state', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="fg-picker-container"></div><div id="bg-picker-container"></div>';
    });
    afterEach(() => document.body.innerHTML = '');

    it('writes to AppState with correct Color type', async () => {
        const { ColorPicker } = await import('../src/ui/ColorPicker');
        const appState: any = { fgColor: [10, 20, 30] as [number, number, number], bgColor: [0, 0, 0] as [number, number, number] };
        const picker = new ColorPicker('fg-picker-container', true, appState, () => {});
        (picker as any).setColor([100, 150, 200]);
        expect(appState.fgColor).toEqual([100, 150, 200]);
        picker.destroy();
        const bgPicker = new ColorPicker('bg-picker-container', false, appState, () => {});
        (bgPicker as any).setColor([5, 6, 7]);
        expect(appState.bgColor).toEqual([5, 6, 7]);
        bgPicker.destroy();
    });
});

describe('char palette isolates custom characters per instance', () => {
    beforeEach(() => {
        localStorage.clear();
        document.body.innerHTML = '<div id="palette-a"></div><div id="palette-b"></div>';
    });
    afterEach(() => {
        document.body.innerHTML = '';
        localStorage.clear();
    });

    it('does not mutate global CHAR_GROUPS when adding', () => {
        const initialGlobalLen = CHAR_GROUPS.find((group) => group.name === 'Custom')!.chars.length;
        const appState: any = { selectedChar: '█' };
        const paletteA = new CharPalette('palette-a', appState, () => {});
        const beforeGlobal = CHAR_GROUPS.find((group) => group.name === 'Custom')!.chars.length;
        paletteA.addCustomChars(['☃', '☺']);
        const afterGlobal = CHAR_GROUPS.find((group) => group.name === 'Custom')!.chars.length;
        expect(afterGlobal).toBe(beforeGlobal);
        expect(afterGlobal).toBe(initialGlobalLen);
        const paletteGroupsLen = (paletteA as unknown as { groups: { name: string; chars: string[] }[] }).groups.find((group) => group.name === 'Custom')!.chars.length;
        expect(paletteGroupsLen).toBe(initialGlobalLen + 2);
    });

    it('keeps two palettes independent', () => {
        const appState: any = { selectedChar: '█' };
        const paletteA = new CharPalette('palette-a', appState, () => {});
        const paletteB = new CharPalette('palette-b', appState, () => {});
        paletteA.addCustomChars(['☃']);
        const lenA = (paletteA as unknown as { groups: { name: string; chars: string[] }[] }).groups.find((group) => group.name === 'Custom')!.chars.length;
        const lenB = (paletteB as unknown as { groups: { name: string; chars: string[] }[] }).groups.find((group) => group.name === 'Custom')!.chars.length;
        expect(lenA).not.toBe(lenB);
        expect(lenB).toBe(CHAR_GROUPS.find((group) => group.name === 'Custom')!.chars.length);
    });

    it('persists custom chars to localStorage', () => {
        const appState: any = { selectedChar: '█' };
        const palette = new CharPalette('palette-a', appState, () => {});
        palette.addCustomChars(['☃']);
        const stored = JSON.parse(localStorage.getItem('atheriz_custom_chars')!);
        expect(stored).toContain('☃');
        document.body.innerHTML = '<div id="palette-a"></div><div id="palette-b"></div>';
        const palette2 = new CharPalette('palette-b', appState, () => {});
        const len2 = (palette2 as unknown as { groups: { name: string; chars: string[] }[] }).groups.find((group) => group.name === 'Custom')!.chars.includes('☃');
        expect(len2).toBe(true);
    });
});

describe('layer manager preserves overflow cells on merge', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="layer-test"></div>';
    });
    afterEach(() => document.body.innerHTML = '');

    it('merges overflow cells from upper to lower', () => {
        const state = new CanvasState(2, 2);
        state.addLayer();
        expect(state.layers.length).toBe(2);
        const upper = state.layers[1];
        const lower = state.layers[0];
        upper.overflowCells!.set('-1,0', { char: 'X', fg: [255, 0, 0] as [number, number, number], bg: [0, 0, 255] as [number, number, number] });
        upper.overflowCells!.set('0,-1', { char: 'Y', fg: [0, 255, 0] as [number, number, number], bg: [-1, -1, -1] as [number, number, number] });
        const manager: any = new LayerManager('layer-test', state, new UndoStack());
        manager.mergeDown(1);
        expect(state.layers.length).toBe(1);
        expect(lower.overflowCells!.has('-1,0')).toBe(true);
        expect(lower.overflowCells!.get('-1,0')!.char).toBe('X');
        expect(lower.overflowCells!.get('-1,0')!.bg).toEqual([0, 0, 255]);
        expect(lower.overflowCells!.has('0,-1')).toBe(true);
    });

    it('does not lose in-bounds cells when merging', () => {
        const state = new CanvasState(2, 2);
        state.addLayer();
        const upper = state.layers[1];
        upper.cells[0][0].char = 'A';
        upper.cells[0][0].bg = [10, 20, 30] as [number, number, number];
        const manager: any = new LayerManager('layer-test', state, new UndoStack());
        manager.mergeDown(1);
        expect(state.layers[0].cells[0][0].char).toBe('A');
    });
});

describe('message dialog handles backdrop and escape', () => {
    function mount(): void {
        document.body.innerHTML = `
        <div id="move-denied-modal" class="modal hidden">
            <div class="modal-content"><p id="move-denied-modal-message"></p><button id="move-denied-modal-ok">OK</button></div>
        </div>`;
    }
    afterEach(() => document.body.innerHTML = '');

    it('hides on backdrop click', () => {
        mount();
        const dialog = new MessageDialog('move-denied-modal');
        dialog.show('hello');
        expect(dialog.isVisible()).toBe(true);
        const container = document.getElementById('move-denied-modal')!;
        container.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(dialog.isVisible()).toBe(false);
        dialog.destroy();
    });

    it('hides on escape key', () => {
        mount();
        const dialog = new MessageDialog('move-denied-modal');
        dialog.show('hello');
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        expect(dialog.isVisible()).toBe(false);
        dialog.destroy();
    });

    it('does not hide on content click', () => {
        mount();
        const dialog = new MessageDialog('move-denied-modal');
        dialog.show('hello');
        const content = document.querySelector('.modal-content')!;
        content.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(dialog.isVisible()).toBe(true);
        dialog.destroy();
    });
});

describe('google font picker fallback for CSS.escape', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="google-font-picker-modal" class="modal hidden">
                <div id="gfp-tabs"></div><input id="gfp-search" /><div id="gfp-list"></div><button id="gfp-cancel"></button><div id="gfp-sentinel"></div>
            </div>`;
    });
    afterEach(() => {
        document.body.innerHTML = '';
        vi.restoreAllMocks();
    });

    it('uses fallback when CSS.escape is missing', async () => {
        const originalCSS = (globalThis as unknown as { CSS?: unknown }).CSS;
        // @ts-ignore
        globalThis.CSS = undefined;
        const { GoogleFontPicker } = await import('../src/ui/GoogleFontPicker');
        const picker: any = new GoogleFontPicker(() => {});
        picker.listContainer.innerHTML = '<div data-family="Special & Family"></div>';
        expect(() => picker.drainPreviewQueue()).not.toThrow();
        // @ts-ignore
        globalThis.CSS = originalCSS;
        picker.destroy();
    });
});

describe('text tool dialog font initialization', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="text-tool-modal" class="modal hidden"></div>
            <textarea id="text-tool-input"></textarea>
            <select id="text-tool-font"></select>
            <select id="text-tool-style"><option value="normal">Normal</option></select>
            <input id="text-tool-max-width" /><span id="text-tool-max-width-val"></span>
            <input id="text-tool-stretch" /><span id="text-tool-stretch-val"></span>
            <canvas id="text-tool-preview"></canvas>
            <button id="btn-text-cancel"></button><button id="btn-text-confirm"></button>
            <button id="text-tool-google-fonts-btn"></button>
            <select id="text-tool-align"><option value="left">Left</option></select>
            <div id="text-chafa-options-container"></div>
            <div id="google-font-picker-modal" class="modal hidden"><div id="gfp-tabs"></div><input id="gfp-search" /><div id="gfp-list"></div><button id="gfp-cancel"></button><div id="gfp-sentinel"></div></div>
        `;
        // @ts-ignore mock document.fonts
        if (!document.fonts) {
            Object.defineProperty(document, 'fonts', {
                value: { load: async () => {}, ready: Promise.resolve() },
                configurable: true,
            });
        }
    });
    afterEach(() => document.body.innerHTML = '');

    it('does not duplicate local fonts on second init', async () => {
        const { TextToolDialog } = await import('../src/ui/TextToolDialog');
        const appState: any = { fontFamily: 'Unifont', bgColor: [0, 0, 0], fgColor: [255, 255, 255] };
        const canvasState: any = { width: 20, height: 10 };
        const dialog: any = new TextToolDialog(appState, canvasState, () => {}, () => ({ width: 10, height: 10 }));
        dialog.initFonts();
        const firstCount = dialog.fontSelect.options.length;
        expect(firstCount).toBeGreaterThan(0);
        dialog.initFonts();
        expect(dialog.fontSelect.options.length).toBe(firstCount);
    });
});

describe('char map dialog removes badge efficiently', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="char-map-modal" class="modal hidden">
                <div id="char-map-scroll-container"><div id="char-map-inner"></div></div>
                <div id="char-map-selection"></div>
                <button id="btn-char-cancel"></button><button id="btn-char-confirm"></button>
                <div id="char-scan-status"></div>
            </div>`;
    });
    afterEach(() => document.body.innerHTML = '');

    it('removes selected class via data-char selector', async () => {
        const { CharMapDialog } = await import('../src/ui/CharMapDialog');
        const dialog: any = new CharMapDialog(() => {});
        dialog.validGlyphs = [65, 66, 67];
        dialog.totalRows = 1;
        dialog.selectedChars = new Set(['A']);
        dialog.activeRows = new Map();
        dialog.innerContainer = document.getElementById('char-map-inner')!;
        dialog.selectedPreview = document.getElementById('char-map-selection')!;
        dialog.renderRow(0);
        const row = dialog.activeRows.get(0)!;
        const cell = row.querySelector('[data-char="A"]') as HTMLElement;
        expect(cell).not.toBeNull();
        expect(cell.classList.contains('selected')).toBe(true);
        dialog.selectedChars = new Set(['A']);
        dialog.updatePreview();
        const badge = dialog.selectedPreview.querySelector('.selected-char-badge') as HTMLElement;
        badge.click();
        expect(cell.classList.contains('selected')).toBe(false);
        expect(dialog.selectedChars.has('A')).toBe(false);
    });
});

describe('preview window disposes without double clearing', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="preview-window"></div>';
    });
    afterEach(() => document.body.innerHTML = '');

    it('close disposes once and leaves container empty', async () => {
        const { PreviewWindow } = await import('../src/ui/PreviewWindow');
        const state = new CanvasState(2, 2);
        const win: any = new PreviewWindow(() => state, () => 'Unifont');
        win.modal = document.getElementById('preview-window')!;
        win.termContainer = document.createElement('div');
        win.modal.appendChild(win.termContainer);
        const mockTerm: any = { dispose: vi.fn(), open: vi.fn(), write: vi.fn() };
        win.terminal = mockTerm;
        win.close();
        expect(mockTerm.dispose).toHaveBeenCalledTimes(1);
        expect(win.terminal).toBeNull();
        win.destroy();
    });
});

describe('modal helper hides other modals', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="color-picker-modal" class="modal"></div>
            <div id="google-font-picker-modal" class="modal"></div>
            <div id="char-map-modal" class="modal"></div>
            <div id="text-tool-modal" class="modal"></div>
            <div id="preview-window" style="display: flex;"></div>
        `;
    });
    afterEach(() => document.body.innerHTML = '');

    it('hides all except current', () => {
        closeOtherModals('char-map-modal');
        expect(document.getElementById('char-map-modal')!.classList.contains('hidden')).toBe(false);
        expect(document.getElementById('color-picker-modal')!.classList.contains('hidden')).toBe(true);
        expect(document.getElementById('google-font-picker-modal')!.classList.contains('hidden')).toBe(true);
        expect(document.getElementById('text-tool-modal')!.classList.contains('hidden')).toBe(true);
        expect((document.getElementById('preview-window') as HTMLElement).style.display).toBe('none');
    });

    it('hides preview when opening another modal', () => {
        closeOtherModals('color-picker-modal');
        expect((document.getElementById('preview-window') as HTMLElement).style.display).toBe('none');
    });
});

describe('sidebar resizer cleans up on destroy', () => {
    beforeEach(() => {
        document.body.innerHTML = '<div id="sidebar"></div><div id="sidebar-resizer"></div><div id="right-sidebar"></div><div id="right-sidebar-resizer"></div>';
    });
    afterEach(() => document.body.innerHTML = '');

    it('removes listeners on destroy and on pagehide', async () => {
        const { SidebarResizer } = await import('../src/ui/SidebarResizer');
        const spy = vi.spyOn(document, 'removeEventListener');
        const resizer = new SidebarResizer('sidebar', 'sidebar-resizer');
        window.dispatchEvent(new Event('pagehide'));
        expect(spy).toHaveBeenCalled();
        spy.mockClear();
        const resizer2 = new SidebarResizer('right-sidebar', 'right-sidebar-resizer', true);
        resizer2.destroy();
        expect(spy).toHaveBeenCalledWith('mousemove', expect.any(Function));
        expect(spy).toHaveBeenCalledWith('mouseup', expect.any(Function));
    });
});

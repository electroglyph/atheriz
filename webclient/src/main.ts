import { measureCellMetrics } from './utils/fontMetrics';
import { CanvasState } from './state/CanvasState';
import { UndoStack } from './state/UndoStack';
import { GridRenderer } from './canvas/GridRenderer';
import { CanvasController } from './canvas/CanvasController';
import { ToolManager } from './tools/ToolManager';
import { AppState, Color } from './types';
import { RectangleTool } from './tools/RectangleTool';
import { OvalTool } from './tools/OvalTool';
import { LineTool } from './tools/LineTool';
import { TextTool } from './tools/TextTool';
import { TypeTool } from './tools/TypeTool';
import { ToolContext } from './tools/Tool';
import { GradientTool } from './tools/GradientTool';
import { FillTool } from './tools/FillTool';
import { SelectionTool } from './tools/SelectionTool';
import { EyedropperTool } from './tools/EyedropperTool';
import { MoveTool } from './tools/MoveTool';
import { MessageDialog } from './ui/MessageDialog';
import { RotateTool } from './tools/RotateTool';

import { CharPalette } from './ui/CharPalette';
import { ColorPicker } from './ui/ColorPicker';
import { ColorPickerModal } from './ui/ColorPickerModal';
import { cssColor } from './utils/colors';
import { Toolbar } from './ui/Toolbar';
import { SidebarResizer } from './ui/SidebarResizer';
import { NewCanvasDialog } from './ui/NewCanvasDialog';
import { ResizeCanvasDialog } from './ui/ResizeCanvasDialog';
import { ImageImportDialog } from './ui/ImageImportDialog';
import { TextToolDialog } from './ui/TextToolDialog';
import { ColorAdjustDialog } from './ui/ColorAdjustDialog';
import { applyColorAdjustments, ColorAdjustOptions } from './utils/colors';
import { convertImageToAnsi } from './utils/imageLoader';
import { parseAnsiToCells, parseAnsiToState, detectAnsiDimensions } from './utils/ansiParser';
import { AnsiExporter } from './export/AnsiExporter';
import { CharMapDialog } from './ui/CharMapDialog';
import { LayerManager } from './ui/LayerManager';
import { PreviewWindow } from './ui/PreviewWindow';
import { GradientPicker } from './ui/GradientPicker';
import { readDrawGrant, clearDrawGrant } from './webclient/launch';
import { loadMapPayload, MapEditSession, MapEditPayload, MapEditOrigin, logRoomData } from './mapedit';
import { toCssFontFamily } from './utils/cssFont';

document.fonts.ready.then(() => {
    void initApp();
});

async function initApp() {
    const canvasEl = document.getElementById('main-canvas') as HTMLCanvasElement;
    if (!canvasEl) throw new Error("Canvas missing");

    const appState: AppState = {
        activeToolId: 'brush',
        rectMode: 'light',
        ovalMode: 'light',
        lineMode: 'light',
        gradientTarget: 'foreground',
        typeStyle: 'regular',
        selectedChar: '█',
        fgColor: [204, 204, 204],
        bgColor: [0, 0, 0],
        fontFamily: 'KreativeSquare',
        gradientStops: [[0, 0, 0] as Color, [255, 255, 255] as Color],
        selectMode: 'rectangle',
        rotateMode: 'cw90',
        fillMode: 'brush',
        lineDiagonal: false,
        eyedropperTarget: 'fg-fg'
    };

    const undoStack = new UndoStack();

    let canvasState = new CanvasState(24, 24);

    const grant = readDrawGrant();
    let mapEditSession: MapEditSession | null = null;
    let mapEditOrigin: MapEditOrigin | null = null;
    let mapPayload: MapEditPayload | null = null;
    let roomCellSet: Set<string> | null = null;
    if (grant) {
        const payload = grant.payload as MapEditPayload;
        mapPayload = payload;
        mapEditOrigin = loadMapPayload(canvasState, payload);
        mapEditSession = new MapEditSession(grant.key, canvasState, mapEditOrigin);
        roomCellSet = new Set(mapEditOrigin.roomCells);
        clearDrawGrant();
    }

    undoStack.setCurrentState(canvasState);

    let currentFontSize = 18;
    if (document.fonts) {
        const family = toCssFontFamily(appState.fontFamily);
        try { await document.fonts.load(`${currentFontSize}px ${family}`, ''); } catch {}
        try { await document.fonts.load(`${currentFontSize}px ${family}`, 'M'); } catch {}
        try { await document.fonts.ready; } catch {}
    }
    let metrics = measureCellMetrics(appState.fontFamily, currentFontSize);
    const renderer = new GridRenderer(canvasEl, canvasState, metrics);

    if (mapEditOrigin) {
        renderer.setRoomCells(roomCellSet ?? mapEditOrigin.roomCells);
    }
    if (mapPayload) {
        logRoomData(mapPayload);
    }

    const context: ToolContext = {
        state: canvasState,
        undoStack,
        renderer,
        appState,
        modifiers: { shiftKey: false, altKey: false, ctrlKey: false }
    };

    context.onCellsMoved = (moves) => {
        if (!mapEditSession || !mapEditOrigin) return;
        const worldMoves = moves.map((m) => ({
            fromX: m.fromCol + mapEditOrigin!.originX,
            fromY: canvasState.height - 1 - m.fromRow + mapEditOrigin!.originY,
            toX: m.toCol + mapEditOrigin!.originX,
            toY: canvasState.height - 1 - m.toRow + mapEditOrigin!.originY,
        }));
        if (roomCellSet) {
            for (const m of moves) {
                const key = `${m.fromCol},${m.fromRow}`;
                if (roomCellSet.has(key)) {
                    roomCellSet.delete(key);
                    roomCellSet.add(`${m.toCol},${m.toRow}`);
                }
            }
            renderer.setRoomCells(roomCellSet);
        }
        mapEditSession.validateRoomMoves(worldMoves);
    };


    const textToolDialog = new TextToolDialog(appState, canvasState, (newState) => {
        canvasState = newState;
        context.state = canvasState;
        undoStack.setCurrentState(canvasState);
        renderer.updateState(canvasState);
    }, () => metrics, undoStack);

    const toolManager = new ToolManager(context);
    toolManager.addTool('rect', new RectangleTool());
    toolManager.addTool('oval', new OvalTool());
    toolManager.addTool('line', new LineTool());
    toolManager.addTool('type', new TypeTool());
    toolManager.addTool('text', new TextTool(() => textToolDialog.open()));
    toolManager.addTool('gradient', new GradientTool());
    toolManager.addTool('fill', new FillTool());
    toolManager.addTool('eyedropper', new EyedropperTool());
    const selectionTool = new SelectionTool();
    toolManager.addTool('select', selectionTool);
    toolManager.addTool('move', new MoveTool());
    const rotateTool = new RotateTool();
    toolManager.addTool('rotate', rotateTool);

    const controller = new CanvasController(canvasEl, metrics, toolManager);
    if (document.fonts && !document.fonts.check(`${currentFontSize}px ${toCssFontFamily(appState.fontFamily)}`)) {
        void document.fonts.ready.then(() => {
            const refreshed = measureCellMetrics(appState.fontFamily, currentFontSize);
            controller.updateMetrics(refreshed);
            renderer.updateMetrics(refreshed);
        });
    }

    canvasEl.addEventListener('mousedown', (e) => {
        if (e.button === 2) {
            selectionTool.clearSelection(context);
            renderer.clearSelection();
        }
    });

    let charMapDialog: CharMapDialog;

    const charPalette = new CharPalette('char-palette', appState, () => {
        if (appState.activeToolId === 'erase') appState.activeToolId = 'brush'; // switch back
    }, () => {
        charMapDialog.open(appState.fontFamily);
    });

    charMapDialog = new CharMapDialog((chars: string[]) => {
        charPalette.addCustomChars(chars);
    });

    new ColorPicker('fg-picker-container', true, appState, () => {
        if (appState.activeToolId === 'erase') appState.activeToolId = 'brush';
    });

    new ColorPicker('bg-picker-container', false, appState, () => {
        if (appState.activeToolId === 'erase') appState.activeToolId = 'brush';
    });

    new GradientPicker('gradient-picker-container', appState);

    const layerManager = new LayerManager('layer-manager-container', canvasState, undoStack);

    const moveDeniedDialog = new MessageDialog('move-denied-modal');

    // Safe to register here: websocket events are async and cannot fire
    // before the synchronous setup below this point has completed.
    mapEditSession?.onEvent((event) => {
        if (event.type === 'reject') {
            console.warn(`Map edit rejected (${event.reason}). Re-run 'mapedit' in-game.`);
        } else if (event.type === 'error') {
            console.warn(`Map edit connection failed: ${event.message}. Re-run 'mapedit' in-game.`);
        } else if (event.type === 'saved') {
            if ((import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV) console.log('Saved to server.');
        } else if (event.type === 'moves_denied') {
            console.warn('Room move denied by server — snapping back.');
            const restored = undoStack.undo();
            if (restored) {
                canvasState = restored;
                context.state = restored;
                renderer.updateState(restored);
                layerManager.updateState(restored);
            }
            if (roomCellSet && mapEditOrigin) {
                for (const m of event.moves) {
                    const toCol = m.toX - mapEditOrigin.originX;
                    const toRow = canvasState.height - 1 - (m.toY - mapEditOrigin.originY);
                    const fromCol = m.fromX - mapEditOrigin.originX;
                    const fromRow = canvasState.height - 1 - (m.fromY - mapEditOrigin.originY);
                    const key = `${toCol},${toRow}`;
                    if (roomCellSet.has(key)) {
                        roomCellSet.delete(key);
                        roomCellSet.add(`${fromCol},${fromRow}`);
                    }
                }
                renderer.setRoomCells(roomCellSet);
            }
            const maxListed = 5;
            const listed = event.moves
                .slice(0, maxListed)
                .map((m) => `(${m.toX}, ${m.toY})`)
                .join(', ');
            const extra = event.moves.length > maxListed ? ` and ${event.moves.length - maxListed} more` : '';
            moveDeniedDialog.show(
                `The server rejected moving ${event.moves.length === 1 ? 'a room' : `${event.moves.length} rooms`} `
                + `to ${listed}${extra} — destination occupied. Your changes were undone.`
            );
        }
    });

    const toolbarInst = new Toolbar(appState, undoStack, () => {
        AnsiExporter.download(canvasState, 'art.ans');
    }, (newState: CanvasState) => {
        canvasState = newState;
        context.state = canvasState;
        renderer.updateState(canvasState);
        layerManager.updateState(canvasState);
    }, async (fontFamily: string) => {
        if (document.fonts) {
            const fam = toCssFontFamily(fontFamily);
            try { await document.fonts.load(`${currentFontSize}px ${fam}`, ''); } catch {}
            try { await document.fonts.load(`${currentFontSize}px ${fam}`, 'M'); } catch {}
        }
        metrics = measureCellMetrics(fontFamily, currentFontSize);
        controller.updateMetrics(metrics);
        renderer.updateMetrics(metrics);
        
        document.documentElement.style.setProperty('--main-font', toCssFontFamily(fontFamily));
        charPalette.reRender();
    }, () => {
        textToolDialog.open();
    });
    toolbarInst.clearSelectionCallback = () => selectionTool.clearSelection();
    toolbarInst.onRotateAction = (mode) => {
        rotateTool.applyTransform(context, mode);
    };

    const syncTextToolDialog = () => {
        textToolDialog.updateCanvasState(canvasState);
    };

    const leftResizer = new SidebarResizer('sidebar', 'sidebar-resizer');
    const rightResizer = new SidebarResizer('right-sidebar', 'right-sidebar-resizer', true);

    const previewWindow = new PreviewWindow(
        () => canvasState,
        () => appState.fontFamily
    );
    document.getElementById('btn-preview')?.addEventListener('click', () => {
        previewWindow.open();
    });

    window.addEventListener('beforeunload', () => {
        leftResizer.destroy();
        rightResizer.destroy();
        previewWindow.destroy();
        toolbarInst.destroy();
    });

    let roomVisible = true;
    let roomColor: [number, number, number] = [0, 204, 204];
    const btnRoomToggle = document.getElementById('btn-room-toggle');
    const roomColorSwatch = document.getElementById('room-color-swatch');
    const applyRoomColor = () => {
        if (roomColorSwatch) roomColorSwatch.style.backgroundColor = cssColor(roomColor);
        renderer.setRoomColor(cssColor(roomColor));
    };
    btnRoomToggle?.addEventListener('click', () => {
        roomVisible = !roomVisible;
        renderer.setRoomVisible(roomVisible);
        btnRoomToggle.textContent = roomVisible ? 'Hide Room Color' : 'Show Room Color';
    });
    document.getElementById('btn-room-color')?.addEventListener('click', () => {
        ColorPickerModal.getInstance().open(roomColor).then((result) => {
            if (result) {
                roomColor = result;
                applyRoomColor();
            }
        });
    });
    applyRoomColor();

    new NewCanvasDialog((w, h) => {
        undoStack.push(canvasState);
        canvasState = new CanvasState(w, h);
        
        context.state = canvasState;
        undoStack.setCurrentState(canvasState);
        renderer.updateState(canvasState);
        layerManager.updateState(canvasState);
        syncTextToolDialog();
    });

    new ResizeCanvasDialog(() => canvasState, (w, h) => {
        undoStack.push(canvasState);
        canvasState.resize(w, h);
        
        renderer.updateState(canvasState);
        layerManager.updateState(canvasState);
        syncTextToolDialog();
    });

    new ImageImportDialog(async (buffer, w, h, config) => {
        try {
            const ansi = await convertImageToAnsi(buffer, w, h, config);
            const cells = await parseAnsiToCells(ansi, w, h);
            
            undoStack.push(canvasState);
            
            canvasState = new CanvasState(w, h);
            context.state = canvasState;
            undoStack.setCurrentState(canvasState);
            layerManager.updateState(canvasState);
            
            // Map flat parsed cells array to batch format for CanvasState
            const batch = [];
            for (let i = 0; i < cells.length; i++) {
                const col = i % w;
                const row = Math.floor(i / w);
                if (row < h) {
                    batch.push({ col, row, cell: cells[i] });
                }
            }
            canvasState.applyBatch(batch);
            renderer.updateState(canvasState);
            syncTextToolDialog();
        } catch (e) {
            console.error("Failed to load image:", e);
        }
    });

    const btnLoadImage = document.getElementById('btn-load-image');
    const imageUpload = document.getElementById('image-upload');
    btnLoadImage?.addEventListener('click', () => {
        imageUpload?.click();
    });

    const btnLoadAnsi = document.getElementById('btn-load-ansi');
    const ansiUpload = document.getElementById('ansi-upload') as HTMLInputElement;
    btnLoadAnsi?.addEventListener('click', () => ansiUpload?.click());

    const btnSaveServer = document.getElementById('btn-save-server');
    btnSaveServer?.addEventListener('click', () => {
        if (!mapEditSession) {
            console.warn('No map edit session — re-run mapedit in-game.');
            return;
        }
        mapEditSession.saveToServer();
    });

    ansiUpload?.addEventListener('change', () => {
        const file = ansiUpload.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            const text = e.target?.result as string;
            if (!text) return;
            try {
                // Detect the file's true dimensions so the canvas is never clipped
                const { width, height } = detectAnsiDimensions(text);
                const newState = await parseAnsiToState(text, width, height);
                undoStack.push(canvasState);
                canvasState = newState;
                context.state = canvasState;
                undoStack.setCurrentState(canvasState);
                renderer.updateState(canvasState);
                layerManager.updateState(canvasState);
                syncTextToolDialog();
            } catch (err) {
                console.error('Failed to load ANSI file:', err);
            }
        };
        reader.readAsText(file);
        ansiUpload.value = '';
    });

    let previewState: CanvasState | null = null;
    
    const applyAdjustmentsToState = (state: CanvasState, opts: ColorAdjustOptions, applyToAll: boolean) => {
        const startIdx = applyToAll ? 0 : state.activeLayerIndex;
        const endIdx = applyToAll ? state.layers.length - 1 : state.activeLayerIndex;
        for (let i = startIdx; i <= endIdx; i++) {
            const layer = state.layers[i];
            for (let r = 0; r < state.height; r++) {
                for (let c = 0; c < state.width; c++) {
                    const cell = layer.cells[r][c];
                    cell.fg = applyColorAdjustments(cell.fg, opts);
                    if (cell.bg[0] !== -1) {
                        cell.bg = applyColorAdjustments(cell.bg, opts);
                    }
                }
            }
            if (layer.overflowCells) {
                for (const [, cell] of layer.overflowCells.entries()) {
                    cell.fg = applyColorAdjustments(cell.fg, opts);
                    if (cell.bg[0] !== -1) {
                        cell.bg = applyColorAdjustments(cell.bg, opts);
                    }
                }
            }
        }
    };

    const colorAdjustDialog = new ColorAdjustDialog(
        (opts, all) => {
            // On Preview
            if (!previewState) previewState = canvasState.clone();
            const tempState = previewState.clone();
            applyAdjustmentsToState(tempState, opts, all);
            renderer.updateState(tempState);
        },
        (opts, all) => {
            // On Apply
            if (!previewState) previewState = canvasState.clone();
            applyAdjustmentsToState(previewState, opts, all);
            
            undoStack.push(canvasState);
            canvasState = previewState;
            previewState = null;
            
            context.state = canvasState;
            undoStack.setCurrentState(canvasState);
            renderer.updateState(canvasState);
            layerManager.updateState(canvasState);
            syncTextToolDialog();
        },
        () => {
            previewState = null;
            renderer.updateState(canvasState);
        }
    );

    document.getElementById('btn-color-adjust')?.addEventListener('click', () => {
        previewState = canvasState.clone();
        colorAdjustDialog.open();
    });

    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');

    const updateFontMetrics = async () => {
        if (document.fonts) {
            const fam = toCssFontFamily(appState.fontFamily);
            try { await document.fonts.load(`${currentFontSize}px ${fam}`, ''); } catch {}
            try { await document.fonts.load(`${currentFontSize}px ${fam}`, 'M'); } catch {}
        }
        metrics = measureCellMetrics(appState.fontFamily, currentFontSize);
        controller.updateMetrics(metrics);
        renderer.updateMetrics(metrics);
        charPalette.reRender();
    };

    btnZoomIn?.addEventListener('click', () => {
        if (currentFontSize < 72) {
            currentFontSize += 2;
            void updateFontMetrics();
        }
    });

    btnZoomOut?.addEventListener('click', () => {
        if (currentFontSize > 6) {
            currentFontSize -= 2;
            void updateFontMetrics();
        }
    });
}

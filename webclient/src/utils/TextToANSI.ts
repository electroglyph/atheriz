import { CanvasState } from "../state/CanvasState";
import { Cell } from "../types";
import { convertImageToAnsi } from "./imageLoader";
import { parseAnsiToCells } from "./ansiParser";
import { ChafaConfig } from "./chafaDefaults";
import { CellMetrics } from "./fontMetrics";

export function calculateGrid(
  cropW: number,
  cropH: number,
  maxWidthGlyphs: number,
  canvasHeight: number,
  fontRatio: number,
): { cols: number; rows: number } {
  const maxRows = Math.max(1, canvasHeight - 2);
  // fontRatio = cellWidth / cellHeight. rows = (cols * cropH * fontRatio) / cropW
  let cols = maxWidthGlyphs;
  let rows = Math.max(1, Math.round((cols * cropH * fontRatio) / cropW));

  if (rows > maxRows) {
    cols = Math.max(1, Math.round((maxRows * cropW) / (cropH * fontRatio)));
    rows = maxRows;
  }

  return { cols: Math.min(cols, maxWidthGlyphs), rows: Math.max(1, rows) };
}

export function previewFontString(cellFont: string, px = 96): string {
  return `${px}px ${cellFont.replace(/^\d+(\.\d+)?px\s+/, '')}`;
}

/**
 * Pipeline to convert drawn text on a temporary Canvas into quantized ANSI art:
 * 1. Derives an exact bounding box isolating the text content.
 * 2. Crops the source canvas to eliminate arbitrary whitespace.
 * 3. Dynamically calculates an ANSI grid matching the font aspect ratio.
 * 4. Passes standard PNG data to Chafa for WASM-based color quantization.
 * 5. Applies resulting Chafa cells natively into the application State.
 */
export async function renderTextToAnsiLayer(
  text: string,
  maxWidthGlyphs: number,
  canvasState: CanvasState,
  chafaConfig: ChafaConfig,
  sourceCanvas: HTMLCanvasElement,
  cellMetrics: CellMetrics,
) {
  const fontRatio = cellMetrics.width / cellMetrics.height;

  const ctx = sourceCanvas.getContext("2d")!;
  const w = sourceCanvas.width;
  const h = sourceCanvas.height;

   ctx.font = previewFontString(cellMetrics.font);
   const textMetrics = ctx.measureText("M");
   const metricsExt = textMetrics as unknown as { actualBoundingBoxAscent?: number; actualBoundingBoxDescent?: number };
   const ascent = metricsExt.actualBoundingBoxAscent ?? 80;
   const descent = metricsExt.actualBoundingBoxDescent ?? 20;

  const pixels = ctx.getImageData(0, 0, w, h).data;

  let minX = w,
    minY = h,
    maxX = 0,
    maxY = 0;
  let hasContent = false;

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const idx = (y * w + x) * 4;
      if (pixels[idx] > 10 || pixels[idx + 1] > 10 || pixels[idx + 2] > 10) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
        hasContent = true;
      }
    }
  }

  if (!hasContent) {
    console.warn(
      "[TextToANSI] SCAN FAILED: No colored pixels found in preview.",
    );
    return;
  }

  const pad = 10;
  const padTop = Math.max(pad, Math.ceil(ascent * 0.15));
  const padBottom = Math.max(pad, Math.ceil(descent * 0.15));
  minX = Math.max(0, minX - pad);
  minY = Math.max(0, minY - padTop);
  maxX = Math.min(w - 1, maxX + pad);
  maxY = Math.min(h - 1, maxY + padBottom);

  const cropW = maxX - minX + 1;
  const cropH = maxY - minY + 1;

  const cropCanvas = document.createElement("canvas");
  cropCanvas.width = cropW;
  cropCanvas.height = cropH;
  const cropCtx = cropCanvas.getContext("2d")!;
  cropCtx.fillStyle = "#000000";
  cropCtx.fillRect(0, 0, cropW, cropH);
  cropCtx.drawImage(
    sourceCanvas,
    minX,
    minY,
    cropW,
    cropH,
    0,
    0,
    cropW,
    cropH,
  );

  const buffer = await new Promise<ArrayBuffer | null>((resolve) => {
    cropCanvas.toBlob((blob) => {
      if (!blob) resolve(null);
      else
        blob
          .arrayBuffer()
          .then(resolve)
          .catch(() => resolve(null));
    }, "image/png");
  });

  if (!buffer) return;

  const grid = calculateGrid(cropW, cropH, maxWidthGlyphs, canvasState.height, fontRatio);
  const totalCols = grid.cols;
  const totalRows = grid.rows;

  const ansi = await convertImageToAnsi(
    buffer,
    totalCols,
    totalRows,
    { ...chafaConfig, fontRatio },
  );

  const rawCells = await parseAnsiToCells(ansi, totalCols, totalRows);

  const batch: { col: number; row: number; cell: Cell }[] = [];
  const startX = Math.floor(canvasState.width / 2 - totalCols / 2);
  const startY = Math.floor(canvasState.height / 2 - totalRows / 2);

  for (let i = 0; i < rawCells.length; i++) {
    const localCol = i % totalCols;
    const localRow = Math.floor(i / totalCols);
    const cell = rawCells[i];

    if (!cell.char) {
      if (
        cell.bg[0] === -1 ||
        (cell.bg[0] === 0 && cell.bg[1] === 0 && cell.bg[2] === 0)
      ) {
        continue;
      }
    }

    batch.push({
      col: startX + localCol,
      row: startY + localRow,
      cell,
    });
  }

  if (batch.length > 0) {
    canvasState.addLayer(`Text: ${text.substring(0, 10)}`, false);
    canvasState.applyBatch(batch);
  }
}

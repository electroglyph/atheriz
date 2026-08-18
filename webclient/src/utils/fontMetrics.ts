import { toCssFontFamily } from "./cssFont";

export interface CellMetrics {
  width: number;
  height: number;
  font: string;
  /** unrounded glyph advance; the editor cell grid is derived from this */
  advance: number;
}

export interface TextMetricsInput {
  width?: number;
  fontBoundingBoxAscent?: number;
  fontBoundingBoxDescent?: number;
  actualBoundingBoxAscent?: number;
  actualBoundingBoxDescent?: number;
}

const GRID_LEADING = 2;

export function deriveCellMetrics(fontSize: number, tm: TextMetricsInput): { width: number; height: number } {
  const width = Math.max(1, Math.ceil(tm.width ?? fontSize * 0.6));

  const ascent = tm.fontBoundingBoxAscent ?? tm.actualBoundingBoxAscent;
  const descent = tm.fontBoundingBoxDescent ?? tm.actualBoundingBoxDescent;
  const height = ascent != null && descent != null
    ? Math.ceil(ascent + descent + GRID_LEADING)
    : Math.ceil(fontSize * 1.2);

  return { width, height };
}

export function measureCellMetrics(
  fontFamily: string,
  fontSize: number,
): CellMetrics {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;

  const font = `${fontSize}px ${toCssFontFamily(fontFamily)}`;
  ctx.font = font;

  const tm = ctx.measureText("M") as TextMetricsInput;
  const { width, height } = deriveCellMetrics(fontSize, tm);
  const advance = tm.width ?? fontSize * 0.6;

  return { width, height, font, advance };
}

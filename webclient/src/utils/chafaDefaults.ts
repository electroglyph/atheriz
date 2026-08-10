export interface ChafaConfig {
  format: string | number;
  height: number;
  colors: string | number;
  colorExtractor: string | number;
  colorSpace: string | number;
  symbols: string;
  fill: string;
  fgOnly: boolean;
  dither: string | number;
  ditherGrainWidth: number;
  ditherGrainHeight: number;
  ditherIntensity: number;
  preprocess: boolean;
  threshold: number;
  optimize: number;
  work: number;
  fontRatio?: number;
}

export const DEFAULT_CHAFA_OPTIONS: ChafaConfig = {
  format: "CHAFA_PIXEL_MODE_SYMBOLS",
  height: 25,
  colors: "CHAFA_CANVAS_MODE_TRUECOLOR",
  colorExtractor: "CHAFA_COLOR_EXTRACTOR_AVERAGE",
  colorSpace: "CHAFA_COLOR_SPACE_RGB",
  symbols: "block+border+space-wide-inverted",
  fill: "none",
  fgOnly: false,
  dither: "CHAFA_DITHER_MODE_NONE",
  ditherGrainWidth: 4,
  ditherGrainHeight: 4,
  ditherIntensity: 1.0,
  preprocess: true,
  threshold: 0.5,
  optimize: 9,
  work: 9,
};

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

const root = join(__dirname, '..');

function src(rel: string): string {
  return readFileSync(join(root, rel), 'utf8');
}

describe('main.ts declares singletons before use', () => {
  it('declares charPalette before any callback that calls it', () => {
    const main = src('src/main.ts');
    const declIdx = main.indexOf('const charPalette');
    // Find the first usage of charPalette.reRender in the source text.
    const useIdx = main.indexOf('charPalette.reRender');
    expect(declIdx).toBeGreaterThan(-1);
    expect(useIdx).toBeGreaterThan(-1);
    // Proper behavior: declaration precedes the usage (no TDZ risk).
    expect(declIdx).toBeLessThan(useIdx);
  });

  it('declares layerManager before any callback that calls it', () => {
    const main = src('src/main.ts');
    const declIdx = main.indexOf('const layerManager');
    const useIdx = main.indexOf('layerManager.');
    expect(declIdx).toBeGreaterThan(-1);
    expect(useIdx).toBeGreaterThan(-1);
    expect(declIdx).toBeLessThan(useIdx);
  });
});

describe('font metrics do not compute unused baselineY', () => {
  it('does not compute a baselineY that is never used', () => {
    const fm = src('src/utils/fontMetrics.ts');
    expect(fm).not.toContain('baselineY');
  });
});

describe('bresenham is shared via the geometry module', () => {
  it('LineTool imports getLinePoints instead of defining its own bresenham', () => {
    const lt = src('src/tools/LineTool.ts');
    expect(lt).not.toMatch(/function\s+bresenham/);
  });

  it('SelectionTool imports getLinePoints instead of defining its own bresenham', () => {
    const st = src('src/tools/SelectionTool.ts');
    expect(st).not.toMatch(/function\s+bresenham/);
  });
});

describe('canvas shows a crosshair cursor', () => {
  it('#main-canvas uses a crosshair cursor, not default', () => {
    const css = src('src/style.css');
    const block = css.match(/#main-canvas\s*\{[^}]*\}/);
    expect(block).toBeTruthy();
    const rule = block![0];
    // Proper behavior: the base canvas rule must not force cursor: default.
    expect(rule).not.toMatch(/cursor:\s*default/);
  });
});

describe('no dead code or debug leftovers', () => {
  it('TextToANSI.ts contains no debug console.log calls', () => {
    const ansi = src('src/utils/TextToANSI.ts');
    expect(ansi).not.toMatch(/console\.log/);
  });

  it('characters.ts no longer exports unused getSmartChar', () => {
    const chars = src('src/utils/characters.ts');
    expect(chars).not.toMatch(/export\s+function\s+getSmartChar/);
  });

  it('characters.ts no longer exports unused getCircleChar', () => {
    const chars = src('src/utils/characters.ts');
    expect(chars).not.toMatch(/export\s+function\s+getCircleChar/);
  });
});
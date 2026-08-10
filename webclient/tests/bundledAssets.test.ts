import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

const root = join(__dirname, '..');

describe('bundled Fira Code family is referenced consistently', () => {
  it('bundled FiraCode.css declares the family the app references', () => {
    const css = readFileSync(join(root, 'fonts/FiraCode.css'), 'utf8');
    // App uses 'Fira Code'; the css currently declares 'Fira Custom'.
    expect(css).toMatch(/'Fira Code'/);
  });
});

describe('chafa.wasm URL resolves under a deployment subpath', () => {
  it('imageLoader resolves the wasm URL from BASE_URL, not hardcoded root', () => {
    const src = readFileSync(join(root, 'src/utils/imageLoader.ts'), 'utf8');
    expect(src).not.toMatch(/['"]\/chafa\.wasm['"]/);
    expect(src).toContain('import.meta.env.BASE_URL');
  });
});
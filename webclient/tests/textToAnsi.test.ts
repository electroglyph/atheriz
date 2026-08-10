import { describe, it, expect } from 'vitest';
import { previewFontString } from '../src/utils/TextToANSI';

describe('previewFontString builds a valid ctx.font', () => {
  it('uses the preview size plus the family from a full font string', () => {
    expect(previewFontString('18px "Unifont"')).toBe('96px "Unifont"');
    expect(previewFontString('18px "Unifont"')).not.toMatch(/^96px "18px /);
  });

  it('passes a multi-family list through without mangling', () => {
    expect(previewFontString("18px 'Fira Code', 'FiraCode'")).toBe(
      "96px 'Fira Code', 'FiraCode'",
    );
  });

  it('leaves bare keywords intact', () => {
    expect(previewFontString('22px monospace')).toBe('96px monospace');
  });
});

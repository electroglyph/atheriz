import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(__dirname, '..');

describe('webclient visual setup', () => {
    it('preloads the bundled terminal font', () => {
        const html = readFileSync(join(root, 'webclient/index.html'), 'utf8');
        expect(html).toContain('/fonts/Fira_Custom.ttf');
    });

    it('keeps legacy terminal pane borders', () => {
        const css = readFileSync(join(root, 'src/webclient/style.css'), 'utf8');
        expect(css).toContain('border-left: 5px solid #333');
        expect(css).toContain('border-right: 5px solid #333');
    });

    it('gives the right terminal the remaining flex space', () => {
        const css = readFileSync(join(root, 'src/webclient/style.css'), 'utf8');
        expect(css).toContain('flex: 1 1 auto');
        expect(css).toContain('width: auto');
    });
});

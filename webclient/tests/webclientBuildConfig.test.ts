import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const root = join(__dirname, '..');

function readJson(rel: string): any {
    return JSON.parse(readFileSync(join(root, rel), 'utf8'));
}
function src(rel: string): string {
    return readFileSync(join(root, rel), 'utf8');
}

describe('typescript project is configured to typecheck source and tests', () => {
    it('primary tsconfig checks src and has strict settings', () => {
        const ts = readJson('tsconfig.json');
        expect(ts.include).toContain('src');
        expect(ts.compilerOptions.strict).toBe(true);
        expect(ts.compilerOptions.noEmit).toBe(true);
        expect(ts.compilerOptions.skipLibCheck).toBe(true);
    });

    it('separate tests config extends primary and includes tests and vite config', () => {
        expect(existsSync(join(root, 'tsconfig.tests.json'))).toBe(true);
        const testTs = readJson('tsconfig.tests.json');
        expect(testTs.extends).toBe('./tsconfig.json');
        const inc: string[] = testTs.include ?? [];
        expect(inc).toContain('tests');
        expect(inc).toContain('src');
        expect(inc.join(' ')).toContain('vite.config');
    });

    it('typecheck script runs both configs', () => {
        const pkg = readJson('package.json');
        const script: string = pkg.scripts?.typecheck ?? '';
        expect(script).toContain('tsc --noEmit');
        expect(script).toContain('tsconfig.tests.json');
    });
});

describe('vite base is compatible with FastAPI static mount', () => {
    it('uses /static/ so assets resolve under the mounted prefix', () => {
        const cfg = src('vite.config.ts');
        expect(cfg).toContain("base: '/static/'");
        expect(cfg).not.toMatch(/base:\s*'\/'\s*,/);
    });

    it('webclient entry is bundled with hashed assets', () => {
        const cfg = src('vite.config.ts');
        expect(cfg).toContain("input:");
        expect(cfg).toContain("webclient:");
        expect(cfg).toContain("draw:");
    });

    it('built webclient html uses hashed asset under /static/', () => {
        const built = src('dist/webclient/index.html');
        expect(built).toContain('/static/assets/');
        expect(built).toContain('Fira_Custom');
    });
});

describe('package declares runtime requirements and avoids dead native deps', () => {
    it('declares node engine so canvas native prebuild requirement is explicit', () => {
        const pkg = readJson('package.json');
        expect(pkg.engines).toBeDefined();
        expect(pkg.engines.node).toMatch(/>=.*18/);
    });

    it('declares browserslist for modern targets', () => {
        const pkg = readJson('package.json');
        expect(pkg.browserslist).toBeDefined();
        expect(Array.isArray(pkg.browserslist)).toBe(true);
        expect(pkg.browserslist.length).toBeGreaterThan(0);
    });

    it('does not depend on unused opentype parser', () => {
        const pkg = readJson('package.json');
        const allDeps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
        expect(allDeps['opentype.js']).toBeUndefined();
        expect(allDeps['@types/opentype.js']).toBeUndefined();
    });

    it('still depends on canvas for node-side font metrics in tests', () => {
        const pkg = readJson('package.json');
        expect(pkg.devDependencies?.canvas).toBeDefined();
    });

    it('is ESM with typecheck and test scripts', () => {
        const pkg = readJson('package.json');
        expect(pkg.type).toBe('module');
        expect(pkg.scripts?.typecheck).toContain('tsc');
        expect(pkg.scripts?.test).toBeDefined();
    });
});

describe('browser shim for node:module is typed to match node API', () => {
    it('createRequire accepts a specifier and never returns', () => {
        const shim = src('src/shims/node-module.ts');
        expect(shim).toMatch(/export function createRequire\s*\(\s*_specifier\s*:\s*string\s*\)\s*:\s*never/);
        expect(shim).toContain("throw new Error('Node module loading is unavailable in the browser')");
    });

    it('is aliased in vite config', () => {
        const cfg = src('vite.config.ts');
        expect(cfg).toContain("'node:module'");
        expect(cfg).toContain('src/shims/node-module.ts');
    });
});

describe('revision is generated from webclient content hash at build time', () => {
    it('defines __WEBCLIENT_REVISION__ via content hash', () => {
        const cfg = src('vite.config.ts');
        expect(cfg).toContain('__WEBCLIENT_REVISION__');
        expect(cfg).toContain('webclientHash');
        expect(cfg).toContain('createHash');
    });

    it('declares the global in vite-env.d.ts', () => {
        const dts = src('src/vite-env.d.ts');
        expect(dts).toContain('__WEBCLIENT_REVISION__');
    });
});

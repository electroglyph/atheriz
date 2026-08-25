import { defineConfig } from 'vite';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

function collectFiles(dir: string, out: string[] = []): string[] {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) collectFiles(full, out);
        else out.push(full);
    }
    return out;
}

function webclientHash(): string {
    const hash = crypto.createHash('sha256');
    const webclientDir = path.resolve(import.meta.dirname, 'src/webclient');
    let files: string[] = [];
    try {
        files = collectFiles(webclientDir);
    } catch {}
    files.sort();
    for (const file of files) {
        try {
            hash.update(fs.readFileSync(file));
        } catch {}
    }
    return hash.digest('hex');
}

function webclientRevision(): string {
    const cachePath = path.resolve(import.meta.dirname, '.webclient-revision.json');
    const hash = webclientHash();
    try {
        const cached = JSON.parse(fs.readFileSync(cachePath, 'utf8')) as { hash?: string; revision?: string };
        if (cached.hash === hash && typeof cached.revision === 'string' && cached.revision) {
            return cached.revision;
        }
    } catch {}
    const revision = new Date().toISOString();
    try {
        fs.writeFileSync(cachePath, JSON.stringify({ hash, revision, generatedAt: revision }, null, 2) + '\n');
    } catch {}
    return revision;
}

export default defineConfig({
  // Both pages are mounted below the AtheriZ static root. Shared absolute
  // assets keep /webclient/ and /atheriz_draw/ compatible with one build.
  // Assets are served via FastAPI's /static mount, so base must be /static/.
  base: '/static/',
  define: {
    __WEBCLIENT_REVISION__: JSON.stringify(webclientRevision()),
  },
  resolve: {
    alias: {
      '@xterm/headless': path.resolve(import.meta.dirname, 'node_modules/@xterm/headless/lib-headless/xterm-headless.mjs'),
      'node:module': path.resolve(import.meta.dirname, 'src/shims/node-module.ts'),
    },
  },
  optimizeDeps: {
    exclude: ['chafa-wasm'],
  },
  build: {
    target: 'esnext',
    rollupOptions: {
      input: {
        draw: path.resolve(import.meta.dirname, 'index.html'),
        webclient: path.resolve(import.meta.dirname, 'webclient/index.html'),
      },
    },
  },
});

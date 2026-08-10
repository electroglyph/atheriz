import { defineConfig } from 'vite';
import path from 'node:path';

export default defineConfig({
  // Both pages are mounted below the AtheriZ static root. Shared absolute
  // assets keep /webclient/ and /atheriz_draw/ compatible with one build.
  base: '/',
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

import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

export default defineConfig({
  esbuild: { jsx: 'automatic' },
  resolve: { alias: { '@': resolve(import.meta.dirname, 'src') } },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] }
});

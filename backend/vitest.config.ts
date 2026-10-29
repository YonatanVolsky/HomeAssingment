import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    exclude: process.env.LIVE ? [] : ['test/live/**'],
    environment: 'node',
    passWithNoTests: true,
  },
});

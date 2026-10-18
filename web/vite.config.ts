import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/admin/invitations': 'http://127.0.0.1:8000',
      '/watchlist': 'http://127.0.0.1:8000',
      '/stocks': 'http://127.0.0.1:8000',
      '/alert-conditions': 'http://127.0.0.1:8000',
      '/notification-connections': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    clearMocks: true,
  },
});

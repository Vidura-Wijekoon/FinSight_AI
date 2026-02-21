import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Proxy API calls to FastAPI during development
      '/auth': 'http://localhost:8000',
      '/documents': 'http://localhost:8000',
      '/query': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})

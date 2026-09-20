import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'https://departmental-wizard-believe-closest.trycloudflare.com',
        changeOrigin: true,
      },
      '/health': {
        target: 'https://departmental-wizard-believe-closest.trycloudflare.com',
        changeOrigin: true,
      },
    },
  },
})
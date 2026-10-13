import { fileURLToPath, URL } from 'node:url'
import { Agent } from 'node:http'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendAgent = new Agent({
  keepAlive: true,
  maxSockets: 32,
  maxFreeSockets: 8,
})

const backendProxy = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  ws: true,
  agent: backendAgent,
}

// https://vite.dev/config/
export default defineConfig({
  build: {
    sourcemap: 'hidden',
  },
  server: {
    strictPort: true,
    proxy: {
      '/api': backendProxy,
      '/files': backendProxy,
      '/exports': backendProxy,
    },
  },
  preview: {
    proxy: {
      '/api': backendProxy,
      '/files': backendProxy,
      '/exports': backendProxy,
    },
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/ws": {
        target: "ws://172.20.10.2:8000",
        ws: true,
      },
      "/camera": {
        target: "http://172.20.10.2:8000",
      },
    },
  }
})



import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期把 /api 代理到本地 FastAPI 后端；生产构建由后端静态托管 dist。
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',   // 显式绑 IPv4：否则 Vite 只监听 ::1，127.0.0.1 访问不到
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8123',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})

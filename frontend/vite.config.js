import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Vite配置文件
 * 前端端口: 13010
 * 后端端口: 18030
 */
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    port: 13010,
    proxy: {
      // 代理API请求到后端
      '/api': {
        target: 'http://localhost:18030',
        changeOrigin: true,
      },
      // 代理上传文件访问
      '/uploads': {
        target: 'http://localhost:18030/uploads',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/uploads/, ''),
      },
    },
  },
})

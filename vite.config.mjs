import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

export default defineConfig({
  plugins: [vue()],
  // Electron 用 file:// 加载打包产物，必须用相对路径
  base: './',
  resolve: {
    alias: {
      '@': path.resolve(process.cwd(), 'src'),
    },
  },
  server: {
    // 固定绑 IPv4：默认的 localhost 在本机会解析到 ::1，
    // 而开发启动器探测的是 127.0.0.1，会一直等不到端口
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
});

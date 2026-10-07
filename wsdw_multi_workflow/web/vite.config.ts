import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const exampleRoot = path.resolve(webRoot, '../..');

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // 包 exports 未开放该 CSS，映射到示例根目录共用的 node_modules
      '@a2ui/react/v0_9/index.css': path.join(
        exampleRoot,
        'node_modules/@a2ui/react/v0_9/index.css',
      ),
    },
  },
  server: {
    port: 5173,
    fs: {
      allow: [exampleRoot],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
});

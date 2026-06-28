import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
const backendPort = process.env.BACKEND_PORT || '3018';
const backendTarget = `http://localhost:${backendPort}`;
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        host: '0.0.0.0', // 允许局域网访问
        port: 3011,
        proxy: {
            // dev 时 /api 转发到 FastAPI
            '/api': {
                target: backendTarget,
                // SSE 端点需要禁用缓冲
                configure: (proxy) => {
                    proxy.on('proxyReq', (_proxyReq, req) => {
                        if (req.url?.includes('/stream')) {
                            _proxyReq.setHeader('Accept', 'text/event-stream');
                            _proxyReq.setHeader('Cache-Control', 'no-cache');
                            _proxyReq.setHeader('Connection', 'keep-alive');
                        }
                    });
                },
            },
            '/health': backendTarget,
        },
    },
    build: {
        outDir: 'dist',
        sourcemap: false,
    },
});

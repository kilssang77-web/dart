import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { '@': path.resolve(__dirname, 'src') },
    },
    build: {
        outDir: '../services/api/static',
        emptyOutDir: true,
    },
    server: {
        port: 8002,
        proxy: {
            '/api': 'http://localhost:8000',
            '/ws': { target: 'ws://localhost:8000', ws: true },
            '/health': 'http://localhost:8000',
            '/metrics': 'http://localhost:8000',
        },
    },
});

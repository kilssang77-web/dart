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
        rollupOptions: {
            output: {
                manualChunks: {
                    'vendor-react': ['react', 'react-dom', 'react-router-dom'],
                    'vendor-query': ['@tanstack/react-query'],
                    'vendor-charts': ['recharts', 'lightweight-charts'],
                    'vendor-ui': ['lucide-react'],
                },
            },
        },
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

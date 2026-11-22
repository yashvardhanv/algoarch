import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Builds the lesson reader as a single IIFE bundle the existing page loads with <script>.
export default defineConfig({
  plugins: [react()],
  publicDir: false,
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: path.resolve(__dirname, '../public/reader'),
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: { entry: path.resolve(__dirname, 'src/main.tsx'), name: 'AlgoArchReaderBundle', formats: ['iife'], fileName: () => 'reader.js' },
    rollupOptions: { output: { assetFileNames: 'reader.[ext]' } }
  }
});

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend do Processador de Documentos (DocWatch — Opção B "Corporate Modern").
// Build estático servido pelo FastAPI em produção (single-origin, sem CORS).
//
// Em DEV o Vite (porta 5173) faz proxy das rotas da API para o backend FastAPI
// (uvicorn em :8000) — assim o cliente usa URLs relativas (/documents, ...) que
// funcionam tanto em dev (proxy) quanto em produção (single-origin).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/documents': 'http://127.0.0.1:8000',
      '/watched-folders': 'http://127.0.0.1:8000',
      '/rescan': 'http://127.0.0.1:8000',
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend do Processador de Documentos (DocWatch — Opção B "Corporate Modern").
// Build estático servido pelo FastAPI em produção (single-origin, sem CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
})

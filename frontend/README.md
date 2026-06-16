# DocWatch — Frontend

Frontend do **Processador de Documentos**, recriado a partir do design **DocWatch — Opção B "Corporate Modern"** (bundle Claude Design). Stack: **React 19 + Vite 8 + TypeScript**.

## Rodar

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check (tsc) + build de produção em dist/
```

Em produção, o `dist/` é servido pelo FastAPI (single-origin, sem CORS).

## Estrutura

```
src/
  index.css            # design system: tokens CSS (tema claro/escuro), fontes, classes dos componentes
  App.tsx              # estado global (tema, página ativa, filtros, toggles) + layout/roteamento
  types.ts             # tipos do modelo de UI
  data/mock.ts         # DADOS MOCK do design (substituir pela API real nas fases GSD)
  components/          # Sidebar, Header, Icon, Switch, StatusPill
  pages/               # DocumentsPage, ConfigPage, TemplatesPage, AutomationsPage
```

## Páginas

- **Documentos** — cards de status, tabela com chips/filtros, busca, seleção, paginação.
- **Configurações** — abas: Pastas monitoradas · Regras de separação · Leitura de dados · Integrações.
- **Templates** — grade de cards com campos extraídos.
- **Automações** — cards no modelo gatilho → condição → ação.

Tema claro/escuro com alternância (persistido em `localStorage`).

## ⚠️ Notas de escopo (design × v1 travado)

O design é um **modelo visual completo**; a fiação com dados reais acontece nas fases GSD respectivas.
Alguns elementos do mock vão **além ou divergem** do escopo v1 já decidido — tratá-los ao ligar cada página:

- **Páginas Templates / Automações / Integrações** → Fases 4, 6+ (mock por enquanto).
- **Múltiplas regras de separação** (QR Code, texto âncora, página em branco) → o v1 da Fase 2 usa **separação por número de páginas, por pasta** (ver `02-CONTEXT.md`). As demais regras são exploração de design (v2+).
- **Motor de OCR (Tesseract/Google/AWS)** → o provedor de extração do v1 é **OpenAI** (ver PROJECT.md). Ajustar o seletor da aba "Leitura" quando a Fase 3 ligar a extração.
- **Coluna "Responsável" / upload** → não fazem parte do v1 da ingestão (ingestão é **folder-only**). Manter como visual até definição.
- **"Forçar varredura", "Filtros", paginação** → ações ainda não ligadas.

## Origem

Design importado de `claude.ai/design`. Referência preservada em `.planning/design/`.

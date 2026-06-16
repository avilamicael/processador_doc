---
phase: 4
slug: templates-sub-templates-e-classificacao
status: draft
shadcn_initialized: false
preset: none
created: 2026-06-16
---

# Phase 4 — UI Design Contract

> Contrato visual e de interação para o frontend da Fase 4 (Templates schema-first + visibilidade da classificação). Gerado pelo gsd-ui-researcher, verificado pelo gsd-ui-checker.
>
> **Sistema de design TRAVADO (DocWatch "Corporate Modern").** Esta fase NÃO introduz um novo sistema de design. Todos os tokens, cores, tipografia, espaçamento e classes de componente já existem em `frontend/src/index.css` e nas páginas reais (`DocumentsPage.tsx`, `ConfigPage.tsx`). A Fase 4 **estende** esse vocabulário; **nunca substitui**. O executor reusa classes existentes (`.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`, `.tpl-*`, `.tag`, `.tags`, `.pill`, `.row-action`, `.select`, `.search-input`, `.tabs`, `.stack`, etc.) antes de criar qualquer nova classe.

---

## Surfaces nesta fase

A Fase 4 entrega/altera estas superfícies de UI. O resto (fila de revisão lado-a-lado, editor de correção de campos, limiar configurável, quarentena resolúvel, sub-templates/automações) é Fase 5/6 e **não** é desenhado aqui.

| # | Surface | Origem | O que muda |
|---|---------|--------|------------|
| S1 | **Lista/grid de templates** (`TemplatesPage`) | Substitui o mock que lê `data/mock.ts` | Passa a ler templates reais via TanStack Query; CTA "Novo template"; estados loading/erro/vazio; ação editar/remover por card |
| S2 | **Construtor de template** (criar/editar) | Novo | Editor schema-first: nome + tipo de documento + lista de campos (nome, tipo, validações, dica) + sinais identificadores. Form inline ou painel, padrão `PastasTab` |
| S3 | **Confirmação de remoção de template** | Novo | Modal destrutivo, padrão idêntico ao `confirmRemove` de `ConfigPage` |
| S4 | **Visibilidade de classificação no documento** | Estende `DocumentsPage` | Mostrar, por documento: template casado, campos preenchidos (bruto + normalizado), marca válido/inválido por campo, e estado `QUARENTENA` para não-casados (somente leitura — sem resolver/corrigir nesta fase) |

> S4 é **somente leitura** nesta fase: mostra o resultado da classificação e o estado de quarentena (TPL-04). A fila de revisão, edição de campos e resolução de quarentena são Fase 5.

### Focal point por superfície (hierarquia visual)

- **S1 (`TemplatesPage`):** quando a lista está **vazia**, o focal point é o empty state centralizado + a CTA **"Novo template"** no `.sec-head`. Quando **populada**, o focal point é o **grid `.tpl-grid`** de `.tpl-card`, com a `.tpl-name` (14px) como âncora de cada card e o `.tpl-icon` (em `--accent-soft`) como gancho visual. A CTA primária permanece o único elemento com cor de accent sólida no topo.
- **S2 (construtor):** o focal point é o **campo "Nome do template"** (primeiro do form) seguido da lista de campos; a CTA de salvar (accent) fecha a hierarquia no rodapé do form.
- **S3 (modal):** o focal point é o título "Remover template" + o nome em mono; o botão destrutivo é o único elemento vermelho sólido.
- **S4 (no documento):** o focal point é o **badge do template casado** no topo da seção "Classificação"; abaixo dele, a tabela campo→valor→normalizado.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — sistema de design próprio TRAVADO em `frontend/src/index.css` (DocWatch "Corporate Modern"). shadcn NÃO usado (CLAUDE.md: stack é React 19 + Vite + CSS com tokens; sem component lib) |
| Preset | not applicable |
| Component library | none — componentes próprios em `frontend/src/components/` (Header, Sidebar, Icon, StatusPill, Switch); classes CSS utilitárias em `index.css` |
| Icon library | `Icon` próprio (`frontend/src/components/Icon.tsx`) — usar nomes já existentes: `plus`, `dots`, `grid`, `tableMini`, `checkSmall`, `check`, `refresh`, `folder`, `docMini`. Não introduzir uma lib de ícones externa |
| Font | UI: `Plus Jakarta Sans` (`--font-ui`); mono: `JetBrains Mono` (`--font-mono`) — usar mono para valores de campo, caminhos e identificadores |

**shadcn gate:** `components.json` não encontrado. Projeto possui sistema de design próprio explícito e maduro; CLAUDE.md e o contexto da fase proíbem introduzir shadcn/Tailwind. Gate resolvido como **Tool: none** (sistema existente). Registry safety gate: não aplicável.

---

## Spacing Scale

Escala 4-point já praticada em `index.css` (gaps de 6/8/10/12/14/16/18/24px). Valores declarados (múltiplos de 4; o sistema existente usa alguns ímpares herdados do bundle — ver Exceções):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Gaps inline, padding de `.tag` (vertical) |
| sm | 8px | Espaçamento compacto, gap entre botões de ação no rodapé do form |
| md | 16px | Espaçamento padrão entre campos do form, padding de card (`.tpl-card` usa 18px) |
| lg | 24px | Padding de seção / `.scroll` (24px 26px 40px) |
| xl | 32px | Gaps de layout maiores |
| 2xl | 48px | Padding de estados vazio/erro (`48px 24px`, padrão de `DocumentsPage`/`ConfigPage`) |
| 3xl | 64px | Espaçamento de nível de página |

Exceções (herdadas do bundle DocWatch, já em produção — manter consistência, não "corrigir"): paddings de 6/10/13/14/18px existentes em `.chip`, `.folder-row`, `.tpl-card`, `--row-py: 13px`. Novas superfícies da Fase 4 devem reusar as classes que já carregam esses valores em vez de inventar novos. Grid de templates: `gap: 14px` (token existente `.tpl-grid`). Gap entre campos do construtor: **14px** (espelha o `gap: 14px` do form de `PastasTab`).

---

## Typography

Tamanhos e pesos TRAVADOS em `index.css`. Esta fase usa exatamente 4 papéis (sem novos tamanhos):

| Role | Size | Weight | Line Height | Token/uso existente |
|------|------|--------|-------------|---------------------|
| Body | 13px | 400 (regular) | 1.5 | texto de tabela/`.sec-desc` (`.docs` td = 13px; descrições 13px) |
| Label | 12px | 600 (semibold) | 1.4 | rótulos de campo do form (`fontSize: 12, fontWeight: 600, color: var(--text-2)`), `.stat-label`, `.tpl-fields-label` (10.5px uppercase para títulos de grupo) |
| Heading | 15px | 600 (semibold) | 1.25 | `.sec-title` / `.tpl-name` (14px) — títulos de seção e de card |
| Display | 16px | 700 (bold) | 1.2 | `.page-title` (cabeçalho da página) |

**Pesos: exatamente 2 — regular `400` e forte (semibold/bold).** Regra prescritiva para os componentes novos da Fase 4 (`.field-row` e similares): usar **600** para rótulos, títulos de seção e headings, e **700** apenas no `.page-title` (Display) e no `.btn-primary`. Não escolher arbitrariamente entre 600 e 700 em elementos novos. (O `index.css` herdado aplica 600 e 700 em produção — isso é o sistema travado, não uma terceira opção introduzida aqui.) Fonte mono (`--font-mono`, JetBrains Mono) reservada a: valores de campo extraído (bruto e normalizado), caminhos de pasta, nomes de arquivo, regex, e os chips `.tag` de campos de template.

---

## Color

Paleta TRAVADA em `:root` / `[data-theme="dark"]` de `index.css`. Tema claro e escuro já suportados — toda cor referenciada por **token CSS var**, nunca hex hardcoded.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `var(--bg)` #F5F7FB (claro) / #0B1017 (escuro) | Fundo da aplicação, área de scroll |
| Secondary (30%) | `var(--surface)` #FFFFFF / #141B25 + `var(--surface-2)`/`--surface-3` | Cards, sidebar, header, toolbars, chips de campo |
| Accent (10%) | `var(--accent)` #2563EB / #3B82F6 | Ver lista reservada abaixo |
| Destructive | `var(--st-erro)` #DC2626 / #F87171 (+ `--st-erro-bg`) | Apenas ação de remover template e mensagens de erro/inválido |

**Accent reservado para:** botão primário "Novo template" / "Salvar"; estado `:focus` de inputs (`box-shadow: 0 0 0 3px var(--accent-ring)`); estado ativo de aba/chip; ícone de template (`.tpl-icon` em `--accent-soft`); indicador de campo obrigatório; link/hover de `.row-action`. **Não** usar accent como cor de fundo geral nem em todo elemento interativo.

**Cores semânticas de status de campo/classificação** (reusar tokens `--st-*` existentes — não criar novos):

| Marca | Token | Aparência |
|-------|-------|-----------|
| Campo válido | `--st-tratado` / `--st-tratado-bg` (verde) | pílula/badge verde "válido" |
| Campo inválido | `--st-erro` / `--st-erro-bg` (vermelho) | pílula/badge vermelha "inválido" + dica do motivo |
| Documento classificado (template casou) | `--st-tratado` ou `--accent` | badge com o nome do template, via `.badge`/`.pill` |
| Documento em quarentena | `--st-leitura` / `--st-leitura-bg` (âmbar) | `StatusPill` já mapeia `quarentena → token 'leitura'` (NÃO alterar esse mapeamento) |

> Regra: campo `obrigatório inválido/faltante` é **marcado** (vermelho), o documento **segue** sem automação (D-10). A UI não bloqueia nem "resolve" aqui — só mostra a marca. Verde "Concluído"/`--st-tratado` para o **estado do documento** continua reservado à automação (Fase 6); nesta fase um documento classificado fica `processando` + `last_completed_step="classificado"` e exibe o badge do template, não o pill verde de "Concluído".

---

## Copywriting Contract

Todo texto em **pt-BR**. Termos técnicos (CNPJ, CPF, regex, ISO) mantidos.

| Element | Copy |
|---------|------|
| CTA primária (S1) | **"Novo template"** (com ícone `plus`) — mantém o label já no mock |
| CTA salvar (S2, criar) | **"Salvar template"** / salvando: **"Salvando…"** |
| CTA salvar (S2, editar) | **"Salvar alterações"** / salvando: **"Salvando…"** |
| CTA descartar (S2, criar) | **"Descartar template"** (`.btn-ghost`) — fecha o form sem salvar |
| CTA descartar (S2, editar) | **"Descartar alterações"** (`.btn-ghost`) — fecha o form sem salvar |
| CTA adicionar campo (S2) | **"Adicionar campo"** (com ícone `plus`, `.btn-ghost`) |
| CTA remover campo (S2) | botão-ícone `.row-action` com `aria-label="Remover campo {nome}"` |
| Empty state heading (S1) | **"Nenhum template ainda"** |
| Empty state body (S1) | **"Crie um template declarando os campos a extrair de um tipo de documento. O sistema usa os templates para classificar e preencher cada documento automaticamente."** |
| Error state (S1) | Heading: **"Não foi possível carregar os templates."** Body: **"Verifique se o serviço está em execução e tente novamente."** + botão **"Tentar novamente"** (padrão `DocumentsPage`) |
| Erro de formulário (S2) | Campo vazio: **"Informe o nome do template."** / **"Informe o nome do campo."** / Sem campos: **"Adicione ao menos um campo ao template."** / Falha ao salvar: **"Não foi possível salvar o template. Confira os dados e tente novamente."** |
| Confirmação destrutiva (S3) | Título: **"Remover template"**. Corpo: **"Remover o template «{nome}»? Os documentos já classificados por ele permanecem; novos documentos deixarão de casar com este template."** Botões: **"Manter template"** (`.btn-ghost`) / **"Remover"** (primário com `background: var(--st-erro)`) / removendo: **"Removendo…"** |
| Quarentena (S4) | Pílula **"Quarentena"** (já existente). Texto auxiliar: **"Nenhum template casou com este documento. Ele fica em quarentena e nunca é descartado."** (resolução é Fase 5) |
| Resultado de classificação (S4) | Cabeçalho da seção: **"Classificação"**. Rótulos: **"Template"**, **"Campos extraídos"**, com colunas **"Campo"**, **"Valor"** (bruto) e **"Normalizado"**, e marca **"válido"** / **"inválido"** por campo |

> Nota sobre CTAs de cancelar: nesta fase **não** se usa o label genérico "Cancelar". O botão de fechar o form é contextual — **"Descartar template"** (criação) / **"Descartar alterações"** (edição) — e a saída do modal destrutivo é **"Manter template"**. Isso evita single-word genérico e deixa explícito o efeito da ação.

### Microcopy do construtor (S2 — campos e dicas)

| Item | Copy |
|------|------|
| Rótulo nome do template | **"Nome do template"** — placeholder: *ex.: Nota Fiscal Eletrônica* |
| Rótulo tipo de documento | **"Tipo de documento"** — placeholder: *ex.: Fiscal, RH, Financeiro* |
| Rótulo sinais identificadores | **"Sinais identificadores"** — hint: **"Dados cuja presença identifica este tipo (ex.: linha digitável, CNPJ, valor total). Usados para classificar antes de recorrer à IA."** |
| Bloco de campo: nome | **"Nome do campo"** — placeholder: *ex.: CNPJ emitente* |
| Bloco de campo: tipo | **"Tipo"** — `select` com: **Texto** (padrão), **Número**, **Data**, **Moeda**, **CPF/CNPJ**, **Booleano** |
| Bloco de campo: obrigatório | **"Obrigatório"** — `Switch` (componente existente) |
| Bloco de campo: regex | **"Validação por padrão (regex)"** — opcional; hint: **"Opcional. Valida o valor extraído contra uma expressão regular."** |
| Bloco de campo: dica | **"Dica para a leitura"** — hint: **"Texto que orienta a IA a encontrar este campo no documento (ex.: número após o rótulo «Nº NF»)."** |
| Tipo CPF/CNPJ | hint inline: **"Valida o dígito verificador (Módulo 11) e normaliza para apenas dígitos."** |
| Tipo Data | hint inline: **"Normaliza para o formato ISO AAAA-MM-DD."** |
| Tipo Moeda | hint inline: **"Normaliza para valor decimal."** |

---

## Component Inventory (reuso vs novo)

**Reusar sem alteração:** `.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`/`.sec-head-col`/`.sec-title`/`.sec-desc`, `.tpl-grid`, `.tpl-card`, `.tpl-head`, `.tpl-icon`, `.tpl-name`, `.tpl-type`, `.tpl-fields-label`, `.tags`/`.tag`, `.tpl-foot`, `.row-action`, `.search-input`, `.select`, `.tabs`/`.tab`, `.stack`, `.list-head`, `.badge`/`.badge-ok`/`.badge-off`, `.pill`/`.pill-dot`, `Switch`, `Icon`, `StatusPill`. Estados loading/erro/vazio e o modal de confirmação: copiar os padrões já implementados em `DocumentsPage.tsx` e `ConfigPage.tsx`.

**Novas classes permitidas (apenas se necessário; prefixo coerente, mesma estética):** linha de campo do construtor (ex.: `.field-row` — espelhar `.read-row`/`.folder-row`), coluna de valor normalizado em S4 (reusar `.cell-mono`/`table.docs`). Qualquer cor via `var(--…)`; qualquer raio via `var(--radius)`/`var(--radius-sm)`; pesos só 600 ou 700 conforme a seção Typography.

**Hooks/dados:** novos hooks TanStack Query (`useTemplates`, `useCreateTemplate`, `useUpdateTemplate`, `useDeleteTemplate`) seguindo exatamente o padrão de `useWatchedFolders.ts` (queryKey, invalidate em onSuccess, fonte de verdade = API). Cliente fetch tipado em `lib/api.ts`; tipos em `types.ts` (substituir o `Template` mock atual pela forma real da API). Estados de tela: `isInitialLoading` (skeleton), `isError` (retry), `isEmpty` (empty state), `isRefetching` (indicador "Atualizando…").

---

## Interaction States (obrigatórios por superfície)

| Surface | Loading | Erro | Vazio | Sucesso |
|---------|---------|------|-------|---------|
| S1 lista de templates | skeleton em cards (`var(--surface-3)` opacity .7) | bloco centralizado + "Tentar novamente" | empty state centralizado (copy acima) | grid de `.tpl-card` |
| S2 construtor | botão salvar mostra "Salvando…" e `disabled` | mensagem inline em `var(--st-erro)` acima dos botões | n/a | fecha o form e invalida a lista |
| S3 remoção | botão "Removendo…" `disabled` | mantém modal aberto, mensagem inline | n/a | fecha modal, invalida lista |
| S4 classificação no doc | herda loading da query de documentos | herda erro da query | "Aguardando classificação" quando ainda não classificado | tabela campo→valor→normalizado + badge do template |

Acessibilidade: inputs com `<label>` associado; botões-ícone com `aria-label` (padrão já usado: `aria-label="Remover {path}"`); `:focus` visível via `--accent-ring` (já no CSS). Foco de teclado preservado nos modais.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none (sem shadcn / sem registry de terceiros) | nenhum | not applicable |

Nenhum registro de componente externo. Toda UI é construída com as classes/componentes próprios já no repositório.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-06-16 (3 flags do checker resolvidos: CTA contextual no lugar de "Cancelar"; pesos fixados em 600/700; focal point declarado por superfície)

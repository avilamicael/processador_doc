---
phase: 6
slug: automacoes-de-arquivo-renomear-mover
status: draft
shadcn_initialized: false
preset: none
created: 2026-06-17
revised: 2026-06-17
revision: pipeline-redesign
supersedes: rule-single-editor model (D-04/D-05 acoplado)
---

# Phase 6 — UI Design Contract (REDESIGN: Construtor de PIPELINE)

> Contrato visual e de interação para o frontend da Fase 6 (Automações de Arquivo: Renomear/Mover) **sob o modelo de PIPELINE** (D-12..D-16). Gerado pelo gsd-ui-researcher; verificado pelo gsd-ui-checker.
>
> **⚠️ REDESIGN — o que mudou neste contrato.** A versão anterior modelava a UI como um **editor de regra única** (condição → nome+pasta numa só regra, "primeira que casa vence"). Este contrato a **SUBSTITUI** por um **CONSTRUTOR DE PIPELINE**: uma lista ORDENADA de **etapas (steps)** componíveis, onde o documento percorre **TODAS** as etapas cujo filtro casa, na ordem definida pelo usuário (encadeado). Cada etapa = **1 filtro de entrada + 1 ação atômica** (Mover / Renomear / Identificar tipo / Rotear). O **design system permanece TRAVADO e idêntico** — só as superfícies são redesenhadas para o modelo de pipeline. Decisões de origem: CONTEXT D-12..D-16 (modelo) + D-01/02/03, D-06..D-11 (mantidas); RESEARCH (executor puro, materialização única, Pitfalls P8/P9/P10).
>
> **Sistema de design TRAVADO (DocWatch "Corporate Modern").** Esta fase NÃO introduz novo sistema de design. Honra integralmente os tokens/classes já em `frontend/src/index.css` e os UI-SPECs das Fases 2/4/5. **Reusar, não reinventar.** O executor reusa classes existentes (`.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`/`.sec-head-col`/`.sec-title`/`.sec-desc`, `.pill`/`.pill-dot`, `.badge`/`.badge-ok`/`.badge-off`, `.row-action`/`.row-actions`, `.select`, `.search-input`, `.chips`/`.chip`/`.chip.active`/`.chip-count`, `.tabs`/`.tab`, `.cell-mono`, `.file-name`, `table.docs`, `.stack`, `.rule-card`/`.rule-name`/`.rule-param`/`.rule-desc`, `.auto-card`/`.auto-head`/`.auto-icon`/`.auto-name`/`.auto-runs`/`.auto-flow`/`.flow-pill`/`.flow-pill.action`/`.flow-tag`, `.checkbox`, `.table-toolbar`/`.table-foot`/`.foot-text`, `.stat-grid`/`.stat-card`/`.stat-num`/`.stat-label`/`.stat-dot`, `.spacer`, `Switch`, `Icon`, `StatusPill`, `ConfidenceBadge`) ANTES de criar qualquer classe nova.
>
> **Restrição de visão herdada (PROJECT.md + 05-CONTEXT D-06): NÃO há visualizador/manuseio de documento na web.** A web é gestão/triagem: configura o pipeline e mostra **caminhos origem→destino como TEXTO PURO**. Sem imagem de página, sem embed de PDF, sem preview do conteúdo do arquivo. O arquivo físico é conferido/aberto no Windows Explorer. Restrição absoluta.
>
> **Regra de segurança como contrato de UI (CLAUDE.md "nunca pode causar perda"):** toda ação que toca o filesystem (Aplicar, Aplicar lote, Desfazer) é precedida por feedback explícito de dry-run e por estado reversível visível. A UI NUNCA sugere irreversibilidade; "Desfazer" é sempre apresentado como disponível após aplicar.
>
> **Valores como texto puro:** zero `dangerouslySetInnerHTML`. Nomes de arquivo, caminhos, padrões `{campo}` e valores de filtro são renderizados como texto (mono onde indicado). Convenção `code-and-config`: **NENHUMA dependência npm nova** (sem lib de drag-and-drop, sem lib de ícones — reordenação por botões ↑/↓; ícones via `Icon.tsx`).

---

## Modelo mental que a UI deve tornar óbvio

O contrato existe para resolver UM problema central detectado: **o usuário técnico NÃO entendeu os tokens e o usuário final também não vai.** A UI precisa reduzir a abstração ao máximo. Dois conceitos têm de ficar visualmente inescapáveis:

1. **PIPELINE = sequência ordenada.** Não é uma lista de regras independentes — é um **encadeamento**. O documento desce pela lista, etapa após etapa, e cada etapa cujo filtro casa transforma o destino-alvo. A ORDEM e o fluxo descendente devem ser visualmente literais (numeração 1,2,3…, conectores verticais entre cards, setas para baixo).
2. **TOKEN `{campo}` = "será trocado pelo valor extraído".** Nunca apresentar um `{campo}` sem, ao lado, **mostrar no que ele vira** (pré-visualização ao vivo com dados de exemplo). O token é um espaço reservado, não um texto literal.

---

## Surfaces nesta fase (REDESENHADAS p/ pipeline)

A `AutomationsPage.tsx` atual (editor de regra única, fiada à API antiga `automation_rules`) e a `DryRunPage.tsx` são **reescritas** para o modelo de pipeline. As classes CSS de regra (`.rule-card`, `.auto-flow`, `.flow-pill`) são reusadas/estendidas para os cards de etapa.

| # | Surface | Origem / molde | O que entrega (modelo PIPELINE) |
|---|---------|----------------|----------------------------------|
| **S1** | **Construtor de pipeline — lista ORDENADA de etapas** | Reescreve `AutomationsPage.tsx`; molde `.stack` + `.rule-card` + reorder ↑/↓ já provado no mock antigo | Lista vertical de **cards de etapa** numerados (1,2,3…), na ordem de execução (D-12). Cada card mostra: nº de ordem, ação (ícone+rótulo), resumo do filtro de entrada, resumo dos params, `Switch` ativar/pausar a etapa, ações ↑/↓/editar/remover. **Conector visual descendente** entre cards (a essência do encadeamento). CTA "Adicionar etapa". Empty state. Loading/erro. Polling/refetch via TanStack Query |
| **S2** | **Editor de etapa (criar/editar)** | Novo; molde do construtor inline schema-first de `TemplatesPage` (form em `.card`) | Form inline em 3 blocos: (a) **Tipo de ação** (4 opções: Mover / Renomear / Identificar tipo / Rotear — seletor de cartões ou `.select`); (b) **Filtro de entrada** (0..N condições combináveis E/OU, multi-tipo: campo / pasta de origem / extensão / nome de arquivo / tamanho / tipo classificado — D-14); (c) **Parâmetros da ação** (depende do tipo). CTAs contextuais (sem "Cancelar" supérfluo) |
| **S3** | **Editor de padrão com tokens `{campo}`** (sub-bloco de S2, ações Renomear/Mover) | Novo — superfície CRÍTICA de UX | Campo do padrão (mono) + **chips de tokens clicáveis** (campos do template + datas) que inserem `{campo}` no cursor + **PRÉ-VISUALIZAÇÃO AO VIVO** logo abaixo mostrando o resultado resolvido com dados de exemplo e a sanitização aplicada + **microcopy inline** explicando "`{campo}` é trocado pelo valor extraído do documento". Autoexplicativo: o usuário entende sem ler manual |
| **S4** | **Dry-run / Preview do pipeline (origem→destino)** | Reescreve `DryRunPage.tsx`; molde `table.docs` + `.stat-grid` | UM par **origem → destino-final** por documento (a materialização é única ao final do pipeline — RESEARCH P8). Texto mono. Coluna de **situação sinalizada** por token de cor (âmbar=sufixo D-09 / azul=duplicata pulada D-10 / vermelho=campo faltando→revisão D-07 / verde=pronto). Contagem-resumo no topo. CTA "Aplicar" **desabilitada até o preview carregar** (AUT-03). Seleção por-doc e por-lote (D-03) |
| **S5** | **Ação por-documento (Aplicar / Desfazer)** | Estende `DocumentsPage`/`AttentionPage` + footer do S4 | Auto-aplicados de alta confiança (D-01) → estado "Concluído"; linha ganha "Desfazer aplicação" (`.row-action`). Documentos rebaixados por campo faltante (D-07) aparecem em "Precisam de atenção" com o motivo. Aplicar/Desfazer por-doc e por-lote |
| **S6** | **Confirmação de Desfazer (undo)** | Novo; molde do diálogo `confirmRemove` existente (overlay + `.card` 22px) | Diálogo que descreve o que será revertido (destino→origem, ou restauração do CAS se o destino sumiu) em **linguagem de reversibilidade**. Comunica o resultado: desfeito / restaurado-do-CAS / falha controlada. NUNCA linguagem de exclusão permanente |

> **S1 e S3 são os focos da fase.** S1 porque a ESSÊNCIA do redesign é tornar o pipeline ordenado/encadeado óbvio; S3 porque é onde a abstração do token precisa ser dissolvida. **S4 é o core surface de confiança** (a rede visível antes de tocar o disco, AUT-03).

### Focal point por superfície (hierarquia visual)

- **S1 (pipeline):** **vazio** → empty state centralizado convidando a montar o primeiro pipeline. **Populado** → o **encadeamento descendente numerado** (a coluna esquerda de números + conectores verticais é o elemento mais forte; é o que comunica "ordem importa"); a CTA "Adicionar etapa" no rodapé da lista. Accent só na CTA primária e na pílula da ação.
- **S2 (editor de etapa):** focal point = o **Tipo de ação** escolhido no topo (decide tudo abaixo); o filtro e os params são segundo nível. O combinador E/OU dos filtros é explícito.
- **S3 (padrão+tokens):** focal point = a **PRÉ-VISUALIZAÇÃO RESOLVIDA** (o que o nome/caminho VAI virar). Os chips de token e o campo de padrão são auxiliares que alimentam a prévia.
- **S4 (dry-run):** focal point = a **coluna destino** + a **sinalização de situação**; a contagem-resumo no topo (N movidos, N pulados, N bloqueados). A CTA "Aplicar" é o único elemento accent e fica desabilitada até o preview carregar.
- **S5 (linha):** focal point = a pílula "Concluído" (verde) pós-aplicação; "Desfazer" é `.row-action` discreta (não destrutiva visualmente).
- **S6 (undo):** focal point = a descrição do que será revertido + a CTA de confirmação. Resultado em texto claro.

---

## Vocabulário de UI do pipeline (rótulos pt-BR travados)

Para consistência entre S1/S2/S4 e com o backend (`action_type`/`filter_type`):

| Conceito (backend) | Rótulo pt-BR na UI | Ícone (`Icon.tsx`) |
|--------------------|---------------------|---------------------|
| pipeline | **Pipeline de automação** / "etapas" | `bolt` |
| step (genérico) | **Etapa** | — |
| `action_type=move` | **Mover** (para a pasta…) | `folder` |
| `action_type=rename` | **Renomear** (para o padrão…) | `docMini` |
| `action_type=identify_type` | **Identificar tipo** (gate) | `grid` |
| `action_type=route` | **Decidir tratativa** (rotear) | `arrowRight` |
| `filter_type=field` | **Campo extraído** | — |
| `filter_type=source_folder` | **Pasta de origem** | `folder` |
| `filter_type=extension` | **Tipo de arquivo (extensão)** | — |
| `filter_type=filename` | **Nome do arquivo** | — |
| `filter_type=size` | **Tamanho do arquivo** | — |
| `filter_type=template` | **Tipo classificado** | — |
| `conjunction=and` / `or` | **E (todas)** / **OU (qualquer)** | — |
| operadores `eq/gt/lt/contains` | **= / > / < / contém** | — |
| `route target` em_revisao / nao_tratar / ignorar | **Enviar para revisão** / **Não tratar** / **Ignorar** | — |

> Step sem nenhum filtro = "**Aplica-se a todos os documentos**" (badge neutra `.badge-off`). Isso deve ser dito explicitamente no card (S1) e no editor (S2), porque é um comportamento não-óbvio (RESEARCH P10).

---

## Design System

| Property | Value |
|----------|-------|
| Tool | **none** — sistema de design próprio TRAVADO em `frontend/src/index.css` (DocWatch "Corporate Modern"). shadcn NÃO usado (CLAUDE.md: React 19 + Vite + CSS com tokens; sem component lib). `components.json` ausente em `frontend/` (verificado) |
| Preset | not applicable |
| Component library | none — componentes próprios em `frontend/src/components/` (Header, Sidebar, Icon, StatusPill, Switch, ConfidenceBadge); classes CSS utilitárias em `index.css`. Reusar `.rule-card`/`.auto-card`/`.flow-pill` para os cards de etapa |
| Icon library | `Icon` próprio (`frontend/src/components/Icon.tsx`). **Já existem todos os ícones necessários** (auditado): `bolt` (automação/pipeline), `folder` (Mover/pasta-origem), `docMini`/`doc` (Renomear/arquivo), `grid` (Identificar tipo), `arrowRight` (Rotear/fluxo), `plus` (adicionar etapa), `arrowUp`/`arrowDown` (reordenar etapa), `dots` (editar), `refresh` (atualizar prévia), `check`/`checkSmall` (selecionado/pronto), `undo` (desfazer), `alert` (bloqueio/colisão). **NÃO importar lib de ícones nova.** Se faltar algum, adicionar a `Icon.tsx` no MESMO estilo de stroke (viewBox 24, `sw` 1.7–2) |
| Font | UI: `Plus Jakarta Sans` (`--font-ui`); mono: `JetBrains Mono` (`--font-mono`). **Mono OBRIGATÓRIO** para: caminhos origem/destino, padrões `{campo}`, chips de token, nome de arquivo, extensão, hash, e o valor de filtros numéricos (tamanho/valor) |

**shadcn gate:** `components.json` não encontrado. Projeto tem sistema de design próprio explícito e maduro; CLAUDE.md e os UI-SPECs anteriores proíbem introduzir shadcn/Tailwind. Gate resolvido como **Tool: none**. Registry safety gate: **não aplicável** (sem registries). Convenção: **code-and-config — sem dependência npm nova** (consistente com 05-04 e RESEARCH "zero dependência nova").

---

## Spacing Scale

Escala 4-point já praticada em `index.css`. Reusa os tokens dos UI-SPECs anteriores; nenhum valor novo nesta fase.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Gaps inline, gap entre ações de linha (`.row-actions`), gap entre chips de token |
| sm | 8px | Espaçamento compacto, gap entre `select`s de filtro, gap do `.auto-flow`/conector de etapa |
| md | 16px | Espaçamento padrão entre cards de etapa (`.stack` gap 12px), entre filtro e params |
| lg | 24px | Padding de seção / `.scroll` (24px 26px) |
| xl | 32px | Gaps de layout maiores |
| 2xl | 48px | Padding de estados vazio/erro (`48px 24px`, padrão `DocumentsPage`/`AttentionPage`) |
| 3xl | 64px | Espaçamento de nível de página |

**Exceções herdadas (do bundle DocWatch, já em produção — manter, NÃO "corrigir"):** `--row-py: 13px` (linhas de `table.docs`, reusado na tabela de dry-run S4); padding de card `16px 18px` (`.rule-card`/`.auto-card`, reusados para cards de etapa); padding de diálogo `22px` (`confirmRemove`, reusado em S6); card de filtro/condição `14px` (padrão do construtor da Fase 4, reusado nas linhas de filtro de S2). **Regra para classes NOVAS desta fase** (ex.: `.step-card`, `.step-connector`, `.step-index`, `.pattern-preview`, `.token-chip`, `.dryrun-row`): NÃO introduzir valores de espaçamento fora dos múltiplos de 4 acima; reusar exclusivamente os tokens ou as classes/cards existentes que já carregam as exceções herdadas (13/14/16-18/22px). As exceções herdadas são travadas, **não licença para criar novos valores ímpares.** O executor deve checar esta regra ao criar qualquer classe nova.

---

## Typography

Tamanhos e pesos TRAVADOS em `index.css`. Esta fase usa exatamente os 4 papéis dos UI-SPECs anteriores; sem novos tamanhos.

| Role | Size | Weight | Line Height | Token/uso existente |
|------|------|--------|-------------|---------------------|
| Body | 13px | 400 (regular) | 1.5 | descrição de etapa/filtro (`.rule-desc`/`.sec-desc`), células da tabela de dry-run, microcopy de S3, hint inline |
| Label | 12px | 600 (semibold) | 1.4 | rótulos de campo do editor de etapa, cabeçalho de coluna, "Tokens disponíveis:" |
| Heading | 15px | 600/700 | 1.25 | `.sec-title` — título "Automações"/"Pré-visualização", título do editor de etapa |
| Display | 16px | 700 (bold) | 1.2 | `.page-title` (cabeçalho da página) |

> **Tamanhos herdados de classes reusadas — referência documental, NÃO novos tamanhos:** `.flow-tag` 10px uppercase (rótulo do tipo de ação na pílula), `table.docs th` 11px uppercase (cabeçalho de coluna), `.rule-name` 14px/600 (nome/ação da etapa), `.stat-num` 27px mono (contagens do topo do dry-run), `.chip-count` 11px mono (nº de ordem da etapa). Esses vêm do bundle DocWatch já em produção e são reusados tal-qual. **Elementos NOVOS desta fase usam exclusivamente os 4 papéis acima.** O contrato tipográfico é de **4 tamanhos**.

**Pesos: exatamente 2 — regular `400` e forte (semibold `600` / bold `700`).** 600 e 700 são subvariantes do mesmo "peso forte". Use **700** apenas em `.page-title` (Display), `.btn-primary` e `.stat-num`; use **600** em todo o resto que precise de peso forte (rótulos, `.rule-name`, títulos de seção, badges, `.flow-tag`, nº de ordem da etapa). Não escolher arbitrariamente entre 600/700 em elementos novos. Fonte mono reservada aos itens listados em §Design System.

---

## Color

Paleta TRAVADA em `:root` / `[data-theme="dark"]` de `index.css`. Tema claro e escuro suportados — toda cor por **token CSS var**, nunca hex hardcoded.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `var(--bg)` #F5F7FB / #0B1017 | Fundo da aplicação, área de scroll |
| Secondary (30%) | `var(--surface)` #FFFFFF / #141B25 + `--surface-2`/`--surface-3` | Cards de etapa, cards de filtro, header, toolbar do dry-run, `.flow-pill` (surface-3), conector de etapa (linha em `--border`/`--border-strong`) |
| Accent (10%) | `var(--accent)` #2563EB / #3B82F6 | Ver lista reservada abaixo |
| Destructive (sinalização) | `var(--st-erro)` #DC2626 / #F87171 (+ `--st-erro-bg`) | Apenas sinalização: bloqueio→revisão por campo faltante (D-07), erro de operação, motivo de FALHA. **Nenhuma ação desta fase é destrutiva** (Aplicar e Desfazer são reversíveis por desenho) |

**Accent reservado para:** botão primário **"Aplicar automações"** / **"Aplicar selecionados"** (S4); **"Adicionar etapa"** e **"Salvar etapa"** (S1/S2); estado `:focus` dos inputs (`box-shadow: 0 0 0 3px var(--accent-ring)`); estado ativo de aba/chip (`.chip.active`/`.tab` ativo em `--accent-soft`); **a pílula da AÇÃO da etapa** no card (`.flow-pill.action`, em `--accent-soft`/`--accent` — é o que distingue a ação dos filtros, em segundo plano); o **número de ordem ativo** da etapa pode usar `--accent-soft` se ajudar a reforçar a sequência (opcional). `--accent-soft` é variante tonal, não um segundo accent. **NÃO** usar accent como fundo geral, nem em todo elemento interativo, nem na ação "Desfazer" nem nos botões ↑/↓ de reordenação (que são `.row-action`/`.btn-ghost` neutros).

### Cores semânticas de situação no dry-run (reusar tokens `--st-*` — NÃO criar novos)

| Marca | Token | Aparência |
|-------|-------|-----------|
| Documento **aplicado/concluído** | `--st-tratado`/`--st-tratado-bg` (verde) | `StatusPill state="concluido"` ("Concluído") após o pipeline aplicar com sucesso — momento reservado ao verde. No dry-run: `.badge` verde "Pronto" |
| **Colisão resolvida por sufixo** (D-09, `_1`/`_2`) | `--st-leitura`/`--st-leitura-bg` (âmbar) | `.badge` âmbar "Renomeado p/ evitar colisão" — informativo, não erro |
| **Duplicata idêntica pulada** (D-10) | `--st-encontrado`/`--st-encontrado-bg` (azul muted) | `.badge` azul "Já existe (idêntico) — pulado" — neutro/informativo |
| **Bloqueado → revisão** por campo faltante (D-07) | `--st-erro`/`--st-erro-bg` (vermelho) | `.badge` vermelha "Campo faltando — enviado para revisão"; o doc aparece em "Precisam de atenção" (EM_REVISAO) |
| **Roteado** (pipeline desviou: revisão/não-tratar/ignorar — P9) | `--st-leitura`/`--st-leitura-bg` (âmbar) ou `--st-quarentena` p/ "não tratar/ignorar" | `.badge` "Enviado para revisão" / "Marcado para não tratar" / "Ignorado pelo pipeline" — informativo; o doc NÃO é materializado |
| **Nenhuma etapa casou** (P10) | `--surface-3`/`--text-3` (neutro) | `.badge-off` "Nenhuma etapa se aplica — mantido na origem" — neutro, não erro (comportamento explícito, não materializa silenciosamente) |
| **Falha de operação** (lock de arquivo, hash divergente) | `--st-erro`/`--st-erro-bg` (vermelho) | `StatusPill state="falha"` ("Falha") + ação "Tentar de novo" (reusa S2 da Fase 5) |
| **Etapa ativa / pausada** | `--st-tratado-bg`/`--surface-3` | `.badge badge-ok` "Ativa" / `.badge badge-off` "Pausada" no card de etapa (reusa o padrão do mock) |

> Regra: "duplicata pulada", "renomeado por colisão", "roteado" e "nenhuma etapa casou" são **informativos** (azul/âmbar/neutro), nunca vermelho — representam o sistema protegendo/decidindo, não falha. Vermelho fica restrito a bloqueio-por-campo-faltante e falha real de operação. O `ConfidenceBadge` (Fase 5) é reusado tal-qual — não redefinido.

---

## Copywriting Contract

Idioma: **pt-BR**. Tom: direto, sem jargão, enfatizando segurança/reversibilidade e dissolvendo a abstração de pipeline/token. Toda cópia abaixo é prescritiva.

| Element | Copy |
|---------|------|
| Page/aba título (S1) | **"Automações"** / desc: **"Monte um pipeline de etapas que renomeiam, movem e organizam os arquivos automaticamente. Cada documento passa pelas etapas, de cima para baixo, na ordem que você definir."** |
| Primary CTA (S1) | **"Adicionar etapa"** (lista vazia: **"Criar primeira etapa"**) |
| Primary CTA (S2 editor) | **"Salvar etapa"** (editar: **"Salvar alterações"**) |
| CTA secundária (S2) | **"Descartar etapa"** (criar) / **"Descartar alterações"** (editar) — fechar já cancela; sem "Cancelar" extra |
| Primary CTA (S4 dry-run) | **"Aplicar automações"** (lote) / **"Aplicar selecionados"** (seleção parcial) — só após o preview |
| CTA por-doc (S5) | **"Desfazer aplicação"** (rótulo curto "Desfazer" só na `.row-action`, com `title` que repete o objeto) / **"Pré-visualizar automação"** (abrir dry-run de 1 doc) |
| Empty state heading (S1) | **"Nenhuma etapa de automação ainda"** |
| Empty state body (S1) | **"Crie etapas para renomear, mover e organizar arquivos automaticamente a partir dos campos extraídos. O documento percorre as etapas na ordem — ex.: 1) Identificar tipo → 2) Renomear → 3) Mover para a pasta certa."** + CTA "Criar primeira etapa" |
| Empty state (S4 dry-run vazio) | **"Nenhum documento pronto para automação. Documentos de alta confiança são aplicados automaticamente; os demais aguardam revisão."** |
| Selecionar tipo de ação (S2) — Mover | **"Mover"** · hint: **"Move o arquivo para uma pasta de destino que você define com tokens dos campos."** |
| Selecionar tipo de ação (S2) — Renomear | **"Renomear"** · hint: **"Renomeia o arquivo seguindo um padrão de nome com tokens dos campos."** |
| Selecionar tipo de ação (S2) — Identificar tipo | **"Identificar tipo"** · hint: **"Classifica o documento contra um template. As etapas seguintes podem filtrar por esse tipo."** |
| Selecionar tipo de ação (S2) — Rotear | **"Decidir tratativa"** · hint: **"Envia o documento para revisão, marca para não tratar ou ignora — e interrompe o pipeline."** |
| Filtro vazio (S1 card e S2) | **"Aplica-se a todos os documentos"** |
| Combinador de filtros (S2) | **"E (todas as condições)"** / **"OU (qualquer condição)"** |
| Hint do filtro de tamanho (S2) | **"Tamanho em KB. Use > ou < para faixas (ex.: > 500 KB)."** |
| Microcopy de token (S3) | **"Tokens disponíveis — clique para inserir. Cada `{campo}` é trocado pelo valor extraído do documento."** |
| Hint da pré-visualização (S3) | **"Pré-visualização com dados de exemplo. Caracteres inválidos no Windows são removidos automaticamente."** |
| Pré-visualização — campo faltante (S3) | **"«{campo}?» — esse campo pode estar vazio em alguns documentos. Quando faltar, o documento vai para revisão antes de aplicar."** |
| Error state (geral) | **"Não foi possível carregar. Verifique se o servidor está rodando e tente de novo."** (reusa o padrão de `DocumentsPage`/`AttentionPage`) |
| Error state (salvar etapa) | **"Não foi possível salvar a etapa. Confira os dados e tente novamente."** |
| Error state (operação falhou) | **"A automação não pôde concluir (o arquivo pode estar aberto em outro programa). O documento foi mantido seguro — tente de novo."** |
| Situação dry-run — bloqueio (D-07) | **"Campo faltando — enviado para revisão"** (title: **"Um campo usado no nome/pasta está faltando ou inválido. Enviado para revisão antes de aplicar."**) |
| Situação dry-run — sufixo (D-09) | **"Renomeado p/ evitar colisão"** (title: **"Já existe um arquivo diferente com esse nome — será salvo com sufixo (ex.: nome_1)."**) |
| Situação dry-run — duplicata (D-10) | **"Já existe (idêntico) — pulado"** (title: **"Esse arquivo já existe no destino com conteúdo idêntico — será pulado."**) |
| Situação dry-run — roteado (P9) | **"Enviado para revisão"** / **"Marcado para não tratar"** / **"Ignorado pelo pipeline"** |
| Situação dry-run — sem etapa (P10) | **"Nenhuma etapa se aplica — mantido na origem"** |
| Situação dry-run — pronto | **"Pronto"** |
| Resultado do undo (sucesso) | **"Desfeito. O arquivo voltou ao local de origem."** |
| Resultado do undo (via CAS) | **"O arquivo de destino não foi encontrado no lugar esperado. Restauramos a cópia íntegra preservada pelo sistema para a pasta de origem."** |
| Remover etapa (confirmação) | **"Remover etapa"** · corpo: **"Remover a etapa «{ação}»? As etapas seguintes continuam valendo. Documentos já aplicados não são afetados."** · CTAs: **"Manter etapa"** / **"Remover"** |
| Destructive confirmation | **Nenhuma ação desta fase é destrutiva.** "Aplicar automações" sempre oferece "Desfazer aplicação" depois; "Desfazer aplicação" restaura (do destino ou do CAS) e nunca apaga sem rede. O diálogo de S6 confirma a intenção mas comunica reversibilidade — **não** usa linguagem de alerta vermelho de exclusão permanente |

> **Convenção de CTA (herdada 04/05-UI-SPEC):** CTAs contextuais, sem "Cancelar" supérfluo onde fechar o painel já cancela. CTAs primárias carregam verbo + substantivo. Onde a linha exige rótulo curto ("Desfazer" na `.row-action`), o objeto vem no `title`/tooltip. "Aplicar automações"/"Aplicar selecionados" SEMPRE vêm depois de o usuário ver o dry-run (AUT-03) — nunca um "aplicar direto" sem preview na UI manual.

---

## Visuals — Encadeamento do pipeline (S1)

A diferença visual central deste redesign. O executor DEVE tornar a sequência literal:

- **Coluna de ordem à esquerda de cada card de etapa:** número (1,2,3…) em `.chip-count` (mono). É a referência de ordem (D-12).
- **Conector descendente entre cards:** uma linha vertical fina (`1px`/`2px` em `--border-strong`) ligando o card N ao card N+1, OU uma seta `arrowDown` discreta (`--text-3`) no gap entre cards. Comunica "o documento desce por aqui". Classe nova permitida: `.step-connector` (respeitando a regra de spacing — só múltiplos de 4 / tokens herdados).
- **Pílula da AÇÃO destacada** (`.flow-pill.action`, accent suave) vs. **pílulas de FILTRO** neutras (`.flow-pill`, surface-3) dentro do `.auto-flow` do card — reforça "1 filtro + 1 ação".
- **Etapa pausada** (`Switch` off): card com opacidade reduzida (ex.: `opacity: .6`) + `.badge-off` "Pausada" — fica claro que não participa do fluxo.
- **Reordenação:** botões ↑/↓ por etapa (mesma mecânica já provada no mock antigo). Sem drag-and-drop (evita dependência npm; D code-and-config).

## Visuals — Notas de acessibilidade

- **Reordenação (S1, botões ↑/↓):** `.row-action` icon-only. Cada um DEVE ter `aria-label` + `title` ("Mover etapa para cima" / "Mover etapa para baixo"). O componente `Icon` não carrega rótulo acessível por si. Desabilitar (com `disabled` + opacidade) o ↑ da primeira e o ↓ da última.
- **Demais ações icon-only** (editar, remover, Desfazer, Pré-visualizar, ativar/pausar via `Switch`): mesma regra — `aria-label` + `title` com o objeto explícito (ex.: "Editar etapa Mover", "Remover etapa Renomear").
- **Chips de token (S3):** botões; `aria-label`/`title` "Inserir {campo} no padrão". O chip mostra o token em mono.
- **Checkbox/seleção (S4):** `aria-label` por linha ("Selecionar {nome do arquivo}"); checkbox de cabeçalho "Selecionar todos os documentos aplicáveis". Linhas bloqueadas (D-07) têm checkbox `disabled` + opacidade.
- **Accent restrito** à CTA primária por superfície + pílula de ação; "Desfazer" e ↑/↓ são neutros, nunca accent.
- **Foco visível:** inputs/selects usam o `:focus` herdado (`box-shadow: 0 0 0 3px var(--accent-ring)`). Não remover outline sem substituto.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none — shadcn não usado neste projeto | not applicable |
| third-party | none | not applicable |

Nenhum registry de componentes é usado. Sistema de design próprio (`index.css` + `components/`). **Nenhuma dependência npm nova** nesta fase (code-and-config) — sem lib de drag-and-drop, sem lib de ícones. O gate de vetting de registry de terceiros não se aplica.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending (draft — redesenhado p/ modelo de PIPELINE; aguardando gsd-ui-checker)

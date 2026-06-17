---
phase: 6
slug: automacoes-de-arquivo-renomear-mover
status: approved
shadcn_initialized: false
preset: none
created: 2026-06-17
reviewed_at: 2026-06-17
---

# Phase 6 — UI Design Contract

> Contrato visual e de interação para o frontend da Fase 6 (Automações de Arquivo: Renomear/Mover). Gerado pelo gsd-ui-researcher, verificado pelo gsd-ui-checker.
>
> **Sistema de design TRAVADO (DocWatch "Corporate Modern").** Esta fase NÃO introduz um novo sistema de design. Honra integralmente `05-UI-SPEC.md`/`04-UI-SPEC.md` e os tokens/classes já em `frontend/src/index.css`. A Fase 6 **estende** esse vocabulário; **nunca substitui**. O executor reusa as classes existentes (`.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`, `.sec-title`, `.sec-desc`, `.pill`, `.pill-dot`, `.badge`/`.badge-ok`/`.badge-off`, `.row-action`, `.row-actions`, `.select`, `.search-input`, `.chips`/`.chip`/`.chip-count`, `.tabs`/`.tab`, `.cell-mono`, `.file-name`, `table.docs`, `.stack`, `.rule-card`/`.rule-name`/`.rule-param`/`.rule-desc`, `.auto-card`/`.auto-head`/`.auto-icon`/`.auto-name`/`.auto-flow`/`.flow-pill`/`.flow-tag`, `.checkbox`, `.table-toolbar`/`.table-foot`, `Switch`, `Icon`, `StatusPill`, `ConfidenceBadge`) ANTES de criar qualquer classe nova.
>
> **Restrição de visão herdada (PROJECT.md + 05-CONTEXT D-06): NÃO há visualizador/manuseio de documento na web.** A web é gestão/triagem: edita o **dado** que a automação usa e mostra **caminhos origem→destino como texto**. Sem imagem de página, sem embed de PDF, sem preview do conteúdo do arquivo. O arquivo físico é conferido/aberto no Windows Explorer. Esta restrição é absoluta.
>
> **Regra de segurança como contrato de UI (CLAUDE.md "nunca pode causar perda"):** toda ação que toca o filesystem do cliente (Aplicar, Aplicar lote, Desfazer) é precedida por feedback explícito de dry-run e por estado reversível visível. A UI NUNCA sugere irreversibilidade; "Desfazer" é sempre apresentado como disponível após aplicar.

---

## Surfaces nesta fase

A Fase 6 entrega **duas superfícies novas** (a aba Automações real, hoje um mock; e a tela de Dry-run/Preview) mais extensões pontuais. A aba Automações atual (`frontend/src/pages/AutomationsPage.tsx`) é um **mock** (lê de `data/mock.ts`, modelo "gatilho→condição→ação") e será **substituída** pela superfície real fiada à API, espelhando como `TemplatesPage` substituiu seu mock na Fase 4.

| # | Surface | Origem | O que muda |
|---|---------|--------|------------|
| S1 | **Aba "Automações" — lista de regras** (substitui o mock) | Reescreve `AutomationsPage.tsx`, molde `TemplatesPage` + classes `.rule-card`/`.stack` | Lista as **regras condicionais** ordenadas por prioridade (D-05, primeira-que-casa-vence). Cada regra: condições `{campo} [op] valor` (E/OU) → automação a aplicar (padrão de nome + pasta destino). Estados loading/erro/vazio. Polling/refetch via TanStack Query (padrão `useTemplates`) |
| S2 | **Editor de regra condicional** (criar/editar) | Novo, molde do construtor schema-first de template (S2 da Fase 4) | Form inline: linhas de condição (`select` campo + `select` operador `= > < contém` + input valor), combinador **E/OU**, e a **ação** (padrão de nome `{campo}_...` + padrão de pasta `Documentos/{cliente}/{data:aaaa-mm}/`). Reordenação por prioridade (botões mover ↑/↓ — ver nota de acessibilidade em §Visuals). Sem "Cancelar" supérfluo (convenção 04-UI-SPEC: CTAs contextuais) |
| S3 | **Editor de padrão (nome/pasta) com tokens `{campo}`** | Novo, sub-bloco de S2 | Campo de texto do padrão + **lista de tokens disponíveis** (campos do template, inseríveis por clique) + **pré-visualização ao vivo** do nome/caminho resolvido com dados de exemplo, mostrando sanitização (D-08) aplicada. `{data:aaaa-mm}` documentado como sufixo de formato |
| S4 | **Tela de Dry-run / Preview** (origem→destino) | Nova página/painel, molde `table.docs` da `DocumentsPage` | Tabela de pares **origem → destino** (texto mono), coluna de **colisão sinalizada** (sufixo `_1` aplicado, D-09 / duplicata idêntica pulada, D-10 / bloqueado→revisão por campo faltante, D-07). CTA **"Aplicar"** (lote) só após o usuário ver o preview. Seleção por documento (`.checkbox`) e por lote (D-03) |
| S5 | **Ação por-documento na lista (Aplicar / Desfazer)** | Estende `DocumentsPage` + `AttentionPage` | Em documentos de alta confiança auto-aplicados (D-01) o estado vira "Concluído"; a linha ganha ação **"Desfazer"** (`.row-action`). Documentos rebaixados a revisão por campo faltante no padrão (D-07) aparecem em "Precisam de atenção" com o motivo "Campo X usado no nome está faltando" |
| S6 | **Confirmação de Desfazer (undo)** (por-doc e por-lote) | Novo, molde do diálogo `confirmRemove` existente | Diálogo de confirmação que descreve o que será revertido (destino→origem, ou restauração do CAS se o destino sumiu). Comunica resultado: revertido / revertido-do-CAS / falha controlada (destino alterado pelo usuário). NUNCA apresenta perda |

> **S4 é o core surface da fase** e o ponto de maior risco percebido: é onde o usuário ganha confiança ANTES de qualquer efeito no disco (AUT-03). O preview é a "rede de confiança" visível. S1 é o segundo foco (configurar regras com clareza e ordem depurável, D-05).

### Focal point por superfície (hierarquia visual)

- **S1 (lista de regras):** quando **vazia**, focal point = empty state centralizado convidando a criar a primeira regra. Quando **populada**, focal point = a **ordem de prioridade** (número/posição visível em cada `.rule-card`) e o resumo condição→ação de cada regra; a CTA "Nova regra" no `.sec-head`. Accent só na CTA primária.
- **S2 (editor de regra):** focal point = a linha de **ação** (qual padrão de nome/pasta) — é o resultado da regra; as condições são o segundo nível. O combinador E/OU é explícito (não escondido).
- **S3 (editor de padrão):** focal point = a **pré-visualização resolvida** (o que o nome/caminho VAI virar), logo abaixo do campo de padrão; os tokens disponíveis são auxiliares.
- **S4 (dry-run):** focal point = a **coluna destino** e a **sinalização de colisão/bloqueio**; a contagem no topo (N serão movidos, N pulados como duplicata, N bloqueados→revisão). A CTA "Aplicar" é o único elemento com accent e fica **desabilitada até o preview carregar**.
- **S5 (ação na linha):** focal point = a pílula de estado ("Concluído" verde após aplicar); "Desfazer" é uma `.row-action` discreta (não destrutiva visualmente).
- **S6 (undo):** focal point = a descrição do que será revertido + a CTA de confirmação. Resultado comunicado em texto claro.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — sistema de design próprio TRAVADO em `frontend/src/index.css` (DocWatch "Corporate Modern"). shadcn NÃO usado (CLAUDE.md: stack é React 19 + Vite + CSS com tokens; sem component lib) |
| Preset | not applicable |
| Component library | none — componentes próprios em `frontend/src/components/` (Header, Sidebar, Icon, StatusPill, Switch, ConfidenceBadge); classes CSS utilitárias em `index.css`. Reusar `.rule-card`/`.auto-card`/`.flow-pill` já existentes para regras/automação |
| Icon library | `Icon` próprio (`frontend/src/components/Icon.tsx`). Usar nomes já existentes: `bolt` (automação — já na nav e no mock), `arrowRight` (fluxo condição→ação, já usado), `plus` (nova regra), `refresh` (reprocessar/reaplicar), `check`/`checkSmall` (aplicado/válido), `folder` (pasta destino), `dots`/`docMini`. Para **"desfazer"**, **"colisão/alerta"** e **"mover ↑/↓"** (reordenação de prioridade), se não houver ícone equivalente, adicionar a `Icon.tsx` no MESMO estilo de stroke dos existentes (não importar lib externa) |
| Font | UI: `Plus Jakarta Sans` (`--font-ui`); mono: `JetBrains Mono` (`--font-mono`). **Mono obrigatório** para: caminhos origem/destino, padrões `{campo}`, nome de arquivo, hash, e o valor numérico de condições |

**shadcn gate:** `components.json` não encontrado (verificado em `frontend/`). Projeto possui sistema de design próprio explícito e maduro; CLAUDE.md e os UI-SPECs anteriores proíbem introduzir shadcn/Tailwind. Gate resolvido como **Tool: none** (sistema existente). Registry safety gate: **não aplicável** (sem registries). Convenção da fase: **code-and-config — sem adicionar dependência npm nova** (consistente com 05-04 e com o RESEARCH "zero dependência nova").

---

## Spacing Scale

Escala 4-point já praticada em `index.css`. Reusa exatamente os tokens dos UI-SPECs anteriores; nenhum valor novo introduzido nesta fase.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Gaps inline, gap entre ações de linha (`.row-actions` gap 2px herdado), gap entre tokens inseríveis |
| sm | 8px | Espaçamento compacto, gap entre `select`s de condição, gap do `.auto-flow` |
| md | 16px | Espaçamento padrão entre regras (`.stack` gap 12px / cards), entre condições e ação |
| lg | 24px | Padding de seção / `.scroll` (24px 26px) |
| xl | 32px | Gaps de layout maiores |
| 2xl | 48px | Padding de estados vazio/erro (`48px 24px`, padrão `DocumentsPage`/`AttentionPage`) |
| 3xl | 64px | Espaçamento de nível de página |

Exceções (herdadas do bundle DocWatch, já em produção — manter, não "corrigir"): `--row-py: 13px` (linhas de `table.docs`, reusado na tabela de dry-run S4); paddings de card `16px 18px` (`.rule-card`/`.auto-card`, reusados para regras); padding de diálogo `22px` (padrão `confirmRemove`, reusado em S6); card de campo/condição `14px` (padrão do construtor da Fase 4, reusado nas linhas de condição de S2). **Regra para classes novas desta fase (ex.: `.dryrun-row`, `.pattern-preview`, `.token-chip`, `.rule-priority`): NÃO introduzir valores de espaçamento fora dos múltiplos de 4 acima; reusar exclusivamente os tokens ou as classes/cards existentes que já carregam as exceções herdadas (13/14/16-18/22px). As exceções herdadas são travadas, não licença para criar novos valores ímpares.** O executor deve checar esta regra explicitamente ao criar `.dryrun-row`, `.pattern-preview`, `.token-chip` e `.rule-priority`.

---

## Typography

Tamanhos e pesos TRAVADOS em `index.css`. Esta fase usa exatamente os 4 papéis dos UI-SPECs anteriores; sem novos tamanhos.

| Role | Size | Weight | Line Height | Token/uso existente |
|------|------|--------|-------------|---------------------|
| Body | 13px | 400 (regular) | 1.5 | texto de motivo/descrição de regra (`.rule-desc`/`.sec-desc`), células da tabela de dry-run, hint de padrão |
| Label | 12px | 600 (semibold) | 1.4 | rótulos de campo, cabeçalho de coluna |
| Heading | 15px | 600 (semibold) | 1.25 | `.sec-title` — título da aba Automações, título do editor de regra, título do dry-run |
| Display | 16px | 700 (bold) | 1.2 | `.page-title` (cabeçalho da página) |

> **Tamanhos herdados de classes existentes reusadas — referência documental, NÃO novos tamanhos desta fase:** `.flow-tag` 10px uppercase ("QUANDO/SE/AÇÃO"), `table.docs th` 11px uppercase (cabeçalho de coluna), `.rule-name` 14px/600 (nome da regra). Esses três valores vêm do bundle DocWatch já em produção e são reusados tal-qual. **Elementos NOVOS desta fase usam exclusivamente os 4 papéis da tabela acima (12/13/15/16px).** O contrato tipográfico da fase é de **4 tamanhos**; os herdados são travados, não licença para criar novos.

**Pesos: exatamente 2 — regular `400` e forte (semibold `600` / bold `700`).** 600 e 700 são subvariantes do mesmo "peso forte" (não dois pesos independentes): use **700** apenas em `.page-title` (Display), `.btn-primary` e `.stat-num` (contagens grandes do topo do dry-run, se exibidas em card); use **600** em todo o resto que precise de peso forte (rótulos, `.rule-name`, títulos de seção, badges, `.flow-tag`). Não escolher arbitrariamente entre 600 e 700 em elementos novos. Fonte mono (`--font-mono`) reservada a: caminhos origem→destino, padrões `{campo}`, nome de arquivo, valor de condição numérica, hash.

---

## Color

Paleta TRAVADA em `:root` / `[data-theme="dark"]` de `index.css`. Tema claro e escuro já suportados — toda cor por **token CSS var**, nunca hex hardcoded.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `var(--bg)` #F5F7FB (claro) / #0B1017 (escuro) | Fundo da aplicação, área de scroll |
| Secondary (30%) | `var(--surface)` #FFFFFF / #141B25 + `var(--surface-2)`/`--surface-3` | Cards de regra, cards de condição, header, toolbar do dry-run, `.flow-pill` (surface-3) |
| Accent (10%) | `var(--accent)` #2563EB / #3B82F6 | Ver lista reservada abaixo |
| Destructive | `var(--st-erro)` #DC2626 / #F87171 (+ `--st-erro-bg`) | Apenas sinalização: bloqueio→revisão por campo faltante (D-07), erro de operação, motivo de FALHA. **Nenhuma ação desta fase é destrutiva** (Aplicar e Desfazer são reversíveis por desenho — ver Copywriting) |

**Accent reservado para:** botão primário **"Aplicar"** (dry-run S4) e **"Aplicar selecionados"**; **"Nova regra"** e **"Salvar regra"** (S1/S2); estado `:focus` dos inputs de condição/padrão (`box-shadow: 0 0 0 3px var(--accent-ring)`); estado ativo de aba/chip de filtro do dry-run (`.chip.active`/`.tab` ativo em `--accent-soft`); `.flow-pill.action` (a pílula da AÇÃO de uma regra, já em `--accent-soft`/`--accent`). `--accent-soft` é variante tonal (fundo suave do mesmo accent para estados ativos), não um segundo accent. **Não** usar accent como cor de fundo geral, nem em todo elemento interativo, nem na ação "Desfazer" (que é `.row-action` neutra/`.btn-ghost`).

### Cores semânticas de status (reusar tokens `--st-*` existentes — NÃO criar novos)

| Marca | Token | Aparência |
|-------|-------|-----------|
| Documento **aplicado/concluído** | `--st-tratado` / `--st-tratado-bg` (verde) | `StatusPill state="concluido"` ("Concluído") após a automação aplicar com sucesso — este é o momento reservado ao verde |
| **Colisão resolvida por sufixo** (D-09, `_1`/`_2`) | `--st-leitura` / `--st-leitura-bg` (âmbar) | `.badge`/`.pill` âmbar "Renomeado p/ evitar colisão" no dry-run — é informativo, não erro |
| **Duplicata idêntica pulada** (D-10) | `--st-encontrado` / `--st-encontrado-bg` (azul muted) | `.badge` azul "Já existe (idêntico) — pulado" — neutro/informativo |
| **Bloqueado → revisão** por campo faltante (D-07) | `--st-erro` / `--st-erro-bg` (vermelho) | `.badge` vermelha "Campo faltando — enviado para revisão"; o documento aparece em "Precisam de atenção" (EM_REVISAO, token `leitura` no StatusPill) |
| **Falha de operação** (lock de arquivo, hash divergente) | `--st-erro` / `--st-erro-bg` (vermelho) | `StatusPill state="falha"` ("Falha") + ação "Tentar de novo" (reusa S2 da Fase 5) |
| **Regra ativa / pausada** | `--st-tratado-bg`/`--surface-3` | `.badge badge-ok` "Ativa" / `.badge badge-off` "Pausada" (reusa o padrão do mock atual) |

> Regra: o estado de "duplicata pulada" e "renomeado por colisão" são **informativos** (azul/âmbar), nunca vermelho — eles representam o sistema protegendo o arquivo, não falha. Vermelho fica restrito a bloqueio-por-campo-faltante e a falha real de operação. O indicador de confiança (`ConfidenceBadge`, S5 da Fase 5) é reusado tal-qual nas linhas — não redefinido aqui.

---

## Copywriting Contract

Idioma: **pt-BR** (consistente com todo o frontend). Tom: direto, sem jargão, enfatizando segurança/reversibilidade. Toda cópia abaixo é prescritiva.

| Element | Copy |
|---------|------|
| Primary CTA (dry-run S4) | **"Aplicar automações"** (lote: **"Aplicar selecionados"**) — após o preview |
| Primary CTA (S1/S2) | **"Nova regra"** (criar) / **"Salvar regra"** (editar) |
| CTA secundária por-doc | **"Desfazer aplicação"** (reverter; rótulo curto "Desfazer" aceitável só na `.row-action` com `title`/tooltip que repete o objeto) / **"Pré-visualizar automação"** (abrir dry-run de 1 doc) |
| Empty state heading (S1 regras) | **"Nenhuma regra de automação ainda"** |
| Empty state body (S1) | **"Crie uma regra para renomear e organizar arquivos automaticamente a partir dos campos extraídos. Ex.: holerite com valor acima de R$ 3.000 → pasta Análise."** + CTA "Nova regra" |
| Empty state (S4 dry-run vazio) | **"Nenhum documento pronto para automação. Documentos de alta confiança são aplicados automaticamente; os demais aguardam revisão."** |
| Error state (geral) | **"Não foi possível carregar. Verifique se o servidor está rodando e tente de novo."** (reusa o padrão de erro de `DocumentsPage`/`AttentionPage`) |
| Error state (operação falhou) | **"A automação não pôde concluir (o arquivo pode estar aberto em outro programa). O documento foi mantido seguro — tente de novo."** |
| Aviso de bloqueio (D-07) | **"Campo '{campo}' usado no nome/pasta está faltando ou inválido. Enviado para revisão antes de aplicar."** |
| Aviso colisão sufixo (D-09) | **"Já existe um arquivo diferente com esse nome — será salvo como '{nome}_1'."** |
| Aviso duplicata (D-10) | **"Esse arquivo já existe no destino (conteúdo idêntico) — será pulado."** |
| Hint de preview (S3) | **"Pré-visualização com dados de exemplo. Caracteres inválidos no Windows são removidos automaticamente."** |
| Resultado do undo (sucesso) | **"Desfeito. O arquivo voltou ao local de origem."** |
| Resultado do undo (via CAS) | **"O arquivo de destino não foi encontrado no lugar esperado. Restauramos a cópia íntegra preservada pelo sistema para a pasta de origem."** |
| Destructive confirmation | **Nenhuma ação desta fase é destrutiva.** "Aplicar automações" sempre oferece "Desfazer aplicação" depois; "Desfazer aplicação" restaura (do destino ou do CAS) e nunca apaga sem rede. O diálogo de S6 confirma a intenção mas comunica reversibilidade — **não** usa linguagem de alerta vermelho de exclusão permanente. |

> Convenção de CTA (herdada 04/05-UI-SPEC): CTAs contextuais, sem botão "Cancelar" supérfluo onde fechar o painel já cancela. CTAs primárias carregam verbo + substantivo ("Aplicar automações", "Salvar regra", "Nova regra", "Pré-visualizar automação"). Onde o espaço da linha exige rótulo curto ("Desfazer" na `.row-action`), o objeto vem no `title`/tooltip. "Aplicar automações" e "Aplicar selecionados" SEMPRE vêm depois de o usuário ver o dry-run (AUT-03) — nunca um "aplicar direto" sem preview na UI manual.

---

## Visuals — Notas de acessibilidade

- **Reordenação de prioridade (S2, botões mover ↑/↓):** são `.row-action`/botões icon-only. Cada botão DEVE ter `aria-label` + `title` ("Aumentar prioridade" / "Diminuir prioridade") — o componente `Icon` não carrega rótulo acessível por si só. Não deixar botão de seta sem label textual acessível.
- **Outras ações icon-only** (Desfazer, Pré-visualizar como `.row-action`): mesma regra — `aria-label` + `title` com o objeto explícito.
- Accent restrito à CTA primária por superfície; "Desfazer" e os controles de reordenação são neutros (`.row-action`/`.btn-ghost`), nunca accent.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none — shadcn não usado neste projeto | not applicable |
| third-party | none | not applicable |

Nenhum registry de componentes é usado. Sistema de design próprio (`index.css` + `components/`). **Nenhuma dependência npm nova** nesta fase (code-and-config), portanto o gate de vetting de registry de terceiros não se aplica.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS (FLAGs de CTA de palavra única resolvidos — verbo+substantivo + objeto no `title`)
- [x] Dimension 2 Visuals: PASS (acessibilidade de ações icon-only ↑/↓/Desfazer documentada)
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS (tamanhos herdados movidos para nota; contrato = 4 papéis)
- [x] Dimension 5 Spacing: PASS (exceções herdadas justificadas; regra para classes novas explícita)
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-06-17

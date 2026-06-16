---
phase: 5
slug: confianca-revisao-humana-e-quarentena
status: approved
shadcn_initialized: false
preset: none
created: 2026-06-16
reviewed_at: 2026-06-16
---

# Phase 5 — UI Design Contract

> Contrato visual e de interação para o frontend da Fase 5 (Confiança, Revisão Humana e Quarentena). Gerado pelo gsd-ui-researcher, verificado pelo gsd-ui-checker.
>
> **Sistema de design TRAVADO (DocWatch "Corporate Modern").** Esta fase NÃO introduz um novo sistema de design. Honra integralmente `04-UI-SPEC.md` e os tokens/classes já em `frontend/src/index.css`. A Fase 5 **estende** esse vocabulário; **nunca substitui**. O executor reusa classes existentes (`.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`, `.sec-title`, `.sec-desc`, `.pill`, `.pill-dot`, `.badge`/`.badge-ok`, `.row-action`, `.select`, `.search-input`, `.chips`/`.chip`, `.tabs`/`.tab`, `.cell-mono`, `table.docs`, `Switch`, `Icon`, `StatusPill`) antes de criar qualquer nova classe.
>
> **Restrição de visão (D-06): NÃO há visualizador de documento na web** — sem imagem de página, sem embed de PDF, sem texto bruto lado-a-lado, sem painel do documento. A UI mostra **motivo + valores de campo**. O arquivo em si é conferido no Windows Explorer. Esta restrição é absoluta nesta fase.

---

## Surfaces nesta fase

A Fase 5 entrega uma única superfície nova de triagem mais um indicador de confiança reutilizável. Automações de arquivo (renomear/mover, dry-run, undo) são Fase 6 e **não** são desenhadas aqui.

| # | Surface | Origem | O que muda |
|---|---------|--------|------------|
| S1 | **Visão "Precisam de atenção"** (nova página/aba) | Novo, molde `DocumentsPage` | Lista os documentos sinalizados, organizados em **3 baldes** (FALHA, QUARENTENA, EM_REVISAO), cada item com o **motivo**. Estados loading/erro/vazio. Polling via TanStack Query (padrão `useDocuments`) |
| S2 | **Item FALHA** | Novo | Mostra motivo da falha + ação única **"Tentar de novo"** (reenfileira; `FALHA→PROCESSANDO`) |
| S3 | **Item QUARENTENA** | Novo | Mostra motivo (nenhum template casou) + `select` **"Atribuir template"** + ação **"Reclassificar"** (`QUARENTENA→PROCESSANDO` com template forçado) |
| S4 | **Item EM_REVISAO** | Novo | Mostra **indicador de confiança** + tabela de campos com **correção inline** dos campos inválidos + ação **"Aprovar"** (`EM_REVISAO→CONCLUIDO`) |
| S5 | **Indicador de confiança** (componente) | Novo, reutilizável | Badge/pílula derivada do score 0–100% (D-02) → rótulo legível (alta/média/baixa). Reusa estética `.badge`/`.pill` + tokens `--st-*`. Aparece em S4 e no detalhe de classificação existente (`DocumentDetailModal`) |
| S6 | **Limiar de confiança na Config** | Estende a página de Configurações | Um campo numérico (0–100%) para o limiar global (D-03), molde dos tunables existentes. Somente leitura+edição de um número; sem UI complexa |

> S1 é o **core surface** da fase. O mock aprovado (05-CONTEXT `<specifics>`) é o norte: uma página única com seções por balde. Discretion (05-CONTEXT): seções por balde vs filtros — o executor pode usar `.chips`/`.tabs` existentes para alternar entre baldes OU seções empilhadas; ambos honram o mock.

### Focal point por superfície (hierarquia visual)

- **S1 (página):** quando **vazia** (nada precisa de atenção), o focal point é o empty state centralizado com a mensagem positiva "Tudo em dia". Quando **populada**, o focal point é a **contagem por balde** no topo (quantos itens em cada um) e, abaixo, a lista do balde selecionado. O motivo de cada item é o segundo nível de hierarquia; a ação primária do item é o único elemento com accent/destaque dentro da linha.
- **S2 (FALHA):** focal point = o **motivo da falha** (texto), com **"Tentar de novo"** como CTA do item.
- **S3 (QUARENTENA):** focal point = o `select` **"Atribuir template"**; **"Reclassificar"** fica desabilitado (`disabled`) até um template ser escolhido.
- **S4 (EM_REVISAO):** focal point = o **indicador de confiança** + os **campos inválidos** (marcados em vermelho, com input de correção inline). **"Aprovar"** é a CTA final, habilitada só quando todos os campos obrigatórios estão válidos (D-07).
- **S5 (indicador):** o número (score %) é a fonte de verdade; o rótulo (alta/média/baixa) e a cor são derivados — o número aparece sempre junto do rótulo.
- **S6 (limiar):** focal point = o campo numérico do limiar com sufixo "%" e hint explicando o efeito.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — sistema de design próprio TRAVADO em `frontend/src/index.css` (DocWatch "Corporate Modern"). shadcn NÃO usado (CLAUDE.md: stack é React 19 + Vite + CSS com tokens; sem component lib) |
| Preset | not applicable |
| Component library | none — componentes próprios em `frontend/src/components/` (Header, Sidebar, Icon, StatusPill, Switch); classes CSS utilitárias em `index.css` |
| Icon library | `Icon` próprio (`frontend/src/components/Icon.tsx`) — usar nomes já existentes: `refresh` (tentar de novo / reclassificar), `check`/`checkSmall` (aprovar / válido), `grid` (template), `dots`, `docMini`, `folder`. NÃO introduzir lib de ícones externa. Se um ícone novo for necessário (ex.: alerta/atenção), adicioná-lo a `Icon.tsx` no mesmo estilo de stroke dos existentes |
| Font | UI: `Plus Jakarta Sans` (`--font-ui`); mono: `JetBrains Mono` (`--font-mono`) — mono para valores de campo (bruto/normalizado), score numérico, caminhos e identificadores |

**shadcn gate:** `components.json` não encontrado. Projeto possui sistema de design próprio explícito e maduro; CLAUDE.md e o 04-UI-SPEC proíbem introduzir shadcn/Tailwind. Gate resolvido como **Tool: none** (sistema existente). Registry safety gate: não aplicável.

---

## Spacing Scale

Escala 4-point já praticada em `index.css`. Reusa exatamente os tokens do 04-UI-SPEC; nenhum valor novo introduzido nesta fase.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Gaps inline, gap entre botões de ação no item |
| sm | 8px | Espaçamento compacto, gap entre ações de um item (`select` + botão) |
| md | 16px | Espaçamento padrão entre campos editáveis e entre baldes/seções |
| lg | 24px | Padding de seção / `.table-scroll` |
| xl | 32px | Gaps de layout maiores |
| 2xl | 48px | Padding de estados vazio/erro (`48px 24px`, padrão `DocumentsPage`) |
| 3xl | 64px | Espaçamento de nível de página |

Exceções (herdadas do bundle DocWatch, já em produção — manter, não "corrigir"): `--row-py: 13px` para linhas de tabela; paddings de modal `22px` (padrão `DocumentDetailModal`/`confirmRemove`); padding de card de campo `14px` (padrão do construtor S2 da Fase 4). A correção inline de campos em S4 reusa o card de campo de 14px do construtor existente. Gap entre campos editáveis: **14px** (espelha o form da Fase 4). **Regra para classes novas desta fase (`.attn-row`, `.conf-badge`, badge "corrigido manualmente"): NÃO introduzir novos valores de espaçamento fora dos tokens múltiplos de 4 acima; reusar exclusivamente os tokens ou as classes/cards existentes que já carregam as exceções herdadas. As exceções 13/14/22px são herança travada, não licença para criar novos valores ímpares.**

---

## Typography

Tamanhos e pesos TRAVADOS em `index.css`. Esta fase usa exatamente os 4 papéis do 04-UI-SPEC; sem novos tamanhos.

| Role | Size | Weight | Line Height | Token/uso existente |
|------|------|--------|-------------|---------------------|
| Body | 13px | 400 (regular) | 1.5 | texto de motivo, texto de tabela, `.sec-desc` |
| Label | 12px | 600 (semibold) | 1.4 | rótulos de campo, rótulo "Confiança", `.stat-label`; títulos de grupo 10.5px uppercase (`.tpl-fields-label`/`table.docs th`) |
| Heading | 15px | 600 (semibold) | 1.25 | `.sec-title` — títulos de balde/seção e de modal |
| Display | 16px | 700 (bold) | 1.2 | `.page-title` (cabeçalho da página "Precisam de atenção") |

**Pesos: exatamente 2 — regular `400` e forte (semibold `600`/bold `700`).** Regra prescritiva para componentes novos: **600** para rótulos, títulos de balde e headings; **700** apenas no `.page-title` (Display), no `.btn-primary` e no `.stat-num` (score numérico grande, se exibido em card de contagem). Não escolher arbitrariamente entre 600 e 700 em elementos novos. **600 e 700 são subvariantes do mesmo "peso forte" (não dois pesos independentes): use 700 apenas em `.page-title` (Display), `.btn-primary` e `.stat-num`; use 600 em todo o resto que precise de peso forte (rótulos, títulos de balde, headings, badges).** Fonte mono (`--font-mono`) reservada a: valores de campo (bruto e normalizado), o **score numérico** (ex.: "72%"), nome de arquivo, caminhos e regex.

---

## Color

Paleta TRAVADA em `:root` / `[data-theme="dark"]` de `index.css`. Tema claro e escuro já suportados — toda cor por **token CSS var**, nunca hex hardcoded.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `var(--bg)` #F5F7FB (claro) / #0B1017 (escuro) | Fundo da aplicação, área de scroll |
| Secondary (30%) | `var(--surface)` #FFFFFF / #141B25 + `var(--surface-2)`/`--surface-3` | Cards, header, toolbars, cards de item de triagem, cards de campo editável |
| Accent (10%) | `var(--accent)` #2563EB / #3B82F6 | Ver lista reservada abaixo |
| Destructive | `var(--st-erro)` #DC2626 / #F87171 (+ `--st-erro-bg`) | Apenas: marca de campo inválido, motivo de FALHA e mensagens de erro. **Nenhuma ação desta fase é destrutiva** (ver Copywriting) — vermelho é só sinalização |

**Accent reservado para:** botão primário **"Aprovar"** (S4) e **"Reclassificar"** (S3) e **"Tentar de novo"** (S2) — cada um é a CTA do seu item; estado `:focus` de inputs de correção (`box-shadow: 0 0 0 3px var(--accent-ring)`); estado ativo de aba/chip de balde (`.chip.active`/`.tab` ativo, em `--accent-soft`); botão "Salvar" do limiar em S6. **Não** usar accent como cor de fundo geral nem em todo elemento interativo.

### Cores semânticas de status (reusar tokens `--st-*` existentes — NÃO criar novos)

| Marca | Token | Aparência |
|-------|-------|-----------|
| Balde / item **FALHA** | `--st-erro` / `--st-erro-bg` (vermelho) | `StatusPill state="falha"` já mapeia para token `erro` ("Falha") |
| Balde / item **QUARENTENA** | `--st-leitura` / `--st-leitura-bg` (âmbar) | `StatusPill state="quarentena"` já mapeia para token `leitura` ("Quarentena") — **NÃO alterar** |
| Balde / item **EM_REVISAO** | `--st-leitura` / `--st-leitura-bg` (âmbar) | `StatusPill state="em_revisao"` já mapeia para token `leitura` ("Em revisão") — **NÃO alterar** |
| Campo válido | `--st-tratado` / `--st-tratado-bg` (verde) | `.badge badge-ok` "válido" |
| Campo inválido / faltante | `--st-erro` / `--st-erro-bg` (vermelho) | `.badge` vermelha "inválido" + `title`/hint com `invalid_reason` |
| Documento aprovado | `--st-tratado` (verde) | Após aprovação → `StatusPill state="concluido"` ("Concluído") verde — reservado a este momento (entra em CONCLUIDO, D-07) |

### Indicador de confiança (S5) — mapeamento score → cor (rótulo derivado, D-02)

O **número** (0–100%) é a fonte de verdade; a faixa abaixo é só apresentação. As faixas são **prescritas** (não inventar outras); a fronteira "média/baixa" acompanha o limiar global, mas o indicador exibe sempre o número.

| Faixa de score | Rótulo | Token |
|----------------|--------|-------|
| ≥ 80% | **Alta** | `--st-tratado` / `--st-tratado-bg` (verde) |
| 50–79% | **Média** | `--st-leitura` / `--st-leitura-bg` (âmbar) |
| < 50% | **Baixa** | `--st-erro` / `--st-erro-bg` (vermelho) |

> Regra: o indicador de confiança NÃO usa cor de accent (accent é só para CTAs/foco). Verde aqui significa "qualidade de extração alta", distinto do verde de "Concluído" (estado do documento) — ambos usam `--st-tratado` por consistência da paleta, mas em contextos diferentes (badge de confiança vs StatusPill de estado).

---

## Copywriting Contract

Todo texto em **pt-BR**. Termos técnicos (CNPJ, CPF, regex, ISO, template) mantidos.

| Element | Copy |
|---------|------|
| Título da página (S1) | **"Precisam de atenção"** |
| Subtítulo da página (S1) | **"Documentos que pararam por falha, quarentena ou baixa confiança. Resolva cada um aqui; o arquivo em si você confere no Explorador de Arquivos."** |
| Rótulo do balde FALHA | **"Falhas"** (com contagem) — sub: *"erro no processamento"* |
| Rótulo do balde QUARENTENA | **"Quarentena"** (com contagem) — sub: *"nenhum template casou"* |
| Rótulo do balde EM_REVISAO | **"Em revisão"** (com contagem) — sub: *"confiança baixa ou campo inválido"* |
| CTA item FALHA (S2) | **"Tentar de novo"** (ícone `refresh`, `.btn-ghost` ou `.btn-primary` por item) / em andamento: **"Reenviando…"** |
| Motivo FALHA (S2) | Mostrar a mensagem de erro persistida; fallback: **"Falha no processamento. Tente novamente; se persistir, verifique o arquivo de origem."** |
| Rótulo "Atribuir template" (S3) | **"Atribuir template"** — `select` com placeholder **"Escolha um template…"** |
| CTA item QUARENTENA (S3) | **"Reclassificar"** (ícone `refresh`) / em andamento: **"Reclassificando…"** — `disabled` até escolher template |
| Motivo QUARENTENA (S3) | **"Nenhum template casou com este documento. Atribua um template para reclassificar."** |
| Rótulo do indicador (S4/S5) | **"Confiança"** seguido de **"{score}% · {Alta/Média/Baixa}"** |
| Cabeçalho de campos (S4) | **"Campos extraídos"** com colunas **"Campo"**, **"Valor"** (bruto), **"Normalizado"**, **"Marca"** |
| Input de correção (S4) | Reusa `.search-input` (mono); `aria-label="Corrigir valor de {nome do campo}"`; marca de campo corrigido: **"corrigido manualmente"** (badge neutra, D-08) |
| CTA item EM_REVISAO (S4) | **"Aprovar documento"** (ícone `check`, `.btn-primary`) / em andamento: **"Aprovando…"** — `aria-label="Aprovar documento {nome do arquivo}"` |
| CTA salvar correção (S4) | **"Salvar correção"** (`.btn-ghost`) / salvando: **"Salvando…"** — revalida pelo tipo do campo, sem chamar IA (D-08) |
| Aprovar bloqueado (S4) | Botão "Aprovar" `disabled` + hint: **"Corrija os campos obrigatórios inválidos antes de aprovar o documento."** |
| Rótulo do limiar (S6) | **"Limiar de confiança"** — sufixo **"%"** — hint: **"Documentos com confiança abaixo deste valor, ou com qualquer campo obrigatório inválido, vão para revisão."** |
| CTA salvar limiar (S6) | **"Salvar limiar"** / salvando: **"Salvando…"** |
| Empty state heading (S1) | **"Tudo em dia"** |
| Empty state body (S1) | **"Nenhum documento precisa de atenção agora. Documentos com falha, em quarentena ou com baixa confiança aparecem aqui automaticamente."** |
| Empty state por balde | FALHA: **"Nenhuma falha pendente."** / QUARENTENA: **"Nada em quarentena."** / EM_REVISAO: **"Nada aguardando revisão."** |
| Error state (S1) | Heading: **"Não foi possível carregar os documentos."** Body: **"Verifique se o serviço está em execução e tente novamente."** + botão **"Tentar novamente"** (padrão `DocumentsPage`) |
| Erro de ação (S2/S3/S4) | **"Não foi possível concluir a ação. Tente novamente."** (mensagem inline em `var(--st-erro)`, item permanece visível) |

> Nota sobre CTAs: **não** se usa o label genérico "Cancelar". Cada ação é um verbo + contexto explícito ("Tentar de novo", "Reclassificar", "Aprovar", "Salvar correção"). **Não há ação destrutiva nesta fase** — nenhum botão remove ou descarta dados; todas as ações avançam o documento na máquina de estados ou corrigem valores. Por isso não há modal de confirmação destrutiva nesta fase.

---

## Component Inventory (reuso vs novo)

**Reusar sem alteração:** `.card`, `.btn-primary`, `.btn-ghost`, `.sec-head`/`.sec-head-col`/`.sec-title`/`.sec-desc`, `.page-title`, `.chips`/`.chip`/`.chip-count`/`.chip.active`, `.tabs`/`.tab`, `.stat-grid`/`.stat-card`/`.stat-label`/`.stat-num`/`.stat-sub`/`.stat-dot` (para contagem por balde), `table.docs`/`.cell-mono`/`.file-name`, `.search-input`, `.select`, `.row-action`, `.badge`/`.badge-ok`, `.pill`/`.pill-dot`, `.table-toolbar`/`.table-scroll`/`.table-foot`/`.foot-text`, `Switch`, `Icon`, `StatusPill`. Estados loading/erro/vazio e o padrão de modal: copiar de `DocumentsPage.tsx` (`DocumentDetailModal`) e `TemplatesPage.tsx`.

**StatusPill (NÃO alterar mapeamento):** `falha → erro` ("Falha"), `quarentena → leitura` ("Quarentena"), `em_revisao → leitura` ("Em revisão"), `concluido → tratado` ("Concluído"). Estes já existem em `StatusPill.tsx` linhas 19–26 e são a fonte de verdade para os pills dos baldes.

**Novas classes permitidas (apenas se necessário; prefixo coerente, mesma estética):**
- Linha de item de triagem (ex.: `.attn-row` — espelhar `table.docs tr`/`.folder-row`): motivo + ações inline.
- Badge de confiança (ex.: `.conf-badge` — espelhar `.badge`): número mono + rótulo, cor por faixa via `var(--st-*)`.
- Badge "corrigido manualmente" (ex.: `.badge` neutra com `--surface-3`/`--text-3`).

Qualquer cor via `var(--…)`; qualquer raio via `var(--radius)`/`var(--radius-sm)`; pesos só 600/700 conforme Typography. O indicador de confiança (S5) deve ser componente isolado (ex.: `ConfidenceBadge`) reutilizável tanto em S4 quanto no `DocumentDetailModal` existente.

**Hooks/dados:** novos hooks TanStack Query seguindo o padrão de `useDocuments.ts`/`useTemplates.ts` (queryKey, `invalidateQueries` em `onSuccess`, fonte de verdade = API): `useAttentionDocuments` (lista os 3 baldes; polling), `useRetryDocument` (FALHA), `useReclassifyDocument` (QUARENTENA + template), `usePatchField` (corrige `raw_value`/`normalized_value`, D-08), `useApproveDocument` (EM_REVISAO → CONCLUIDO). Cliente fetch tipado em `lib/api.ts`; tipos em `types.ts` (estender `DocumentDetail`/`FilledField` com `confidence_score` e `manually_corrected`). Estados de tela: `isInitialLoading` (skeleton), `isError` (retry), `isEmpty` (empty state "Tudo em dia"), `isRefetching` (indicador "Atualizando…"), `isPending` por ação (label "…ando" + `disabled`).

---

## Interaction States (obrigatórios por superfície)

| Surface | Loading | Erro | Vazio | Sucesso |
|---------|---------|------|-------|---------|
| S1 lista "Precisam de atenção" | skeleton em linhas (`var(--surface-3)` opacity .7, padrão `DocumentsPage`) | bloco centralizado + "Tentar novamente" | empty state "Tudo em dia" (geral) ou por balde | linhas por balde + contagens no topo |
| S2 FALHA | botão "Reenviando…" `disabled` | mensagem inline `var(--st-erro)`, item permanece | n/a | item sai da lista (vira PROCESSANDO) + invalida query |
| S3 QUARENTENA | botão "Reclassificando…" `disabled` | mensagem inline, item permanece | n/a | item sai da lista (vira PROCESSANDO) + invalida query |
| S4 EM_REVISAO (correção) | botão "Salvando…" `disabled` no salvar; revalida pelo tipo | mensagem inline; campo mantém valor digitado | n/a | campo revalidado → marca atualiza (verde/vermelho); badge "corrigido manualmente" |
| S4 EM_REVISAO (aprovar) | botão "Aprovando…" `disabled` | mensagem inline, item permanece | n/a | item sai da lista (vira CONCLUIDO) + invalida query; pill vira "Concluído" verde |
| S5 indicador de confiança | herda loading do detalhe | herda erro do detalhe | n/a | badge "{score}% · {rótulo}" colorida por faixa |
| S6 limiar (Config) | botão "Salvando…" `disabled` | mensagem inline | n/a | valor persistido + confirmação visual sutil |

**Aprovação condicionada (D-07):** "Aprovar" fica `disabled` enquanto qualquer campo obrigatório estiver inválido/faltante, com hint explicando. Habilita assim que todos os obrigatórios ficam válidos após correção.

**Acessibilidade:** inputs de correção com `<label>` associado ou `aria-label`; botões-ícone com `aria-label` (padrão `aria-label="…"` já usado); `:focus` visível via `--accent-ring` (já no CSS); foco de teclado preservado em qualquer modal; `title` com `invalid_reason` no badge "inválido" (padrão `DocumentDetailModal`). Valores de campo renderizados como **texto puro** (React, sem `dangerouslySetInnerHTML`) — padrão de segurança já estabelecido na Fase 4.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none (sem shadcn / sem registry de terceiros) | nenhum | not applicable |

Nenhum registro de componente externo. Toda UI é construída com as classes/componentes próprios já no repositório. Registry vetting gate: não aplicável.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS (FLAG resolvido: "Aprovar documento")
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS (FLAG resolvido: regra 600/700 explicitada)
- [x] Dimension 5 Spacing: PASS (FLAG resolvido: regra para classes novas explicitada)
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-06-16 (3 FLAGs não-bloqueantes do checker absorvidos: CTA "Aprovar documento"; subvariantes 600/700 do peso forte com regra prescritiva reforçada; instrução explícita de manter classes novas em múltiplos de 4)

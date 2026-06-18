# Phase 6: Automações de Arquivo (Renomear/Mover) - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

O sistema renomeia e move os **arquivos reais do cliente** (o original na pasta monitorada) com base nos campos extraídos, de forma **reversível e segura**: dry-run obrigatório, log de auditoria escrito ANTES de agir, anti-colisão (nunca sobrescreve), undo por-documento e por-lote, e mover entre discos é copia→verifica→remove. Inclui **regras condicionais de tratativa** (TPL-02): condição sobre os campos extraídos → qual automação aplicar, permitindo tratativas diferentes para o mesmo tipo de documento por cliente/emissor/valor.

Escopo: AUT-01..AUT-06 + TPL-02. **Fora de escopo:** automações além de renomear/mover (chamar API, e-mail/WhatsApp) — fases futuras.
</domain>

<decisions>
## Implementation Decisions

### ⚠️ REDESIGN — Modelo de PIPELINE de automações (2026-06-17) — SUBSTITUI o modelo de regra-única
> Decisão do usuário ao revisar a Fase 6: as automações deixam de ser uma "regra única (condição → nome+pasta, primeira-que-casa-vence)" e passam a ser um **pipeline ordenado de etapas componíveis**. Isto **SUBSTITUI D-04, D-05 e o acoplamento de D-06** (nome+pasta numa só regra). Demais decisões abaixo (D-07, D-08, D-09, D-10, D-11, D-01/02/03, AUT-04/05) permanecem válidas.

- **D-12:** Automações = **pipeline ORDENADO de etapas (steps)**. Cada documento passa por **TODAS as etapas cujo filtro casa, na ordem** definida pelo usuário (encadeado), não "primeira que casa vence". (SUBSTITUI D-05.)
- **D-13:** Cada etapa = **um filtro de entrada + UMA ação atômica**. Ações do v1: **Mover** (pasta destino com tokens), **Renomear** (tokens dos campos), **Identificar tipo (gate)** (classifica contra template; porteiro p/ etapas seguintes), **Rotear/decidir tratar** (enviar p/ revisão humana / marcar não-tratar / ignorar). Renomear+mover = duas etapas encadeadas. (SUBSTITUI D-04 e o acoplamento de D-06.)
- **D-14:** **Filtros de entrada** combináveis por etapa: pasta de origem monitorada, tipo de arquivo (extensão), tipo/template classificado, valor de campo extraído, **nome do arquivo, tamanho** (e atributos simples afins).
- **D-15:** A ação **Identificar tipo** REUSA a classificação/extração já existentes (Fases 3/4) — não cria parsers novos. Parser de linha digitável de boleto e afins permanecem na Fase 7.
- **D-16:** **Escopo v1 do pipeline:** ações de arquivo (mover/renomear/rotear) + identificação de tipo como etapa. **Fora do v1:** etapas que extraem campo específico (ex. buscar linha digitável) — Fase 7.

**Open questions a resolver no replan:**
- Semântica do "caminho corrente" de um documento no pipeline: como Renomear (muda nome-alvo) e Mover (muda pasta-alvo) compõem antes da materialização do CAS para o disco (D-11) — a operação física acontece a cada etapa de arquivo ou é resolvida e materializada ao final? O write-ahead/undo (AUT-04/05) precisa cobrir o pipeline inteiro (undo de todas as etapas de um documento).
- Como o pipeline se relaciona com a fila/worker existente (step `apply`): o `apply_stage` passa a executar o pipeline ordenado por documento.

### Refinamentos do construtor (validados via mockup, 2026-06-17)
> Após 2 reescritas confusas, validamos a UI por um mockup HTML clicável (`06-MOCKUP-automacoes.html`). APROVADO pelo usuário. Refina/ajusta D-13/D-14.

- **D-17:** **"Identificar arquivo"** é uma ação/etapa de GATE PRÓPRIA (separada de "Identificar tipo (template)"). Filtra por **tipo de arquivo via extensão DIGITÁVEL** pelo usuário (`.pdf`, `.xlsx`, …; pode aceitar múltiplas) — NÃO um select fixo. Permite "primeiro só PDFs, depois identificar o template". As ações de gate do v1 são: Identificar arquivo (extensão) e Identificar tipo (template).
- **D-18:** **Semântica de GATE:** uma etapa de identificação (arquivo OU tipo) cujo filtro NÃO casa **INTERROMPE o pipeline** para aquele documento (porteiro — só os que passam seguem às etapas seguintes). Etapas de ação (Renomear/Mover) com filtro próprio apenas PULAM quando não casam (não interrompem).
- **D-19:** **Tokens = campos do template escolhido.** Os chips de campo (renomear/mover) são os **campos definidos no template** selecionado no gate "Identificar tipo" — NÃO uma lista fixa; mudam conforme o usuário cria/edita templates. O frontend busca os campos do template para os chips; a resolução do valor usa os campos extraídos do próprio documento.
- **D-20:** **Reordenação por DRAG-AND-DROP** (HTML5 nativo, SEM dependência npm nova) + botões ↑/↓ para acessibilidade. (SUPERA a decisão anterior do UI-SPEC de "sem drag-and-drop".)
- **D-21:** **Campos de caminho** (Mover destino, pasta de origem, qualquer path) **aceitam com ou sem aspas** — normalizar removendo aspas nas pontas (front-end ao sair do campo + back-end defensivo). Usuário cola caminho do Windows (`"C:\...\Análise"`).
- **D-22:** A ação **"Rotear/decidir tratativa"** (revisão/não-tratar/ignorar) **REMOVIDA do v1** (sem caso de uso claro; volta quando houver). Backend pode manter dormente, UI não expõe.

### Disparo da automação
- **D-01:** **Auto-aplica para documentos de alta confiança** (acima do `review_confidence_threshold` da Fase 5 — i.e., os que NÃO caíram em EM_REVISAO). Documentos de baixa confiança / em revisão só têm a automação aplicada **após** aprovação humana.
- **D-02:** Mesmo no auto-aplica, as garantias de segurança NÃO são puladas: log-antes-de-agir e undo continuam valendo. O que o auto-aplica dispensa é o clique humano de confirmação para os de alta confiança.
- **D-03:** Aplicação disponível **por documento E por lote/execução** (espelha o undo de AUT-05, que é por-doc e por-lote).

### Regras condicionais (TPL-02)
- **D-04:** O usuário expressa regras como **condições estruturadas `{campo} [operador] valor`** (operadores: =, >, <, contém; combináveis com E/OU) → **qual automação aplicar**. Cobre tipo/cliente/emissor/valor (ex.: "tipo == holerite E valor > 3000 → pasta Análise").
- **D-05:** **Precedência por ordem de prioridade**: regras ordenadas pelo usuário; a **primeira que casar vence**. Simples de entender e depurar; o usuário controla a ordem.

### Padrões de nome e pasta (AUT-01/AUT-02)
- **D-06:** Padrões usam tokens `{campo}` referenciando os campos extraídos (ex.: `{cliente}_{numero}_{data}.pdf`, `Documentos/{cliente}/{ano-mes}/`).
- **D-07:** **Campo vazio/inválido no padrão → bloqueia e manda pra revisão humana** (não aplica nome incompleto). Mesmo um documento de alta confiança é **rebaixado para revisão** se faltar um campo usado no nome/pasta. Evita arquivos com nome quebrado.
- **D-08:** O sistema **sanitiza automaticamente** caracteres inválidos no Windows (`\ / : * ? " < > |`) e **formata datas** via sufixo no token (ex.: `{data:aaaa-mm}`). O usuário não precisa se preocupar com isso.

### Política de colisão (AUT-04)
- **D-09:** Destino já ocupado por arquivo de **conteúdo DIFERENTE** (mesmo nome) → **sufixo incremental automático** (`nome_1.pdf`, `nome_2.pdf`). Nunca sobrescreve, não trava o fluxo, nada se perde; a colisão é registrada no log/dry-run.
- **D-10:** Destino já ocupado por arquivo de **conteúdo IDÊNTICO** (mesmo SHA-256 do CAS) → **considera já-feito e pula como duplicata** (não cria `_1` de cópias idênticas). Reusa o dedup por hash já existente.

### Arquivo físico de destino (resolução da Open Q1 do research — 2026-06-17)
- **D-11:** A operação **materializa o destino a partir do CAS** (`cas.read_bytes(content_hash)` → escreve no destino + verifica hash), em vez de mover o arquivo original da pasta. Comportamento **uniforme** para blocos de PDF separado (que só existem no CAS) e para documentos não-separados; intrinsecamente seguro (o CAS é a fonte da verdade). AUT-06 passa a ser "materializar do CAS + verificar hash" (cross-device deixa de ser um caso especial, pois nunca se "move" o original — escreve-se do CAS). O **caminho de origem resolvido é persistido no `AuditLog`** no momento da aplicação (não se reconstrói depois), resolvendo o risco A2 do research. Política sobre o arquivo original na pasta de origem (manter/quarentenar/remover) é decisão do plan.

### Claude's Discretion
- Comportamento detalhado do **undo quando o arquivo de destino já foi movido/renomeado/apagado pelo usuário** depois da automação (resolver com checagem de integridade + falha controlada, sem corromper estado). O planejador define a abordagem mais robusta.
- **Formato/estrutura do audit log** (extensão do modelo `AuditLog` existente para guardar origem→destino + dados de undo) — o planejador modela.
- **Onde a automação aparece na UI**: nova aba de Automações (padrões + regras condicionais) + tela de dry-run/preview com pares origem→destino e colisões sinalizadas. Honra o design system travado (mesmos tokens das fases 2/4/5).
- Mecânica cross-device (AUT-06): copia→verifica(hash)→remove a origem — implementação determinada pelo planejador (o CAS já dá a base de verificação por hash).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisitos e roadmap
- `.planning/REQUIREMENTS.md` §AUT-01..AUT-06, §TPL-02 — requisitos travados da fase (renomear, mover, dry-run, anti-colisão+log, undo, cross-device, regras condicionais).
- `.planning/ROADMAP.md` §"Phase 6" — goal + 6 critérios de sucesso (o que deve ser VERDADE).

### Decisões de produto relevantes
- `.planning/PROJECT.md` — "web é gestão/triagem, não manuseio de documento; sem visualizador" (correção de campo = corrigir o dado que a automação usa); Windows é plataforma primária (NTFS/atomicidade/cross-device); "Integridade de arquivos: reversível, nunca causar perda".
- `.planning/phases/04-templates-sub-templates-e-classifica-o/04-CONTEXT.md` — re-escopo de TPL-02 (sub-templates → regras condicionais de automação; o que variava era a automação, não a extração/campos).
- `.planning/phases/05-confian-a-revis-o-humana-e-quarentena/05-CONTEXT.md` — `review_confidence_threshold` e o estado EM_REVISAO que governam o "auto-aplica para alta confiança" (D-01).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/models/audit_log.py` — modelo `AuditLog` (document_id, action, details, created_at) JÁ existe, porém **mínimo**; precisa estender para registrar origem→destino e os dados necessários ao undo (AUT-04/AUT-05).
- `backend/app/storage/cas.py` — CAS imutável por SHA-256: o **conteúdo original está preservado para sempre** (rede de segurança independente do arquivo físico do cliente) e dá a base de verificação por hash para cross-device (AUT-06) e dedup de colisão (D-10).
- `backend/app/models/document.py` + `ingested_original.py` — vínculo `documento → original` (`origin_original_id`) carrega o caminho/pasta de origem do arquivo físico a renomear/mover.
- `backend/app/models/enums.py` (`DocState`) + máquina de estados/`transition` — a automação roda sobre documentos classificados/aprovados; D-07 (campo faltante) usa o roteamento para EM_REVISAO da Fase 5.
- `backend/app/validation/fields.py` — normalização de campos (data/moeda/cnpj) reutilizável para formatar tokens do nome (D-08) e avaliar condições numéricas das regras (D-04).

### Established Patterns
- Stages idempotentes com **commit atômico único** (extract/classify): a automação deve seguir o mesmo padrão (escrever audit-intent + executar + marcar, sem janelas inconsistentes).
- Migrações **somente via Alembic** (próxima seria 0006); nada de create_all.
- API fina espelhando `watched_folders.py`/`templates` (In/Patch/Out, 409 duplicado, 422 inválido) para os endpoints de automações/regras.
- Frontend token-driven (TanStack Query + polling sem flicker + design system `--st-*`/`--surface-*` travado) — a tela de dry-run e a aba de Automações reusam esses padrões.

### Integration Points
- Fila/worker: a automação é um novo **step** no pipeline (após classify/aprovação), despachado pelo worker — seguir o padrão de `classify_stage`/dispatch.
- Limiar da Fase 5 (`review_confidence_threshold`) é a fronteira do "auto-aplica para alta confiança" (D-01).

</code_context>

<specifics>
## Specific Ideas

- Exemplos de padrão citados pelo usuário/roadmap: `{cliente}_{numero}_{data}.pdf`, `Documentos/{cliente}/{ano-mes}/`.
- Exemplo de regra condicional: "nota fiscal do cliente Y → pasta Documentos"; "holerite > R$ 3.000 → pasta Análise".

</specifics>

<deferred>
## Deferred Ideas

- Automações além de renomear/mover (chamar API, enviar por e-mail/WhatsApp) — explicitamente fora do v1 (PROJECT.md "Não-objetivos").
- Separação de documentos dirigida por IA e roteamento determinístico de custo (boleto/NF-e sem IA) — Fase 7.

</deferred>

---

*Phase: 6-Automações de Arquivo (Renomear/Mover)*
*Context gathered: 2026-06-17*

# Phase 3: Extração Genérica via IA e Medição de Tokens - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 3-Extração Genérica via IA e Medição de Tokens
**Areas discussed:** Contrato de campos + validações, Caminho nativo vs IA (custo), Destino após extração, Licença lib PDF

---

## Contrato de campos + validações

### Representação dos campos antes do builder (Fase 4)

| Option | Description | Selected |
|--------|-------------|----------|
| Modelo schema-first já agora | Criar o modelo de template/campos + derivação de JSON Schema nesta fase | ✓ (inicialmente) |
| Definição provisória mínima | Field-set fixo/seed só para a Fase 3 rodar | |
| Extração livre (sem schema) | IA devolve pares chave→valor sem schema definido | |

**User's choice:** Inicialmente "schema-first já agora" — porém **reinterpretado em seguida** pelo usuário (ver Notes).

### Tipos de campo no v1

| Option | Description | Selected |
|--------|-------------|----------|
| Conjunto pragmático | texto, número, data, valor, CNPJ/CPF, booleano | |
| Mínimo | texto, número, data | |
| Você decide | A critério do planejamento | ✓ |

### O que as validações fazem nesta fase

| Option | Description | Selected |
|--------|-------------|----------|
| Aplicar e marcar válido/inválido | Validação pós-extração (formato + domínio) por campo | ✓ |
| Só formato/tipo no v1 | Sem checagens de domínio (DV de CNPJ) | |
| Você decide | A critério do planejamento | |

**Notes:** O usuário corrigiu o modelo mental de templates: a extração deve ser **genérica primeiro** (a IA extrai os dados que encontrar), e **templates são construídos a partir dos dados extraídos** (Fase 4) para identificar o tipo do documento (pela presença de certos dados) e buscar valores específicos. Consequência: o modelo de template/campos, o schema derivado de template e as validações de campo configuráveis (EXT-04) **migram para a Fase 4**. As respostas de "tipos de campo" e "validações" foram desconsideradas no novo enquadramento (são conceitos de template/Fase 4). O usuário também destacou que o template serve para **evitar custo** (padrão conhecido → extração local sem IA), o que é a visão das Fases 4 + 7.

---

## Caminho nativo vs IA (custo)

| Option | Description | Selected |
|--------|-------------|----------|
| Mandar texto à IA, não imagem | Texto nativo → IA como texto (barato); escaneado → visão | ✓ (interpretado/travado) |
| Texto nativo resolve sem IA nenhuma | Estruturar localmente sem IA | |
| Sempre visão (render) | Ignora nativo | |

**User's choice:** Sem opção selecionada; nota livre confirmando a lógica de custo. Travado por interpretação: **PDF com texto nativo → texto à IA (barato); escaneado/imagem → render + visão**.
**Notes:** "Se já tivermos um layout para um documento e conseguirmos identificar os dados antes de enviar para a IA é melhor, pq aí temos custo 0. No caso de PDF que conseguimos extrair local, podemos criar padrões para buscar os dados, evitando enviar texto para a IA." → o custo-zero por layout conhecido é Fases 4+7; a alavanca *dentro* da Fase 3 é texto-vs-imagem à IA. A Fase 3 persiste texto nativo + resultado para alimentar a criação de padrões.

---

## Destino após extração

### Sucesso

| Option | Description | Selected |
|--------|-------------|----------|
| PROCESSANDO + marcador 'extraído' | Aguarda classificação Fase 4; nunca CONCLUIDO | ✓ |
| Vai a CONCLUIDO | Marca como concluído após extrair | |

### Falha

| Option | Description | Selected |
|--------|-------------|----------|
| FALHA após esgotar retries | Retry/backoff da fila; esgotou → FALHA (re-tentável) | ✓ |
| Quarentena já na Fase 3 | Falhas para QUARENTENA com motivo | |
| Você decide | A critério do planejamento | |

**User's choice:** Sucesso → `PROCESSANDO`/`extraido`; Falha → `FALHA` após retries.
**Notes:** Quarentena visível/resolúvel e revisão humana são Fase 5; aqui só o estado terminal de falha, sem perder o documento (CAS preserva o original).

---

## Licença lib PDF

| Option | Description | Selected |
|--------|-------------|----------|
| Stack permissiva, sem PyMuPDF | pypdfium2 (BSD) + pdfplumber (MIT) | |
| Usar PyMuPDF + licença comercial | PyMuPDF AGPL + contrato Artifex | |
| Você decide | A critério do planejamento, sem AGPL no produto vendido | |

**User's choice:** Sem opção selecionada; nota livre redefinindo a premissa → **usar PyMuPDF**.
**Notes:** "Eu não vou vender o produto, irei usar internamente. Se puder, vamos usar ele para uso pessoal." Como o uso é interno/pessoal (sem distribuir/vender), a AGPL não impõe ônus → PyMuPDF liberado. Fallback permissivo documentado caso o uso mude. Esta fala diverge do PROJECT.md ("produto vendido") — registrada como premissa a confirmar num passo à parte.

---

## Claude's Discretion

- Estrutura do modelo `Extraction` e formato exato do schema genérico de saída (Pydantic → Structured Outputs).
- Tipos de campo (genérico na Fase 3; tipagem é Fase 4).
- Heurística "tem texto nativo suficiente" (texto vs render).
- Modelo OpenAI específico e parâmetros (confirmar vigente; família gpt-4o com visão + Structured Outputs).
- Granularidade de extração de bloco multi-página (sugestão: 1 chamada por Document).
- Enfileiramento/dispatch da extração por `step` e chave de idempotência (por hash do bloco).
- Tratamento de chave OpenAI ausente/inválida.

## Deferred Ideas

- Modelo de template/campos + schema derivado + validações configuráveis (EXT-04) → Fase 4.
- Identificação/classificação por presença de dados → Fase 4.
- Extração local custo-zero por layout + roteamento determinístico→nativo→IA (EXT-03/EXT-05) → Fase 7.
- Validações de domínio (DV CNPJ, datas) → Fase 4/5.
- Painel de consumo de tokens/custo na UI (INT2-02) → v2.
- Stack permissiva de PDF (pypdfium2/pdfplumber) — fallback se o uso mudar para venda.
- Premissa "uso interno" vs "produto vendido" — confirmar e possivelmente atualizar PROJECT.md/REQUIREMENTS (passo à parte; afeta Fase 8, LGPD, billing).
</content>

# Pitfalls Research

**Domain:** Processamento e organização automática de documentos fiscais BR (NF-e, boletos) com extração por IA (OpenAI) e automações de arquivo (renomear/mover) — produto single-tenant
**Researched:** 2026-06-15
**Confidence:** HIGH (estruturas BR e comportamento OpenAI verificados em fontes oficiais/atuais; armadilhas operacionais baseadas em padrões conhecidos do ecossistema de file watchers, filas e LLM-OCR)

---

## Critical Pitfalls

Erros que causam perda de dados do cliente, conta de tokens descontrolada, ou perda de confiança no produto. Para um produto cujo valor central é "nunca perder arquivos e não confiar cegamente na IA", estes são existenciais.

---

### Pitfall 1: Processar arquivo parcialmente escrito (race com a cópia/download)

**What goes wrong:**
O watcher (hot folder) dispara no primeiro evento de criação/modificação e o pipeline começa a ler um PDF que ainda está sendo copiado/baixado para a pasta. Resultado: PDF truncado, hash calculado sobre conteúdo incompleto (quebra a dedup), extração de IA sobre um documento parcial (paga tokens por lixo), e em alguns casos o arquivo é renomeado/movido enquanto o processo de origem ainda escreve nele — corrompendo o arquivo do cliente.

**Why it happens:**
`watchdog` (e o inotify/ReadDirectoryChangesW por baixo) emite múltiplos eventos `modified` durante a escrita de um arquivo grande e não há, de forma portável, um evento confiável de "terminou de escrever". `on_closed` existe mas só é confiável no backend inotify (Linux) e não dispara para arquivos movidos para dentro da pasta por `mv`/rename atômico. Devs assumem que "evento de criação = arquivo pronto".

**How to avoid:**
- Tratar o evento do watcher apenas como *gatilho de candidatura*, não como "pronto para processar".
- **Estabilização por quiescência:** só enfileirar quando `size` e `mtime` ficarem estáveis por N segundos (ex.: 2 polls de 1s sem mudança). Combinar com tentativa de lock exclusivo / abrir em modo `r+`/append-test no Windows para detectar lock do gravador.
- **Padrão pasta de staging:** orientar que ingestão por upload/CLI escreva primeiro em arquivo `.tmp`/`.partial` e faça rename atômico para o nome final — o watcher ignora qualquer extensão temporária.
- Em todos os modos de ingestão, calcular hash só após estabilização.

**Warning signs:**
PDFs que falham parsing intermitentemente; hashes diferentes para o "mesmo" arquivo entre execuções; chamadas à OpenAI com conteúdo vazio/cortado; reclamações de arquivo corrompido logo após drop na pasta.

**Phase to address:**
Fase de ingestão/watcher (early). Estabilização deve estar na primeira versão do watcher — não é polimento posterior.

---

### Pitfall 2: Operação de arquivo destrutiva — sobrescrita silenciosa e colisão de nomes

**What goes wrong:**
Dois documentos geram o mesmo nome alvo (ex.: dois boletos do mesmo cliente/mês, ou número de nota repetido entre emissores) e o `move`/`rename` sobrescreve silenciosamente o primeiro. Ou o destino é em outro volume/filesystem e `os.rename` falha no meio de um move (rename é atômico só dentro do mesmo filesystem); um copy+delete mal feito perde o arquivo se o processo morre entre as etapas.

**Why it happens:**
`shutil.move` / `os.replace` sobrescrevem o destino sem avisar. Templates de nome definidos pelo usuário quase nunca garantem unicidade. Devs testam com arquivos distintos e nunca veem a colisão. Cross-device move parece atômico mas não é.

**How to avoid:**
- **Nunca sobrescrever sem decisão explícita.** Antes de mover, checar existência do destino. Se existir: estratégia configurável (sufixo `_2`, `_v2`, ou enviar para quarentena/conflito) — *jamais* default silencioso.
- **Move seguro:** copy → fsync → verificar hash no destino → só então remover origem. Ou usar `os.replace` apenas quando comprovadamente mesmo filesystem; caso contrário copy+verify+delete.
- **Log de auditoria + undo é requisito v1 (já está no PROJECT.md):** registrar caminho origem, caminho destino, hash, timestamp ANTES de executar, e oferecer desfazer que reverte o move exato. Tratar o log como write-ahead (gravar intenção antes de agir).
- **Dry-run/preview** deve mostrar exatamente os pares origem→destino e sinalizar colisões em vermelho antes de aplicar.

**Warning signs:**
Contagem de arquivos de saída < entrada após um lote; usuário relata "sumiu um arquivo"; logs sem registro de undo possível; testes só com nomes únicos.

**Phase to address:**
Fase de automações (renomear/mover) — co-projetar com log/undo/dry-run desde o início; não tratar segurança de arquivo como feature separada posterior.

---

### Pitfall 3: Confiar cegamente na IA — alucinação de campos sem gate de confiança

**What goes wrong:**
A IA retorna um JSON bem formado e plausível mas com valores inventados (CNPJ que não existe no documento, valor lido errado em scan torto, data trocada). O sistema renomeia/move com base nisso. Pior: nomes de arquivo e estrutura de pastas ficam permanentemente errados, contaminando o arquivo organizado do cliente. JSON válido NÃO significa dado correto — Structured Outputs garante *formato*, não *veracidade*.

**Why it happens:**
Devs confundem "saída estruturada válida" com "extração confiável". Modelos de visão alucinam com confiança alta em imagens de baixa qualidade. Não há um score de confiança nativo confiável vindo da API para extração de visão.

**How to avoid:**
- **Validação determinística pós-extração como gate primário** (não a "confiança" auto-reportada pela IA, que é não-confiável):
  - CNPJ/CPF: validar dígitos verificadores.
  - Valor/data: validar formato e faixas plausíveis.
  - **NF-e:** se houver chave de acesso de 44 dígitos, validar DV (módulo 11 base 2-9) e *cross-check* dos campos embutidos na chave (UF, AAMM, CNPJ do emitente) contra os campos extraídos. A chave é fonte de verdade barata e exata.
  - **Boleto:** validar DVs dos campos (módulo 10) e DV geral do código de barras (módulo 11); derivar vencimento do fator de vencimento e valor do código de barras, comparando com o que a IA "leu".
- **Roteamento de confiança:** campo que passa em todas as validações determinísticas → auto-aplica. Qualquer falha de validação ou campo crítico ausente → **revisão humana obrigatória** antes de qualquer automação.
- Cross-field consistency: se a IA leu um valor e o código de barras diz outro, a fonte determinística vence e/ou força revisão.

**Warning signs:**
Campos "extraídos" que não batem com os dados embutidos na chave/código de barras; alta taxa de auto-aprovação sem revisão; nomes de arquivo com CNPJ/valores que não validam.

**Phase to address:**
Fase de extração/validação + fase de gate de confiança/revisão humana. O gate determinístico deve existir ANTES de qualquer automação ser ligada.

---

### Pitfall 4: Custo de tokens descontrolado (roteamento inexistente ou falho)

**What goes wrong:**
Tudo vai para a OpenAI: PDFs com texto nativo (que poderiam ser lidos local a custo zero), boletos/NF-e com dados determinísticos extraíveis sem IA, imagens em resolução desnecessariamente alta (custo de visão escala com tiles), e reprocessamento de arquivos já processados (dedup falha). Como a cobrança ao cliente é por consumo, custo descontrolado vira disputa de fatura e perda de confiança.

**Why it happens:**
É mais fácil mandar tudo pro modelo do que construir a cascata determinística-primeiro. Resolução de imagem não é otimizada. Caching de resultados por hash não é implementado ou é furado pela armadilha 1 (hash sobre arquivo parcial).

**How to avoid:**
- **Cascata explícita (já é decisão do PROJECT.md — garantir que seja implementada de fato):**
  1. PDF com texto nativo → extrair texto local (PyMuPDF/pdfplumber), sem IA.
  2. Boleto/NF-e → parsing determinístico de linha digitável/código de barras / chave / XML, sem IA.
  3. OCR local (Tesseract) para texto datilografado simples antes de recorrer a visão da IA — avaliar custo/qualidade.
  4. IA de visão **só** para o que sobrou (scans, imagens, layouts não estruturados).
- **Dedup por hash robusto** (após estabilização) com cache de resultado de extração: nunca reprocessar/recobrar o mesmo conteúdo.
- **Otimizar payload de visão:** redimensionar/comprimir imagem ao mínimo necessário; mandar só a(s) página(s) relevante(s), não o documento inteiro.
- **Orçamento/limite e medição por documento e por chave:** registrar tokens de prompt+completion por chamada, atrelado ao documento, para a cobrança e para alertar consumo anômalo.

**Warning signs:**
Tokens consumidos não caem ao adicionar PDFs com texto; mesmo arquivo aparece duas vezes na medição; custo por documento varia muito sem razão; fatura do cliente cresce sem aumento proporcional de documentos.

**Phase to address:**
Fase de roteamento de extração + fase de medição/dedup. Roteamento determinístico-primeiro é a alavanca de custo número 1 — deve ser core, não otimização tardia.

---

### Pitfall 5: Vazamento de dados fiscais sensíveis para a OpenAI sem controle/explicitação (LGPD)

**What goes wrong:**
Documentos fiscais (CNPJ, valores, partes, eventualmente CPF de pessoas físicas em algumas notas) são enviados à API da OpenAI sem o cliente saber exatamente o que sai da máquina. Por padrão, a API da OpenAI **não** treina com dados de API, mas **retém logs por até 30 dias para monitoramento de abuso** (Zero Data Retention só via acordo enterprise/aprovação). Isso é um fato que precisa ser explicitado ao cliente para conformidade LGPD; assumir "ZDR por padrão" é incorreto.

**Why it happens:**
Suposição de que API ≠ ChatGPT logo "não guarda nada". Falta de minimização: manda-se o documento inteiro quando só uma página/região era necessária. Falta de transparência ao cliente sobre o que é enviado.

**How to avoid:**
- **Minimização real:** só enviar à OpenAI o que a cascata determinística não resolveu, e só a região/página necessária. Tudo que for resolvido local nunca sai da máquina.
- **Transparência/explicabilidade:** registrar e poder mostrar ao cliente exatamente quais documentos/páginas foram enviados à OpenAI e quais foram processados 100% local. Isso é diferencial de confiança e suporte a LGPD.
- **Documentar a realidade da retenção** (30 dias, não usado para treino por padrão; ZDR opcional via enterprise) na documentação do produto; não prometer ZDR sem tê-lo contratado.
- Tratar a chave da OpenAI como segredo (nunca em log, nunca no frontend) — ver Pitfall 9.

**Warning signs:**
Nenhum registro de "o que foi enviado"; documentos com texto nativo ainda indo para a IA; cliente pergunta "onde meus dados vão?" e não há resposta precisa.

**Phase to address:**
Fase de roteamento/extração (minimização) e fase de auditoria/transparência. LGPD é "objetivo de evolução" no PROJECT.md, mas a *minimização* e o *registro do que sai* são baratos de fazer desde o v1 e caros de retrofitar.

---

### Pitfall 6: Fila sem idempotência e retry mal feito — duplicação de cobrança e de ações

**What goes wrong:**
O worker reprocessa um item após crash/retry e (a) chama a OpenAI de novo (cobra duas vezes) e (b) executa o move/rename de novo (em arquivo que já foi movido → erro ou ação sobre arquivo errado). Rate limit (429) da OpenAI sem backoff adequado vira tempestade de retries que estoura ainda mais o limite.

**Why it happens:**
Jobs sem chave de idempotência. Estado do documento não persistido entre etapas (extraído ≠ automação aplicada). Retry com backoff fixo/sem jitter em cima de 429.

**How to avoid:**
- **Máquina de estados por documento** persistida: `ingerido → estabilizado → extraído → validado → (revisão) → automação aplicada → concluído/quarentena`. Cada transição é idempotente e não repete a anterior.
- **Idempotência por hash do conteúdo + etapa:** resultado de extração em cache; automação só roda se estado != aplicada.
- **Backoff exponencial com jitter e respeito ao header de rate limit** da OpenAI; limite de concorrência configurável; dead-letter para itens que falham N vezes (vão para quarentena, não somem).
- Separar claramente "falha de extração" (re-tentar) de "falha de automação" (não re-extrair; só re-aplicar a automação).

**Warning signs:**
Tokens cobrados em duplicidade para o mesmo doc; logs com a mesma automação aplicada 2x; picos de 429 em rajada; itens "presos" sem dead-letter.

**Phase to address:**
Fase de fila/worker assíncrono. Idempotência e máquina de estados devem ser projetadas junto com a fila, não adicionadas depois.

---

### Pitfall 7: Parsing BR ingênuo — não validar dígitos verificadores / confundir DANFE com XML

**What goes wrong:**
Aceita-se uma "chave de acesso" de 44 dígitos lida por OCR sem validar o DV → chave errada vira nome/pasta errado. Ou trata-se o **DANFE** (a representação impressa/PDF da nota, para conferência visual) como se fosse a NF-e — quando o documento fiscal válido é o **XML**. Linha digitável de boleto lida com 1 dígito errado passa se o DV não for checado.

**Why it happens:**
Subestima-se a riqueza determinística do domínio BR. OCR introduz erros de 1 dígito que parecem corretos. Confusão conceitual DANFE×XML é comum em quem não é do domínio fiscal.

**How to avoid:**
- **NF-e:** chave = 44 dígitos com estrutura conhecida (UF[2] + AAMM[4] + CNPJ[14] + modelo[2] + série[3] + número[9] + tipo emissão[1] + código numérico[8] + DV[1]). Validar DV por módulo 11 (base 2-9). Se houver XML disponível, ele é a fonte de verdade — preferir XML ao DANFE/PDF sempre que existir.
- **Boleto:** linha digitável de 47 dígitos em 5 campos; 3 primeiros campos com DV módulo 10, DV geral módulo 11; fator de vencimento = dias desde 07/10/1997. Validar todos os DVs antes de confiar; recalcular valor/vencimento a partir do código de barras e comparar.
- Tratar valores que falham DV como sinal forte de erro de OCR → revisão humana.

**Warning signs:**
Chaves/linhas que não passam DV sendo aceitas; pastas nomeadas a partir de DANFE quando XML existia; vencimentos/valores divergentes entre o que a IA leu e o que o código de barras decodifica.

**Phase to address:**
Fase de parsing determinístico BR. Implementar validadores de DV como biblioteca testada com casos reais antes de plugar na cascata.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Mandar todo documento direto pra IA (sem cascata determinística) | Pipeline funciona em 1 dia | Custo de tokens 5-20x maior, disputa de fatura, vazamento desnecessário à OpenAI | Nunca — é a proposta de valor central; protótipo descartável só |
| Move com `shutil.move` sem checar destino | Código simples | Sobrescrita silenciosa = perda de arquivo do cliente = produto perde a razão de existir | Nunca |
| Watcher processa no primeiro evento (sem estabilização) | Menos código | Arquivos parciais, hashes errados, corrupção | Nunca em produção; ok em demo com upload manual |
| Sem máquina de estados (reprocessa do zero a cada retry) | Worker mais simples | Cobrança dupla, automações repetidas | Só pré-MVP sem cobrança ativa |
| Confiar no "confidence" auto-reportado da IA como gate | Não precisa escrever validadores | Alucinação confiante passa direto | Nunca como gate único; ok como sinal secundário |
| Guardar chave OpenAI em arquivo de config versionável/plaintext acessível | Fácil de configurar | Vazamento de credencial = consumo/custo de terceiros na conta do cliente | Nunca |
| Log de undo gravado *depois* da ação | Menos código | Crash entre ação e log = ação não-reversível | Nunca — log é write-ahead |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenAI Vision/Responses API | Mandar imagem em resolução máxima e documento inteiro | Redimensionar ao mínimo legível, mandar só página/região relevante; custo de visão escala com tiles |
| OpenAI Structured Outputs (JSON Schema) | Assumir que schema válido = dado correto | Schema garante formato; veracidade exige validação determinística (DVs, faixas, cross-check) |
| OpenAI rate limits | Retry imediato/fixo em 429 | Backoff exponencial + jitter, respeitar `retry-after`, limite de concorrência |
| OpenAI data retention | Assumir ZDR por padrão | Padrão = 30 dias de logs p/ abuso, sem treino; ZDR só via enterprise — documentar p/ LGPD |
| `watchdog` / inotify | Confiar em evento único = arquivo pronto | Estabilização por quiescência (size+mtime) + staging com rename atômico |
| Filesystem `os.rename`/`shutil.move` | Assumir atomicidade cross-device | Atômico só no mesmo FS; cross-device = copy+fsync+verify+delete |
| Parsing XML de NF-e | Tratar DANFE/PDF como fonte de verdade | XML é o documento fiscal; preferir XML quando existe |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Processamento síncrono na request HTTP | UI trava, timeouts em lotes | Fila assíncrona desde o início (já no escopo) | Já em lotes de dezenas de docs |
| Concorrência ilimitada contra a OpenAI | Rajada de 429, custo errático | Pool de workers com limite configurável + rate limiter | Centenas de docs num lote |
| Polling/estabilização caro em pasta com milhares de arquivos | CPU/IO alto, atraso na ingestão | Debounce por arquivo, fila de candidatos, não re-escanear tudo | Pastas com milhares de arquivos legados |
| Carregar PDF inteiro em memória para separar páginas | Pico de RAM, OOM em PDFs grandes | Processar página a página com lib streaming (PyMuPDF) | PDFs de centenas de páginas / scans grandes |
| Cache de extração inexistente | Reprocessa/recobra arquivos reaparecendo na pasta | Dedup por hash + cache de resultado | Reprocessamento de pastas / re-drops |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Chave OpenAI em frontend, log, ou config versionável | Vazamento → consumo de terceiros, custo na conta do cliente | Backend-only, em secret/env ou cofre local; nunca em resposta de API nem log |
| Enviar documentos resolvíveis localmente à OpenAI | Exposição desnecessária de dado fiscal (LGPD) | Minimização via cascata; só sobe o que precisa |
| App web servindo em `0.0.0.0` sem auth na máquina do cliente | Qualquer um na rede acessa documentos fiscais | Default bind em `127.0.0.1`; se servidor, exigir auth/reverse proxy e documentar |
| Path traversal nos templates de nome/pasta | Usuário (ou dado extraído) com `../` move arquivo p/ fora da raiz permitida | Sanitizar componentes de nome; confinar destino a raiz configurada; rejeitar separadores/`..` |
| Não tratar conteúdo extraído como não-confiável ao montar caminhos | CNPJ/nome alucinado com caracteres inválidos quebra/escapa o FS | Sanitização + whitelist de caracteres em nomes derivados de extração |
| Sem isolamento entre instâncias (assumir single-tenant = sem segurança) | Em servidor compartilhado, dados de um cliente acessíveis | Single-tenant não dispensa auth/isolamento quando exposto além de localhost |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Aplicar automações sem dry-run obrigatório na primeira vez | Usuário descobre erro depois de centenas de arquivos movidos | Dry-run/preview por padrão até o usuário "confiar" no template |
| Quarentena que parece "erro/sumiço" em vez de fila de revisão | Usuário acha que perdeu arquivo | Quarentena visível, com motivo claro e ação de resolver |
| Não mostrar *por que* a IA pediu revisão | Usuário não sabe o que conferir | Destacar campos que falharam validação e a fonte (IA vs determinístico) |
| Undo escondido ou só do último item | Usuário não consegue reverter um lote ruim | Undo por documento e por lote/execução, com log navegável |
| Mostrar "confiança da IA" como número sem significado | Falsa sensação de segurança | Mostrar resultado das validações determinísticas (passou/falhou), não score opaco |
| Construtor de template sem teste contra documento real | Template parece certo, falha em produção | "Testar template" contra um doc de exemplo antes de salvar |

## "Looks Done But Isn't" Checklist

- [ ] **Watcher:** parece funcionar com upload manual — verificar com cópia de arquivo grande/lento e com drop de muitos arquivos de uma vez (estabilização).
- [ ] **Move/rename:** funciona com nomes únicos — verificar colisão de destino, cross-device, e crash no meio do move (origem preservada?).
- [ ] **Dedup:** funciona no caminho feliz — verificar hash sobre arquivo parcial (não pode), e mesmo conteúdo com nome diferente.
- [ ] **Extração IA:** retorna JSON válido — verificar valores contra DV da chave/código de barras; injetar scan torto/baixa qualidade e ver se vai para revisão.
- [ ] **Parsing BR:** lê a linha/chave — verificar que rejeita DV inválido (erro de 1 dígito de OCR) em vez de aceitar.
- [ ] **NF-e:** lê o documento — verificar que prefere XML ao DANFE quando ambos existem.
- [ ] **Fila/retry:** processa lote — verificar reprocessamento após crash (não recobra OpenAI, não re-move).
- [ ] **Undo:** botão existe — verificar que reverte o move/rename exato mesmo após restart do app.
- [ ] **Custo:** medição mostra tokens — verificar que PDF com texto nativo gera 0 tokens de IA.
- [ ] **LGPD/transparência:** verificar registro do que foi enviado à OpenAI vs processado local.
- [ ] **Chave OpenAI:** verificar que não aparece em log, resposta de API nem config versionada.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Arquivo movido/renomeado errado | LOW (se undo+log existem) | Usar log de auditoria para reverter o move exato; reprocessar com correção |
| Arquivo sobrescrito (sem proteção de colisão) | HIGH | Provavelmente irrecuperável sem backup — por isso prevenir é obrigatório |
| Cobrança dupla por reprocessamento | MEDIUM | Reconciliar pela medição por hash+etapa; creditar cliente; corrigir idempotência |
| Dados sensíveis enviados desnecessariamente à OpenAI | MEDIUM | Não revogável (logs 30d); ajustar minimização daqui pra frente; comunicar ao cliente |
| Pasta organizada com nomes alucinados | MEDIUM-HIGH | Reverter via undo/log; re-extrair com gate determinístico ligado |
| Fila travada por 429 em rajada | LOW | Drenar dead-letter, aplicar backoff, reduzir concorrência, reprocessar |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Arquivo parcialmente escrito | Ingestão/Watcher | Teste com cópia lenta de arquivo grande e drop em massa |
| Move destrutivo / colisão | Automações (renomear/mover) + Auditoria/Undo | Teste de colisão, cross-device, crash no meio do move |
| Alucinação sem gate de confiança | Extração/Validação + Revisão humana | Scan ruim → vai para revisão; valores batem com DV/código de barras |
| Custo de tokens descontrolado | Roteamento de extração + Medição/Dedup | PDF com texto nativo = 0 tokens; sem reprocessamento de duplicata |
| Vazamento LGPD à OpenAI | Roteamento (minimização) + Auditoria/Transparência | Registro do que saiu; resolvíveis localmente não saem |
| Fila sem idempotência | Fila/Worker assíncrono | Crash+retry não recobra nem re-move |
| Parsing BR ingênuo (DV/DANFE×XML) | Parsing determinístico BR | Rejeita DV inválido; prefere XML ao DANFE |
| Chave OpenAI exposta / path traversal | Configuração/Segurança (transversal) | Grep por chave em logs; teste de `..` em template de nome |

## Sources

- [Estrutura linha digitável boleto 47 dígitos / DV módulo 10 e 11 / fator de vencimento — Efí](https://sejaefi.com.br/blog/campos-dos-boletos-linha-digitavel)
- [Validação de linha digitável de boletos (referência de cálculo de DV)](https://github.com/rruy/validacao-linha-digitavel-boletos-ruby/blob/master/README.md)
- [Composição da chave de acesso NF-e 44 dígitos / DV módulo 11 — TecnoSpeed](https://blog.tecnospeed.com.br/chave-de-acesso/)
- [Como é formada a chave de acesso da NF-e (UF/AAMM/CNPJ/modelo/série/número/DV)](https://focusnfe.com.br/blog/como-e-formada-a-chave-de-acesso-de-nf-e-nfc-e-ct-e-e-mdf-e/)
- [Data controls in the OpenAI platform (retenção 30 dias, sem treino por padrão, ZDR via enterprise)](https://platform.openai.com/docs/guides/your-data)
- [OpenAI API Compliance / Zero-Retention checklist 2026 — Janus Compliance](https://www.januscompliance.co.uk/blog/gdpr-compliant-chatgpt-api-setup-guide-2026)
- [watchdog: múltiplos eventos modified em arquivos grandes / problema de detectar fim de escrita (issue #309)](https://github.com/gorakhargosh/watchdog/issues/309)
- [Mastering File System Monitoring with Watchdog (on_closed, padrões de estabilização)](https://dev.to/devasservice/mastering-file-system-monitoring-with-watchdog-in-python-483c)
- Conhecimento de domínio: idempotência de filas, backoff/jitter em rate limits, atomicidade de rename cross-device, sanitização de path traversal (padrões estabelecidos do ecossistema)

---
*Pitfalls research for: processamento de documentos fiscais BR com IA + automações de arquivo (single-tenant)*
*Researched: 2026-06-15*

# Auditoria de Copy do Frontend — base para refatoração de copywriting

Data: 2026-06-26
Objetivo: catalogar TODO o texto de interface voltado ao usuário para embasar uma refatoração que deixe o sistema didático para um usuário LEIGO (não-técnico) e GENÉRICO (qualquer tipo de documento; nota fiscal é só exemplo).

Convenções de classificação:
- **[JARGÃO]** termo técnico que leigo não entende (template, sinais, matcher, quarentena, ingestão, dedup, CAS, normalizado, regex, limiar, watcher, dry-run, fallback, pipeline, token, anchor, etc.)
- **[FISCAL]** exemplo/placeholder acoplado a nota fiscal / DANFE / CNPJ / NF / emitente que deveria ser neutro
- **[CONFUSO]** verboso, ambíguo ou pouco didático
- **[OK]** já claro

Arquivos auditados: `App.tsx`, `components/{StatusPill,Sidebar,Header,ConfidenceBadge}.tsx`, `data/mock.ts`, `pages/{DocumentsPage,AttentionPage,TemplatesPage,AutomationsPage,DryRunPage,ConfigPage}.tsx`.

---

## 1. App.tsx — títulos/descrições das páginas (PAGE_META)

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| App.tsx:16 | "Documentos" / "Arquivos encontrados e tratados pelo watcher" | [JARGÃO] | "watcher" é técnico; leigo não sabe o que é. |
| App.tsx:17-20 | "Precisam de atenção" / "Documentos que pararam por falha, quarentena ou baixa confiança" | [JARGÃO] | "quarentena" e "baixa confiança" são jargão interno. |
| App.tsx:21 | "Templates" / "Modelos de extração de dados por tipo de documento" | [JARGÃO] | "Templates" e "extração" são técnicos. |
| App.tsx:22 | "Automações" / "Ações executadas após o tratamento dos documentos" | [CONFUSO] | "tratamento" é vago. |
| App.tsx:23 | "Pré-visualização das automações" / "Confira origem → destino antes de aplicar" | [OK] | Clara; "aplicar" aceitável. |
| App.tsx:24 | "Configurações" / "Pastas monitoradas, regras, leitura e integrações" | [OK] | Aceitável. |

Observação: o nome interno de localStorage `docwatch-theme` (App.tsx:28,46) não é visível ao usuário — fora de escopo.

## 2. components/Sidebar.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| Sidebar.tsx:25 | "OPERAÇÃO" (título de grupo) | [OK] | — |
| Sidebar.tsx:27 | nav "Documentos" | [OK] | — |
| Sidebar.tsx:28 | nav "Precisam de atenção" | [OK] | — |
| Sidebar.tsx:31 | "PROCESSAMENTO" (grupo) | [OK] | Aceitável. |
| Sidebar.tsx:33 | nav "Templates" | [JARGÃO] | Termo técnico no menu principal. |
| Sidebar.tsx:34 | nav "Automações" | [OK]/[JARGÃO leve] | Conhecido o bastante; manter. |
| Sidebar.tsx:35 | nav "Pré-visualização" | [OK] | — |
| Sidebar.tsx:38 | "SISTEMA" / "Configurações" | [OK] | — |
| Sidebar.tsx:71 | "DocWatch" (marca) | [OK] | Nome do produto. |
| Sidebar.tsx:72 | "Gestão documental" (subtítulo) | [OK] | — |
| Sidebar.tsx:101 | "Watcher ativo" / "Watcher inativo" | [JARGÃO] | "Watcher" exposto ao usuário no rodapé. |
| Sidebar.tsx:53 | "verificando…" | [OK] | — |
| Sidebar.tsx:58 | "{n} pastas · varredura há X min" | [OK] | "varredura" tolerável; ver glossário. |

## 3. components/Header.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| Header.tsx:30 | placeholder "Buscar documento, pasta…" | [OK] | — (campo desabilitado, "em breve"). |
| Header.tsx:31,39 | title "em breve" | [OK] | — |
| Header.tsx:35 | title "Alternar tema" | [OK] | — |

## 4. components/StatusPill.tsx — rótulos de status (alta visibilidade)

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| StatusPill.tsx:20 | "Na fila" (recebido) | [OK] | — |
| StatusPill.tsx:21 | "Processando" | [OK] | — |
| StatusPill.tsx:22 | "Em revisão" (em_revisao) | [JARGÃO leve]/[CONFUSO] | Leigo não sabe que precisa AGIR; "Aguardando sua conferência" seria mais claro. |
| StatusPill.tsx:23 | "Concluído" | [OK] | — |
| StatusPill.tsx:24 | "Quarentena" | [JARGÃO] | Termo técnico forte; usuário não entende. |
| StatusPill.tsx:25 | "Falha" | [OK]/[CONFUSO] | "Falha" seco; ok. |
| StatusPill.tsx:32 | "Aguardando extração" | [JARGÃO] | "extração" é técnico (= ler os dados). |
| StatusPill.tsx:40 | "Classificado — pronto" | [JARGÃO] | "Classificado" técnico; "Pronto" bastaria. |

## 5. components/ConfidenceBadge.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| ConfidenceBadge.tsx:23-25 | "Alta" / "Média" / "Baixa" (+ "{pct}%") | [OK]/[CONFUSO] | "confiança" como conceito precisa de contexto, mas labels ok. |

## 6. data/mock.ts (Regras de separação e Integrações — telas "em breve")

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| mock.ts:10 | "Por marcador QR Code" / "Divide o lote sempre que detecta um QR Code de separação na página." | [CONFUSO] | "lote" e "separação" técnico; tela futura. |
| mock.ts:11 | "Por número de páginas" / "Cria um novo documento a cada N páginas do PDF de origem." | [OK] | — |
| mock.ts:12 | "Por texto âncora" / "Inicia um novo documento ao encontrar um texto-chave no topo da página." | [JARGÃO] | "texto âncora" é jargão. |
| mock.ts:12 | param '"NOTA FISCAL"' | [FISCAL] | Exemplo de âncora fixado em nota fiscal. |
| mock.ts:13 | "Por página em branco" / "sens. 98%" | [JARGÃO leve] | "sens." abreviação obscura. |

## 7. pages/DocumentsPage.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| DocumentsPage.tsx:35 | stat "Na fila" / "aguardando processamento" | [OK] | — |
| :36 | stat "Processando" / "ingestão / separação" | [JARGÃO] | "ingestão" é termo interno. |
| :37 | stat "Concluídos" / "prontos / arquivados" | [OK] | — |
| :38 | stat "Falhas" / "requerem atenção" | [OK] | — |
| :135-138 | chips "Todos / Na fila / Processando / Falha" | [OK] | — |
| :191 | title "Remover os documentos selecionados da lista (não apaga arquivos)" | [OK] | Bom: tranquiliza. |
| :196 | botão "Remover (N)" / "Removendo…" | [OK] | — |
| :203 | title "Forçar uma varredura das pastas monitoradas agora" | [CONFUSO] | "Forçar varredura" é técnico/agressivo. |
| :206 | botão "Forçar varredura" / "Varrendo…" | [JARGÃO]/[CONFUSO] | "Varredura" pouco amigável; "Procurar novos arquivos agora" seria claro. |
| :99-100 | toast "N novos enfileirados, N pulados por já existirem" | [JARGÃO] | "enfileirados" técnico. |
| :244-248 | th "Arquivo / Pasta de origem / Status / Tamanho / Data" | [OK] | — |
| :273,276 | erro "Não foi possível carregar os documentos." / "Verifique se o serviço está em execução e tente novamente." | [CONFUSO] | "serviço está em execução" é linguagem de TI. (repete em várias telas) |
| :292-296 | vazio "Nenhum documento ainda" / "...aparecem aqui automaticamente quando arquivos chegam nas pastas monitoradas. Configure uma pasta em Configurações → Pastas monitoradas." | [OK] | Didático. |
| :351 | title "Conferir origem → destino antes de aplicar" / botão "Pré-visualizar" | [OK] | — |
| :353,359 | botão "Aprovar" / title "Aplicar as automações configuradas a este documento" | [OK] | — |
| :379 | "Mostrando N de M documentos" | [OK] | — |
| :384 | "Atualizando…" | [OK] | — |
| :391-393 | "N duplicados ignorados" / title "Arquivos com conteúdo idêntico a documentos já ingeridos não são reprocessados." | [JARGÃO] | "duplicados"/"ingeridos" técnico; aceitável mas pode melhorar. |
| :513 | modal "Classificação" (título) | [JARGÃO] | "Classificação" técnico. |
| :528 | "Carregando classificação…" | [JARGÃO] | idem. |
| :535-536 | "Não foi possível carregar a classificação. Verifique se o serviço está em execução." | [JARGÃO]/[CONFUSO] | idem. |
| :547,550 | "Aguardando classificação" / "Este documento ainda não foi classificado." | [JARGÃO] | "classificado" técnico. |
| :560 | label "Template" | [JARGÃO] | — |
| :569 | pílula "Quarentena" | [JARGÃO] | — |
| :571-574 | "Nenhum template casou com este documento. Ele fica em quarentena e nunca é descartado." | [JARGÃO] | "template casou" e "quarentena" — frase chave a reescrever. |
| :587 | "Campos extraídos" | [JARGÃO leve] | "extraídos" técnico; aceitável. |
| :594-597 | th "Campo / Valor / Normalizado / Marca" | [JARGÃO] | "Normalizado" e "Marca" obscuros para leigo. |
| :608,617 | badge "válido" / "inválido" | [OK] | — |
| :642 | "Operações aplicadas" | [CONFUSO] | "Operações" frio; "O que foi feito com o arquivo". |
| :647 | "Cópia" / "Movido" | [OK] | — |
| :667-669 | "Reverter para a origem? O arquivo volta para a pasta original (restaurado do armazenamento interno) e o documento reabre para reprocessamento." | [JARGÃO] | "armazenamento interno" e "reprocessamento" técnicos. |
| :679 | "Revertendo…" / "Confirmar reversão" | [OK] | — |
| :683-684 | "Não foi possível reverter. Tente novamente." | [OK] | — |
| :693 | title "Desfazer as operações deste documento e devolver o arquivo à origem" / botão "Reverter para a origem" | [OK] | Clara. |
| :421-426 | modal "Remover N documentos da lista?" / "Isto remove apenas o registro no aplicativo — os arquivos originais NÃO são apagados nem movidos. Se um arquivo ainda estiver numa pasta monitorada, ele pode ser reprocessado numa próxima varredura." | [JARGÃO leve] | "reprocessado"/"varredura"; mensagem boa no geral. |
| :435,442 | "Manter" / "Remover" / "Removendo…" | [OK] | — |

## 8. pages/AttentionPage.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| AttentionPage.tsx:27 | balde "Falhas" / "erro no processamento" | [OK] | — |
| :28 | balde "Quarentena" / "nenhum template casou" | [JARGÃO] | "Quarentena" + "template casou" — duplo jargão. |
| :29 | balde "Em revisão" / "confiança baixa ou campo inválido" | [JARGÃO] | "campo inválido" técnico. |
| :33-35 | vazios "Nenhuma falha pendente." / "Nada em quarentena." / "Nada aguardando revisão." | [JARGÃO leve] | "quarentena". |
| :115-118 | erro "Não foi possível carregar os documentos." / "Verifique se o serviço está em execução..." | [CONFUSO] | linguagem TI (repetido). |
| :129,139-140 | vazio "Tudo em dia" / "Nenhum documento precisa de atenção agora. Documentos com falha, em quarentena ou com baixa confiança aparecem aqui automaticamente." | [JARGÃO leve] | "quarentena". |
| :213 | "Editou os templates? Reprocesse {a quarentena/a revisão} para reaplicar a classificação." | [JARGÃO] | "templates", "reprocesse", "classificação". |
| :222-223 | confirm "Reprocessar toda a revisão vai re-rodar a classificação e DESCARTAR as correções manuais dos documentos. Continuar?" | [JARGÃO]/[CONFUSO] | "re-rodar a classificação". |
| :224 | confirm "Reprocessar todos os documentos d{a quarentena/a revisão}?" | [JARGÃO] | "Reprocessar". |
| :230 | botão "Reprocessar todos" / "Reprocessando…" | [JARGÃO] | — |
| :263-264 | erro "Não foi possível concluir a ação. Tente novamente." | [OK] | — |
| :281 | botão "Tentar de novo" / "Reenviando…" | [OK] | — |
| :315 | confirm "Reprocessar este documento?" | [JARGÃO] | — |
| :321 | botão "Reprocessar" / "Reprocessando…" | [JARGÃO] | — |
| :325 | label "Atribuir template" | [JARGÃO] | — |
| :332 | option "Escolha um template…" | [JARGÃO] | — |
| :348 | botão "Reclassificar" / "Reclassificando…" | [JARGÃO] | termo técnico forte. |
| :369 | label "Confiança" | [CONFUSO] | precisa de contexto p/ leigo. |
| :376 | "Campos extraídos" | [JARGÃO leve] | — |
| :381-384 | th "Campo / Valor / Normalizado / Marca" | [JARGÃO] | "Normalizado"/"Marca". |
| :400-401 | "Corrija os campos obrigatórios inválidos antes de aprovar o documento." | [OK] | — |
| :411 | confirm "Reprocessar vai re-rodar a classificação e DESCARTAR as correções manuais feitas neste documento. Continuar?" | [JARGÃO] | — |
| :412 | confirm "Reprocessar vai re-rodar a classificação deste documento. Continuar?" | [JARGÃO] | — |
| :428 | botão "Aprovar documento" / "Aprovando…" | [OK] | — |
| :465 | botão "Salvar correção" / "Salvando…" | [OK] | — |
| :484,490 | badge "corrigido manualmente" | [OK] | — |

## 9. pages/TemplatesPage.tsx (maior concentração de jargão + fiscal)

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| TemplatesPage.tsx:22-29 | tipos de campo: texto/número/data/moeda/CPF-CNPJ/booleano | [JARGÃO leve] | "booleano" é técnico (vs "sim/não"). |
| :248 | título "Templates de documento" | [JARGÃO] | "Templates". |
| :249-252 | "Defina um tipo de documento: como reconhecê-lo (Passo 1, sem IA) e o que extrair (Passo 2, com IA)." | [JARGÃO] | "extrair" técnico; "Passo X sem/com IA" exige contexto. |
| :256 | botão "Novo template" | [JARGÃO] | — |
| :266 | "Nome do template" / "Editar template" | [JARGÃO] | — |
| :269-273 | tip "Como este tipo aparece no app (ex.: Holerite, Nota Fiscal). É também o nome que você seleciona nas automações." | [FISCAL leve]/[OK] | Holerite + Nota Fiscal — pelo menos varia; ok mas "Nota Fiscal" recorrente. |
| :278 | placeholder "ex.: Nota Fiscal, Nota Fiscal — TryLab" | [FISCAL] | Exemplo 100% fiscal + emissor "TryLab". |
| :288 | "Como reconhecer este tipo" + tag "sem IA" | [OK] | Boa reformulação de "sinais". |
| :291-296 | tip "Passo 1 — sem IA, de graça. O sistema procura estes sinais no texto do documento. Bateu na lógica abaixo → é deste tipo. Em dúvida → vai para revisão humana (nada se perde)." | [JARGÃO] | "sinais", "bateu na lógica". |
| :299-300 | "O documento é deste tipo se bater em qualquer grupo (OU); dentro do grupo, todas as condições (E)." | [JARGÃO]/[CONFUSO] | lógica booleana E/OU exposta crua ao leigo. |
| :304-314 | tip "Cada condição é uma busca no documento: contém o texto = procura essa palavra/frase dentro do documento (ex.: DANFE, ou o nome TryLab). corresponde ao padrão (regex) = um 'molde' para formatos que variam. Ex.: \d{44} casa qualquer chave de 44 dígitos... Dica: um template geral usa âncoras como DANFE; um template por cliente adiciona o CNPJ ou o nome do cliente." | [JARGÃO]/[FISCAL] | "regex", "âncoras", "casa"; exemplos DANFE/chave 44 dígitos/CNPJ — fortemente fiscal. |
| :321 | "Grupo {n} — todas (E)" | [JARGÃO] | lógica E exposta. |
| :335-336 | option "contém o texto" / "corresponde ao padrão (regex)" | [JARGÃO] | "regex". |
| :341-343 | placeholder regex "cole o regex, ex.: \d{44}" / texto "ex.: NOTA FISCAL ELETRÔNICA, TryLab" | [JARGÃO]/[FISCAL] | "regex" + exemplo "NOTA FISCAL ELETRÔNICA" + emissor "TryLab". |
| :351 | title/aria "Remover condição" | [OK] | — |
| :360 | link "+ E — adicionar condição" | [JARGÃO] | "+ E". |
| :368 | link "+ OU — adicionar grupo" | [JARGÃO] | "+ OU". |
| :379 | "O que extrair" + tag "com IA" | [JARGÃO leve] | "extrair". |
| :382-386 | tip "Passo 2 — com IA. A IA lê o documento inteiro e preenche os campos. O nome do campo descreve o dado que você quer (ex.: Emitente, Número da NF)..." | [FISCAL] | exemplos "Emitente", "Número da NF". |
| :389 | "Liste os dados que você quer tirar do documento." | [OK] | Boa. |
| :393-403 | "Nome do campo — o dado que você quer" + tip com exemplo NF da TryLab: Emitente→TryLab, CNPJ do emitente→12.345..., Número da NF→000123456, Valor total→R$ 1.234,56 | [FISCAL] | Exemplo inteiro é uma nota fiscal da "TryLab". |
| :407,410-413 | "Tipo" + tip "Valida e normaliza o formato: data, moeda, CPF/CNPJ, número, texto, sim/não." | [JARGÃO leve]/[FISCAL leve] | "normaliza"; CPF/CNPJ ok como tipo genérico. |
| :417,420-424 | "Obrig." + tip "Se marcado e a IA não encontrar o dado, o documento vai para revisão humana em vez de seguir." | [OK] | Clara. |
| :434 | placeholder campo "ex.: Emitente, Número da NF, Valor total" | [FISCAL] | 100% fiscal. |
| :458 | title ⚙ "Avançado: regex de validação e dica para a IA" | [JARGÃO] | "regex". |
| :479-488 | "Validação por regex — opcional" + tip "Regra extra de formato... Cole um regex... Ex.: \d{2}/\d{4} (mês/ano)... O tipo já valida o básico..." | [JARGÃO] | "regex" repetido. |
| :493 | placeholder "cole o regex, ex.: \d{2}/\d{4}" | [JARGÃO] | "regex". |
| :499-507 | "Dica para a IA — opcional" + tip "Texto livre para orientar a IA onde/como achar o dado. Ex.: 'o valor após Total da nota' ou 'o nome no topo, em maiúsculas'." | [FISCAL leve] | "Total da nota". |
| :512 | placeholder "ex.: o valor após 'Total da nota'" | [FISCAL] | "Total da nota". |
| :537,543-544 | "Descartar template" / "Descartar alterações" / "Salvar template" / "Salvar alterações" | [JARGÃO] | "template". |
| :196,200,203 | erro de form "Informe o nome do template." / "Adicione ao menos um campo ao template." / "Informe o nome do campo." | [JARGÃO] | "template". |
| :226 | erro "Não foi possível salvar o template. Confira os dados e tente novamente." | [JARGÃO] | — |
| :567-570 | erro "Não foi possível carregar os templates." / "Verifique se o serviço está em execução..." | [JARGÃO]/[CONFUSO] | — |
| :583-597 | vazio "Nenhum template ainda" / "Crie um template declarando como reconhecer o tipo (sinais) e os campos a extrair. O sistema usa os templates para classificar e preencher cada documento automaticamente." | [JARGÃO] | "template", "sinais", "extrair", "classificar". |
| :617-619 | card "N grupos de sinais" / "Sem sinais" | [JARGÃO] | "sinais". |
| :643 | "CAMPOS EXTRAÍDOS" | [JARGÃO leve] | — |
| :655,660 | "N campos" / "N sinais" | [JARGÃO] | "sinais". |
| :626,633 | title "Editar template" / "Remover template" | [JARGÃO] | — |
| :685-691 | modal "Remover template" / "Remover o template «X»? Os documentos já classificados por ele permanecem; novos documentos deixarão de casar com este template." | [JARGÃO] | "template", "casar". |
| :699 | "Manter template" | [JARGÃO] | — |
| :729-733 | "Salve o template para liberar a ferramenta Testar sinais (enviar um PDF de teste e ver quais sinais casam ou falham)." | [JARGÃO] | "template", "sinais", "casam". |
| :740 | "Testar sinais" (título painel) | [JARGÃO] | — |
| :741-744 | "Envie um PDF de teste (texto nativo) para conferir quais grupos e sinais casam ou falham — sem IA e sem custo. Use para diagnosticar por que um documento não casou." | [JARGÃO] | "texto nativo", "sinais casam", "diagnosticar", "não casou". |
| :751 | aria "PDF de teste para testar os sinais" | [JARGÃO] | "sinais". |
| :759 | botão "Testar sinais" / "Testando…" | [JARGÃO] | — |
| :764-765 | erro "Não foi possível testar os sinais. Confira se o arquivo é um PDF válido e tente novamente." | [JARGÃO] | "sinais". |
| :781-783 | "Este documento parece escaneado; o teste de sinais só funciona com PDF de texto nativo. Na ingestão real, a IA cuida de escaneados." | [JARGÃO] | "sinais", "texto nativo", "ingestão". |
| :788-794 | "✓ O documento casa este template." / "✗ Nenhum grupo casou — o documento não casaria este template." | [JARGÃO] | "casa template". |
| :799-800 | "Este template não tem sinais definidos." | [JARGÃO] | — |
| :807-814 | "Grupo {n} — casa (todas as condições) / não casa" | [JARGÃO] | "casa". |
| :834,837-839 | "regex" / "texto" / "— encontrado" / "— não encontrado" | [JARGÃO] | "regex". |

## 10. pages/AutomationsPage.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| AutomationsPage.tsx:38-54 | campos de condição: "Pasta de origem / Tipo de arquivo / Tipo de documento / Valor de campo / Nome do arquivo / Tamanho" | [OK] | Boa tradução (note: "Tipo de documento" = template, bem disfarçado). |
| :57-68 | operadores "é / contém / > / <" | [OK] | — |
| :77-79 | ações "Renomear / Mover / Copiar" | [OK] | — |
| :148 | "Nova automação" (nome default) | [OK] | — |
| :565 | erro "Informe o nome da automação." | [OK] | — |
| :573-575 | erro "Na condição 'Tipo de documento', escolha um template." | [JARGÃO] | vaza "template" na mensagem (UI usa "Tipo de documento"). |
| :578-581 | erro "Na condição 'Valor de campo', escolha um template na condição 'Tipo de documento'..." | [JARGÃO] | "template". |
| :588 | erro "Adicione ao menos uma ação (Renomear ou Mover)." | [OK] | — |
| :590-598 | erros "Em 'Renomear', defina o padrão do nome." / "Em 'Mover', defina a pasta de destino." / idem Copiar | [OK] | — |
| :350 | "Sem condições — roda para qualquer documento" | [OK] | — |
| :703-705 | nochip "Adicione a condição «Tipo de documento» para usar os campos do template como tokens." | [JARGÃO] | "tokens", "template". |
| :718-720 | "Campos do template X — clique para inserir:" | [JARGÃO leve] | "template". |
| :724 | "Esse template ainda não tem campos." | [JARGÃO leve] | — |
| :777 | "Prévia:" | [OK] | — |
| :878 | "Escolha um template na condição «Tipo de documento» para comparar um campo." | [JARGÃO] | "template". |
| :1039,1044-1047 | label "Padrão do nome" / "Pasta de destino — aceita com ou sem aspas" | [CONFUSO] | "Padrão do nome" técnico. |
| :1052 | placeholder rename "{cliente}_{numero}" | [FISCAL leve]/[OK] | genérico-ish ({cliente},{numero}); aceitável mas é "cliente/numero". |
| :1052 | placeholder move "Documentos/{cliente}/{data}/" | [OK] | genérico. |
| :1059-1074 | hint rename longo: "{campo} é trocado pelo valor lido do documento... A extensão do arquivo é mantida... Exemplo: {Nome_Emitente}_{Numero_NF} vira IGUACU DIST_000.001.137.pdf... filtros: {fornecedor:maiusc:palavras=2}, {cliente:sem_acento}, {data:formato=aaaa-mm-dd}." | [FISCAL]/[JARGÃO] | exemplos Nome_Emitente/Numero_NF/IGUACU DIST/fornecedor — fiscal; "filtros" técnico. |
| :1077-1083 | hint move: "Cole o caminho como vier do Windows... Caminhos absolutos (C:\…, \\servidor\…) vão exatamente para onde você indicar. Use filtros nos campos, ex.: C:\NOTAS\{fornecedor:maiusc:palavras=1}." | [FISCAL]/[JARGÃO] | "C:\NOTAS\{fornecedor...}"; "filtros". |
| :1087 | "O original permanece onde está — uma cópia é criada no destino." | [OK] | — |
| :1100-1104 | desc "Quando um documento bate nas condições, a automação executa suas ações (renomear/mover), na ordem definida. As automações são avaliadas de cima para baixo — a primeira cujas condições casam vence." | [JARGÃO leve]/[CONFUSO] | "bate"/"casam vence" — pode simplificar. |
| :1122-1125 | erro "Não foi possível carregar." / "Verifique se o servidor está rodando e tente de novo." | [CONFUSO] | "servidor rodando" linguagem TI. |
| :1147 | "Minhas automações" | [OK] | — |
| :1155 | "Nenhuma automação ainda. Crie a primeira abaixo." | [OK] | — |
| :1193,1195 | "Sem nome" / "(nova)" | [OK] | — |
| :1243-1248 | "Selecione ou crie uma automação" / "Cada automação define quando rodar (condições) e o que fazer (renomear/mover)." | [OK] | — |
| :1281,1286 | "Ativa" / "Pausada" / title "Pausar/Ativar automação" | [OK] | — |
| :1307-1313 | tag "Quando rodar" + "Condições" + "O documento precisa atender a TODAS as condições (E) para esta automação rodar." | [JARGÃO leve] | "(E)" exposto; resto bom. |
| :1354-1359 | tag "O que fazer" + "Ações" + "Executadas em ordem, de cima para baixo. Arraste ⠿ para reordenar." | [OK] | — |
| :1364 | "Nenhuma ação ainda — adicione Renomear e/ou Mover abaixo." | [OK] | — |
| :1443,1449 | "Alterações não salvas" / "Descartar" / "Excluir" / "Salvar automação" | [OK] | — |
| :1485-1489 | modal "Excluir automação" / "Excluir a automação «X»? As demais automações continuam valendo. Documentos já tratados não são afetados." | [OK] | — |
| :965 | title "Arraste para reordenar" | [OK] | — |
| :1006-1029 | aria/title "Mover ação para cima/baixo" / "Remover ação" | [OK] | — |

## 11. pages/DryRunPage.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| DryRunPage.tsx:25-28 | badge "Campo faltando — enviado para revisão" / title "Campo usado no nome/pasta está faltando ou inválido. Enviado para revisão antes de aplicar." | [OK] | Clara. |
| :33-38 | badge "Nenhuma automação se aplica — mantido na origem" / title idem | [OK] | — |
| :44-49 | badge "Já existe (idêntico) — pulado" / title "Esse arquivo já existe no destino (conteúdo idêntico) — será pulado." | [OK] | — |
| :55-60 | badge "Renomeado p/ evitar colisão" / title "...será salvo com sufixo (ex.: nome_1)." | [CONFUSO] | "colisão" técnico; title ok. |
| :66-71 | badge "Copiado — original mantido" / title idem | [OK] | — |
| :77-81 | badge "Pronto" / title "O documento está pronto para ser movido/renomeado conforme o pipeline." | [JARGÃO] | "pipeline" no title. |
| :195-199 | título "Pré-visualização das automações" / "Confira origem → destino de cada documento antes de aplicar. Nada é movido até você confirmar — e toda aplicação pode ser desfeita." | [OK] | Excelente copy de confiança. |
| :203 | botão "Atualizar prévia" / "Atualizando…" | [OK] | — |
| :222-225 | banner "Modo de aprovação ligado — as automações aguardam você. Aprovar aplica a automação (move/renomeia); Negar deixa o documento pronto sem mover — o arquivo não é tocado." | [OK] | Clara. |
| :234,241,248,255 | stat "Prontos" / "Duplicatas puladas" / "Sem automação" / "Bloqueados → revisão" | [JARGÃO leve] | "Duplicatas", "Bloqueados". |
| :266-269 | "N selecionado(s)" / "N documento(s) prontos" | [OK] | — |
| :277,287-291 | botões "Aplicar selecionados" / "Aplicar automações" / "Aplicando…" + titles | [OK] | — |
| :309-312 | th "Origem / Destino / Situação / Ações" | [OK] | — |
| :329-334 | erro "Não foi possível carregar." / "Verifique se o servidor está rodando e tente de novo." | [CONFUSO] | linguagem TI. |
| :348-354 | vazio "Nenhum documento pronto para automação" / "Documentos de alta confiança são aplicados automaticamente; os demais aguardam revisão." | [CONFUSO] | "alta confiança" precisa contexto. |
| :398-409 | botões "Aprovar" / "Negar / Pular" + titles longos | [OK] | titles claros. |
| :433-435 | "Último lote aplicado pode ser revertido." | [JARGÃO leve] | "lote". |
| :439-440 | botão/title "Desfazer aplicação do último lote" | [JARGÃO leve] | "lote". |
| :173 | sucesso undo "Desfeito. O arquivo voltou ao local de origem." | [OK] | — |
| :177-179 | erro undo "O arquivo de destino não foi encontrado no lugar esperado. Restauramos a cópia íntegra preservada pelo sistema para a pasta de origem." | [OK] | Boa (tranquiliza). |
| :477-481 | confirm undo "Os arquivos movidos deste lote voltam ao local de origem (se o destino tiver sumido, restauramos a cópia íntegra preservada pelo sistema). As cópias criadas são apagadas do destino — o original nunca é tocado. Nenhum arquivo se perde." | [JARGÃO leve]/[OK] | "lote"; conteúdo excelente. |
| :492,495 | "Manter como está" / "Fechar" / "Desfazer aplicação" / "Desfazendo…" | [OK] | — |

## 12. pages/ConfigPage.tsx

| Local | Texto atual | Classif. | Problema |
|---|---|---|---|
| ConfigPage.tsx:38-41 | abas "Pastas monitoradas / Regras de separação / Leitura de dados / Integrações" | [OK] | — |
| :60-61 | "Em breve — disponível na versão 2." | [OK] | — |
| :75,427 | badge "em breve" | [OK] | — |
| :168-173 | título "Pastas monitoradas" / "O watcher varre estas pastas em busca de novos documentos e os envia para a fila de processamento conforme a regra de separação definida por pasta." | [JARGÃO] | "watcher", "fila de processamento". |
| :177 | botão "Adicionar pasta" | [OK] | — |
| :184 | "Adicionar pasta" / "Editar pasta" | [OK] | — |
| :188 | label "Caminho da pasta" | [OK] | — |
| :192 | placeholder "C:\Documentos\Entrada" | [OK] | genérico. |
| :199 | label "Separar a cada N páginas" | [OK] | — |
| :205 | placeholder "Não separar" | [OK] | — |
| :209-212 | hint "Cada bloco de N páginas vira um documento independente. Deixe vazio (ou 0) em 'Não separar' para tratar o arquivo inteiro como um documento." | [OK] | Clara. |
| :230 | label switch "Separar fisicamente o PDF em arquivos na pasta" | [CONFUSO] | "fisicamente" técnico. |
| :232-237 | hint "Quando ligado, ao chegar um PDF a separação acontece NA PRÓPRIA PASTA: o PDF é dividido em arquivos (substituindo o original) antes do processamento. O arquivo original continua recuperável — nada é perdido. Depende de 'Separar a cada N páginas' estar configurado." | [CONFUSO] | longo/denso; "substituindo o original". |
| :269-272 | "Watcher global" / "monitora as pastas ativas continuamente" | [JARGÃO] | "Watcher". |
| :274 | title "Ativar/desativar watcher" | [JARGÃO] | — |
| :280 | "Carregando pastas…" | [OK] | — |
| :286-287 | erro "Não foi possível carregar as pastas. Verifique se o serviço está em execução." | [CONFUSO] | TI. |
| :297-299 | vazio "Nenhuma pasta monitorada" / "Adicione uma pasta para o sistema começar a ingerir documentos automaticamente." | [JARGÃO leve] | "ingerir". |
| :312-319 | meta "Separar a cada N páginas / Ativa / Inativa / Separa em arquivos" | [OK] | — |
| :323-330 | title "Ativar/desativar pasta" / "Editar pasta" / "Remover pasta" | [OK] | — |
| :357-361 | modal "Remover pasta" / "Remover X do monitoramento? Os documentos já ingeridos permanecem; apenas o monitoramento desta pasta para." | [JARGÃO leve] | "ingeridos". |
| :393-394 | "Regras de separação" / "Definem como um PDF de várias páginas é dividido em documentos individuais antes da leitura. Aplicadas em ordem de prioridade." | [OK] | (tela "em breve"). |
| :440 | "Leitura e extração de dados" | [JARGÃO leve] | "extração". |
| :446-447 | "Motor de OCR" / "Engine usado quando o PDF não possui texto nativo" | [JARGÃO] | "OCR", "Engine", "texto nativo" (tela mock em breve). |
| :461-462 | "Idioma principal" / "Dicionário usado na correção de leitura" | [OK] | — |
| :473-476 | "Confiança mínima" / "Abaixo deste valor o campo é marcado para revisão manual" | [CONFUSO] | "Confiança" precisa contexto (mock). |
| :489-492 | "Corrigir inclinação (deskew)" / "Endireita páginas digitalizadas antes do OCR" | [JARGÃO] | "deskew", "OCR" (mock). |
| :500-504 | "Remoção de ruído" / "Limpa manchas e pontos de digitalizações antigas" | [OK] | (mock). |
| :554-562 | "Automações aguardam minha aprovação" / "Quando ligado, as automações ficam pendentes na Pré-visualização para você aprovar ou negar — nada é movido sozinho. Quando desligado, documentos de alta confiança são aplicados automaticamente (a trava de confiança continua valendo). Padrão: desligado." | [CONFUSO] | "alta confiança"/"trava de confiança" exige contexto; no geral boa. |
| :629-634 | "IA classifica quando nenhum template casa" / "Quando ligado, cada documento que nenhum template reconhecer gera 1 chamada de IA (custo por token). Padrão: desligado." | [JARGÃO] | "template casa", "chamada de IA", "custo por token". |
| :706-711 | "Limiar de confiança" / "Documentos com confiança abaixo deste valor, ou com qualquer campo obrigatório inválido, vão para revisão." | [JARGÃO] | "Limiar" é a palavra mais técnica do app. |
| :698 | erro "Não foi possível salvar o limiar. Tente novamente." | [JARGÃO] | "limiar". |
| :692 | erro "Informe um valor entre 0 e 100." | [OK] | — |
| :715,720-723 | "Carregando limiar…" / "Não foi possível carregar o limiar..." | [JARGÃO] | "limiar". |
| :741,747 | aria "Limiar de confiança em porcentagem" / botão "Salvar limiar" | [JARGÃO] | "limiar". |
| :762-763 | "Integrações" / "Destinos e serviços conectados para onde os documentos tratados são enviados." | [OK] | (mock). |
| :773 | badge "Indisponível" | [OK] | — |

---

## RESUMO 1 — GLOSSÁRIO de termos técnicos recorrentes (sugestões a DECIDIR, não decididas)

| Termo técnico atual | Onde aparece | Sugestão para leigo (propor) |
|---|---|---|
| **template** | Sidebar, Templates*, Automações, Documentos, Atenção | "tipo de documento" / "modelo de documento" |
| **sinais** | TemplatesPage (todo o Passo 1) | "pistas" / "como reconhecer" / "marcas de identificação" |
| **casar / casou / matcher** | Templates, Atenção, Config | "reconhecer" / "bater com" / "identificar como" |
| **quarentena** | StatusPill, Documentos, Atenção | "não identificado" / "tipo desconhecido" / "separado para conferir" |
| **em revisão** | StatusPill, Atenção | "aguardando sua conferência" / "para revisar" |
| **classificação / classificar / classificado** | Documentos, Atenção, Config | "identificação" / "reconhecer o tipo" / "identificado" |
| **extrair / extração / campos extraídos** | Templates, Config, modal | "ler dados" / "dados lidos" / "informações capturadas" |
| **normalizado / normaliza** | tabelas de campos | "valor padronizado" / "formatado" |
| **Marca** (coluna) | tabelas de campos | "Situação" / "Conferência" / "OK?" |
| **regex / padrão (regex)** | TemplatesPage | "padrão avançado" / "molde de texto (avançado)" — manter "regex" só em modo avançado |
| **ingestão / ingerir / enfileirar** | Documentos, Config | "receber" / "entrar na fila" / "começar a processar" |
| **watcher** | Sidebar, Config, App | "monitor de pastas" / "vigia de pastas" / "monitoramento" |
| **varredura / forçar varredura** | Documentos, Sidebar | "procurar novos arquivos (agora)" / "última verificação" |
| **dry-run / pré-visualização** | Sidebar, DryRun, App | "pré-visualização" (já adotado) / "ver antes de aplicar" / "ensaio" |
| **limiar / limiar de confiança / threshold** | ConfigPage | "nível mínimo de certeza" / "confiança mínima para aplicar sozinho" |
| **confiança / score** | ConfidenceBadge, Atenção, Config | "certeza da leitura" / "quão certo a IA está" |
| **fallback (IA)** | ConfigPage | "usar IA quando não reconhecer" (já reescrito; só não chamar de fallback) |
| **token** ({campo}) | AutomationsPage | "campo" / "etiqueta de campo" / "{campo} = valor lido" |
| **filtros** (maiusc/palavras=...) | AutomationsPage | "transformações" / "ajustes do texto" |
| **pipeline** | DryRun title, StatusPill | remover; falar "conforme as automações" |
| **lote / run** | DryRun | "última aplicação" / "este grupo" |
| **colisão** | DryRun badge | "nome repetido" / "já existe um arquivo com esse nome" |
| **duplicata / duplicado** | Documentos, DryRun | "arquivo repetido" / "igual a um já recebido" |
| **booleano** | TemplatesPage tipo de campo | "sim/não" |
| **texto nativo / escaneado** | TemplatesPage teste | "PDF que já tem texto" vs "PDF de imagem/foto" |
| **operações aplicadas** | modal Documentos | "o que foi feito com o arquivo" |
| **reprocessar / re-rodar** | Atenção | "tentar identificar de novo" / "rodar de novo" |
| **serviço está em execução / servidor rodando** | erros em todas as telas | "o aplicativo está aberto/ligado" |

## RESUMO 2 — Exemplos FISCAIS embutidos no copy (precisam virar neutros)

1. **TemplatesPage.tsx:278** — placeholder do nome: `"ex.: Nota Fiscal, Nota Fiscal — TryLab"` (fiscal + emissor real "TryLab").
2. **TemplatesPage.tsx:304-314** — tip dos sinais: exemplos `DANFE`, `\d{44}` ("chave de 44 dígitos"), `CNPJ`, nome `TryLab`.
3. **TemplatesPage.tsx:343** — placeholder de condição texto: `"ex.: NOTA FISCAL ELETRÔNICA, TryLab"`.
4. **TemplatesPage.tsx:393-403** — tip "Nome do campo": exemplo inteiro é uma NF da TryLab (Emitente→TryLab, CNPJ do emitente→12.345.678/0001-99, Número da NF→000123456, Valor total→R$ 1.234,56).
5. **TemplatesPage.tsx:382-386** — tip Passo 2: exemplos "Emitente", "Número da NF".
6. **TemplatesPage.tsx:434** — placeholder de campo: `"ex.: Emitente, Número da NF, Valor total"`.
7. **TemplatesPage.tsx:499-512** — "Dica para a IA": exemplo `"o valor após 'Total da nota'"`.
8. **AutomationsPage.tsx:1052** — placeholder rename `{cliente}_{numero}` (cliente/numero; semi-fiscal).
9. **AutomationsPage.tsx:1059-1074** — hint rename: `{Nome_Emitente}_{Numero_NF}` → `IGUACU DIST_000.001.137.pdf`; filtros com `{fornecedor...}`.
10. **AutomationsPage.tsx:1077-1083** — hint move: `C:\NOTAS\{fornecedor:maiusc:palavras=1}` (pasta "NOTAS" + "fornecedor").
11. **data/mock.ts:12** — regra "Por texto âncora", param `"NOTA FISCAL"` (tela "em breve").
12. (Aceitáveis mas recorrentes) Tip do nome do template usa "Holerite, Nota Fiscal" (TemplatesPage:271) — pelo menos varia o tipo; manter variedade.

Sugestão de neutralização: usar exemplos de domínios variados e rotativos — ex.: "Contrato", "Recibo", "Currículo", "Boleto", "Holerite", "Relatório", com campos genéricos ("Nome", "Data", "Valor", "Número do documento"). Evitar emissores reais (TryLab, IGUACU DIST).

## RESUMO 3 — Contagem por página (visão de esforço)

Aproximada (strings de UI relevantes; [OK] inclui as já claras). Strings podem ter mais de uma classificação.

| Página/arquivo | [JARGÃO] | [FISCAL] | [CONFUSO] | [OK] | Total aprox. |
|---|---|---|---|---|---|
| App.tsx (PAGE_META) | 3 | 0 | 1 | 2 | 6 |
| Sidebar.tsx | 2 | 0 | 0 | 9 | 11 |
| Header.tsx | 0 | 0 | 0 | 3 | 3 |
| StatusPill.tsx | 4 | 0 | 1 | 4 | 8 |
| ConfidenceBadge.tsx | 0 | 0 | 1 | 1 | 2 |
| data/mock.ts | 2 | 1 | 1 | 2 | 5 |
| DocumentsPage.tsx | 12 | 0 | 4 | 16 | ~30 |
| AttentionPage.tsx | 14 | 0 | 2 | 8 | ~22 |
| TemplatesPage.tsx | 28 | 7 | 2 | 12 | ~45 |
| AutomationsPage.tsx | 6 | 3 | 4 | 22 | ~32 |
| DryRunPage.tsx | 4 | 0 | 4 | 22 | ~30 |
| ConfigPage.tsx | 10 | 0 | 5 | 22 | ~35 |
| **TOTAL** | **~85** | **~11** | **~25** | **~123** | **~229** |

Maior esforço (ordem): **TemplatesPage** (jargão + todos os exemplos fiscais), **ConfigPage** (limiar/watcher/OCR/IA), **AttentionPage** (reprocessar/reclassificar/quarentena), **DocumentsPage** (modal de classificação/normalizado/marca).

Pontos já fortes (preservar tom): DryRunPage (copy de reversibilidade), confirmações destrutivas em geral ("nenhum arquivo se perde / é tocado"), estados vazios de Documentos.

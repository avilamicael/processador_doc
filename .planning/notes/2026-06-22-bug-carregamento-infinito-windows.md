# BUG: páginas com carregamento infinito no Windows (cliente piloto)

**Reportado:** 2026-06-22 — primeira instalação no Windows via release v0.1.0 (ZIP).
**Status:** investigado, NÃO reproduzido no Linux/WSL; hipótese principal identificada; aguarda evidência do Windows para confirmar antes de corrigir.

## Sintoma (relato do usuário)
Instalou no Windows pela release, acessou o `localhost`, e as páginas "parecem querer carregar mas não carregam — parecem buscar dados que não existem e ficam carregando infinitamente". Banco vazio (instalação nova).

## O que foi testado (Playwright, neste host Linux/WSL)
Subi a build **idêntica** (mesmo `frontend/dist` da release) servida pelo FastAPI single-origin, com um **DATA_DIR limpo / banco vazio** (igual a uma instalação nova), em `http://127.0.0.1:8001`.

- **API em banco vazio** — todos os endpoints respondem `200 application/json`:
  - `/health` → `{"status":"ok","db":"ok","version":"0.1.0"}`
  - `/documents` → `{"items":[],"counts":{...},"total":0}`
  - `/documents/duplicates-count`, `/watched-folders` `[]`, `/automations` `[]`, `/templates` `[]`
  - `/documents/attention` → baldes vazios; `/config/review-threshold` → `{"threshold":0.8}`
- **Frontend (navegador real, Playwright)** — TODAS as páginas renderizam o **estado vazio corretamente**, sem spinner infinito:
  - Documentos ("Nenhum documento ainda"), Precisam de atenção ("Tudo em dia"), Templates, Automações, Pré-visualização, Configurações.
  - **Console: 0 erros / 0 warnings** na sessão inteira.
  - Polling (documents + duplicates-count a cada ~4s) retorna 200 sem flicker.

➡️ **Conclusão: não reproduz no Linux.** O código do frontend/API está ok com banco vazio. O problema é **específico do ambiente Windows**.

## Evidência visual do Windows (prints enviados 2026-06-22)
Três prints confirmam **carregamento perpétuo**, NÃO estado vazio:
- **Documentos:** tabela travada em *skeleton* (barras cinzas) para sempre; cards "0" e "Mostrando 0 de 0" são apenas os **defaults exibidos durante o loading** (`?? 0`), não dados resolvidos.
- **Automações:** 3 caixas de *skeleton* travadas.
- **Configurações → Pastas monitoradas:** texto **"Carregando pastas…"** travado.

Diagnóstico refinado: o **shell estático carrega** (sidebar/layout/fontes OK = catch-all/StaticFiles serve), mas **TODAS as chamadas de lista da API ficam penduradas uniformemente** (`/documents`, `/automations`, `/watched-folders`). No Linux/WSL essas mesmas chamadas resolveram na hora (empty states corretos). Logo: diferença de **ambiente/conexão**, não bug de página. As duas hipóteses abaixo explicam isso; o teste `127.0.0.1` direto na barra de endereço as distingue.

### Teste discriminador (barra de endereço, sem frontend)
| URL | IPv6 (hipótese 1) | Event loop bloqueado (hipótese 2) |
|-----|-------------------|-----------------------------------|
| `http://127.0.0.1:8000/health` | responde na hora | trava |
| `http://localhost:8000/health` | trava | trava |

## Hipótese principal (mais provável + barata de confirmar)
**`localhost` (IPv6 `::1`) × uvicorn escutando só IPv4 `127.0.0.1`.**

- `instalar.ps1:118` e `atualizar.ps1:138` sobem `uvicorn ... --host 127.0.0.1` (somente IPv4).
- Porém o guia e as mensagens mandam abrir **`http://localhost:8000`** (`instalar.ps1:115`, `INSTALL-WINDOWS.md:5,100`, etc.).
- No Windows, `localhost` resolve primeiro para **`::1` (IPv6)**. Como o servidor não escuta em `::1`, a conexão pode ficar pendurada (quando o firewall/stack DROPa em vez de recusar) → requisições HTTP "pending" para sempre → **spinner infinito**. No Linux o fallback p/ IPv4 é imediato, por isso não aparece.

### Teste imediato que o usuário pode fazer (discrimina a hipótese)
Abrir **`http://127.0.0.1:8000`** (IP, não `localhost`) no Windows. Se carregar normal → hipótese confirmada.

### Correção candidata (quando confirmado)
- Trocar o bind do uvicorn para algo que cubra `localhost` no Windows. Opções:
  - `--host 127.0.0.1` **e** instruir o usuário a usar `http://127.0.0.1:8000` (alinhar guia + mensagens p/ o IP, não `localhost`); OU
  - bind dual-stack / `--host ::1` + IPv4, ou `--host 0.0.0.0` (IPv4 todas as interfaces) — avaliar implicação de expor em rede; preferir loopback.
- **Mínimo seguro:** alinhar TODAS as mensagens/guia para `http://127.0.0.1:8000` (já é onde o servidor escuta) — corrige sem mudar bind nem exposição de rede.

## Hipóteses secundárias (se o teste 127.0.0.1 NÃO resolver)
1. **Event loop bloqueado por SQLite síncrono no worker (Windows).** O worker (`queue/worker.py::_run_once`) chama `repo.claim_next(session)` de forma **síncrona dentro do loop async** (poll a cada 1s). Em `%ProgramData%` com disco lento/antivírus escaneando o `.db`, ou contenção de lock WAL no Windows, essas chamadas podem **travar o event loop** e segurar as respostas HTTP → loading infinito intermitente. Arquivos estáticos (leitura de arquivo) podem continuar servindo enquanto a API trava.
2. **WAL/permissões em `%ProgramData%\ProcessadorDocumentos`** — escrita do SQLite (WAL/-shm) bloqueada por ACL/antivírus.
3. **Catch-all SPA devolvendo `index.html` (HTML) para alguma rota de API inexistente na build** → `fetch` tenta parsear HTML como JSON → normalmente vira ERRO (não loading infinito), mas vale conferir no Network se alguma chamada volta `text/html`.

## Evidência a coletar no Windows (para fechar o diagnóstico)
No navegador, F12 → e mandar print de:
1. **Console** — há erros vermelhos? (CORS, mixed content, JSON parse, connection refused?)
2. **Network** — quais requisições ficam **(pending)** ou vermelhas? Status code, tempo, e `Content-Type` da resposta (JSON vs HTML).
3. Testar `http://127.0.0.1:8000/health` direto no navegador (deve mostrar o JSON).
4. Confirmar se foi acessado via `localhost` ou `127.0.0.1`.

## Arquivos relevantes
- `instalar.ps1` / `atualizar.ps1` — linha do `uvicorn --host` e mensagens "Abra http://localhost:8000".
- `INSTALL-WINDOWS.md` — instruções de acesso.
- `backend/app/main.py` — catch-all SPA + serve estático.
- `backend/app/queue/worker.py` — `_run_once`/`claim_next` síncrono no loop (hipótese secundária 1).

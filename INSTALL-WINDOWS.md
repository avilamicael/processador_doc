# Instalação no Windows — Processador de Documentos

Guia para instalar, configurar, acessar e atualizar o **Processador de
Documentos** no Windows. O sistema sobe o backend (API) e o frontend (interface)
num único processo, acessível pelo navegador em `http://localhost:8000`.

Há **dois fluxos** distintos:

- **[Fluxo A — Cliente (produção)](#fluxo-a--cliente-produção--sem-git-sem-node):**
  você recebeu um **pacote ZIP de release** (com a interface já buildada dentro).
  **Não precisa de Git nem de Node.**
- **[Fluxo B — Dev (gerar o pacote)](#fluxo-b--dev--gerar-o-pacote-de-release):**
  você desenvolve/publica o produto e precisa **gerar** o ZIP de release a partir
  do código-fonte (requer Node).

---

## Fluxo A — Cliente (produção) — sem Git, sem Node

Você recebeu o pacote `processador-doc-X.Y.Z.zip` (baixado da GitHub Release ou
entregue por outro meio). Ele **já traz o frontend buildado** (`frontend\dist`),
então o instalador **não builda nada** e você **não precisa de Node**.

### 1. Pré-requisitos

- **Windows** (10 ou 11).
- **PowerShell** (já vem no Windows).

Você **não precisa** instalar Python nem o `uv` manualmente: o `instalar.ps1`
cuida disso — instala o **Python 3.12** (via `winget`) e o **uv** (gerenciador de
pacotes) automaticamente se estiverem ausentes.

### 2. Baixar e extrair o pacote

1. Baixe o ZIP da última release em:

   ```
   https://github.com/avilamicael/processador_doc/releases/latest
   ```

2. **Extraia** o ZIP para uma pasta (ex.: `C:\ProcessadorDoc`).

### 3. Rodar o instalador (`instalar.ps1`)

1. Abra o **PowerShell** na pasta extraída (onde estão `instalar.ps1` e a pasta
   `backend`).
2. Execute:

   ```powershell
   .\instalar.ps1
   ```

3. Se o PowerShell **bloquear a execução de scripts**, libere a execução **apenas
   para esta sessão** (vale só até fechar a janela) e rode de novo:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\instalar.ps1
   ```

O `instalar.ps1` é **idempotente** (pode rodar de novo sem medo). Ele faz, em
ordem: garante Python 3.12 → garante o `uv` → instala as dependências
(`uv sync`) → cria `backend\.env` se faltar → **detecta que `frontend\dist` já
vem no pacote e PULA o build** (por isso não precisa de Node) → aplica o schema do
banco (`alembic upgrade head`) → sobe o servidor com **`uvicorn --workers 1`**.

> **Por que `--workers 1`?** O sistema sobe o monitor de pasta (watcher) e o
> processador (worker) uma única vez por processo. Mais de um worker duplicaria
> esses processos e causaria conflito de escrita no banco SQLite. Sempre use
> `--workers 1`.

> **Se o instalador instalar o Python ou o `uv`:** pode ser necessário **fechar e
> reabrir o PowerShell** para atualizar o `PATH`. O script avisa quando for o
> caso — basta rodar `.\instalar.ps1` de novo.

### 4. Configurar a chave da OpenAI (`OPENAI_API_KEY`)

A parte de IA (leitura de imagens e PDFs escaneados) exige uma chave válida da
OpenAI, **uma por instalação**.

1. Abra o arquivo `backend\.env` (criado pelo instalador a partir de
   `backend\.env.example`) em um editor de texto.
2. Preencha a linha:

   ```env
   OPENAI_API_KEY=sua-chave-aqui
   ```

3. Salve o arquivo.

> **Segurança:** o arquivo `.env` **nunca é versionado** (não vai para o git, nem
> entra no pacote ZIP) e a chave é tratada como **segredo** — ela nunca aparece em
> logs, telas nem respostas da API. Trate-a como uma senha.

### 5. Acessar o sistema

Com o servidor no ar (o instalador o deixa rodando), abra no navegador:

```
http://localhost:8000
```

Para **parar** o servidor, volte ao PowerShell e pressione **Ctrl+C**. Para subir
de novo mais tarde, rode `.\instalar.ps1` outra vez (é seguro — idempotente).

### 6. Atualizar para uma nova versão (`atualizar.ps1`)

O atualizador funciona **sem Git e sem Node** e traz o frontend já buildado no
pacote. Há dois modos:

- **Online (recomendado)** — baixa o ZIP da última release automaticamente:

  ```powershell
  .\atualizar.ps1
  ```

- **Offline** — quando você recebeu o ZIP por outro meio (sem internet):

  ```powershell
  .\atualizar.ps1 -LocalZip C:\caminho\processador-doc-X.Y.Z.zip
  ```

O `atualizar.ps1` extrai o pacote, **sobrescreve apenas o código**, roda
`uv sync` + `alembic upgrade head` e reinicia o servidor. **Seus dados são
preservados:** o banco SQLite, o armazenamento de arquivos (CAS), os templates e a
configuração vivem em

```
%ProgramData%\ProcessadorDocumentos
```

Essa pasta **não é tocada** pela atualização, e o `backend\.env` (com a sua chave)
também é **preservado**. O Alembic migra apenas o *schema* do banco, mantendo todo
o conteúdo. O código fica separado dos dados — por isso a atualização é segura.

---

## Fluxo B — Dev — gerar o pacote de release

Este fluxo é para quem **desenvolve/publica** o produto e precisa gerar o ZIP de
release que o cliente vai instalar.

### 1. Pré-requisitos

- **Git** (para clonar o repositório).
- **Node.js 20.19+ ou 22.12+** (obrigatório: o empacotador **builda** o frontend).
- **PowerShell**.

### 2. Clonar o repositório

```powershell
git clone https://github.com/avilamicael/processador_doc
cd processador_doc
```

### 3. Gerar o pacote (`empacotar.ps1`)

Na **raiz** do repositório, rode:

```powershell
.\empacotar.ps1
```

O `empacotar.ps1`:

1. Exige Node/npm (build do frontend é **obrigatório** aqui).
2. Builda o frontend (`npm ci` + `npm run build`) → gera `frontend\dist`.
3. Lê a versão de `backend\pyproject.toml`.
4. Monta o pacote por **inclusão explícita** (exclui `.env`, `.git`, `.planning`,
   `node_modules`, `frontend\src`, `tests`, `*.db*`, `data`, etc.).
5. Gera `processador-doc-<versao>.zip` na raiz, com o `frontend\dist` **dentro**.

> A pasta `frontend\dist` é **git-ignored** e o ZIP **não é commitado** — o pacote
> só existe localmente até você anexá-lo a uma GitHub Release.

### 4. Publicar a release

O `empacotar.ps1` **imprime ao final** o comando sugerido (não executa o upload).
Com o [gh CLI](https://cli.github.com/) autenticado:

```powershell
gh release create vX.Y.Z processador-doc-X.Y.Z.zip --title "vX.Y.Z" --notes "Release X.Y.Z"
```

A partir daí, o cliente atualiza com `.\atualizar.ps1` (online) ou recebe o ZIP e
usa `.\atualizar.ps1 -LocalZip <caminho>` (offline).

---

## Troubleshooting

### PowerShell bloqueando o script (ExecutionPolicy)

Se `.\instalar.ps1`, `.\atualizar.ps1` ou `.\empacotar.ps1` forem bloqueados,
libere a execução **apenas nesta sessão** e rode de novo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Porta 8000 ocupada

Se aparecer um erro de porta em uso, descubra qual processo está usando a 8000:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <PID> -Force   # encerra o processo (use o PID acima)
```

Ou suba em **outra porta**, trocando o `--port` no comando do servidor, por exemplo:

```powershell
uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
```

(nesse caso acesse `http://localhost:8080`).

### `OPENAI_API_KEY` ausente ou inválida

**Sintoma:** as extrações por IA falham (imagens/PDFs escaneados não são lidos),
embora a interface e o restante funcionem.

**Solução:** abra `backend\.env`, confira/defina a linha `OPENAI_API_KEY=...` com
uma chave válida e reinicie o servidor.

### Release não encontrada / sem internet (atualização)

**Sintoma:** `.\atualizar.ps1` falha ao consultar o GitHub (sem internet) ou não
encontra um asset `.zip` na última release.

**Solução:** use o modo **offline**, passando um ZIP de release que você tenha em
mãos:

```powershell
.\atualizar.ps1 -LocalZip C:\caminho\processador-doc-X.Y.Z.zip
```

### `frontend/dist` faltando (UI não carrega / 404 na raiz)

**No fluxo do Cliente (ZIP de release), isto não deve acontecer:** o `dist` já vem
dentro do pacote e o `instalar.ps1` **pula o build**. Se você abriu
`http://localhost:8000` e aparece um 404 (mas `http://localhost:8000/health`
responde), provavelmente o pacote foi extraído incompleto — **extraia o ZIP de
release novamente** e rode `.\instalar.ps1`.

Se você está num **clone do repositório** (sem o `dist` buildado) e quer apenas
rodar localmente sem empacotar, builde manualmente (requer Node 20.19+/22.12+):

```powershell
cd frontend
npm ci
npm run build
cd ..
```

Depois rode `.\instalar.ps1` (ele detecta o `dist` e pula o build).

### Onde ficam os dados e os logs

Todos os dados do cliente ficam em:

```
%ProgramData%\ProcessadorDocumentos
```

Isso inclui o banco SQLite (ex.: `app.db`), o armazenamento de arquivos (CAS) e a
configuração. Como os **dados são separados do código**, a atualização
(`.\atualizar.ps1`) é segura e não apaga nada dessa pasta. Para fazer **backup**,
basta copiar essa pasta inteira.

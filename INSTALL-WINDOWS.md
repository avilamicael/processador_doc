# Instalação no Windows — Processador de Documentos

Guia passo a passo para instalar, configurar, acessar e atualizar o
**Processador de Documentos** no Windows. O sistema sobe o backend (API) e o
frontend (interface) num único processo, acessível pelo navegador em
`http://localhost:8000`.

---

## 1. Pré-requisitos

- **Windows** (10 ou 11).
- **PowerShell** (já vem no Windows).
- **(Opcional) Node.js 20.19+ ou 22.12+** — necessário apenas para *buildar* a
  interface (frontend). Sem o Node, a **API funciona normalmente**, mas a tela no
  navegador não é servida até o frontend ser buildado (veja
  [Troubleshooting](#6-troubleshooting)).

Você **não precisa** instalar Python nem o `uv` manualmente: o `instalar.ps1`
cuida disso — instala o **Python 3.12** (via `winget`) e o **uv** (gerenciador de
pacotes) automaticamente se estiverem ausentes.

---

## 2. Rodar o instalador (`instalar.ps1`)

1. Abra o **PowerShell** na pasta do projeto (onde estão `instalar.ps1` e a pasta
   `backend`).
2. Execute:

   ```powershell
   .\instalar.ps1
   ```

3. Se o PowerShell **bloquear a execução de scripts**, libere a execução **apenas
   para esta sessão** (não muda nada permanentemente — vale só até você fechar a
   janela) e rode de novo:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\instalar.ps1
   ```

O `instalar.ps1` é **idempotente**: você pode rodá-lo de novo sem medo — ele só
instala o que estiver faltando. Ele faz, em ordem: garante Python 3.12 → garante
o `uv` → instala as dependências (`uv sync`) → cria `backend\.env` se faltar →
builda o frontend (se o Node estiver disponível) → aplica o schema do banco
(`alembic upgrade head`) → sobe o servidor com **`uvicorn --workers 1`**.

> **Por que `--workers 1`?** O sistema sobe o monitor de pasta (watcher) e o
> processador (worker) uma única vez por processo. Mais de um worker duplicaria
> esses processos e causaria conflito de escrita no banco SQLite. Sempre use
> `--workers 1`.

> **Se o instalador instalar o Python ou o `uv`:** pode ser necessário **fechar e
> reabrir o PowerShell** para atualizar o `PATH`. O script avisa quando for o
> caso — basta rodar `.\instalar.ps1` de novo.

---

## 3. Configurar a chave da OpenAI (`OPENAI_API_KEY`)

A parte de IA (leitura de imagens e PDFs escaneados) exige uma chave válida da
OpenAI, **uma por instalação**.

1. Abra o arquivo `backend\.env` (criado pelo instalador a partir de
   `backend\.env.example`) em um editor de texto.
2. Preencha a linha:

   ```env
   OPENAI_API_KEY=sua-chave-aqui
   ```

3. Salve o arquivo.

> **Segurança:** o arquivo `.env` **nunca é versionado** (não vai para o git) e a
> chave é tratada como **segredo** — ela nunca aparece em logs, telas nem
> respostas da API. Trate-a como uma senha.

---

## 4. Acessar o sistema

Com o servidor no ar (o instalador o deixa rodando), abra no navegador:

```
http://localhost:8000
```

Para **parar** o servidor, volte ao PowerShell e pressione **Ctrl+C**. Para subir
de novo mais tarde, rode `.\instalar.ps1` outra vez (é seguro — idempotente).

---

## 5. Atualizar para uma nova versão (`atualizar.ps1`)

Quando houver uma nova versão do sistema:

```powershell
.\atualizar.ps1
```

O `atualizar.ps1` atualiza o código, as dependências e o schema do banco, e
reinicia o servidor. **Seus dados são preservados:** o banco SQLite, o
armazenamento de arquivos (CAS), os templates e a configuração vivem em

```
%ProgramData%\ProcessadorDocumentos
```

Essa pasta **não é tocada** pela atualização. O Alembic migra apenas o *schema*
do banco, mantendo todo o conteúdo. O código fica separado dos dados — por isso a
atualização é segura.

---

## 6. Troubleshooting

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

### PowerShell bloqueando o script (ExecutionPolicy)

Se `.\instalar.ps1` ou `.\atualizar.ps1` forem bloqueados, libere a execução
**apenas nesta sessão** e rode de novo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### `OPENAI_API_KEY` ausente ou inválida

**Sintoma:** as extrações por IA falham (imagens/PDFs escaneados não são lidos),
embora a interface e o restante funcionem.

**Solução:** abra `backend\.env`, confira/defina a linha `OPENAI_API_KEY=...` com
uma chave válida e reinicie o servidor.

### `frontend/dist` faltando (UI não carrega / 404 na raiz)

**Sintoma:** ao abrir `http://localhost:8000` aparece um 404 ou a tela não carrega
(mas `http://localhost:8000/health` responde). Isso significa que o frontend ainda
não foi buildado. A pasta `frontend/dist` é **gerada** pelo build e é
**git-ignored** (não vem no repositório).

**Solução** (requer Node 20.19+/22.12+):

```powershell
cd frontend
npm ci
npm run build
cd ..
```

Depois reinicie o servidor (`.\instalar.ps1`). O `instalar.ps1` e o
`atualizar.ps1` já tentam buildar automaticamente quando o Node está disponível.

### Onde ficam os dados e os logs

Todos os dados do cliente ficam em:

```
%ProgramData%\ProcessadorDocumentos
```

Isso inclui o banco SQLite (ex.: `app.db`), o armazenamento de arquivos (CAS) e a
configuração. Como os **dados são separados do código**, a atualização
(`.\atualizar.ps1`) é segura e não apaga nada dessa pasta. Para fazer **backup**,
basta copiar essa pasta inteira.

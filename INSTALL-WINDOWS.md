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

> O `instalar.ps1` mantém uma **janela do PowerShell aberta** com o servidor
> rodando. Para que o sistema rode **sempre em background** (e suba sozinho), use um
> dos **dois modos de background** — veja a próxima seção.

### 6. Rodar sempre em background — recomendado em produção

Em produção, o sistema **não deve depender de uma janela do PowerShell aberta**.
Há **dois modos** de manter o servidor rodando em background, ambos pelo
`servico.ps1`:

- **Modo padrão — Tarefa Agendada no logon (sem admin):** sobe sozinho quando você
  **faz logon** no Windows e reinicia se cair. Roda como a **sua própria conta de
  usuário** — por isso **não exige Administrador** nem configuração extra de Python.
  É o modo recomendado para a maioria das instalações (o computador onde uma pessoa
  faz login e usa o sistema).
- **Modo servidor 24/7 — Serviço Windows (NSSM, avançado):** inicia no **boot**,
  antes do login, ideal para um **PC-servidor headless** sem sessão aberta. Exige
  **Administrador** e um **pré-requisito de Python** (veja abaixo).

> **Como escolher:** se uma pessoa loga e usa a máquina, fique no **modo padrão**.
> Só use o **modo servidor 24/7** se o sistema precisa rodar **antes/sem ninguém
> logado** (ex.: um servidor dedicado).

#### Modo padrão — Tarefa Agendada no logon (sem admin)

1. Abra o **PowerShell** na pasta extraída (onde está `servico.ps1`) e rode (sem
   `-Modo`, pois **tarefa é o padrão**; **não precisa** de Administrador):

   ```powershell
   .\servico.ps1 instalar
   ```

O `instalar` cuida de tudo: prepara o ambiente Python, aplica o schema do banco e
registra a Tarefa Agendada **`ProcessadorDocumentos-Servidor`** (gatilho **ao
logon**, reinício automático se cair, uma única instância). Ao final, faz uma
**verificação de saúde** em `http://localhost:8000/health` — se algo falhar, ele
**avisa** e mostra onde olhar. A partir daí, o servidor **sobe sozinho toda vez
que você fizer logon**.

**Logs deste modo:**

```
%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log
```

> **Limitação (honesta):** a Tarefa roda **enquanto o usuário está logado**. Ela
> **não** sobe o servidor **antes do login**, nem mantém o sistema no ar num
> servidor **headless** sem ninguém com a sessão aberta. Se você precisa disso, use
> o **modo servidor 24/7** abaixo.

#### Modo servidor 24/7 — Serviço Windows (NSSM, avançado)

1. Abra o **PowerShell** na pasta extraída e rode (o script **se auto-eleva** via
   **UAC**, pois este modo **exige Administrador**):

   ```powershell
   .\servico.ps1 instalar -Modo servico
   ```

O `instalar -Modo servico` garante o `nssm.exe`, prepara o ambiente Python, aplica
o schema do banco e registra/inicia o serviço **`ProcessadorDocumentos`** (auto-start
no boot, reinício automático, logs com rotação), terminando com a mesma
**verificação de saúde**.

> **Pré-requisito importante:** este modo roda o servidor como a conta do sistema
> (**LocalSystem**) e **exige Python instalado para TODOS os usuários (all-users)**.
> Sem ele, a conta LocalSystem **não consegue ler** o Python que o `uv` instalou no
> seu perfil de usuário, e **o serviço sobe e cai** (a verificação de saúde avisa).
> O **modo padrão (Tarefa)** não tem essa exigência — por isso é o recomendado na
> maioria dos casos.

**Logs deste modo** (com rotação automática quando crescem):

```
%ProgramData%\ProcessadorDocumentos\logs\service.out.log
%ProgramData%\ProcessadorDocumentos\logs\service.err.log
```

#### Comandos de controle (valem para os dois modos)

Os subcomandos abaixo **detectam automaticamente** o modo instalado (Tarefa ou
Serviço) e agem sobre ele:

| Comando                    | O que faz                                       |
| -------------------------- | ----------------------------------------------- |
| `.\servico.ps1 status`     | mostra se está rodando                          |
| `.\servico.ps1 parar`      | para o servidor                                 |
| `.\servico.ps1 iniciar`    | inicia o servidor                               |
| `.\servico.ps1 reiniciar`  | reinicia o servidor                             |
| `.\servico.ps1 logs`       | mostra onde estão os logs e as últimas linhas   |
| `.\servico.ps1 remover`    | para e remove (Tarefa ou Serviço)               |

> **Forçar um modo nos comandos de controle:** normalmente a detecção automática
> resolve. Se precisar, passe `-Modo servico` (ou `-Modo tarefa`) explicitamente,
> por exemplo `.\servico.ps1 status -Modo servico`.

> **AVISO — não rode duas instâncias.** Com um modo de background ativo, **NÃO**
> execute o `instalar.ps1` em primeiro plano (e não instale os **dois** modos ao
> mesmo tempo): isso sobe uma **segunda instância** na porta 8000 e causa conflito
> (porta ocupada + escrita concorrente no banco SQLite). Em produção, use **apenas
> um** modo de background. O `instalar.ps1` em primeiro plano serve só para teste
> rápido / desenvolvimento.

### 7. Atualizar para uma nova versão (`atualizar.ps1`)

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

### O servidor não inicia em background / health-check falhou

**Sintoma:** `.\servico.ps1 instalar` termina com aviso de falha na verificação de
saúde, ou `.\servico.ps1 status` não mostra o servidor em execução.

**Solução:** abra os logs e veja a causa:

```powershell
.\servico.ps1 logs
```

- **Modo padrão (Tarefa):** o log fica em
  `%LOCALAPPDATA%\ProcessadorDocumentos\logs\servidor.log`. Reinstale com
  `.\servico.ps1 instalar` (não precisa de Administrador).
- **Modo servidor 24/7 (Serviço NSSM):** o log de erros fica em
  `%ProgramData%\ProcessadorDocumentos\logs\service.err.log`. A causa mais provável
  é o ambiente Python **não estar acessível à conta LocalSystem** — confirme que há
  **Python instalado para todos os usuários (all-users)** e reinstale com
  `.\servico.ps1 instalar -Modo servico` (como Administrador). Se não houver Python
  all-users, prefira o **modo padrão (Tarefa)**, que não tem essa exigência.

### Logs de execução dos scripts e diagnóstico

Cada execução de `instalar.ps1`, `atualizar.ps1` e `servico.ps1` agora grava um
**log de execução** com data e hora em:

```
%ProgramData%\ProcessadorDocumentos\logs\
```

com nomes como `instalar-AAAAMMDD-HHMMSS.log`, `atualizar-AAAAMMDD-HHMMSS.log` e
`servico-<comando>-AAAAMMDD-HHMMSS.log` (por exemplo, `servico-status-...log`).

**Mesmo que a janela do PowerShell feche** após um erro (típico do duplo-clique), o
**arquivo de log fica gravado** nessa pasta. O caminho do log também é **impresso no
fim** de cada execução, na linha `Log desta execucao: ...`.

> **Dica para não perder a mensagem na hora:** em vez de dar **duplo-clique** no
> script, abra o **PowerShell manualmente** (menu Iniciar → digite *PowerShell*),
> vá até a pasta do programa e rode o script de lá (ex.: `.\instalar.ps1`). Assim a
> janela **não fecha** ao terminar nem ao dar erro, e você lê a mensagem na própria
> tela — além de o log continuar gravado em disco.

Para gerar e enviar um **diagnóstico** ao suporte:

```powershell
.\servico.ps1 diagnostico
```

Isso gera **um único arquivo**
`%ProgramData%\ProcessadorDocumentos\logs\diagnostico-AAAAMMDD-HHMMSS.log` com as
versões (PowerShell e Windows), os caminhos da instalação, o estado da persistência
(Tarefa/Serviço), a porta 8000 / `/health` e trechos finais dos logs. O comando
**imprime o caminho do arquivo** ao final — basta **anexar esse arquivo** no contato
com o suporte.

> **Segurança:** o log de execução e o diagnóstico **nunca incluem a chave da
> OpenAI** nem o conteúdo do `backend\.env` — o `.env` aparece no diagnóstico apenas
> como "existe sim/não". Pode enviar o arquivo ao suporte sem expor o segredo.

### Onde ficam os dados e os logs

Todos os dados do cliente ficam em:

```
%ProgramData%\ProcessadorDocumentos
```

Isso inclui o banco SQLite (ex.: `app.db`), o armazenamento de arquivos (CAS) e a
configuração. Os **logs de execução dos scripts** (`instalar.ps1`, `atualizar.ps1`,
`servico.ps1`) e o **diagnóstico** ficam na subpasta `logs\` dessa mesma pasta. Como
os **dados são separados do código**, a atualização (`.\atualizar.ps1`) é segura e
não apaga nada dessa pasta. Para fazer **backup**, basta copiar essa pasta inteira.

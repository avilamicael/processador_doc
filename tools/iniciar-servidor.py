"""Launcher do servidor (uvicorn) para a Tarefa Agendada do Windows.

Por que este arquivo existe
---------------------------
No modo PADRAO de persistencia no Windows, o servidor sobe por uma **Tarefa
Agendada no logon**, executada por `pythonw.exe` (sem console) — e NAO pelo
servico NSSM/LocalSystem. A Tarefa roda como o **proprio usuario dono do venv**,
o que evita a "Pegadinha 1": o `uv` costuma instalar o Python gerenciado dentro
do perfil do usuario (`%APPDATA%\\uv\\python\\...`), e o `backend\\.venv` aponta
para la. A conta LocalSystem (do servico) muitas vezes NAO consegue ler esse
Python por ACL — o servico sobe e morre. Rodando como o usuario, esse problema
desaparece (sem admin, sem senha de servico).

Como `pythonw.exe` nao tem console, TODA a saida do uvicorn precisa ir para um
arquivo de log — senao some. Por isso este launcher redireciona stdout/stderr
para `%LOCALAPPDATA%\\ProcessadorDocumentos\\logs\\servidor.log`.

SEGREDO: este launcher NUNCA le, imprime nem loga a chave da IA. O proprio
app a le do `backend\\.env` (por isso o CWD precisa ser `backend\\`); o launcher
so cuida de CWD, sys.path, log e de subir o uvicorn.
"""

from __future__ import annotations

import datetime
import os
import socket
import sys
from pathlib import Path


def _resolver_backend() -> Path:
    """Resolve a pasta backend\\ a partir da localizacao DESTE arquivo.

    NAO depende do CWD do processo: a Tarefa Agendada define um WorkingDirectory,
    mas o launcher nao pode confiar nisso. Layout: repo/tools/iniciar-servidor.py
    -> repo/backend.
    """
    return Path(__file__).resolve().parent.parent / "backend"


def _resolver_dir_logs() -> Path:
    """Pasta de logs em %LOCALAPPDATA%\\ProcessadorDocumentos\\logs.

    Usa LOCALAPPDATA do ambiente; se ausente, cai para ~/AppData/Local.
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        raiz = Path(base)
    else:
        raiz = Path.home() / "AppData" / "Local"
    return raiz / "ProcessadorDocumentos" / "logs"


def _porta_em_uso(host: str, porta: int) -> bool:
    """Retorna True se ja ha algo escutando em host:porta (servidor de pe).

    Guarda de instancia unica: quando o .vbs da pasta Inicializar roda no logon,
    pode acontecer de ja haver um servidor de pe (ex.: o proprio `instalar` do
    modo startup ja subiu, ou um `instalar.ps1` ficou em primeiro plano). Subir um
    SEGUNDO uvicorn na mesma porta gera conflito de porta + escrita concorrente no
    SQLite single-writer. Esta checagem tenta uma conexao TCP curta: se CONECTA, ja
    ha servidor (True); se falha (recusada/timeout), ninguem escuta (False).
    """
    try:
        with socket.create_connection((host, porta), timeout=0.5):
            return True
    except OSError:
        return False


def main() -> None:
    backend = _resolver_backend()
    # CWD e sys.path em backend\\ ANTES de importar o app: o app le backend\\.env
    # (DATA_DIR/DATABASE_URL/chave da IA) relativo ao CWD, e "app.main" precisa
    # estar resolvivel no sys.path. Mesmo motivo do --workers 1 em backend\\ no
    # instalar.ps1.
    os.chdir(backend)
    sys.path.insert(0, str(backend))

    # Pasta + arquivo de log. Como pythonw nao tem console, redirecionamos toda a
    # saida (do launcher e do uvicorn) para o arquivo, em modo append e
    # line-buffered (buffering=1) para que as linhas aparecam sem esperar flush.
    dir_logs = _resolver_dir_logs()
    dir_logs.mkdir(parents=True, exist_ok=True)
    arquivo_log = dir_logs / "servidor.log"

    log = open(arquivo_log, "a", buffering=1, encoding="utf-8")
    sys.stdout = log
    sys.stderr = log

    # Cabecalho legivel para o subcomando `logs` (sem segredos).
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{agora}] iniciar-servidor: subindo uvicorn | cwd={os.getcwd()}")
    log.flush()

    # GUARDA DE INSTANCIA UNICA: se ja ha um servidor escutando na 8000, NAO sobe
    # um segundo (conflito de porta + SQLite single-writer). Sai com codigo 0 — nao
    # e erro: e o comportamento esperado quando o .vbs roda no logon e algo ja
    # estava de pe. So loga (sem segredos) e encerra limpo.
    if _porta_em_uso("127.0.0.1", 8000):
        agora = datetime.datetime.now().isoformat(timespec="seconds")
        print(f"[{agora}] ja ha um servidor escutando em 127.0.0.1:8000 — saindo")
        log.flush()
        log.close()
        sys.exit(0)

    # uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
    # OBRIGATORIO workers=1: watcher+worker sobem 1x por processo; SQLite
    # single-writer. Sem reload. Instancia unica garantida por workers=1 +
    # MultipleInstances=IgnoreNew na Tarefa Agendada.
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()

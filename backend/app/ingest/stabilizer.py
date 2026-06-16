"""Estabilizador de arquivo — quiescência size/mtime + lock-test (Windows).

O evento do watcher (Plano 04) é apenas uma *candidatura*: o arquivo pode ainda
estar sendo escrito quando o evento dispara (cópia lenta em rede, gravação em
streaming). Fazer hash/split sobre conteúdo parcial corromperia a dedup e o split
(Pitfall 1 / T-02-03). `wait_stable` resolve isso esperando o arquivo *parar* de
mudar antes de qualquer leitura de conteúdo.

Critério de estabilidade (D-04):
1. A assinatura `(st_size, st_mtime_ns)` precisa ficar idêntica por toda uma
   janela configurável (`window_s`). Qualquer mudança no meio reinicia a
   contagem — arquivo ainda está sendo escrito.
2. Depois da janela, um *lock-test*: abrir o arquivo em `"rb"`. No Windows, isso
   falha enquanto o gravador mantém um lock exclusivo de escrita, então é o sinal
   mais confiável de "o gravador soltou o arquivo" (no NTFS o `mtime` pode ter
   granularidade grosseira — size+mtime+lock-test é mais robusto que mtime só).

Retorna `False` (não estável / não processar) se o arquivo for removido durante a
espera ou se o lock-test falhar — o chamador apenas reagenda/ignora; nunca
processa conteúdo parcial.

Utilidade pura: só stdlib (`os`/`pathlib`/`asyncio`); sem HTTP, sem DB. Despachada
pelo worker; o `await asyncio.sleep` entre polls cede o event loop.
"""

import asyncio
from pathlib import Path

from app.config import get_settings


async def wait_stable(
    path: Path,
    window_s: float | None = None,
    poll_s: float = 1.0,
) -> bool:
    """Espera `path` ficar estável e retorna se está seguro processá-lo.

    Args:
        path: arquivo candidato vindo da pasta monitorada.
        window_s: janela de quiescência em segundos. Quando `None`, usa o default
            global `get_settings().stabilization_window_seconds` (D-04).
        poll_s: intervalo entre verificações de assinatura.

    Returns:
        `True` se `(size, mtime)` ficaram parados por toda a janela e o arquivo
        abriu sem lock; `False` se foi removido durante a espera (FileNotFoundError)
        ou se o lock-test falhou (gravador ainda segura o arquivo no Windows).
    """
    if window_s is None:
        window_s = get_settings().stabilization_window_seconds

    last: tuple[int, int] | None = None
    stable_for = 0.0
    while stable_for < window_s:
        try:
            st = path.stat()
        except FileNotFoundError:
            return False  # removido enquanto estabilizava
        sig = (st.st_size, st.st_mtime_ns)
        if sig == last:
            stable_for += poll_s
        else:
            stable_for = 0.0
            last = sig
        await asyncio.sleep(poll_s)

    # Lock-test Windows: no NTFS, `open` falha se outro processo ainda mantém o
    # arquivo aberto para escrita exclusiva. Em POSIX raramente falha, mas o
    # try/except é inócuo e mantém o mesmo caminho de código nas duas plataformas.
    try:
        with path.open("rb"):
            pass
    except (PermissionError, OSError):
        return False
    return True

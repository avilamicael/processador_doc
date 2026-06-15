"""Enumerações de domínio.

`DocState` é o conjunto **enxuto** de estados de topo de um documento (D-04):
`RECEBIDO → PROCESSANDO → EM_REVISAO → CONCLUIDO`, mais os estados laterais
`QUARENTENA` e `FALHA`. Identificadores Python sem acento; os valores em string
são a forma persistida no banco (e em logs/API).

As subetapas internas do pipeline (dedup, separação, extração, classificação,
validação) NÃO são estados de topo (D-05) — vivem no marcador interno
`Document.last_completed_step`.
"""

from enum import Enum


class DocState(str, Enum):  # noqa: UP042 — forma explícita do plano (str, Enum)
    """Estados de topo de um documento (D-04).

    Herda de `str` para que o valor persistido/serializado seja a string do
    membro (ex.: `DocState.RECEBIDO == "recebido"`), simplificando armazenamento
    em coluna de texto e exposição na API.
    """

    RECEBIDO = "recebido"
    PROCESSANDO = "processando"
    EM_REVISAO = "em_revisao"
    CONCLUIDO = "concluido"
    QUARENTENA = "quarentena"
    FALHA = "falha"

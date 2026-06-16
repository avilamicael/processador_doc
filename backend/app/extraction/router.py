"""Seam de extração D-03 (Fase 3) — o ponto de costura mais importante da fase.

Função de módulo única (estilo `cas.py`/`repo.py`, sem classe) que decide POR ONDE
um bloco de documento será extraído. É a interface que isola "como decidir o
caminho" do resto do motor.

> O SEAM D-03 (Fases 4 e 7 estendem AQUI):
> - default v1 = "decide texto-vs-visão e SEMPRE chama a IA" (esta implementação);
> - Fase 4 (template casado) e Fase 7 (determinístico → nativo → IA) plugam neste
>   mesmo ponto o ATALHO LOCAL de custo ZERO para padrões conhecidos, SEM reescrever
>   o motor (D-03/D-05). Por isso `choose` é mínimo e plugável: usa só `pdf_io`
>   (magic bytes + heurística texto-vs-visão), NUNCA embute lógica de OpenAI nem DB.

Manter este módulo deliberadamente pequeno: a tentação de cravar "sempre IA" aqui
é o Critical Failure Mode 4 (acoplamento que mata o seam de custo).
"""

from app.config import get_settings
from app.extraction import pdf_io


def choose(blob: bytes) -> str:
    """Decide a rota de extração de um bloco (seam D-03): "native_text" | "vision".

    Fluxo v1 (Fases 4/7 plugam atalhos locais neste mesmo ponto, sem reescrever o
    motor — D-03/D-05):
    - imagem (jpeg/png) → "vision" direto (a imagem já é a página; nunca aberta
      como PDF — Pitfall 5);
    - PDF → delega a `pdf_io.extract_text_and_decide`, que mede o texto nativo por
      página e devolve "native_text" (há texto suficiente, caminho barato) ou
      "vision" (escaneado, EXT-01/D-04).

    Blob que não é PDF/imagem levanta `ValueError` (via `detect_blob_type`) — não
    chuta uma rota; o stage (Plan 03) transforma isso em FALHA controlada.
    """
    blob_type = pdf_io.detect_blob_type(blob)
    if blob_type in ("jpeg", "png"):
        return "vision"
    # blob_type == "pdf"
    min_chars = get_settings().openai_extract_min_chars_per_page
    _text, route = pdf_io.extract_text_and_decide(blob, min_chars_per_page=min_chars)
    return route

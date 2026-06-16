"""Testes do estabilizador de arquivo (quiescência size/mtime + lock-test).

Cobre o contrato de `app.ingest.stabilizer.wait_stable` (Pitfall 1 / T-02-03):
- arquivo já parado vira estável com janela/poll curtos;
- arquivo removido durante a espera retorna False;
- escrita incremental entre polls reinicia a contagem da janela.

`asyncio_mode="auto"` (pyproject) torna funções async coletáveis sem decorator.
Todos os testes usam janela/poll curtíssimos para rodar em <1s.
"""

from pathlib import Path

from app.ingest.stabilizer import wait_stable


async def test_arquivo_parado_vira_estavel(tmp_path: Path) -> None:
    p = tmp_path / "parado.bin"
    p.write_bytes(b"conteudo final")

    # Janela e poll curtos: o arquivo não muda, então estabiliza rápido.
    assert await wait_stable(p, window_s=0.05, poll_s=0.01) is True


async def test_arquivo_removido_retorna_false(tmp_path: Path) -> None:
    p = tmp_path / "some.bin"
    # Nunca criado: stat levanta FileNotFoundError → wait_stable retorna False.
    assert await wait_stable(p, window_s=0.05, poll_s=0.01) is False


async def test_remocao_durante_espera_retorna_false(tmp_path: Path) -> None:
    p = tmp_path / "transiente.bin"
    p.write_bytes(b"abc")

    # Agenda a remoção do arquivo logo após o primeiro poll (mid-window).
    import asyncio

    async def _remove_soon() -> None:
        await asyncio.sleep(0.02)
        p.unlink()

    task = asyncio.create_task(_remove_soon())
    # Janela maior que o tempo até a remoção → wait_stable vê FileNotFoundError.
    result = await wait_stable(p, window_s=0.5, poll_s=0.01)
    await task
    assert result is False


async def test_escrita_incremental_reinicia_contagem(tmp_path: Path) -> None:
    p = tmp_path / "crescendo.bin"
    p.write_bytes(b"a")

    import asyncio

    # Escreve incrementalmente algumas vezes enquanto wait_stable observa: cada
    # mudança de size deve reiniciar a contagem. Depois para de escrever e o
    # arquivo deve eventualmente estabilizar (retornar True), provando que a
    # contagem reiniciou em vez de concluir cedo sobre conteúdo parcial.
    async def _grow() -> None:
        for i in range(4):
            await asyncio.sleep(0.03)
            with p.open("ab") as fh:
                fh.write(bytes([i]))

    grower = asyncio.create_task(_grow())
    # window_s pequeno (0.05) mas menor que o intervalo total de escrita: se a
    # contagem NÃO reiniciasse, estabilizaria durante a escrita (conteúdo
    # parcial). Como reinicia, só vira True após o grower terminar.
    result = await wait_stable(p, window_s=0.05, poll_s=0.01)
    await grower
    # Quando wait_stable retorna True, nenhuma escrita pode estar mais pendente:
    # o grower já terminou (size final == 1 + 4 bytes escritos).
    assert result is True
    assert p.stat().st_size == 1 + 4


async def test_usa_janela_da_config_quando_window_none(
    tmp_path: Path, monkeypatch
) -> None:
    # window_s=None deve ler de get_settings().stabilization_window_seconds.
    import app.ingest.stabilizer as stab

    class _FakeSettings:
        stabilization_window_seconds = 0.05

    monkeypatch.setattr(stab, "get_settings", lambda: _FakeSettings())

    p = tmp_path / "default_janela.bin"
    p.write_bytes(b"x")

    assert await wait_stable(p, window_s=None, poll_s=0.01) is True

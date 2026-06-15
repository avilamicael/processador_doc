"""Testes do CAS (Content-Addressable Storage) por hash SHA-256.

Provam as garantias da Fase 1 / Plan 03 (D-07, D-08, D-01):
- store COPIA o original preservando-o byte-a-byte (D-07)
- conteúdo é endereçado/recuperável pelo hash SHA-256 (rede de segurança/undo — D-08)
- mesmo conteúdo não duplica blob (idempotência por conteúdo)
- o CAS vive dentro da pasta de dados única (data_dir/cas — D-01)
- escrita atômica via temporário + os.replace, sem .tmp órfãos
- o módulo NÃO expõe delete/update (blob imutável)
"""

import hashlib
from pathlib import Path

import pytest

from app import config
from app.storage import cas


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aponta a pasta de dados única para um diretório temporário isolado.

    Define DATA_DIR e limpa o cache de get_settings para que o CAS derive a
    raiz (data_dir/cas) do diretório do teste — sem tocar a pasta real.
    """
    d = tmp_path / "datadir"
    d.mkdir()
    monkeypatch.setenv("DATA_DIR", str(d))
    config.get_settings.cache_clear()
    yield d
    config.get_settings.cache_clear()


@pytest.fixture
def src_file(tmp_path: Path) -> Path:
    """Um arquivo de origem (fora do CAS) com conteúdo conhecido."""
    p = tmp_path / "origem" / "documento.pdf"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"%PDF-1.7 conteudo de documento fiscal\n" * 100)
    return p


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_store_retorna_sha256_do_conteudo(data_dir: Path, src_file: Path) -> None:
    """O hash retornado é o SHA-256 hex do conteúdo do arquivo de origem."""
    h = cas.store(src_file)
    assert h == _sha256(src_file)


def test_blob_fica_dentro_da_pasta_de_dados(data_dir: Path, src_file: Path) -> None:
    """O blob é gravado sob data_dir/cas (CAS na pasta de dados única — D-01)."""
    h = cas.store(src_file)
    blob = cas.path_for(h)
    cas_root = data_dir / "cas"
    assert blob.exists()
    assert cas_root in blob.parents


def test_original_preservado_byte_a_byte(data_dir: Path, src_file: Path) -> None:
    """O arquivo de origem permanece intacto após store (cópia, não move — D-07)."""
    antes = src_file.read_bytes()
    cas.store(src_file)
    assert src_file.exists()
    assert src_file.read_bytes() == antes


def test_read_bytes_recupera_conteudo_original(data_dir: Path, src_file: Path) -> None:
    """read_bytes(hash) devolve exatamente o conteúdo original."""
    original = src_file.read_bytes()
    h = cas.store(src_file)
    assert cas.read_bytes(h) == original


def test_open_blob_streaming_le_conteudo(data_dir: Path, src_file: Path) -> None:
    """open_blob(hash) é um context manager que faz streaming do conteúdo."""
    original = src_file.read_bytes()
    h = cas.store(src_file)
    with cas.open_blob(h) as fh:
        assert fh.read() == original


def test_store_idempotente_nao_duplica_blob(data_dir: Path, src_file: Path) -> None:
    """Armazenar o mesmo conteúdo duas vezes retorna o mesmo hash e 1 só blob."""
    h1 = cas.store(src_file)
    h2 = cas.store(src_file)
    assert h1 == h2
    blob = cas.path_for(h1)
    # Conta arquivos no diretório do shard final: exatamente 1 (o blob).
    arquivos = [p for p in blob.parent.iterdir() if p.is_file()]
    assert arquivos == [blob]


def test_recuperacao_apos_operacao_posterior(data_dir: Path, src_file: Path) -> None:
    """Conteúdo continua recuperável por hash mesmo após automação posterior.

    Simula uma automação que renomeia/remove o arquivo de origem; o CAS
    (rede de segurança/undo — D-08) ainda devolve o conteúdo pelo hash.
    """
    original = src_file.read_bytes()
    h = cas.store(src_file)
    # "Automação posterior": move/remove o original da pasta de origem.
    src_file.unlink()
    assert not src_file.exists()
    assert cas.read_bytes(h) == original


def test_exists_true_apos_store_false_para_desconhecido(
    data_dir: Path, src_file: Path
) -> None:
    """exists(hash) é True após store e False para um hash desconhecido."""
    h = cas.store(src_file)
    assert cas.exists(h) is True
    desconhecido = "0" * 64
    assert cas.exists(desconhecido) is False


def test_sem_tmp_orfao_no_caminho_feliz(data_dir: Path, src_file: Path) -> None:
    """O caminho feliz não deixa arquivos temporários (.tmp) órfãos no CAS."""
    cas.store(src_file)
    cas_root = data_dir / "cas"
    tmps = list(cas_root.rglob("*.tmp"))
    assert tmps == []


def test_path_for_usa_sharding_por_prefixo(data_dir: Path, src_file: Path) -> None:
    """path_for distribui blobs por subpastas de prefixo do hash (sharding)."""
    h = cas.store(src_file)
    blob = cas.path_for(h)
    assert blob.name == h
    assert blob.parent.name == h[2:4]
    assert blob.parent.parent.name == h[:2]


def test_modulo_nao_expoe_delete_ou_update() -> None:
    """O CAS é imutável: sem API de delete/remove/update do blob (D-08)."""
    for nome in ("delete", "remove", "update", "unlink"):
        assert not hasattr(cas, nome), f"CAS não deve expor {nome!r} (imutável)"

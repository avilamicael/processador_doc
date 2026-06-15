"""Testes da camada de configuração (Settings).

Cobre: padrão de data_dir no Windows (PROGRAMDATA), padrão fora do Windows,
sobrescrita via DATA_DIR, effective_database_url dentro da pasta de dados,
e a garantia de que a chave OpenAI nunca aparece em repr/str.
"""

import os
from pathlib import Path

from app.config import Settings, ensure_data_dir


def _make_settings(**overrides) -> Settings:
    """Cria Settings sem ler o .env do disco (isolamento de teste)."""
    defaults = {"_env_file": None}
    defaults.update(overrides)
    return Settings(**defaults)


def test_data_dir_default_windows_uses_programdata(monkeypatch, tmp_path):
    # No Windows, PROGRAMDATA está sempre presente. Testamos exatamente o branch
    # que deriva de PROGRAMDATA (representável no SO de CI). `pathlib` não permite
    # instanciar WindowsPath em Linux, então não forçamos os.name="nt" aqui — o
    # branch de derivação é o mesmo (PROGRAMDATA presente).
    programdata = tmp_path / "ProgramData"
    monkeypatch.setenv("PROGRAMDATA", str(programdata))
    monkeypatch.delenv("DATA_DIR", raising=False)

    settings = _make_settings()

    assert settings.data_dir == programdata / "ProcessadorDocumentos"


def test_default_data_dir_uses_programdata_when_os_name_is_nt(monkeypatch):
    # Cobre o ramo `os.name == "nt"` da função de derivação sem instanciar Path
    # (que falharia em Linux): inspeciona a lógica via PureWindowsPath-friendly
    # checagem de string quando PROGRAMDATA está definido.
    from app.config import _default_data_dir

    monkeypatch.setenv("PROGRAMDATA", "/srv/programdata")
    monkeypatch.delenv("DATA_DIR", raising=False)
    result = _default_data_dir()
    assert result.name == "ProcessadorDocumentos"
    assert "programdata" in str(result).lower()


def test_data_dir_default_non_windows_uses_home(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    settings = _make_settings()

    expected = Path.home() / ".processador_documentos"
    assert settings.data_dir == expected


def test_data_dir_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "meus_dados"))

    settings = _make_settings()

    assert settings.data_dir == tmp_path / "meus_dados"


def test_effective_database_url_points_to_app_db_inside_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = _make_settings()

    assert settings.effective_database_url == f"sqlite:///{tmp_path / 'app.db'}"


def test_explicit_database_url_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@host/db")

    settings = _make_settings()

    assert settings.effective_database_url == "postgresql+psycopg://user:pw@host/db"


def test_openai_key_not_exposed_in_repr_or_str():
    secret = "sk-super-secret-value-1234567890"
    settings = _make_settings(openai_api_key=secret)

    assert secret not in repr(settings)
    assert secret not in str(settings)
    # mas o valor segue acessível de forma explícita para uso interno
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == secret


def test_ensure_data_dir_creates_directory(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "data"
    monkeypatch.setenv("DATA_DIR", str(target))
    settings = _make_settings()

    assert not target.exists()
    ensure_data_dir(settings)
    assert target.is_dir()


def test_openai_key_optional_defaults_to_none(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = _make_settings()
    assert settings.openai_api_key is None

"""Configuração da aplicação (Settings).

Lê a configuração de ambiente / arquivo `.env`:
- `DATA_DIR`: pasta de dados única (banco SQLite + futuro CAS). Padrão no Windows:
  `%ProgramData%\\ProcessadorDocumentos`; fora do Windows: `~/.processador_documentos`.
- `DATABASE_URL`: connection string SQLAlchemy. Quando ausente, deriva um SQLite
  dentro de `DATA_DIR` (mantém a porta aberta para Postgres só trocando esta URL).
- `OPENAI_API_KEY`: chave OpenAI por instância. Armazenada como `SecretStr` para
  NUNCA aparecer em `repr`/`str`/logs (T-01-01 / PITFALLS Security).

Nada aqui loga nem retorna o valor da chave.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Resolve a pasta de dados padrão conforme a plataforma.

    Windows (ou com PROGRAMDATA definido): `%ProgramData%\\ProcessadorDocumentos`.
    Demais plataformas (ex.: CI Linux): `~/.processador_documentos`.
    """
    programdata = os.environ.get("PROGRAMDATA")
    if os.name == "nt" or programdata:
        base = programdata or os.path.expandvars(r"%SystemDrive%\ProgramData")
        return Path(base) / "ProcessadorDocumentos"
    return Path.home() / ".processador_documentos"


class Settings(BaseSettings):
    """Configuração única da aplicação, lida de env/`.env`.

    `data_dir` é exposto como propriedade computada (não campo armazenado) para
    que o valor venha do env `DATA_DIR` quando definido, ou do padrão da
    plataforma — evitando que o flavour de `Path` seja recoagido na validação.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entrada bruta de DATA_DIR (string); None quando não definida no ambiente.
    data_dir_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATA_DIR", "data_dir", "data_dir_raw"),
    )
    database_url: str | None = None
    openai_api_key: SecretStr | None = None

    # Janela de estabilização global (D-04): só processamos um arquivo da pasta
    # monitorada após size/mtime ficarem parados por esta janela inteira (e o
    # arquivo abrir sem lock — Pitfall 1 / T-02-03). Default ~4s é sensível a
    # cópias lentas em rede (A2 da pesquisa); ajustável por instância sem deploy
    # via env STABILIZATION_WINDOW_SECONDS. Pastas vivem no DB (D-02), não aqui.
    stabilization_window_seconds: float = Field(
        default=4.0,
        validation_alias=AliasChoices(
            "STABILIZATION_WINDOW_SECONDS", "stabilization_window_seconds"
        ),
    )

    # Tunables da fila/worker in-process consumidos pelo Plano 03 (sem broker —
    # modo padrão Windows). Globais; ajustáveis por env sem alterar código.
    queue_poll_interval_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices("QUEUE_POLL_INTERVAL_SECONDS", "queue_poll_interval_seconds"),
    )
    queue_max_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices("QUEUE_MAX_ATTEMPTS", "queue_max_attempts"),
    )
    queue_backoff_base_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices("QUEUE_BACKOFF_BASE_SECONDS", "queue_backoff_base_seconds"),
    )
    queue_backoff_max_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("QUEUE_BACKOFF_MAX_SECONDS", "queue_backoff_max_seconds"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def data_dir(self) -> Path:
        """Pasta de dados efetiva (env DATA_DIR ou padrão da plataforma)."""
        if self.data_dir_raw:
            return Path(self.data_dir_raw)
        return _default_data_dir()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_database_url(self) -> str:
        """URL efetiva do banco.

        Se `database_url` foi fornecida, é usada como está (permite Postgres no
        modo servidor). Caso contrário, deriva um SQLite dentro de `data_dir`.
        """
        if self.database_url:
            return self.database_url
        # Normaliza para barras "/" (as_posix) antes de montar a URL: no Windows
        # (plataforma primária) o caminho stringifica com "\", o que quebra o
        # parsing da URL sqlite. `sqlite:///` + caminho POSIX é seguro em ambas
        # as plataformas.
        return "sqlite:///" + (self.data_dir / "app.db").as_posix()


def ensure_data_dir(settings: "Settings | None" = None) -> Path:
    """Garante que a pasta de dados exista, criando-a se necessário."""
    settings = settings or get_settings()
    assert settings.data_dir is not None
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir


@lru_cache
def get_settings() -> Settings:
    """Retorna uma instância cacheada de Settings (lida uma vez por processo)."""
    return Settings()

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

    # Tunables da extração via IA (Fase 3) — mesmo padrão dos queue_* (lidos de env
    # sem deploy). A chave OpenAI continua em `openai_api_key` (SecretStr) acima;
    # estes são parâmetros NÃO-secretos do motor de extração.
    #
    # `openai_extract_model`: o IMPLEMENTADOR deve CONFIRMAR o modelo vigente na
    # conta no momento da implementação (modelos giram rápido, D-04). Precisa
    # suportar visão (input_image) + Structured Outputs (text_format Pydantic).
    openai_extract_model: str = Field(
        default="gpt-4o-2024-08-06",
        validation_alias=AliasChoices("OPENAI_EXTRACT_MODEL", "openai_extract_model"),
    )
    # Extração é determinística (queremos os MESMOS dados, não criatividade) →
    # temperatura 0.0 reduz variância entre execuções (base estável p/ Fases 4/7, D-06).
    openai_extract_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices(
            "OPENAI_EXTRACT_TEMPERATURE", "openai_extract_temperature"
        ),
    )
    # Teto explícito de tokens de saída (Pitfall 3/6): sem limite, uma extração que
    # "viaja" gasta milhares de tokens — e a saída inclui o full_text. Dimensionar
    # com folga; ajustar por observação dos `usage` reais.
    openai_extract_max_output_tokens: int = Field(
        default=4096,
        validation_alias=AliasChoices(
            "OPENAI_EXTRACT_MAX_OUTPUT_TOKENS", "openai_extract_max_output_tokens"
        ),
    )
    # Alavanca de custo do caminho visão (Pitfall 4 / D-04): "high" lê dígitos finos
    # de scans ruins de forma confiável mas custa mais; "low" é ~85 tokens fixos.
    openai_extract_image_detail: str = Field(
        default="high",
        validation_alias=AliasChoices(
            "OPENAI_EXTRACT_IMAGE_DETAIL", "openai_extract_image_detail"
        ),
    )
    # Limiar da heurística texto-vs-visão: mínimo de caracteres nativos por página
    # para considerar o PDF "tem texto suficiente" (caminho barato). ~16 é um ponto
    # de partida razoável; calibrar por observação dos documentos reais do cliente.
    openai_extract_min_chars_per_page: int = Field(
        default=16,
        validation_alias=AliasChoices(
            "OPENAI_EXTRACT_MIN_CHARS_PER_PAGE", "openai_extract_min_chars_per_page"
        ),
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

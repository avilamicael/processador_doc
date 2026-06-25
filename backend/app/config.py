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
        default="gpt-4o-mini-2024-07-18",
        validation_alias=AliasChoices("OPENAI_EXTRACT_MODEL", "openai_extract_model"),
    )
    # Extração é determinística (queremos os MESMOS dados, não criatividade) →
    # temperatura 0.0 reduz variância entre execuções (base estável p/ Fases 4/7, D-06).
    openai_extract_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices("OPENAI_EXTRACT_TEMPERATURE", "openai_extract_temperature"),
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
        # TODO(custo): baixado de "high" → "low" para economizar tokens no caminho
        # visão (~85 tokens fixos/página vs milhares). VERIFICAR DEPOIS: medir, com a
        # tabela `usage`, se a qualidade de leitura em scans reais se mantém aceitável;
        # se cair, voltar para "high" ou tornar por-template. (decisão de teste)
        default="low",
        validation_alias=AliasChoices("OPENAI_EXTRACT_IMAGE_DETAIL", "openai_extract_image_detail"),
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

    # Tunables da CLASSIFICAÇÃO (Fase 4) — mesmo padrão dos extract_*/queue_*
    # (lidos de env sem deploy). Governam o matcher local custo-zero e o desempate
    # pago por IA contra os templates do cliente.
    #
    # `classify_match_threshold`: limiar GLOBAL de confiança do matcher local
    # (discretion D-03; um limiar por-template é v2/INT2-05). Score do matcher ACIMA
    # do limiar → casa o template sem custo de IA; zona cinzenta abaixo → a IA
    # desempata (chamada paga); zero sinais → quarentena (template_id null).
    # Faixa restrita a [0.0, 1.0] (WR-01): a confiança do matcher é booleana (0.0/1.0),
    # então um threshold fora dessa faixa não tem sentido — e a falha-fechada de
    # decide() já barra confiança 0.0 mesmo com threshold 0/negativo.
    classify_match_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("CLASSIFY_MATCH_THRESHOLD", "classify_match_threshold"),
    )
    # `review_confidence_threshold` (Fase 5, D-03): limiar GLOBAL de QUALIDADE DE
    # EXTRAÇÃO abaixo do qual o documento vai para revisão humana (EM_REVISAO).
    # Score = fração de obrigatórios válidos (compute_confidence). default 0.8
    # alinha à faixa "Alta ≥80%" do 05-UI-SPEC (Assumption A2 — calibrar). Lido de
    # env sem deploy, mesmo padrão de classify_match_threshold.
    review_confidence_threshold: float = Field(
        default=0.8,
        validation_alias=AliasChoices("REVIEW_CONFIDENCE_THRESHOLD", "review_confidence_threshold"),
    )
    # `classify_ai_fallback_enabled` (Fase 10, D-05/D-06): toggle GLOBAL opt-in que
    # liga a "IA classifica quando NENHUM template casa". Com OFF (default) o doc
    # não-casado vai direto para QUARENTENA (comportamento atual — custo zero). Com
    # ON, ANTES de quarentenar, o `classify_stage` chama a IA (uma chamada PAGA por
    # doc não-casado) contra TODOS os templates; se a IA casar, o doc segue o caminho
    # de casamento. CUSTO EXPLÍCITO: cada doc não-casado vira 1 chamada paga quando
    # ON. Default FALSE preserva o comportamento atual e o custo zero. A decisão de
    # chamar IA vive no stage, NUNCA no `matcher.decide` (seam D-06). Lido de env sem
    # deploy (mesmo padrão dos tunables vizinhos); espelhado em GET/PUT /config/ai-fallback.
    classify_ai_fallback_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CLASSIFY_AI_FALLBACK_ENABLED", "classify_ai_fallback_enabled"
        ),
    )
    # `approval_mode_enabled` (Fase 12, D-03/D-04/D-05): toggle GLOBAL de "modo de
    # aprovação". Com OFF (default) o sweep `enqueue_pending_applications` auto-aplica
    # os docs de ALTA confiança como hoje — a trava de confiança/limiar (D-04) segue
    # intacta no `classify_stage` (baixa confiança continua indo a EM_REVISAO). Com ON,
    # o sweep curto-circuita e NÃO auto-aplica nada: os docs de alta confiança ficam
    # pendentes aguardando aprovação humana via DryRunPage (modo de teste, D-05). O
    # GATE vive SÓ no enqueue do worker, NUNCA em `apply_stage` (executor compartilhado
    # com a aprovação manual — gateá-lo quebraria D-06: aprovar = apply). Lido de env
    # sem deploy (mesmo padrão dos tunables vizinhos); espelhado em GET/PUT
    # /config/approval-mode.
    approval_mode_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "APPROVAL_MODE_ENABLED", "approval_mode_enabled"
        ),
    )
    # `openai_classify_model`: modelo das chamadas PAGAS de desempate/classificação
    # (D-01/D-06). Modelos giram rápido (CLAUDE.md) → tunável por env; o default
    # reusa o modelo de extract para uma instância só precisar definir um modelo.
    openai_classify_model: str = Field(
        default="gpt-4o-mini-2024-07-18",
        validation_alias=AliasChoices("OPENAI_CLASSIFY_MODEL", "openai_classify_model"),
    )
    # Classificação é determinística (mesma decisão para o mesmo documento) →
    # temperatura 0.0, espelhando o equivalente de extract.
    openai_classify_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices("OPENAI_CLASSIFY_TEMPERATURE", "openai_classify_temperature"),
    )
    # Teto de tokens de saída do desempate por IA (a saída é compacta:
    # template casado + confiança + razão), espelhando o de extract.
    openai_classify_max_output_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices(
            "OPENAI_CLASSIFY_MAX_OUTPUT_TOKENS", "openai_classify_max_output_tokens"
        ),
    )

    # Tunables das AUTOMAÇÕES (Fase 6) — mesmo padrão dos demais (lidos de env sem
    # deploy). Governam o confinamento e o saneamento dos destinos resolvidos a
    # partir de tokens {campo} (valores vindos da IA, NÃO-confiáveis).
    #
    # `automation_dest_root`: raiz-base de confinamento dos destinos (V4 path
    # traversal). Quando definida, todo destino resolvido DEVE cair sob esta raiz
    # (`resolved.is_relative_to(root)`); fora dela = bloqueio. None = sem
    # confinamento adicional além da sanitização — mas o campo existe para o
    # cliente travar a base por env sem alterar código.
    automation_dest_root: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUTOMATION_DEST_ROOT", "automation_dest_root"),
    )
    # `automation_max_component_len`: teto de comprimento (em chars) por COMPONENTE
    # de nome/pasta, para mitigar o limite MAX_PATH (260) do Windows (Pitfall 5).
    # Componentes mais longos são truncados de forma controlada na resolução.
    automation_max_component_len: int = Field(
        default=200,
        validation_alias=AliasChoices(
            "AUTOMATION_MAX_COMPONENT_LEN", "automation_max_component_len"
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


def env_file_path() -> Path:
    """Caminho do arquivo `.env` que o `Settings` lê (SettingsConfigDict.env_file).

    Resolvido relativo à CWD (mesma semântica de `pydantic-settings`). Centralizado
    aqui para que a persistência de tunables (ex.: `persist_env_setting`) escreva
    EXATAMENTE no arquivo que o `Settings` relê — e para que os testes possam
    monkeypatchar este ponto único em vez de poluir o `.env` real.
    """
    env_file = Settings.model_config.get("env_file", ".env")
    return Path(env_file)


def persist_env_setting(key: str, value: str) -> None:
    """Persiste `KEY=value` no `.env`, substituindo a linha existente ou anexando.

    Escrita ATÔMICA (arquivo temporário + `os.replace`) para não corromper o `.env`
    sob crash/concorrência. `key` é uma constante do código (não input do usuário);
    `value` já vem validado (ex.: faixa Pydantic do endpoint) — nunca interpolamos
    input cru em SQL/shell (T-05-15). Preserva as demais linhas do arquivo.

    Após chamar, o chamador deve invocar `get_settings.cache_clear()` para que o
    novo valor seja relido (o `lru_cache` mantém a instância antiga até limpar).
    """
    path = env_file_path()
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    new_line = f"{key}={value}"
    replaced = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        # Casa a chave no início da linha (ignorando comentários e linhas em branco).
        if stripped and not stripped.startswith("#"):
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                lines[i] = new_line
                replaced = True
                break
    if not replaced:
        lines.append(new_line)

    content = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)

"""Pacote da API HTTP — routers finos consumidos pela UI (Plano 05).

Cada módulo expõe um `APIRouter` registrado em `app.main`. As rotas são FINAS:
só validam entrada, leem/configuram estado e delegam a lógica para os módulos de
domínio (`ingest`, `pipeline`, `queue`). Sem regra de negócio aqui.
"""

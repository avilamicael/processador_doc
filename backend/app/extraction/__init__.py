"""Pacote de extração (Fase 3).

Reúne o motor genérico de extração via IA da OpenAI: schema Pydantic dos
Structured Outputs (`schema.py`), e — nos planos seguintes — o cliente
`AsyncOpenAI`, o roteador texto-vs-visão (D-03), o I/O de PDF (PyMuPDF) e o
estágio de pipeline `extract_stage`.

A chave OpenAI continua em `app.config.Settings.openai_api_key` (SecretStr);
nada aqui loga nem retorna o seu valor.
"""

"""Pacote de automações de arquivo (Fase 6) — renomear/mover com reversibilidade.

Os dois motores PUROS da fase vivem aqui (sem IA, sem disco, sem banco):

- `naming`  — resolve padrões `{campo}`/`{campo:fmt}` para um NOME/PASTA sanitizado
              e confinado sob a raiz-base (AUT-01/AUT-02). Campo faltante/inválido →
              `None` (caller rebaixa para revisão, D-07). O confinamento contra path
              traversal (V4) vive aqui, na fronteira onde o valor não-confiável da IA
              vira caminho de filesystem.
- `rules`   — avaliador puro de regras condicionais `{campo} [=,>,<,contém] valor`
              combinadas por E/OU; primeira-que-casa-vence (TPL-02/D-04/D-05).
              Coerção numérica via `Decimal` (NUNCA comparação lexicográfica de
              string); dispatch explícito por operador (NUNCA `eval`).

As peças de efeito (fileops/stage/undo) e a orquestração persistente ficam nos
Plans seguintes da fase — estes módulos permanecem funções puras testáveis.
"""

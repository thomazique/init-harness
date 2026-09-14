"""
.claude/hooks/pre_compact.py

PreCompact: não bloqueia (bloquear compactação automática pode travar a sessão).
Grava a pendência para o SessionStart(compact) reinjetar após a compactação.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402


def main() -> None:
    e = L.ler_entrada()
    r = L.raiz(e)
    if L.harness(r) is None:
        return
    arq, estado = L.estado_sessao(r, e.get("session_id", ""))
    p = L.pendencia(r, estado.get("inicio"))
    if p:
        estado["pendente_na_compactacao"] = L.descrever_pendencia(p)
        L.salvar_estado(arq, estado)


if __name__ == "__main__":
    main()

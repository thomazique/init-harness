"""
.claude/hooks/stop_check.py

Stop: impede encerrar o turno com código alterado sem registro na frente.
Bloqueia no máximo 2 vezes por sessão; depois avisa o usuário e libera.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402

MAX_BLOQUEIOS = 2


def main() -> None:
    e = L.ler_entrada()
    r = L.raiz(e)
    if L.harness(r) is None:
        return
    arq, estado = L.estado_sessao(r, e.get("session_id", ""))
    p = L.pendencia(r, estado.get("inicio"))
    if p is None:
        if estado.get("bloqueios"):
            estado["bloqueios"] = 0
            L.salvar_estado(arq, estado)
        return

    n = int(estado.get("bloqueios", 0))
    if n >= MAX_BLOQUEIOS or e.get("stop_hook_active") and n >= 1:
        estado["bloqueios"] = 0
        L.salvar_estado(arq, estado)
        L.emitir({"systemMessage": "harness: registro de contexto continua pendente. " + L.descrever_pendencia(p)})
        return

    estado["bloqueios"] = n + 1
    L.salvar_estado(arq, estado)
    L.emitir({"decision": "block", "reason": L.descrever_pendencia(p)})


if __name__ == "__main__":
    main()

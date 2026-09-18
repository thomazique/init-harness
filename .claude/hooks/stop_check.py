"""
.claude/hooks/stop_check.py

Stop: impede encerrar o turno com código alterado sem registro na frente.
Bloqueia no máximo 2 vezes por sessão; depois avisa o usuário e libera.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402
import skill_evolution as E  # noqa: E402

MAX_BLOQUEIOS = 2


def main() -> None:
    e = L.ler_entrada()
    r = L.raiz(e)
    if L.harness(r) is None:
        return
    try:
        session_file, session_state = L.estado_sessao(r, e.get("session_id", ""))
        event = dict(e)
        if session_state.get("active_skill") and "active_skill" not in event:
            event["active_skill"] = session_state["active_skill"]
        observation = session_state.get("skill_observation")
        consolidated = E.consolidate_hook_experience(event, observation if isinstance(observation, dict) else None)
        if consolidated is not None:
            event["skill_experience"] = consolidated
        captured = E.capture_hook_experience(r, event)
        if captured is not None:
            session_state.pop("skill_observation", None)
            session_state.pop("skill_observation_seen", None)
            L.salvar_estado(session_file, session_state)
    except Exception:
        pass
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

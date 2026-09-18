"""Observa eventos de ferramentas sem capturar prompts ou respostas completas."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import _lib as L  # noqa: E402
import skill_evolution as E  # noqa: E402


def main() -> None:
    event = L.ler_entrada()
    root = L.raiz(event)
    if L.harness(root) is None:
        return
    try:
        E.observe_tool_event(root, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()

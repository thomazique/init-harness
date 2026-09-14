"""
.claude/hooks/guard_files.py

PreToolUse (Read|Edit|Write|MultiEdit|NotebookEdit):
- .env e variantes sensíveis: nega leitura e escrita.
- Conteúdo com segredo de padrão forte: nega. Padrão genérico: pede confirmação.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402


def decisao(tipo: str, motivo: str) -> None:
    L.emitir(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": tipo,
                "permissionDecisionReason": motivo,
            }
        }
    )


def conteudo(ti: dict) -> str:
    partes = [ti.get("content") or "", ti.get("new_string") or "", ti.get("new_source") or ""]
    for ed in ti.get("edits") or []:
        partes.append(ed.get("new_string") or "")
    return "\n".join(partes)


def main() -> None:
    e = L.ler_entrada()
    ti = e.get("tool_input") or {}
    caminho = ti.get("file_path") or ti.get("notebook_path") or ""

    if caminho and L.e_env_sensivel(caminho):
        decisao(
            "deny",
            f"{caminho} é arquivo de ambiente com possíveis credenciais (seção 9 do harness). "
            "Use o .env.example para estrutura ou peça ao usuário o dado necessário.",
        )
        return

    if e.get("tool_name") == "Read":
        return

    fortes, genericos = L.segredos(conteudo(ti))
    if fortes:
        decisao(
            "deny",
            "Conteúdo contém padrão de segredo (" + ", ".join(fortes) + "). "
            "Credencial vai para variável de ambiente, nunca para código.",
        )
        return
    if genericos:
        decisao("ask", "Conteúdo atribui valor literal a nome sensível (" + ", ".join(genericos) + ").")


if __name__ == "__main__":
    main()

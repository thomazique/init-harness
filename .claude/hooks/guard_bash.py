"""
.claude/hooks/guard_bash.py

PreToolUse (Bash|PowerShell): bloqueia ou pede confirmação para comandos de risco.
- Dados destrutivos: decisão pelo ambiente detectado em .init-harness/config.json.
- Git e arquivos destrutivos: sempre pede confirmação.
- Burlar verificação (--no-verify, HARNESS_SEM_CONTEXTO): sempre nega.
- Referência a .env (exceto .example/.sample/.template/.dist): pede confirmação.
"""

from __future__ import annotations

import re
import sys

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402

DADOS = [
    r"\bmigrate:(fresh|reset|refresh|rollback)\b",
    r"\bdb:(wipe|drop|reset)\b",
    r"(?i)\bdrop\s+(table|database|schema)\b",
    r"(?i)\btruncate\s+(table\s+)?[\w.\"`]",
    r"(?i)\bdelete\s+from\s+[\w.\"`]+(?![^;]*\bwhere\b)",
    r"\bdropdb\b",
    r"manage\.py\s+flush\b",
    r"\bprisma\s+migrate\s+reset\b",
    r"\bdocker\s+volume\s+(rm|prune)\b",
    r"\bdocker(-compose|\s+compose)\s+down\b.*(\s-v\b|--volumes)",
    r"\bdocker\s+system\s+prune\b",
]
GIT_ARQUIVOS = [
    r"\brm\s+(-[^\s]*[rR][^\s]*|.*--recursive)",
    r"(?i)\bRemove-Item\b.*-Recurse",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[^\s]*f",
    r"\bgit\s+push\b.*(--force\b|--force-with-lease\b|\s-f\b)",
    r"\bgit\s+branch\s+-D\b",
]
BURLAR = [r"--no-verify\b", r"\bHARNESS_SEM_CONTEXTO\b", r"\bgit\s+config\b(?!.*--get).*\bcore\.hooksPath\b"]
ENV_REF = re.compile(r"(?<![\w/.-])(?:[\w./\\-]*[/\\])?\.env(?:\.([\w-]+))?(?![\w.-])")


def casa(padroes: list[str], cmd: str) -> str | None:
    for p in padroes:
        if re.search(p, cmd):
            return p
    return None


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


def main() -> None:
    e = L.ler_entrada()
    cmd = (e.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    r = L.raiz(e)
    h = L.harness(r)

    if casa(BURLAR, cmd):
        decisao(
            "deny",
            "Comando altera ou contorna a verificação de commit do harness "
            "(--no-verify, HARNESS_SEM_CONTEXTO ou core.hooksPath). Isso exige ação humana direta.",
        )
        return

    if casa(DADOS, cmd):
        nome, politica = L.ambiente(r, h)
        autonomia = (h or {}).get("autonomia") or {}
        piso = autonomia.get("destrutivo", "confirmar")
        if piso == "bloquear":
            politica = "bloquear"
        elif piso == "confirmar" and politica == "permitir":
            politica = "confirmar"
        if politica == "bloquear":
            decisao(
                "deny",
                f"Comando destrutivo de dados com ambiente '{nome}', cuja política é bloquear "
                f"(.init-harness/config.json). Confirme o ambiente com o usuário.",
            )
            return
        if politica == "confirmar":
            decisao("ask", f"Comando destrutivo de dados no ambiente '{nome}'.")
            return

    if casa(GIT_ARQUIVOS, cmd):
        decisao("ask", "Comando destrutivo de git ou arquivos (seção 9 do harness).")
        return

    for m in ENV_REF.finditer(cmd):
        sufixo = (m.group(1) or "").lower()
        if sufixo not in L.ENV_SUFIXOS_PERMITIDOS:
            decisao("ask", "Comando referencia arquivo .env; o conteúdo pode expor credenciais (seção 9 do harness).")
            return


if __name__ == "__main__":
    main()

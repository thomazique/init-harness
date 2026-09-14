"""
.githooks/pre_commit.py

Verificações de commit do harness. Vale para humano, Claude Code e qualquer outra ferramenta.
Falha (exit 1): segredo forte, arquivo .env sensível, método do harness em modo cliente,
código sem contexto (docs/ai/ ou specs/) quando o harness está implantado.
Aviso (não falha): segredo genérico, mudança estrutural sem docs/ai/ESTRUTURA.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / ".claude" / "hooks"))
import _lib as L  # noqa: E402


def main() -> int:
    gd = Path(L.git(["rev-parse", "--git-dir"], RAIZ) or ".git")
    gd = gd if gd.is_absolute() else RAIZ / gd
    if any((gd / x).exists() for x in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")):
        return 0

    staged = [c for c in L.git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], RAIZ).splitlines() if c]
    if not staged:
        return 0

    h = L.harness(RAIZ)
    erros: list[str] = []
    avisos: list[str] = []

    for c in staged:
        if L.e_env_sensivel(c):
            erros.append(f"{c}: arquivo de ambiente sensível não pode ser commitado.")

    if h and h.get("modo") == "cliente":
        metodo = [c for c in staged if any(c == m or c.startswith(m) for m in L.METODO_CLIENTE)]
        for c in metodo:
            erros.append(f"{c}: arquivo de método do harness em modo cliente (deve ficar em .git/info/exclude).")

    diff = L.git(["diff", "--cached", "-U0", "--no-color"], RAIZ)
    atual = "?"
    for linha in diff.splitlines():
        if linha.startswith("+++ "):
            atual = linha[6:] if linha.startswith("+++ b/") else linha[4:]
            continue
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        fortes, genericos = L.segredos(linha[1:])
        for f in fortes:
            erros.append(f"{atual}: padrão de segredo ({f}).")
        for g in genericos:
            avisos.append(f"{atual}: valor literal atribuído a '{g}'. Confirme que não é credencial.")

    if h:
        codigo = [c for c in staged if L.e_codigo(c) and not c.startswith((".claude/", ".githooks/"))]
        contexto = [c for c in staged if L.e_contexto(c)]
        if codigo and not contexto and os.environ.get("HARNESS_SEM_CONTEXTO") != "1":
            erros.append(
                "Código em stage sem atualização de docs/ai/ ou specs/ (seção 14 do harness). "
                "Registre o checkpoint na frente. Commit humano sem frente: HARNESS_SEM_CONTEXTO=1 git commit ..."
            )
        estruturais = [c for c in codigo if L.e_estrutural(c)]
        if estruturais and "docs/ai/ESTRUTURA.md" not in staged:
            avisos.append(
                "Mudança possivelmente estrutural ("
                + ", ".join(estruturais[:5])
                + ") sem docs/ai/ESTRUTURA.md em stage."
            )

    for a in dict.fromkeys(avisos):
        print(f"harness [aviso] {a}", file=sys.stderr)
    for e in dict.fromkeys(erros):
        print(f"harness [erro] {e}", file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

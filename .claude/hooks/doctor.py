"""
.claude/hooks/doctor.py

Diagnóstico portátil da instalação do harness. Não altera arquivos.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import _lib as L  # noqa: E402


def _duplicate_ids(path: Path, pattern: str, first_column_only: bool = False) -> dict[str, list[int]]:
    """Encontra identificadores duplicados sem interpretar o restante do Markdown."""
    if not path.is_file():
        return {}
    matches: dict[str, list[int]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if first_column_only:
            subject = line.split("|", 2)[1] if line.lstrip().startswith("|") and "|" in line else ""
        else:
            subject = line
        found = re.search(pattern, subject)
        if found:
            matches.setdefault(found.group(1), []).append(line_number)
    return {identifier: lines for identifier, lines in matches.items() if len(lines) > 1}


def main() -> int:
    raiz = Path(__file__).resolve().parents[2]
    erros: list[str] = []
    avisos: list[str] = []
    ok: list[str] = []

    h = L.harness(raiz)
    if h is None:
        erros.append(".init-harness/config.json ausente")
        h = {}
    elif h.get("_erro"):
        erros.append(".init-harness/config.json inválido")
    else:
        ok.append(f"config.json versão {h.get('harness_version', '?')}")
        if h.get("modo") not in {"proprio", "cliente"}:
            erros.append(f"modo inválido em config.json: {h.get('modo', '?')}")
        if h.get("grafo") not in {"graphify", "manual"}:
            erros.append(f"grafo inválido em config.json: {h.get('grafo', '?')}")
        if h.get("instalado_em") in {None, "", "AAAA-MM-DD"}:
            erros.append("instalado_em não foi preenchido em config.json")
        providers = h.get("providers")
        if not isinstance(providers, list) or not providers or not set(providers) <= {"claude", "codex"}:
            erros.append("providers deve conter claude e/ou codex")
        autonomia = h.get("autonomia")
        chaves_autonomia = {
            "tarefas_seguras",
            "apos_checkpoint",
            "producao",
            "destrutivo",
            "politica_negocio",
        }
        if not isinstance(autonomia, dict) or set(autonomia) != chaves_autonomia:
            erros.append("bloco autonomia ausente ou incompleto")
        memoria = h.get("memoria")
        if not isinstance(memoria, dict) or not isinstance(memoria.get("mcp"), bool):
            erros.append("bloco memoria.mcp ausente ou inválido")

    nucleo = raiz / "INIT-HARNESS.md"
    if not nucleo.exists():
        if h.get("modo") == "proprio":
            erros.append("INIT-HARNESS.md ausente no modo proprio")
    else:
        texto = nucleo.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"harness_version:\s*([\w.]+)", texto)
        versao_doc = m.group(1) if m else None
        if not versao_doc:
            erros.append("versão não encontrada em INIT-HARNESS.md")
        elif versao_doc != h.get("harness_version"):
            erros.append(f"versões divergentes: documento={versao_doc}, config.json={h.get('harness_version', '?')}")
        else:
            ok.append(f"documento e manifesto na versão {versao_doc}")

    obrigatorios = [
        "CLAUDE.md",
        "docs/ai/ESTADO.md",
        "docs/ai/ESTRUTURA.md",
        "docs/ai/DECISOES.md",
        "docs/ai/DEBITOS.md",
        ".claude/settings.json",
        ".claude/hooks/_lib.py",
        ".claude/hooks/session_start.py",
        ".claude/hooks/guard_bash.py",
        ".claude/hooks/guard_files.py",
        ".claude/hooks/memory.py",
        ".claude/hooks/memory_mcp.py",
        ".claude/hooks/pre_compact.py",
        ".claude/hooks/stop_check.py",
        ".claude/hooks/doctor.py",
        ".githooks/pre-commit",
        ".githooks/pre_commit.py",
        ".init-harness/schema/config.schema.json",
    ]
    providers = h.get("providers", [])
    if "codex" in providers:
        obrigatorios.append("AGENTS.md")
    if h.get("modo") != "cliente":
        obrigatorios.append("tests/guardrails/test_guardrails.py")
    ausentes = [c for c in obrigatorios if not (raiz / c).exists()]
    if ausentes:
        erros.append("arquivos obrigatórios ausentes: " + ", ".join(ausentes))
    else:
        ok.append("arquivos de enforcement presentes")

    settings = raiz / ".claude" / "settings.json"
    if "claude" in providers and not settings.exists():
        erros.append("provider claude configurado, mas .claude/settings.json está ausente")
    elif "claude" in providers:
        try:
            dados = json.loads(settings.read_text(encoding="utf-8"))
            serializado = json.dumps(dados)
            faltantes = [
                nome
                for nome in (
                    "session_start.py",
                    "guard_bash.py",
                    "guard_files.py",
                    "pre_compact.py",
                    "stop_check.py",
                )
                if nome not in serializado
            ]
            if faltantes:
                erros.append("hooks ausentes de settings.json: " + ", ".join(faltantes))
            else:
                ok.append("hooks registrados em settings.json")
            if re.search(r'"command"\s*:\s*"(?:[A-Za-z]:[\\/]|/)', serializado):
                avisos.append("settings.json contém comando com caminho absoluto; a instalação pode não ser portátil")
        except (OSError, json.JSONDecodeError):
            erros.append(".claude/settings.json inválido")

    dentro_git = bool(L.git(["rev-parse", "--is-inside-work-tree"], raiz))
    if not dentro_git:
        erros.append("diretório não é um worktree Git")
    else:
        hooks_path = L.git(["config", "--get", "core.hooksPath"], raiz)
        if hooks_path.replace("\\", "/").rstrip("/") != ".githooks":
            erros.append(f"core.hooksPath esperado .githooks, encontrado {hooks_path or 'não definido'}")
        else:
            ok.append("pre-commit configurado em .githooks")

    if not shutil.which("uv"):
        avisos.append(
            "uv não está no PATH; instale-o e exponha seu diretório de binários ao cliente de IA e ao Git "
            "(Linux/macOS: ~/.local/bin ou ~/.cargo/bin; Windows: %USERPROFILE%\\.local\\bin)."
        )
    else:
        ok.append("uv disponível no PATH")

    updates = raiz / ".init-harness" / "updates"
    pending_updates = list(updates.rglob("*.new")) if updates.is_dir() else []
    if pending_updates:
        avisos.append(f"{len(pending_updates)} atualização(ões) de kit pendentes de revisão em .init-harness/updates/")

    if h.get("grafo") == "graphify":
        if shutil.which("graphify"):
            resultado = subprocess.run(
                ["graphify", "--version"],
                cwd=raiz,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            saida = (resultado.stdout + resultado.stderr).strip()
            if resultado.returncode:
                erros.append("graphify está no PATH, mas graphify --version falhou")
            else:
                versao = next(
                    (linha for linha in saida.splitlines() if linha.startswith("graphify ")),
                    "disponível",
                )
                ok.append(versao)
                if "warning:" in saida.lower():
                    avisos.append("graphify reportou deriva entre pacote e integração do projeto")
        else:
            erros.append("grafo configurado como graphify, mas o comando não está no PATH")

    por_branch: dict[str, list[str]] = {}
    for arq, fm in L.frentes(raiz):
        if fm.get("status") == "concluida":
            continue
        branch = str(fm.get("branch", "")).strip()
        if branch and branch not in {"-", "?"}:
            por_branch.setdefault(branch, []).append(arq.name)
    for branch, nomes in por_branch.items():
        if len(nomes) > 1:
            erros.append(f"branch {branch} tem múltiplas frentes não concluídas: {', '.join(nomes)}")

    duplicate_sources = (
        (raiz / "docs/ai/DECISOES.md", r"^##\s+(D-\d+)\b", False),
        (raiz / "docs/ai/DEBITOS.md", r"\b(DB-\d+)\b", True),
    )
    for path, pattern, first_column_only in duplicate_sources:
        for identifier, lines in _duplicate_ids(path, pattern, first_column_only).items():
            erros.append(
                f"ID duplicado {identifier} em {path.relative_to(raiz).as_posix()}: linhas {', '.join(map(str, lines))}"
            )

    for mensagem in ok:
        print(f"[OK] {mensagem}")
    for mensagem in avisos:
        print(f"[AVISO] {mensagem}")
    for mensagem in erros:
        print(f"[ERRO] {mensagem}")
    print(f"Resultado: {len(erros)} erro(s), {len(avisos)} aviso(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

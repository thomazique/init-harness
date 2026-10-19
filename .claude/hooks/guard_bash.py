"""
.claude/hooks/guard_bash.py

PreToolUse (Bash|PowerShell): bloqueia ou pede confirmação para comandos de risco.
- Burlar verificação (--no-verify, HARNESS_SEM_CONTEXTO): sempre nega.
- Catastrófico em comando simples (remoção recursiva da raiz ou da home, force-push na branch
  padrão): sempre nega. Comando composto cai na confirmação, nunca em palpite.
- Ofuscação ou comando não inspecionável (${IFS}, base64 para shell, iex, -EncodedCommand):
  pede confirmação.
- Dados destrutivos: decisão pelo ambiente detectado em .init-harness/config.json.
- Git, arquivos e infraestrutura destrutivos (inclusive PowerShell e cmd): pede confirmação.
  Remoção só de pastas de build conhecidas (node_modules, dist, __pycache__...) passa direto.
- Padrões extras do projeto (guardrails.bash_extras): só acrescentam confirmação, nunca removem.
- Referência a .env (exceto .example/.sample/.template/.dist): pede confirmação.

Casamento por texto é melhor esforço, não fronteira de segurança: comando montado em tempo de
execução escapa. Bloqueio duro de verdade fica nas regras deny de .claude/settings.json.
Famílias de padrões adaptadas do /careful do gstack (MIT).
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
    # Descartar o trabalho não commitado da árvore inteira.
    r"\bgit\s+checkout\b[^;&|\n]*\s\.(?=\s|$|[;&|])",
    r"\bgit\s+restore\b(?![^;&|\n]*--staged)[^;&|\n]*\s\.(?=\s|$|[;&|])",
    r"\bgit\s+restore\b[^;&|\n]*--worktree\b[^;&|\n]*\s\.(?=\s|$|[;&|])",
    r"\bgit\s+stash\s+(clear|drop)\b",
    # Force-push sem flag (refspec com +) e remoção de branch remota.
    r"\bgit\s+push\b[^;&|\n]*\s\+\S",
    r"\bgit\s+push\b[^;&|\n]*(--delete\b|\s:\S)",
    # Infraestrutura.
    r"\bkubectl\s+delete\b",
    r"\bhelm\s+(uninstall|delete)\b",
    r"\bterraform\s+(destroy\b|apply\b[^;&|\n]*-destroy\b)",
    r"\bdocker\s+(container\s+)?rm\b[^;&|\n]*\s-[^\s]*f",
    # PowerShell (aliases e prefixo de parâmetro) e cmd.
    r"(?i)(?:^|[;|&({]\s*)(?:remove-item|ri|rm|del|erase|rd|rmdir)\b[^;|&\n]*?\s-(?:r\w*|fo\w*)\b",
    r"(?i)\b(?:rd|rmdir|del|erase)\b[^;|&\n]*\s/s\b",
    r"(?i)\b(?:Format-Volume|Clear-Disk|Initialize-Disk|Clear-Content)\b",
    r"(?i)\[(?:System\.)?IO\.(?:Directory|File)\]::Delete\b",
]
OFUSCACAO = [
    r"\$\{?IFS\b",
    r"\$\(\s*echo[^)]*base64",
    r"\bbase64\s+(?:-d|-D|--decode)\b[^|\n]*\|\s*(?:ba|z|da)?sh\b",
    r"(?i)\b(?:iex|invoke-expression)\b",
    r"(?i)\b(?:powershell|pwsh)(?:\.exe)?\b[^;|&\n]*\s-(?:e|ec|en|enc\w*)\s",
]
BURLAR = [r"--no-verify\b", r"\bHARNESS_SEM_CONTEXTO\b", r"\bgit\s+config\b(?!.*--get).*\bcore\.hooksPath\b"]
ENV_REF = re.compile(r"(?<![\w/.-])(?:[\w./\\-]*[/\\])?\.env(?:\.([\w-]+))?(?![\w.-])")

VERBOS_REMOCAO = {"rm", "remove-item", "ri", "del", "erase", "rd", "rmdir"}
VERBOS_CMD = {"del", "erase", "rd", "rmdir"}
ALVOS_RAIZ = {
    "/",
    "//",
    "/*",
    "\\",
    "~",
    "~/",
    "~/*",
    "$home",
    "$home/",
    "${home}",
    "${home}/",
    "$env:userprofile",
    "%userprofile%",
}
DRIVE_RAIZ = re.compile(r"^[a-z]:[\\/]?\*?$", re.IGNORECASE)
PASTAS_BUILD = {
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".cache",
    ".turbo",
    "coverage",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}


def casa(padroes: list[str], cmd: str) -> str | None:
    for p in padroes:
        if re.search(p, cmd):
            return p
    return None


def simples(cmd: str) -> bool:
    """Comando único, sem encadeamento nem substituição: só nele um bloqueio duro é seguro."""
    return not any(s in cmd for s in (";", "&&", "||", "|", "\n", "`", "$("))


def _tokens(cmd: str) -> list[str]:
    tokens = [t.strip("\"'") for t in cmd.split()]
    while tokens and tokens[0] == "sudo":
        tokens = tokens[1:]
    return tokens


def _alvos_remocao(tokens: list[str]) -> list[str]:
    cmd_style = tokens[0].lower() in VERBOS_CMD
    alvos = []
    for t in tokens[1:]:
        if t.startswith("-") or t in {"--", "&"} or re.match(r"^\d?[<>]", t):
            continue
        if cmd_style and re.fullmatch(r"/[a-zA-Z]", t):
            continue
        alvos.append(t)
    return alvos


def _recursivo(tokens: list[str]) -> bool:
    for t in tokens[1:]:
        if t == "--recursive" or re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*", t):
            return True
        if re.fullmatch(r"(?i)-r\w*", t) or t.lower() == "/s":
            return True
    return False


def remove_raiz(cmd: str) -> bool:
    """Remoção recursiva em que todo alvo é a raiz do sistema ou a home."""
    if not simples(cmd):
        return False
    tokens = _tokens(cmd)
    if not tokens or tokens[0].lower() not in VERBOS_REMOCAO or not _recursivo(tokens):
        return False
    alvos = _alvos_remocao(tokens)
    return bool(alvos) and all(a.lower() in ALVOS_RAIZ or DRIVE_RAIZ.match(a) for a in alvos)


def remove_so_build(cmd: str) -> bool:
    """Remoção cujos alvos são todos pastas de build relativas conhecidas."""
    if not simples(cmd):
        return False
    tokens = _tokens(cmd)
    if not tokens or tokens[0].lower() not in VERBOS_REMOCAO:
        return False
    alvos = _alvos_remocao(tokens)
    if not alvos:
        return False
    for alvo in alvos:
        caminho = alvo.replace("\\", "/").rstrip("/")
        partes = caminho.split("/")
        if (
            not caminho
            or caminho.startswith(("/", "~", "$", "%"))
            or re.match(r"^[a-zA-Z]:", caminho)
            or any(c in caminho for c in "*?")
            or ".." in partes
            or partes[-1] not in PASTAS_BUILD
        ):
            return False
    return True


def _branches_padrao(r) -> set[str]:
    ref = L.git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], r)
    return {ref.split("/", 1)[1]} if "/" in ref else {"main", "master"}


def force_push_padrao(cmd: str, r) -> bool:
    """Force-push (-f, --force ou refspec com +) cujo destino é a branch padrão."""
    if not simples(cmd):
        return False
    tokens = _tokens(cmd)
    if tokens[:2] != ["git", "push"]:
        return False
    args = tokens[2:]
    forca = any(t in {"-f", "--force"} for t in args) or any(t.startswith("+") for t in args)
    if not forca:
        return False
    posicionais = [t for t in args if not t.startswith("-")]
    refspecs = posicionais[1:]
    atual = L.branch_atual(r)
    destinos = set()
    for ref in refspecs or ["HEAD"]:
        destino = ref.lstrip("+").split(":", 1)[-1].removeprefix("refs/heads/")
        destinos.add(atual if destino == "HEAD" else destino)
    return bool(destinos & _branches_padrao(r))


def extras_do_projeto(h: dict | None) -> list[str]:
    padroes = ((h or {}).get("guardrails") or {}).get("bash_extras") or []
    validos = []
    for p in padroes:
        if not isinstance(p, str):
            continue
        try:
            re.compile(p)
        except re.error:
            continue
        validos.append(p)
    return validos


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

    if remove_raiz(cmd):
        decisao("deny", "Remoção recursiva da raiz do sistema ou da home. Isso exige ação humana direta.")
        return
    if force_push_padrao(cmd, r):
        decisao(
            "deny", "Force-push na branch padrão reescreve o histórico compartilhado. Isso exige ação humana direta."
        )
        return

    if casa(OFUSCACAO, cmd):
        decisao(
            "ask",
            "Comando ofuscado ou não inspecionável (${IFS}, base64 para shell, iex, -EncodedCommand). "
            "Leia o comando antes de aprovar (seção 9 do harness).",
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

    if casa(GIT_ARQUIVOS, cmd) and not remove_so_build(cmd):
        decisao("ask", "Comando destrutivo de git, arquivos ou infraestrutura (seção 9 do harness).")
        return

    if casa(extras_do_projeto(h), cmd):
        decisao("ask", "Comando casa padrão de risco do projeto (guardrails.bash_extras em .init-harness/config.json).")
        return

    for m in ENV_REF.finditer(cmd):
        sufixo = (m.group(1) or "").lower()
        if sufixo not in L.ENV_SUFIXOS_PERMITIDOS:
            decisao("ask", "Comando referencia arquivo .env; o conteúdo pode expor credenciais (seção 9 do harness).")
            return


if __name__ == "__main__":
    main()

"""
.claude/hooks/_lib.py

Funções compartilhadas pelos hooks do harness e pelo pre-commit.
Somente biblioteca padrão (Python >= 3.10). Executado via `uv run --no-project`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONTEXTO_PREFIXOS = ("docs/ai/", "specs/")
CONTEXTO_ARQUIVOS = ("CLAUDE.md", "INIT-HARNESS.md", "AGENTS.md", "CODEX.md")
IGNORAR_PREFIXOS = ("graphify-out/",)
CODIGO_PREFIXOS = (".claude/hooks/", ".githooks/", ".github/workflows/")
CODIGO_EXTENSOES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".php",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".cs",
    ".fs",
    ".fsx",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".swift",
    ".m",
    ".mm",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".psm1",
    ".psd1",
    ".bat",
    ".cmd",
    ".sql",
    ".graphql",
    ".gql",
    ".proto",
    ".tf",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
}
CODIGO_NOMES = {
    "Dockerfile",
    "Makefile",
    "Justfile",
    "Procfile",
    "Gemfile",
    "Rakefile",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "composer.json",
    "composer.lock",
    "pyproject.toml",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "pom.xml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
METODO_CLIENTE = (
    "INIT-HARNESS.md",
    ".claude/skills/init-harness/",
    ".claude/skills/spec/",
    ".claude/skills/record/",
    ".claude/skills/pilares/",
    ".claude/skills/commit/",
    ".claude/skills/offboarding/",
    ".claude/agents/auditor-pilares.md",
    ".claude/settings.init-harness.json",
    "tests/guardrails/",
)
ENV_SUFIXOS_PERMITIDOS = {"example", "sample", "template", "dist"}

# Padrões fortes: alta confiança de segredo real.
SEGREDOS_FORTES = [
    ("chave AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("chave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("token GitHub (fine-grained)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}")),
    ("token Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("chave Stripe live", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}")),
    ("chave Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("chave OpenAI", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("chave Google API", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
]
# Padrão genérico: atribuição literal a nome sensível. Pede confirmação, não bloqueia.
SEGREDO_GENERICO = re.compile(
    r"(?i)\b(password|passwd|senha|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
    r"\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"
)
PLACEHOLDER = re.compile(
    r"(?i)(\$\{|env\(|os\.environ|process\.env|getenv|<|xxx|your[_-]|change[_-]?me|example|placeholder)"
)

ESTRUTURAIS = [
    re.compile(p)
    for p in (
        r"(^|/)migrations?/",
        r"(^|/)alembic/versions/",
        r"(^|/)routes?/",
        r"(^|/)(jobs?|queues?|dags|schedul\w*)/",
        r"(^|/)(docker-compose[^/]*\.ya?ml|Dockerfile[^/]*)$",
        r"(^|/)(package\.json|composer\.json|pyproject\.toml|requirements[^/]*\.txt|go\.mod|Cargo\.toml)$",
    )
]


# ---------------------------------------------------------------- entrada/saída


def ler_entrada() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def emitir(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


# ---------------------------------------------------------------- git e raiz


def git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def raiz(entrada: dict) -> Path:
    """Raiz do worktree em que o agente está (cwd segue o worktree; CLAUDE_PROJECT_DIR não)."""
    base = Path(entrada.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    top = git(["rev-parse", "--show-toplevel"], base)
    return Path(top) if top else base


def branch_atual(r: Path) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"], r) or "?"


def dir_estado(r: Path) -> Path:
    gd = git(["rev-parse", "--git-dir"], r)
    p = (r / gd) if gd and not Path(gd).is_absolute() else Path(gd or r / ".git")
    d = p / "init-harness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def estado_sessao(r: Path, session_id: str) -> tuple[Path, dict]:
    arq = dir_estado(r) / f"sessao-{re.sub(r'[^A-Za-z0-9_-]', '_', session_id or 'sem-id')}.json"
    try:
        return arq, json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return arq, {}


def salvar_estado(arq: Path, dados: dict) -> None:
    try:
        arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- config.json


def harness(r: Path) -> dict | None:
    arq = r / ".init-harness" / "config.json"
    if not arq.exists():
        return None
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return {"_erro": "config.json inválido"}


def ler_dotenv(arq: Path) -> dict:
    valores = {}
    try:
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.startswith("export "):
                linha = linha[7:]
            k, v = linha.split("=", 1)
            valores[k.strip()] = v.strip().strip("'\"")
    except Exception:
        pass
    return valores


def ambiente(r: Path, h: dict | None) -> tuple[str, str]:
    """Retorna (nome, politica_destrutiva). Política: permitir | confirmar | bloquear."""
    amb = (h or {}).get("ambientes") or {}
    padrao = amb.get("se_indeterminado", "bloquear")
    for regra in amb.get("regras") or []:
        arq = r / regra.get("arquivo", "")
        if not arq.is_file():
            continue
        valor = ler_dotenv(arq).get(regra.get("chave", ""))
        if valor is not None and valor in (regra.get("valores") or []):
            return regra.get("nome", "?"), regra.get("destrutivo", padrao)
    return "indeterminado", padrao


# ---------------------------------------------------------------- frentes


def frontmatter(arq: Path) -> dict:
    """Frontmatter plano: 'chave: valor' por linha, entre '---'."""
    dados = {}
    try:
        linhas = arq.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return dados
    inicio = next((i for i, linha in enumerate(linhas) if linha.lstrip("\ufeff").strip()), None)
    if inicio is None or linhas[inicio].lstrip("\ufeff").strip() != "---":
        return dados
    for linha in linhas[inicio + 1 :]:
        if linha.strip() == "---":
            break
        if ":" in linha:
            k, v = linha.split(":", 1)
            dados[k.strip()] = v.strip()
    return dados


def secao(arq: Path, titulo: str) -> str:
    try:
        texto = arq.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    m = re.search(rf"^##\s+{re.escape(titulo)}\s*$(.*?)(?=^##\s|\Z)", texto, re.M | re.S)
    if not m:
        return ""
    corpo = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return corpo


def frentes(r: Path) -> list[tuple[Path, dict]]:
    d = r / "docs" / "ai" / "frentes"
    if not d.is_dir():
        return []
    return [(a, frontmatter(a)) for a in sorted(d.glob("*.md"))]


def frente_da_branch(r: Path, branch: str) -> tuple[Path, dict] | None:
    candidatas = frentes_da_branch(r, branch)
    return candidatas[0] if len(candidatas) == 1 else None


def frentes_da_branch(r: Path, branch: str) -> list[tuple[Path, dict]]:
    """Frentes não concluídas da branch; mais de uma significa posse ambígua."""
    return [(arq, fm) for arq, fm in frentes(r) if fm.get("branch") == branch and fm.get("status") != "concluida"]


# ---------------------------------------------------------------- arquivos e segredos


def e_env_sensivel(caminho: str) -> bool:
    nome = Path(caminho.replace("\\", "/")).name
    if nome == ".env":
        return True
    if nome.startswith(".env."):
        return nome.split(".", 2)[2].lower() not in ENV_SUFIXOS_PERMITIDOS
    return False


def segredos(texto: str) -> tuple[list[str], list[str]]:
    """Retorna (fortes, genericos) como nomes de tipo, nunca o valor."""
    fortes = [nome for nome, p in SEGREDOS_FORTES if p.search(texto)]
    genericos = []
    for m in SEGREDO_GENERICO.finditer(texto):
        if not PLACEHOLDER.search(m.group(0)):
            genericos.append(m.group(1).lower())
    return fortes, sorted(set(genericos))


def e_contexto(caminho: str) -> bool:
    caminho = caminho.replace("\\", "/")
    return caminho in CONTEXTO_ARQUIVOS or caminho.startswith(CONTEXTO_PREFIXOS)


def e_codigo(caminho: str) -> bool:
    caminho = caminho.replace("\\", "/")
    if e_contexto(caminho) or caminho.startswith(IGNORAR_PREFIXOS):
        return False
    if "__pycache__/" in caminho or e_env_sensivel(caminho):
        return False
    nome = Path(caminho).name
    if caminho.startswith(CODIGO_PREFIXOS):
        return True
    if nome in CODIGO_NOMES or nome.startswith(("Dockerfile.", "requirements")):
        return True
    return Path(nome).suffix.lower() in CODIGO_EXTENSOES


def e_estrutural(caminho: str) -> bool:
    return any(p.search(caminho) for p in ESTRUTURAIS)


# ---------------------------------------------------------------- pendência de registro


def arquivos_alterados(r: Path) -> list[str]:
    try:
        saida = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(r),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        ).stdout
    except Exception:
        return []
    arquivos = []
    itens = saida.split("\0")
    i = 0
    while i < len(itens):
        item = itens[i]
        i += 1
        if len(item) < 4:
            continue
        arquivos.append(item[3:])
        if item[0] in "RC":  # renomeado/copiado: próximo item é a origem
            i += 1
    return arquivos


def mtime_alteracao(r: Path, caminho: str) -> float:
    """mtime do arquivo; se removido, do diretório pai existente mais próximo."""
    alvo = r / caminho
    while True:
        try:
            return alvo.stat().st_mtime
        except OSError:
            if alvo == r or alvo.parent == alvo:
                return 0.0
            alvo = alvo.parent


def pendencia(r: Path, desde: float | None) -> dict | None:
    """Código alterado depois do último registro na frente da branch."""
    alterados = []
    ultimo = 0.0
    for c in arquivos_alterados(r):
        if not e_codigo(c):
            continue
        mt = mtime_alteracao(r, c)
        if desde and mt < desde:
            continue
        alterados.append(c)
        ultimo = max(ultimo, mt)
    if not alterados:
        return None
    branch = branch_atual(r)
    candidatas = frentes_da_branch(r, branch)
    if not candidatas:
        return {"tipo": "sem_frente", "branch": branch, "arquivos": alterados}
    if len(candidatas) > 1:
        return {
            "tipo": "frentes_ambiguas",
            "branch": branch,
            "frentes": [arq.relative_to(r).as_posix() for arq, _ in candidatas],
            "arquivos": alterados,
        }
    arq, _ = candidatas[0]
    if arq.stat().st_mtime >= ultimo:
        return None
    return {
        "tipo": "frente_desatualizada",
        "branch": branch,
        "frente": arq.relative_to(r).as_posix(),
        "arquivos": alterados,
    }


def descrever_pendencia(p: dict) -> str:
    lista = ", ".join(p["arquivos"][:8]) + (" e outros" if len(p["arquivos"]) > 8 else "")
    if p["tipo"] == "sem_frente":
        return (
            f"Há código alterado na branch {p['branch']} ({lista}) e nenhuma frente registrada para ela "
            f"em docs/ai/frentes/. Pela seção 4 do harness, a frente é criada antes de alterar código."
        )
    if p["tipo"] == "frentes_ambiguas":
        nomes = ", ".join(p["frentes"])
        return (
            f"Há mais de uma frente não concluída na branch {p['branch']} ({nomes}). "
            "Mantenha no máximo uma frente aberta por branch ou use branches/worktrees separados."
        )
    return (
        f"Há código alterado ({lista}) depois da última atualização de {p['frente']}. "
        f"Pela seção 6 do harness, o checkpoint é registrado na frente antes de encerrar."
    )

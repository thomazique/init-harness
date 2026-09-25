"""CLI de instalação, atualização e diagnóstico do init-harness."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VERSION = "4.0.0"

MANAGED_FILES = (
    "INIT-HARNESS.md",
    ".claude/settings.init-harness.json",
    ".claude/hooks/_lib.py",
    ".claude/hooks/doctor.py",
    ".claude/hooks/guard_bash.py",
    ".claude/hooks/guard_files.py",
    ".claude/hooks/memory.py",
    ".claude/hooks/memory_mcp.py",
    ".claude/hooks/skill_evolution.py",
    ".claude/hooks/skill_observe.py",
    ".claude/hooks/skill_worker.py",
    ".claude/hooks/skill_reviewer.py",
    ".claude/hooks/pre_compact.py",
    ".claude/hooks/session_start.py",
    ".claude/hooks/stop_check.py",
    ".claude/agents/auditor-pilares.md",
    ".claude/agents/executor.md",
    ".claude/agents/revisor.md",
    ".codex/agents/harness_executor.toml",
    ".codex/agents/harness_auditor.toml",
    ".codex/config.toml",
    ".githooks/pre-commit",
    ".githooks/pre_commit.py",
    ".init-harness/schema/config.schema.json",
    ".init-harness/schema/orquestracao.schema.json",
    "tests/guardrails/__init__.py",
    "tests/guardrails/test_guardrails.py",
)
MANAGED_TREES = (
    ".claude/skills/init-harness",
    ".claude/skills/frontend",
    ".claude/skills/commit",
    ".claude/skills/pilares",
    ".claude/skills/spec",
    ".claude/skills/record",
    ".claude/skills/evolve",
    ".claude/skills/orquestrar",
)
PROJECT_TEMPLATES = {
    "CLAUDE.md": ".claude/skills/init-harness/templates/CLAUDE.template.md",
    "AGENTS.md": ".claude/skills/init-harness/templates/AGENTS.template.md",
    "docs/ai/ESTADO.md": ".claude/skills/init-harness/templates/ESTADO.template.md",
    "docs/ai/ESTRUTURA.md": ".claude/skills/init-harness/templates/ESTRUTURA.template.md",
    "docs/ai/DECISOES.md": ".claude/skills/init-harness/templates/DECISOES.template.md",
    "docs/ai/DEBITOS.md": ".claude/skills/init-harness/templates/DEBITOS.template.md",
}
LEGACY_REPLACEMENTS = (
    ("CLAUDE-HARNESS.md", "INIT-HARNESS.md"),
    ("claude-harness", "init-harness"),
    (".claude/harness.json", ".init-harness/config.json"),
    (".claude\\harness.json", ".init-harness\\config.json"),
    ("settings.harness.json", "settings.init-harness.json"),
    ("harness.template.json", "config.template.json"),
    ("cold-start", "init-harness"),
)
LEGACY_AGENT_SUBAGENT_RULE = (
    "- Usar subagentes somente quando as instruções ativas permitirem e houver\n"
    "  paralelismo real; subagentes nunca editam `docs/ai/`."
)
MULTIAGENT_AGENT_RULE = (
    "- Em toda solicitação de implementação, ler `.claude/skills/orquestrar/SKILL.md`.\n"
    "  Ler `.init-harness/orquestracao.json` e perguntar qual perfil será a base desta atividade;\n"
    "  registrar a escolha na frente correspondente.\n"
    "  O agente principal coordena e delega a execução; não implementa diretamente\n"
    "  subtarefas atribuídas. Usar `harness_executor` para executar e\n"
    "  `harness_auditor` para revisar o diff agregado em sandbox somente de leitura.\n"
    "- Se o cliente ou a sessão não disponibilizar subagentes, informar a limitação e\n"
    "  parar antes de implementar em modo de agente único."
)


class Reporter:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.changed: list[str] = []
        self.preserved: list[str] = []
        self.warnings: list[str] = []

    def change(self, message: str) -> None:
        self.changed.append(message)
        print(f"[{'PLANO' if self.dry_run else 'OK'}] {message}")

    def preserve(self, message: str) -> None:
        self.preserved.append(message)
        print(f"[PRESERVADO] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"[AVISO] {message}")


def kit_root(explicit: Path | None = None) -> Path:
    return (explicit or Path(__file__).resolve().parent).resolve()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _managed_baseline(target: Path, relative: str) -> Path:
    return target / ".init-harness" / "managed-baselines" / relative


def _managed_candidate(target: Path, relative: str) -> Path:
    return target / ".init-harness" / "updates" / (relative + ".new")


def _write_managed_baseline(target: Path, relative: str, content: bytes) -> None:
    baseline = _managed_baseline(target, relative)
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_bytes(content)


def managed_paths(source: Path) -> list[str]:
    """Arquivos do kit que o instalador gerencia; bytecode gerado ao rodar runners não entra."""
    files = list(MANAGED_FILES)
    for tree in MANAGED_TREES:
        root = source / tree
        files.extend(
            str(path.relative_to(source)).replace("\\", "/")
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    return list(dict.fromkeys(files))


def copy_managed(source: Path, target: Path, reporter: Reporter) -> None:
    for relative in managed_paths(source):
        src = source / relative
        dst = target / relative
        if not src.is_file():
            raise FileNotFoundError(f"arquivo gerenciado ausente no kit: {relative}")
        new_content = src.read_bytes()
        baseline = _managed_baseline(target, relative)
        old_content = baseline.read_bytes() if baseline.is_file() else None
        local_content = dst.read_bytes() if dst.is_file() else None
        if local_content == new_content:
            candidate = _managed_candidate(target, relative)
            if not reporter.dry_run and candidate.is_file():
                candidate.unlink()
            if not reporter.dry_run and old_content != new_content:
                _write_managed_baseline(target, relative, new_content)
            continue
        # Uma cópia anterior do kit sem alteração local pode evoluir normalmente.
        if local_content is None or (old_content is not None and local_content == old_content):
            reporter.change(f"atualizar {relative}")
            if not reporter.dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(new_content)
                _write_managed_baseline(target, relative, new_content)
            continue
        # Sem baseline (instalações antigas) ou com edição local, a única opção
        # segura é preservar o contexto do projeto e oferecer a nova versão.
        candidate = _managed_candidate(target, relative)
        reporter.preserve(relative)
        reporter.warn(f"atualização de {relative} disponível em {candidate.relative_to(target).as_posix()}")
        if not reporter.dry_run:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(new_content)
            if old_content is None:
                _write_managed_baseline(target, relative, new_content)


def merge_settings(current: Any, required: Any) -> Any:
    if isinstance(current, dict) and isinstance(required, dict):
        merged = dict(current)
        for key, value in required.items():
            merged[key] = merge_settings(merged[key], value) if key in merged else value
        return merged
    if isinstance(current, list) and isinstance(required, list):
        merged = list(current)
        for value in required:
            if not any(_settings_item_matches(existing, value) for existing in merged):
                merged.append(value)
        return merged
    return current


def _settings_item_matches(current: Any, required: Any) -> bool:
    """Reconhece um hook pelo evento, matcher e script, não pelo comando inteiro.

    Um projeto pode precisar prefixar PATH ou usar outro lançador. Nessa situação,
    a entrada local equivalente deve prevalecer durante o upgrade.
    """
    if not isinstance(current, dict) or not isinstance(required, dict):
        return current == required
    current_hooks, required_hooks = current.get("hooks"), required.get("hooks")
    if not isinstance(current_hooks, list) or not isinstance(required_hooks, list):
        return current == required

    def scripts(hooks: list[Any]) -> tuple[str, ...]:
        values = []
        for hook in hooks:
            if not isinstance(hook, dict):
                return ()
            args = hook.get("args")
            if isinstance(args, list) and args and isinstance(args[-1], str):
                values.append(Path(args[-1]).name)
                continue
            command = hook.get("command")
            matches = re.findall(r"([A-Za-z0-9_.-]+\.py)\b", command) if isinstance(command, str) else []
            if len(matches) != 1:
                return ()
            values.append(matches[0])
        return tuple(values)

    current_scripts, required_scripts = scripts(current_hooks), scripts(required_hooks)
    return (
        bool(current_scripts)
        and current.get("matcher", "") == required.get("matcher", "")
        and current_scripts == required_scripts
    )


def install_settings(source: Path, target: Path, providers: list[str], reporter: Reporter) -> None:
    if "claude" not in providers:
        return
    template = load_json(source / ".claude/settings.init-harness.json")
    destination = target / ".claude/settings.json"
    current = load_json(destination) if destination.exists() else {}
    merged = merge_settings(current, template)
    if merged == current:
        return
    reporter.change("mesclar hooks e permissões em .claude/settings.json")
    if not reporter.dry_run:
        write_json(destination, merged)


def create_project_files(source: Path, target: Path, providers: list[str], reporter: Reporter) -> None:
    for destination, template in PROJECT_TEMPLATES.items():
        if destination == "AGENTS.md" and "codex" not in providers:
            continue
        dst = target / destination
        if dst.exists():
            reporter.preserve(destination)
            continue
        reporter.change(f"criar {destination}")
        if not reporter.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = (source / template).read_text(encoding="utf-8")
            if destination == "AGENTS.md":
                content = content.replace("<!-- <CAMINHO-ABSOLUTO-DO-PROJETO>/AGENTS.md -->\n\n", "")
            dst.write_text(content, encoding="utf-8")


def migrate_multiagent_adapter(target: Path, providers: list[str], reporter: Reporter) -> None:
    """Atualiza apenas a regra padrão antiga de subagentes no AGENTS.md."""
    if "codex" not in providers:
        return
    path = target / "AGENTS.md"
    if not path.is_file():
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    if LEGACY_AGENT_SUBAGENT_RULE not in content:
        return
    reporter.change("atualizar regra padrão de subagentes em AGENTS.md")
    if not reporter.dry_run:
        path.write_text(content.replace(LEGACY_AGENT_SUBAGENT_RULE, MULTIAGENT_AGENT_RULE), encoding="utf-8")


def config_data(
    source: Path, mode: str, providers: list[str], graph: str, memory_mcp: bool, bootstrap: bool
) -> dict[str, Any]:
    data = load_json(source / ".claude/skills/init-harness/templates/config.template.json")
    data["instalado_em"] = date.today().isoformat()
    data["modo"] = mode
    data["providers"] = providers
    data["grafo"] = graph
    data["memoria"]["mcp"] = memory_mcp
    data["bootstrap"]["opt_in"] = bootstrap
    return data


def install_config(
    source: Path,
    target: Path,
    mode: str,
    providers: list[str],
    graph: str,
    memory_mcp: bool,
    bootstrap: bool,
    reporter: Reporter,
) -> dict[str, Any]:
    destination = target / ".init-harness/config.json"
    if destination.exists():
        data = load_json(destination)
        original = json.dumps(data, sort_keys=True)
        data["harness_version"] = VERSION
        data["$schema"] = "./schema/config.schema.json"
        data.setdefault("providers", providers)
        defaults = config_data(source, mode, providers, graph, memory_mcp, bootstrap)
        data.setdefault("autonomia", defaults["autonomia"])
        data.setdefault("memoria", defaults["memoria"])
        data.setdefault("bootstrap", defaults["bootstrap"])
        data.setdefault("orquestracao", defaults["orquestracao"])
        if bootstrap:
            data["bootstrap"]["opt_in"] = True
        if json.dumps(data, sort_keys=True) != original:
            reporter.change("atualizar metadados de .init-harness/config.json")
            if not reporter.dry_run:
                write_json(destination, data)
    else:
        data = config_data(source, mode, providers, graph, memory_mcp, bootstrap)
        reporter.change("criar .init-harness/config.json")
        if not reporter.dry_run:
            write_json(destination, data)
    return data


def install_orchestration_config(source: Path, target: Path, reporter: Reporter) -> None:
    """Cria os perfis iniciais sem substituir escolhas locais em instalações existentes."""
    destination = target / ".init-harness/orquestracao.json"
    if destination.exists():
        reporter.preserve(".init-harness/orquestracao.json (perfis de agentes configurados pelo projeto)")
        return
    template = source / ".claude/skills/orquestrar/templates/orquestracao.template.json"
    data = load_json(template)
    data["$schema"] = "./schema/orquestracao.schema.json"
    reporter.change("criar .init-harness/orquestracao.json com perfis iniciais de agentes")
    if not reporter.dry_run:
        write_json(destination, data)


def replace_legacy_references(target: Path, reporter: Reporter) -> None:
    candidates = [target / "CLAUDE.md", target / "AGENTS.md", target / ".claude/settings.json"]
    docs = target / "docs" / "ai"
    if docs.is_dir():
        candidates.extend(docs.rglob("*.md"))
    specs = target / "specs"
    if specs.is_dir():
        candidates.extend(specs.rglob("*.md"))
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        updated = text
        for old, new in LEGACY_REPLACEMENTS:
            updated = updated.replace(old, new)
        if updated == text:
            continue
        reporter.change(f"atualizar referências legadas em {path.relative_to(target).as_posix()}")
        if not reporter.dry_run:
            path.write_text(updated, encoding="utf-8")


def migrate_legacy(target: Path, reporter: Reporter) -> None:
    moves = (
        ("CLAUDE-HARNESS.md", "INIT-HARNESS.md"),
        (".claude/harness.json", ".init-harness/config.json"),
        (".claude/settings.harness.json", ".claude/settings.init-harness.json"),
        (".claude/skills/cold-start", ".claude/skills/init-harness"),
        (
            ".claude/skills/init-harness/templates/harness.template.json",
            ".claude/skills/init-harness/templates/config.template.json",
        ),
    )
    migrated = False
    for old, new in moves:
        src = target / old
        dst = target / new
        if not src.exists():
            continue
        if dst.exists():
            reporter.warn(f"legado mantido porque o destino já existe: {old}")
            continue
        reporter.change(f"migrar {old} -> {new}")
        if not reporter.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
        migrated = True
    # Referências só são trocadas no momento de uma migração material. Rodar esta
    # substituição em todo upgrade destrói registros históricos deliberados.
    if migrated:
        replace_legacy_references(target, reporter)


def append_lines(path: Path, lines: list[str], reporter: Reporter) -> None:
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    missing = [line for line in lines if line not in existing.splitlines()]
    if not missing:
        return
    reporter.change(f"adicionar entradas em {path.name}: {', '.join(missing)}")
    if reporter.dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(existing + prefix + "\n".join(missing) + "\n", encoding="utf-8")


def git_output(target: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(target), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def client_method_paths(source: Path) -> list[str]:
    """Carrega a política única de exclusão usada também pelo pre-commit."""
    lib_path = source / ".claude" / "hooks" / "_lib.py"
    spec = importlib.util.spec_from_file_location("init_harness_client_policy", lib_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("não foi possível carregar a política de modo cliente")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = getattr(module, "METODO_CLIENTE", ())
    if not isinstance(paths, tuple) or not all(isinstance(path, str) for path in paths):
        raise RuntimeError("METODO_CLIENTE inválido")
    return list(paths)


def configure_git(source: Path, target: Path, mode: str, init_git: bool, force_hooks: bool, reporter: Reporter) -> None:
    if not git_output(target, "rev-parse", "--is-inside-work-tree"):
        if not init_git:
            reporter.warn("destino não é repositório Git; use --init-git para inicializá-lo")
            return
        reporter.change("executar git init")
        if not reporter.dry_run:
            result = subprocess.run(["git", "init", str(target)], check=False)
            if result.returncode:
                raise RuntimeError("git init falhou")
    hooks_path = git_output(target, "config", "--get", "core.hooksPath")
    normalized_hooks = hooks_path.replace("\\", "/").rstrip("/")
    if normalized_hooks == ".githooks":
        pass
    elif hooks_path and not force_hooks:
        reporter.warn(f"core.hooksPath já usa {hooks_path}; não alterado sem --force-hooks")
    else:
        reporter.change("configurar core.hooksPath=.githooks")
        if not reporter.dry_run:
            subprocess.run(["git", "-C", str(target), "config", "core.hooksPath", ".githooks"], check=True)
    if mode == "cliente":
        git_dir = git_output(target, "rev-parse", "--git-dir")
        if git_dir:
            base = Path(git_dir)
            exclude = (base if base.is_absolute() else target / base) / "info" / "exclude"
            append_lines(
                exclude,
                client_method_paths(source),
                reporter,
            )


def run_optional_bootstrap(target: Path, reporter: Reporter) -> None:
    """Executa apenas a leitura do mapa inicial já existente; não dispara Graphify automaticamente."""
    script = target / ".claude" / "hooks" / "memory.py"
    reporter.change("executar bootstrap revisável do mapa inicial")
    if reporter.dry_run:
        return
    result = subprocess.run(
        [sys.executable, str(script), "bootstrap"],
        cwd=target,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        reporter.warn("bootstrap opcional não pôde ser executado: " + result.stderr.strip())
        return
    print("Bootstrap opcional:")
    print(result.stdout.strip())


def run_project_bootstrap(target: Path, reporter: Reporter) -> None:
    """Materializa o contexto inicial sem inventar fatos de domínio."""
    paths = (
        target / ".init-harness" / "bootstrap",
        target / ".init-harness" / "skills",
        target / ".init-harness" / "memory",
        target / "docs" / "ai" / "memoria",
    )
    for path in paths:
        if path.is_dir():
            continue
        reporter.change(f"criar {path.relative_to(target).as_posix()}")
        if not reporter.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    skill_script = target / ".claude" / "hooks" / "skill_evolution.py"
    skill_sync = {"status": "skipped", "skills": []}
    if skill_script.is_file() and not reporter.dry_run:
        result = subprocess.run(
            [sys.executable, str(skill_script), "sync"],
            cwd=target,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        skill_sync = {"status": "ok" if result.returncode == 0 else "failed", "output": result.stdout[-2000:]}
        if result.returncode:
            reporter.warn("catálogo inicial de skills não pôde ser sincronizado: " + result.stderr.strip())

    graph = target / "graphify-out" / "graph.json"
    fronts = target / "docs" / "ai" / "frentes"
    debts = target / "docs" / "ai" / "DEBITOS.md"
    report = {
        "schema_version": 1,
        "generated_at": date.today().isoformat(),
        "analysis": {
            "graph": {"present": graph.is_file(), "path": "graphify-out/graph.json"},
            "fronts": (
                sorted(path.relative_to(target).as_posix() for path in fronts.glob("*.md")) if fronts.is_dir() else []
            ),
            "debts": {"present": debts.is_file(), "path": "docs/ai/DEBITOS.md"},
            "project_files": len([path for path in target.rglob("*") if path.is_file() and ".git" not in path.parts]),
        },
        "skills": skill_sync,
        "notes": [
            "Fatos estruturais foram apenas descobertos; hipóteses continuam revisáveis.",
            "A análise Graphify não é executada automaticamente pelo instalador.",
        ],
    }
    report_path = target / ".init-harness" / "bootstrap" / "report.json"
    reporter.change("registrar relatório inicial do bootstrap")
    if not reporter.dry_run:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_install(args: argparse.Namespace, source: Path) -> int:
    target = args.target.resolve()
    if not target.is_dir():
        raise NotADirectoryError(target)
    reporter = Reporter(args.dry_run)
    migrate_legacy(target, reporter)
    providers = list(dict.fromkeys(args.providers))
    copy_managed(source, target, reporter)
    create_project_files(source, target, providers, reporter)
    migrate_multiagent_adapter(target, providers, reporter)
    install_settings(source, target, providers, reporter)
    install_config(source, target, args.mode, providers, args.graph, args.memory_mcp, args.bootstrap, reporter)
    install_orchestration_config(source, target, reporter)
    append_lines(
        target / ".gitignore",
        [
            "graphify-out/cache/",
            ".init-harness/state/",
            ".init-harness/memory/",
            ".init-harness/managed-baselines/",
            ".init-harness/updates/",
        ],
        reporter,
    )
    configure_git(source, target, args.mode, args.init_git, args.force_hooks, reporter)
    if args.memory_mcp:
        reporter.preserve("MCP de memória opt-in: registre `python .claude/hooks/memory_mcp.py` no cliente desejado")
    if args.bootstrap:
        run_optional_bootstrap(target, reporter)
        run_project_bootstrap(target, reporter)
    print(
        f"Resultado: {len(reporter.changed)} mudança(s), "
        f"{len(reporter.preserved)} arquivo(s) preservado(s), {len(reporter.warnings)} aviso(s)."
    )
    return 0


def run_upgrade(args: argparse.Namespace, source: Path) -> int:
    target = args.target.resolve()
    config = target / ".init-harness/config.json"
    legacy = target / ".claude/harness.json"
    data = load_json(config if config.exists() else legacy) if config.exists() or legacy.exists() else {}
    args.mode = data.get("modo", "proprio")
    args.providers = data.get("providers", ["claude", "codex"])
    args.graph = data.get("grafo", "graphify")
    args.memory_mcp = bool((data.get("memoria") or {}).get("mcp", False))
    args.bootstrap = bool((data.get("bootstrap") or {}).get("opt_in", False))
    args.init_git = False
    return run_install(args, source)


def run_doctor(args: argparse.Namespace) -> int:
    script = args.target.resolve() / ".claude/hooks/doctor.py"
    if not script.is_file():
        print(f"[ERRO] doctor não instalado em {script}", file=sys.stderr)
        return 1
    return subprocess.run([sys.executable, str(script)], cwd=args.target, check=False).returncode


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="init-harness", description="Instala e atualiza o init-harness.")
    root.add_argument("--version", action="version", version=VERSION)
    commands = root.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install", help="Instala o harness em um projeto.")
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--mode", choices=("proprio", "cliente"), default="proprio")
    install.add_argument("--providers", nargs="+", choices=("claude", "codex"), default=["claude", "codex"])
    install.add_argument("--graph", choices=("graphify", "manual"), default="graphify")
    install.add_argument("--memory-mcp", action="store_true", help="Marca a integração MCP de memória como opt-in.")
    install.add_argument(
        "--bootstrap",
        action="store_true",
        help="Executa o mapa inicial revisável se houver Graphify; nunca extrai ou cria estrutura automaticamente.",
    )
    install.add_argument("--init-git", action="store_true")
    install.add_argument("--force-hooks", action="store_true")
    install.add_argument("--dry-run", action="store_true")

    upgrade = commands.add_parser("upgrade", help="Atualiza uma instalação existente preservando o projeto.")
    upgrade.add_argument("--target", type=Path, required=True)
    upgrade.add_argument("--force-hooks", action="store_true")
    upgrade.add_argument("--dry-run", action="store_true")

    doctor = commands.add_parser("doctor", help="Executa o diagnóstico de uma instalação.")
    doctor.add_argument("--target", type=Path, required=True)
    return root


def main(argv: list[str] | None = None, source: Path | None = None) -> int:
    args = parser().parse_args(argv)
    root = kit_root(source)
    if args.command == "install":
        return run_install(args, root)
    if args.command == "upgrade":
        return run_upgrade(args, root)
    return run_doctor(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

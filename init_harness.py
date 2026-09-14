"""CLI de instalação, atualização e diagnóstico do init-harness."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VERSION = "2.1.0"

MANAGED_FILES = (
    "INIT-HARNESS.md",
    ".claude/settings.init-harness.json",
    ".claude/hooks/_lib.py",
    ".claude/hooks/doctor.py",
    ".claude/hooks/guard_bash.py",
    ".claude/hooks/guard_files.py",
    ".claude/hooks/pre_compact.py",
    ".claude/hooks/session_start.py",
    ".claude/hooks/stop_check.py",
    ".claude/agents/auditor-pilares.md",
    ".claude/agents/revisor.md",
    ".githooks/pre-commit",
    ".githooks/pre_commit.py",
    ".init-harness/schema/config.schema.json",
    "tests/guardrails/__init__.py",
    "tests/guardrails/test_guardrails.py",
)
MANAGED_TREES = (
    ".claude/skills/init-harness",
    ".claude/skills/commit",
    ".claude/skills/pilares",
    ".claude/skills/spec",
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


def copy_managed(source: Path, target: Path, reporter: Reporter) -> None:
    files = list(MANAGED_FILES)
    for tree in MANAGED_TREES:
        root = source / tree
        files.extend(str(path.relative_to(source)).replace("\\", "/") for path in root.rglob("*") if path.is_file())
    for relative in dict.fromkeys(files):
        src = source / relative
        dst = target / relative
        if not src.is_file():
            raise FileNotFoundError(f"arquivo gerenciado ausente no kit: {relative}")
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        reporter.change(f"sincronizar {relative}")
        if not reporter.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def merge_settings(current: Any, required: Any) -> Any:
    if isinstance(current, dict) and isinstance(required, dict):
        merged = dict(current)
        for key, value in required.items():
            merged[key] = merge_settings(merged[key], value) if key in merged else value
        return merged
    if isinstance(current, list) and isinstance(required, list):
        merged = list(current)
        for value in required:
            if value not in merged:
                merged.append(value)
        return merged
    return current


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
            shutil.copy2(source / template, dst)


def config_data(source: Path, mode: str, providers: list[str], graph: str) -> dict[str, Any]:
    data = load_json(source / ".claude/skills/init-harness/templates/config.template.json")
    data["instalado_em"] = date.today().isoformat()
    data["modo"] = mode
    data["providers"] = providers
    data["grafo"] = graph
    return data


def install_config(
    source: Path,
    target: Path,
    mode: str,
    providers: list[str],
    graph: str,
    reporter: Reporter,
) -> dict[str, Any]:
    destination = target / ".init-harness/config.json"
    if destination.exists():
        data = load_json(destination)
        original = json.dumps(data, sort_keys=True)
        data["harness_version"] = VERSION
        data["$schema"] = "./schema/config.schema.json"
        data.setdefault("providers", providers)
        data.setdefault("autonomia", config_data(source, mode, providers, graph)["autonomia"])
        if json.dumps(data, sort_keys=True) != original:
            reporter.change("atualizar metadados de .init-harness/config.json")
            if not reporter.dry_run:
                write_json(destination, data)
    else:
        data = config_data(source, mode, providers, graph)
        reporter.change("criar .init-harness/config.json")
        if not reporter.dry_run:
            write_json(destination, data)
    return data


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


def configure_git(target: Path, mode: str, init_git: bool, force_hooks: bool, reporter: Reporter) -> None:
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
                [
                    "INIT-HARNESS.md",
                    ".claude/skills/init-harness/",
                    ".claude/skills/spec/",
                    ".claude/skills/pilares/",
                    ".claude/skills/commit/",
                    "tests/guardrails/",
                ],
                reporter,
            )


def run_install(args: argparse.Namespace, source: Path) -> int:
    target = args.target.resolve()
    if not target.is_dir():
        raise NotADirectoryError(target)
    reporter = Reporter(args.dry_run)
    migrate_legacy(target, reporter)
    providers = list(dict.fromkeys(args.providers))
    copy_managed(source, target, reporter)
    create_project_files(source, target, providers, reporter)
    install_settings(source, target, providers, reporter)
    install_config(source, target, args.mode, providers, args.graph, reporter)
    append_lines(target / ".gitignore", ["graphify-out/cache/", ".init-harness/state/"], reporter)
    configure_git(target, args.mode, args.init_git, args.force_hooks, reporter)
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

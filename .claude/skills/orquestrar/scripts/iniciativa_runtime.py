"""Runtime hierarquico para iniciativas encaminhadas pelo runner CLI."""

from __future__ import annotations

import asyncio
import copy
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
SPECIALTIES = {"frontend", "backend", "security", "deploy_cicd", "database"}


def _specialty_prompt(root: Path, repo: Path, specialty: str) -> str:
    """Carrega a orientação versionada da especialidade da frente."""
    prompts = Path(__file__).resolve().parent.parent / "templates" / "supervisores"
    prompt_file = prompts / f"{specialty}.md"
    if not prompt_file.is_file():
        raise ValueError(f"preset de supervisor ausente: {specialty}")
    content = prompt_file.read_text(encoding="utf-8")
    if specialty == "frontend":
        skill_candidates = [repo / ".claude/skills/frontend/SKILL.md", root / ".claude/skills/frontend/SKILL.md"]
        skill = next((path for path in skill_candidates if path.is_file()), None)
        content += "\n\nFONTE FRONTEND DO PROJETO:\n"
        content += (
            skill.read_text(encoding="utf-8")
            if skill
            else "Skill frontend não localizada neste repositório; siga os padrões existentes da aplicação."
        )
    return content


def _validar_manifesto(data: Any) -> tuple[str, str, dict[str, int], list[dict[str, Any]]]:
    if not isinstance(data, dict) or data.get("contract_version") != 1:
        raise ValueError("manifesto precisa declarar contract_version: 1")
    initiative = data.get("initiative_id")
    profile = data.get("profile")
    limits = data.get("limits")
    fronts = data.get("fronts")
    if not isinstance(initiative, str) or not _ID.fullmatch(initiative):
        raise ValueError("initiative_id inválido")
    if not isinstance(profile, str) or not profile:
        raise ValueError("profile é obrigatório")
    keys = ("max_parallel", "max_agents", "max_calls", "max_builders_per_supervisor")
    if not isinstance(limits, dict) or any(type(limits.get(k)) is not int or limits[k] < 1 for k in keys):
        raise ValueError("limits precisa conter inteiros positivos: " + ", ".join(keys))
    if not isinstance(fronts, list) or not fronts:
        raise ValueError("fronts precisa conter ao menos uma frente")
    ids: set[str] = set()
    for front in fronts:
        if not isinstance(front, dict):
            raise ValueError("cada frente precisa ser um objeto")
        for key in ("id", "team", "specialty", "spec", "repository", "branch", "base_commit"):
            if not isinstance(front.get(key), str) or not front[key].strip():
                raise ValueError(f"frente precisa informar {key}")
        if not _ID.fullmatch(front["id"]) or front["id"] in ids:
            raise ValueError("id de frente inválido ou duplicado")
        ids.add(front["id"])
        if front["specialty"] not in SPECIALTIES:
            raise ValueError(f"specialty inválida em {front['id']}; use uma de: {', '.join(sorted(SPECIALTIES))}")
        if not isinstance(front.get("dependencies"), list) or not all(
            isinstance(x, str) for x in front["dependencies"]
        ):
            raise ValueError(f"dependencies inválidas na frente {front['id']}")
        if not isinstance(front.get("scope"), list) or not all(isinstance(x, str) and x for x in front["scope"]):
            raise ValueError(f"scope precisa ser uma lista de caminhos na frente {front['id']}")
    for front in fronts:
        if any(dep not in ids or dep == front["id"] for dep in front["dependencies"]):
            raise ValueError(f"dependência de frente inválida em {front['id']}")
    _toposort(fronts, "id", "dependencies")
    return initiative, profile, {k: limits[k] for k in keys}, fronts


def _toposort(items: list[dict[str, Any]], id_key: str, deps_key: str) -> list[str]:
    by_id = {item[id_key]: item for item in items}
    pending = {key: set(item.get(deps_key, [])) for key, item in by_id.items()}
    output: list[str] = []
    while pending:
        ready = sorted(key for key, deps in pending.items() if deps <= set(output))
        if not ready:
            raise ValueError("dependências contêm ciclo ou referência inexistente")
        for key in ready:
            output.append(key)
            del pending[key]
    return output


def _strict_json(text: str, expected: set[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} deve retornar JSON estrito, sem cercas ou texto adicional: {exc}") from exc
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"formato JSON inválido em {label}; chaves esperadas: {sorted(expected)}")
    return value


def _lista_texto(obj: dict[str, Any], key: str, label: str) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}.{key} precisa ser uma lista de textos")
    return value


def _validar_plan(front: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"plano {front['id']} precisa conter tasks")
    _lista_texto(plan, "interfaces", front["id"])
    _lista_texto(plan, "questions", front["id"])
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not _ID.fullmatch(task["id"]):
            raise ValueError(f"task com id inválido em {front['id']}")
        if task["id"] in seen:
            raise ValueError(f"task id duplicado em {front['id']}")
        seen.add(task["id"])
        for key in ("objective",):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError(f"task {task['id']} precisa de {key}")
        for key in ("files", "depends_on", "acceptance"):
            if not isinstance(task.get(key), list) or not all(isinstance(x, str) for x in task[key]):
                raise ValueError(f"task {task['id']}.{key} precisa ser uma lista de textos")
        if not task["files"] or not task["acceptance"]:
            raise ValueError(f"task {task['id']} precisa declarar arquivos e critérios de aceite")
        if "pair_with" in task and (
            not isinstance(task["pair_with"], list) or not all(isinstance(x, str) for x in task["pair_with"])
        ):
            raise ValueError(f"task {task['id']}.pair_with precisa ser uma lista de ids")
        for name in task["files"]:
            path = PurePosixPath(name.replace("\\", "/"))
            if (
                path.is_absolute()
                or ".." in path.parts
                or not name
                or name.endswith("/")
                or any(char in name for char in "*?[]")
            ):
                raise ValueError(f"caminho de arquivo inseguro em {task['id']}: {name}")
            if not any(
                name.startswith(pattern) if pattern.endswith("/") else fnmatch.fnmatch(name, pattern)
                for pattern in front["scope"]
            ):
                raise ValueError(f"arquivo fora do scope da frente {front['id']}: {name}")
    local_ids = {task["id"] for task in tasks}
    for task in tasks:
        if any(dep not in local_ids for dep in task["depends_on"]):
            raise ValueError(f"dependência de tarefa inválida em {task['id']}")
        if any(peer not in local_ids or peer == task["id"] for peer in task.get("pair_with", [])):
            raise ValueError(f"pair_with inválido em {task['id']}")
    _toposort(tasks, "id", "depends_on")
    for task in tasks:
        if len(set(task.get("pair_with", []))) != len(task.get("pair_with", [])):
            raise ValueError(f"pair_with duplicado em {task['id']}")
        for peer in task.get("pair_with", []):
            if task["id"] not in next(t for t in tasks if t["id"] == peer).get("pair_with", []):
                raise ValueError(f"pair_with deve ser recíproco entre {task['id']} e {peer}")
    return plan


def _repo_path(root: Path, front: dict[str, Any]) -> Path:
    value = Path(front["repository"])
    path = (value if value.is_absolute() else root / value).resolve()
    if not path.is_dir():
        raise ValueError(f"repositório da frente {front['id']} não existe: {path}")
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True, check=False)
    if branch.returncode != 0 or branch.stdout.strip() != front["branch"]:
        raise ValueError(f"branch ativa do repositório não corresponde à frente {front['id']}")
    base = subprocess.run(
        ["git", "merge-base", "--is-ancestor", front["base_commit"], "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    if base.returncode != 0:
        raise ValueError(f"base_commit não é ancestral do HEAD da frente {front['id']}")
    return path


async def _invoke(
    root: Path,
    state: dict[str, Any],
    state_file: Path,
    profile: dict[str, Any],
    role: str,
    prompt: str,
    call_id: str,
    timeout: int,
    semaphore: asyncio.Semaphore,
    cwd: Path | None = None,
    read_only: bool = False,
) -> tuple[str, str]:
    from invocar_agentes import comando_para

    limits = state["limits"]
    if state["calls"] >= limits["max_calls"]:
        raise ValueError("limite global max_calls atingido; iniciativa pausada")
    fallback = {"supervisor": "auditor", "construtor": "executor"}
    agent = profile.get(role) or profile.get(fallback.get(role, ""))
    if not isinstance(agent, dict) or agent.get("modo") != "cli" or agent.get("provedor") not in {"claude", "codex"}:
        raise ValueError(f"perfil requer papel CLI {role}")
    if not shutil.which("claude" if agent["provedor"] == "claude" else "codex"):
        raise ValueError(f"CLI do papel {role} indisponível")
    state["calls"] += 1
    state["reserved_calls"].append(call_id)
    _save(state_file, state)
    async with semaphore:
        process = await asyncio.create_subprocess_exec(
            *comando_para(
                agent["provedor"], {**agent, "_papel": "auditor" if role == "auditor" or read_only else "executor"}
            ),
            cwd=cwd or root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(prompt.encode("utf-8")), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ValueError(f"timeout na chamada {call_id}")
    if process.returncode != 0:
        raise ValueError(
            f"CLI falhou na chamada {call_id} (código {process.returncode}): {err.decode('utf-8', 'replace')[-1200:]}"
        )
    return out.decode("utf-8", "replace").strip(), agent["modelo"]


def _save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _changed_files(repo: Path) -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise ValueError(f"não foi possível ler git status em {repo}")
    paths: set[str] = set()
    for item in result.stdout.split(b"\0"):
        if len(item) >= 4:
            name = item[3:].decode("utf-8", "replace").replace("\\", "/")
            if not name.startswith(".init-harness/state/"):
                paths.add(name)
    return paths


def _change_context(repo: Path, paths: list[str]) -> str:
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", *paths], cwd=repo, capture_output=True, text=True, check=False
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    additions = []
    for name in untracked:
        file_path = (repo / name).resolve()
        if file_path.is_relative_to(repo) and file_path.is_file():
            try:
                body = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                body = "[arquivo não textual ou não legível como UTF-8]"
            additions.append(f"\nNOVO ARQUIVO: {name}\n{body[:12000]}")
    return (diff + "\n".join(additions))[-50000:]


def _safe_repo_file(repo: Path, worktree: Path, relative: str) -> tuple[Path, Path]:
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"caminho inseguro no escopo de construtor: {relative}")
    source = repo.joinpath(*rel.parts)
    target = worktree.joinpath(*rel.parts)
    for base, path in ((repo, source), (worktree, target)):
        current = base
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"caminho com symlink recusado no escopo: {relative}")
        if not path.parent.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"caminho sai do repositório: {relative}")
    return source, target


def _file_fingerprint(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"somente arquivos regulares podem integrar: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{path.stat().st_mode & 0o777}:{digest}"


def _repo_snapshot(repo: Path) -> tuple[set[str], dict[str, str]]:
    paths = _changed_files(repo)
    fingerprints: dict[str, str] = {}
    for name in paths:
        path = repo.joinpath(*PurePosixPath(name).parts)
        if path.is_symlink():
            fingerprints[name] = "symlink:" + str(path.readlink())
        elif path.is_file():
            fingerprints[name] = _file_fingerprint(path)
        else:
            fingerprints[name] = "missing"
    return paths, fingerprints


def _copy_declared_paths(repo: Path, worktree: Path, paths: set[str]) -> None:
    for relative in sorted(paths):
        source, target = _safe_repo_file(repo, worktree, relative)
        if source.exists() and not source.is_file():
            raise ValueError(f"o caminho declarado como arquivo não é arquivo regular: {relative}")
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            if target.is_dir():
                raise ValueError(f"o caminho declarado como arquivo é um diretório: {relative}")
            target.unlink()


def _project_guidance(repo: Path, task_files: list[str]) -> tuple[set[str], str]:
    directories: set[tuple[str, ...]] = {()}
    for name in task_files:
        parts = PurePosixPath(name).parts[:-1]
        directories.update(parts[:index] for index in range(1, len(parts) + 1))
    paths: set[str] = set()
    contents: list[str] = []
    for directory in sorted(directories):
        for filename in ("AGENTS.md", "CLAUDE.md"):
            name = "/".join((*directory, filename))
            file_path = repo.joinpath(*PurePosixPath(name).parts)
            if file_path.is_file() and not file_path.is_symlink():
                try:
                    contents.append(f"\n--- {name} ---\n{file_path.read_text(encoding='utf-8')[:12000]}")
                    paths.add(name)
                except (OSError, UnicodeDecodeError):
                    continue
    return paths, "\n".join(contents)[-30000:]


async def _run_isolated_builder(
    root: Path,
    repo: Path,
    state: dict[str, Any],
    state_file: Path,
    profile: dict[str, Any],
    task: dict[str, Any],
    front_id: str,
    context_paths: set[str],
    prompt: str,
    call_id: str,
    timeout: int,
    semaphore: asyncio.Semaphore,
) -> tuple[str, Path, set[str]]:
    worktree = Path(tempfile.mkdtemp(prefix="init-harness-builder-"))
    registered = False
    keep_worktree = False
    try:
        added = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if added.returncode != 0:
            raise ValueError(f"não foi possível criar worktree isolado para {call_id}: {added.stderr[-1000:]}")
        registered = True
        _copy_declared_paths(repo, worktree, context_paths)
        baseline_status = _changed_files(worktree)
        baseline_hashes = {
            name: _file_fingerprint(_safe_repo_file(repo, worktree, name)[1])
            for name in context_paths - set(task["files"])
        }
        raw, _ = await _invoke(
            root, state, state_file, profile, "construtor", prompt, call_id, timeout, semaphore, worktree
        )
        after_status = _changed_files(worktree)
        unexpected_status = after_status - baseline_status - set(task["files"])
        changed_context = [
            name
            for name, before in baseline_hashes.items()
            if _file_fingerprint(_safe_repo_file(repo, worktree, name)[1]) != before
        ]
        if unexpected_status or changed_context:
            raise ValueError(
                f"construtor alterou arquivos fora do escopo: {sorted(unexpected_status | set(changed_context))}"
            )
        keep_worktree = True
        return raw, worktree, after_status - baseline_status
    finally:
        if registered and not keep_worktree:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True, check=False
            )
        if not keep_worktree:
            shutil.rmtree(worktree, ignore_errors=True)


def _integrate_task_files(repo: Path, worktree: Path, task: dict[str, Any]) -> None:
    prepared: list[tuple[Path, Path, str]] = []
    for name in task["files"]:
        source, _ = _safe_repo_file(repo, worktree, name)
        destination = repo.joinpath(*PurePosixPath(name).parts)
        if not destination.parent.resolve().is_relative_to(repo.resolve()):
            raise ValueError(f"caminho de destino sai do repositório: {name}")
        if any(part.is_symlink() for part in [destination.parent, *destination.parents] if part != repo.parent):
            raise ValueError(f"destino inclui symlink e foi recusado: {name}")
        if source.exists() and not source.is_file():
            raise ValueError(f"o construtor produziu um caminho que não é arquivo regular: {name}")
        if destination.exists() and destination.is_dir():
            raise ValueError(f"o destino declarado como arquivo é um diretório: {name}")
        prepared.append((source, destination, name))
    for source, destination, name in prepared:
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        elif destination.exists():
            destination.unlink()


def _cleanup_task_worktree(repo: Path, worktree: Path) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True, check=False)
    shutil.rmtree(worktree, ignore_errors=True)


def _pause(
    state: dict[str, Any],
    reason: str,
    questions: list[str] | None = None,
    checkpoint: dict[str, str] | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    state["estado"] = "pausada"
    state["motivo"] = reason
    if questions:
        state["questions"] = questions
    if checkpoint:
        state["pending_checkpoint"] = checkpoint
    if blockers:
        state["blockers"] = blockers
    return state


def _checkpoint_key(checkpoint: dict[str, str]) -> str:
    return ":".join(checkpoint.get(key, "") for key in ("stage", "front_id", "task_id"))


def _resume_with_answers(state: dict[str, Any], answers: Any) -> None:
    checkpoint = state.get("pending_checkpoint")
    questions = state.get("questions", [])
    if not checkpoint or checkpoint.get("stage") not in {
        "plan",
        "agreement",
        "consultation",
        "closure",
        "build",
        "audit",
        "chief_review",
    }:
        raise ValueError("esta pausa não aceita respostas; ajuste o manifesto ou inicie uma nova iniciativa")
    if not isinstance(answers, dict) or set(answers) != {"answers"} or not isinstance(answers["answers"], list):
        raise ValueError('arquivo de respostas deve conter {"answers":[{"question":"...","answer":"..."}]}')
    provided: dict[str, str] = {}
    for item in answers["answers"]:
        if not isinstance(item, dict) or set(item) != {"question", "answer"}:
            raise ValueError("cada resposta precisa conter somente question e answer")
        question, answer = item["question"], item["answer"]
        if not isinstance(question, str) or not isinstance(answer, str) or not answer.strip():
            raise ValueError("pergunta e resposta devem ser textos, e a resposta não pode ser vazia")
        if question in provided:
            raise ValueError(f"resposta duplicada para a pergunta: {question}")
        provided[question] = answer.strip()
    if set(provided) != set(questions):
        raise ValueError("responda exatamente todas as perguntas pendentes, sem omitir nem acrescentar perguntas")
    key = _checkpoint_key(checkpoint)
    state.setdefault("resolutions", {}).setdefault(key, []).extend(
        {"question": q, "answer": provided[q]} for q in questions
    )
    state.setdefault("human_decisions", []).extend(
        {"checkpoint": key, "question": q, "answer": provided[q]} for q in questions
    )
    stage, front_id, task_id = checkpoint["stage"], checkpoint["front_id"], checkpoint.get("task_id", "")
    artifact = {"plan": "plans", "agreement": "agreements", "closure": "closures", "audit": "audits"}.get(stage)
    if artifact:
        state.get(artifact, {}).pop(front_id, None)
        if stage == "plan":
            state.get("models", {}).pop(f"supervisor:{front_id}", None)
    elif stage == "consultation":
        state.get("consultations", {}).get(front_id, {}).pop(task_id, None)
    elif stage == "build":
        state.get("build_attempts", {}).pop(f"{front_id}:{task_id}", None)
    state.pop("questions", None)
    state.pop("blockers", None)
    state.pop("pending_checkpoint", None)
    state["estado"] = "aguardando_auditoria_chefe" if stage == "chief_review" else "em_andamento"
    state["motivo"] = None


def _decision_context(state: dict[str, Any], checkpoint: dict[str, str]) -> str:
    decisions = state.get("resolutions", {}).get(_checkpoint_key(checkpoint), [])
    if not decisions:
        return ""
    return "\nDECISÕES HUMANAS PARA ESTA ETAPA:\n" + json.dumps(decisions, ensure_ascii=False)


def _minimum_remaining_calls(state: dict[str, Any], fronts: list[dict[str, Any]]) -> int:
    needed = sum(front["id"] not in state.get("plans", {}) for front in fronts)
    needed += sum(front["id"] not in state.get("agreements", {}) for front in fronts)
    for front in fronts:
        plan = state.get("plans", {}).get(front["id"], {})
        for task in plan.get("tasks", []):
            if task.get("pair_with") and task["id"] not in state.get("consultations", {}).get(front["id"], {}):
                needed += 1
        if front["id"] not in state.get("closures", {}):
            needed += 1
        needed += sum(f"{front['id']}:{task['id']}" not in state.get("builds", {}) for task in plan.get("tasks", []))
        if front["id"] not in state.get("audits", {}):
            needed += 1
    return needed


def _revision_task_keys(
    state: dict[str, Any], fronts: list[dict[str, Any]], findings: list[dict[str, str]]
) -> tuple[set[str], set[str]]:
    tasks_by_front = {front["id"]: state["plans"][front["id"]]["tasks"] for front in fronts}
    affected = {f"{item['front_id']}:{item['task_id']}" for item in findings}
    changed_fronts = {item["front_id"] for item in findings}
    while True:
        before = len(affected)
        for front_id, tasks in tasks_by_front.items():
            for task in tasks:
                dependency_keys = {dep if ":" in dep else f"{front_id}:{dep}" for dep in task["depends_on"]}
                if dependency_keys & affected:
                    affected.add(f"{front_id}:{task['id']}")
                    changed_fronts.add(front_id)
        for front in fronts:
            if front["id"] not in changed_fronts and set(front["dependencies"]) & changed_fronts:
                changed_fronts.add(front["id"])
                affected.update(f"{front['id']}:{task['id']}" for task in tasks_by_front[front["id"]])
        if len(affected) == before:
            break
    return affected, changed_fronts


def _apply_chief_decision(state: dict[str, Any], decision: Any, fronts: list[dict[str, Any]]) -> None:
    if not isinstance(decision, dict) or not isinstance(decision.get("decision"), str):
        raise ValueError("decisão do chefe deve ser um objeto JSON com o campo decision")
    action = decision["decision"]
    if action == "approve":
        if set(decision) != {"decision", "summary"} or not isinstance(decision["summary"], str):
            raise ValueError("aprovação exige exatamente decision e summary em texto")
        state.setdefault("chief_reviews", []).append(
            {"decision": action, "summary": decision["summary"], "created_at": datetime.now(timezone.utc).isoformat()}
        )
        state["estado"] = "concluida"
        state["motivo"] = None
        return
    if action == "ask_human":
        if set(decision) != {"decision", "questions"}:
            raise ValueError("ask_human exige exatamente decision e questions")
        questions = decision["questions"]
        if (
            not isinstance(questions, list)
            or not questions
            or not all(isinstance(q, str) and q.strip() for q in questions)
        ):
            raise ValueError("questions deve conter perguntas humanas não vazias")
        state.setdefault("chief_reviews", []).append(
            {"decision": action, "questions": questions, "created_at": datetime.now(timezone.utc).isoformat()}
        )
        _pause(
            state,
            "auditoria final do chefe aguarda decisão humana",
            questions,
            {"stage": "chief_review", "front_id": "global"},
        )
        return
    if action != "revise" or set(decision) != {"decision", "findings"}:
        raise ValueError("decision deve ser approve, revise ou ask_human com o formato documentado")
    findings = decision["findings"]
    if not isinstance(findings, list) or not findings:
        raise ValueError("revise exige ao menos um achado com escopo de tarefa")
    fronts_by_id = {front["id"]: front for front in fronts}
    task_index: dict[str, dict[str, Any]] = {}
    for front_id, plan in state["plans"].items():
        for task in plan["tasks"]:
            task_index[f"{front_id}:{task['id']}"] = task
    validated: list[dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"front_id", "task_id", "instruction"}:
            raise ValueError("cada finding precisa conter front_id, task_id e instruction")
        if not all(isinstance(finding[key], str) and finding[key].strip() for key in finding):
            raise ValueError("campos de finding devem ser textos não vazios")
        key = f"{finding['front_id']}:{finding['task_id']}"
        if finding["front_id"] not in fronts_by_id or key not in task_index:
            raise ValueError(f"tarefa de revisão não pertence à iniciativa: {key}")
        validated.append({key: finding[key].strip() for key in finding})
    affected, changed_fronts = _revision_task_keys(state, fronts, validated)
    for item in validated:
        key = f"{item['front_id']}:{item['task_id']}"
        state.setdefault("chief_revisions", {})[key] = item["instruction"]
    for key in affected:
        state.get("builds", {}).pop(key, None)
        state.get("build_attempts", {}).pop(key, None)
        if key not in state.get("chief_revisions", {}):
            state.setdefault("chief_revisions", {})[key] = (
                "Reexecute porque uma tarefa dependente foi revisada pelo chefe; confira as dependências atualizadas."
            )
    for front_id in changed_fronts:
        state.get("audits", {}).pop(front_id, None)
    state.setdefault("chief_reviews", []).append(
        {
            "decision": action,
            "findings": validated,
            "rerun_tasks": sorted(affected),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    state["estado"] = "em_andamento"
    state["motivo"] = None


async def executar_iniciativa(
    root: Path, manifest: dict[str, Any], answers: Any = None, chief_decision: Any = None
) -> dict[str, Any]:
    from invocar_agentes import ler_config, obter_perfil

    initiative, profile_id, limits, fronts = _validar_manifesto(manifest)
    config, _ = ler_config(root)
    profile = obter_perfil(config, profile_id)
    timeout = config.get("timeout_segundos", 1800)
    if type(timeout) is not int or timeout < 1:
        raise ValueError("timeout_segundos inválido")
    repos = {f["id"]: _repo_path(root, f) for f in fronts}
    for front in fronts:
        spec_path = (repos[front["id"]] / front["spec"]).resolve()
        if not spec_path.is_relative_to(repos[front["id"]]) or not spec_path.is_file():
            raise ValueError(f"spec inexistente ou fora do repositório da frente {front['id']}: {front['spec']}")
    state_dir = root / ".init-harness" / "state" / "orquestracao" / initiative
    state_file = state_dir / "estado.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if state.get("manifest_fingerprint") != _fingerprint(manifest):
            raise ValueError("manifesto mudou desde a criação do estado; use outro initiative_id")
        if state.get("estado") == "pausada":
            if answers is None:
                return state
            candidate = copy.deepcopy(state)
            _resume_with_answers(candidate, answers)
            minimum = _minimum_remaining_calls(candidate, fronts)
            if candidate.get("calls", 0) + minimum > candidate.get("limits", {}).get("max_calls", 0):
                raise ValueError(
                    "limite max_calls insuficiente para retomar; "
                    f"mínimo restante estimado: {minimum}. A pausa foi preservada"
                )
            state = candidate
            _save(state_file, state)
        elif answers is not None:
            raise ValueError("--respostas só pode ser usado para retomar iniciativa pausada")
        if state.get("estado") == "concluida":
            if chief_decision is not None:
                raise ValueError("a iniciativa já foi concluída")
            return state
        if state.get("estado") == "aguardando_auditoria_chefe":
            if chief_decision is None:
                return state
            candidate = copy.deepcopy(state)
            _apply_chief_decision(candidate, chief_decision, fronts)
            minimum = sum(
                1 for key in candidate.get("chief_revisions", {}) if key not in candidate.get("builds", {})
            ) + sum(1 for front in fronts if front["id"] not in candidate.get("audits", {}))
            if candidate["estado"] == "em_andamento" and candidate.get("calls", 0) + minimum > candidate.get(
                "limits", {}
            ).get("max_calls", 0):
                raise ValueError(
                    "limite max_calls insuficiente para as revisões; "
                    f"chamadas restantes estimadas: {minimum}. Auditoria preservada"
                )
            state = candidate
            _save(state_file, state)
            if state["estado"] != "em_andamento":
                report_file = state_dir / "relatorio_para_chefe.json"
                report = {
                    k: state.get(k)
                    for k in (
                        "initiative_id",
                        "profile",
                        "plans",
                        "agreements",
                        "consultations",
                        "closures",
                        "builds",
                        "audits",
                        "calls",
                        "estado",
                        "chief_reviews",
                        "questions",
                    )
                    if k in state
                }
                report["chefe_auditoria"] = (
                    "concluida"
                    if state["estado"] == "concluida"
                    else "aguardando resposta humana"
                    if state["estado"] == "pausada"
                    else "pendente"
                )
                report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return state
        elif chief_decision is not None:
            raise ValueError("--decisao-chefe só pode ser usada quando aguardando_auditoria_chefe")
    else:
        state = {
            "contract_version": 1,
            "initiative_id": initiative,
            "profile": profile_id,
            "limits": limits,
            "manifest_fingerprint": _fingerprint(manifest),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "calls": 0,
            "reserved_calls": [],
            "plans": {},
            "agreements": {},
            "consultations": {},
            "closures": {},
            "builds": {},
            "audits": {},
            "resolutions": {},
            "human_decisions": [],
            "estado": "em_andamento",
        }
        if answers is not None:
            raise ValueError("--respostas requer uma iniciativa previamente pausada")
        if chief_decision is not None:
            raise ValueError("--decisao-chefe requer iniciativa aguardando auditoria do chefe")
        _save(state_file, state)
    semaphore = asyncio.Semaphore(limits["max_parallel"])
    supervisor_count = len(fronts)
    if supervisor_count > limits["max_agents"]:
        raise ValueError("max_agents insuficiente para um supervisor por frente")

    # Cada supervisor planeja sua frente; a reconciliação cruzada ocorre antes da escrita.
    for front in fronts:
        if front["id"] in state["plans"]:
            continue
        spec_text = (repos[front["id"]] / front["spec"]).read_text(encoding="utf-8")
        specialty = _specialty_prompt(root, repos[front["id"]], front["specialty"])
        checkpoint = {"stage": "plan", "front_id": front["id"]}
        prompt = (
            "PAPEL: supervisor read-only. Analise a spec e o escopo desta frente; não edite arquivos nem rode testes. "
            'Retorne JSON estrito {"tasks":[{"id":"...","objective":"...","files":[...],'
            '"depends_on":[...],"acceptance":[...],"pair_with":[...]}],"interfaces":[],"questions":[]}. '
            "pair_with declara pares recíprocos para uma única rodada consultiva pré-escrita.\nESPECIALIDADE:\n"
            + specialty
            + "\nFRONT:\n"
            + json.dumps(front, ensure_ascii=False)
            + "\nSPEC:\n"
            + spec_text
            + _decision_context(state, checkpoint)
        )
        raw, model = await _invoke(
            root,
            state,
            state_file,
            profile,
            "supervisor",
            prompt,
            f"plan:{front['id']}",
            timeout,
            semaphore,
            repos[front["id"]],
            read_only=True,
        )
        plan = _validar_plan(front, _strict_json(raw, {"tasks", "interfaces", "questions"}, f"plano de {front['id']}"))
        state["plans"][front["id"]] = plan
        state.setdefault("models", {})[f"supervisor:{front['id']}"] = model
        _save(state_file, state)
        if plan["questions"]:
            return _persist_pause(state_file, state, "perguntas humanas no planejamento", plan["questions"], checkpoint)

    tasks_all = [(f, t) for f in fronts for t in state["plans"][f["id"]]["tasks"]]
    if supervisor_count + len(tasks_all) > limits["max_agents"]:
        return _persist_pause(state_file, state, "max_agents insuficiente para supervisores e construtores planejados")
    if any(
        sum(1 for f, _ in tasks_all if f["id"] == front["id"]) > limits["max_builders_per_supervisor"]
        for front in fronts
    ):
        return _persist_pause(state_file, state, "max_builders_per_supervisor excedido")
    ownership: dict[tuple[str, str], str] = {}
    for front, task in tasks_all:
        for file in task["files"]:
            key = (front["id"], file)
            if key in ownership:
                return _persist_pause(state_file, state, f"colisão de arquivo dentro da frente: {front['id']}:{file}")
            ownership[key] = task["id"]
    cross: dict[tuple[str, str], str] = {}
    for front, task in tasks_all:
        for file in task["files"]:
            key = (str(repos[front["id"]]), file)
            if key in cross and cross[key] != front["id"]:
                return _persist_pause(state_file, state, f"conflito de arquivos entre frentes: {file}")
            cross[key] = front["id"]

    state.setdefault("initial_paths", {})
    assigned_by_front: dict[str, set[str]] = {}
    for front in fronts:
        assigned = {
            name for owner_front, task in tasks_all if owner_front["id"] == front["id"] for name in task["files"]
        }
        dirty = _changed_files(repos[front["id"]])
        overlap = sorted(assigned & dirty)
        if overlap and front["id"] not in state["initial_paths"]:
            return _persist_pause(
                state_file,
                state,
                f"arquivos atribuídos já tinham alterações antes da escrita em {front['id']}: {overlap}",
            )
        state["initial_paths"].setdefault(front["id"], sorted(dirty))
        assigned_by_front[front["id"]] = assigned
    _save(state_file, state)

    # Alinhamento de supervisores em uma rodada mediada pelo scheduler.
    all_plans = {f["id"]: state["plans"][f["id"]] for f in fronts}
    for front in fronts:
        if front["id"] in state["agreements"]:
            continue
        checkpoint = {"stage": "agreement", "front_id": front["id"]}
        specialty = _specialty_prompt(root, repos[front["id"]], front["specialty"])
        prompt = (
            "PAPEL: supervisor read-only. Compare seu plano com todos os planos pares antes da escrita. "
            'Responda JSON estrito {"agreements":[],"conflicts":[],"questions":[]}. '
            "Registre interfaces compatíveis e conflitos concretos de escopo/contrato.\nSUA FRENTE:\n"
            + json.dumps(front, ensure_ascii=False)
            + "\nESPECIALIDADE:\n"
            + specialty
            + "\nPLANOS:\n"
            + json.dumps(all_plans, ensure_ascii=False)
            + _decision_context(state, checkpoint)
        )
        raw, _ = await _invoke(
            root,
            state,
            state_file,
            profile,
            "supervisor",
            prompt,
            f"agreement:{front['id']}",
            timeout,
            semaphore,
            repos[front["id"]],
            read_only=True,
        )
        answer = _strict_json(raw, {"agreements", "conflicts", "questions"}, f"alinhamento de {front['id']}")
        for key in ("agreements", "conflicts", "questions"):
            _lista_texto(answer, key, front["id"])
        state["agreements"][front["id"]] = answer
        _save(state_file, state)
        if answer["questions"]:
            return _persist_pause(
                state_file, state, "perguntas humanas no alinhamento", answer["questions"], checkpoint
            )
        if answer["conflicts"]:
            return _persist_pause(
                state_file, state, "conflitos de supervisores bloqueiam o despacho", blockers=answer["conflicts"]
            )

    # Consulta curta entre pares: uma rodada, sem escrita; o supervisor fecha assignments.
    tasks_by_front = {f["id"]: state["plans"][f["id"]]["tasks"] for f in fronts}
    for front in fronts:
        tasks = tasks_by_front[front["id"]]
        for task in tasks:
            if not task.get("pair_with") or task["id"] in state["consultations"].get(front["id"], {}):
                continue
            checkpoint = {"stage": "consultation", "front_id": front["id"], "task_id": task["id"]}
            proposals = [
                {
                    "id": peer,
                    "objective": next(t for t in tasks if t["id"] == peer)["objective"],
                    "files": next(t for t in tasks if t["id"] == peer)["files"],
                    "interfaces": state["plans"][front["id"]]["interfaces"],
                }
                for peer in task["pair_with"]
            ]
            prompt = (
                "PAPEL: construtor em consulta read-only, rodada única antes da escrita. "
                "Não edite arquivos nem rode testes. "
                "Revise sua proposta e as propostas dos pares; responda JSON estrito "
                '{"suggestions":[],"questions":[]}. '
                "Não amplie arquivos atribuídos.\nSUA TAREFA:\n"
                + json.dumps(task, ensure_ascii=False)
                + "\nPROPOSTAS DOS PARES:\n"
                + json.dumps(proposals, ensure_ascii=False)
                + _decision_context(state, checkpoint)
            )
            raw, _ = await _invoke(
                root,
                state,
                state_file,
                profile,
                "construtor",
                prompt,
                f"consult:{front['id']}:{task['id']}",
                timeout,
                semaphore,
                repos[front["id"]],
                read_only=True,
            )
            feedback = _strict_json(raw, {"suggestions", "questions"}, f"consulta de {task['id']}")
            _lista_texto(feedback, "suggestions", task["id"])
            _lista_texto(feedback, "questions", task["id"])
            state.setdefault("consultations", {}).setdefault(front["id"], {})[task["id"]] = feedback
            _save(state_file, state)
            if feedback["questions"]:
                return _persist_pause(
                    state_file,
                    state,
                    "perguntas humanas na consulta entre construtores",
                    feedback["questions"],
                    checkpoint,
                )
    for front in fronts:
        if front["id"] in state["closures"]:
            continue
        checkpoint = {"stage": "closure", "front_id": front["id"]}
        specialty = _specialty_prompt(root, repos[front["id"]], front["specialty"])
        prompt = (
            "PAPEL: supervisor read-only. Feche o plano após consultar as propostas dos pares. "
            'Retorne JSON estrito {"assignments":[{"task_id":"...","files":[...],'
            '"builder_context":"..."}],"interfaces":[],"questions":[]}. '
            "Preserve arquivos e escopo. Em builder_context, entregue apenas decisões, contexto técnico, "
            "limites e instruções necessários para aquela tarefa, incluindo orientação especializada "
            "aplicável; não repita a spec inteira.\nESPECIALIDADE:\n"
            + specialty
            + "\nPLANO:\n"
            + json.dumps(state["plans"][front["id"]], ensure_ascii=False)
            + "\nCONSULTAS:\n"
            + json.dumps(state["consultations"].get(front["id"], {}), ensure_ascii=False)
            + _decision_context(state, checkpoint)
        )
        raw, _ = await _invoke(
            root,
            state,
            state_file,
            profile,
            "supervisor",
            prompt,
            f"closure:{front['id']}",
            timeout,
            semaphore,
            repos[front["id"]],
            read_only=True,
        )
        closure = _strict_json(raw, {"assignments", "interfaces", "questions"}, f"fechamento de {front['id']}")
        if not isinstance(closure["assignments"], list) or not all(
            isinstance(a, dict)
            and set(a) == {"task_id", "files", "builder_context"}
            and isinstance(a.get("task_id"), str)
            and isinstance(a.get("files"), list)
            and all(isinstance(name, str) for name in a["files"])
            and isinstance(a.get("builder_context"), str)
            and a["builder_context"].strip()
            for a in closure["assignments"]
        ):
            raise ValueError(f"assignments inválidos no fechamento de {front['id']}")
        _lista_texto(closure, "interfaces", front["id"])
        _lista_texto(closure, "questions", front["id"])
        expected = {t["id"]: sorted(t["files"]) for t in tasks_by_front[front["id"]]}
        assignment_ids = [a["task_id"] for a in closure["assignments"]]
        if len(assignment_ids) != len(set(assignment_ids)):
            return _persist_pause(state_file, state, f"fechamento duplicou task_id em {front['id']}")
        actual = {a["task_id"]: sorted(a["files"]) for a in closure["assignments"]}
        if actual != expected:
            return _persist_pause(state_file, state, f"fechamento alterou assignments/arquivos em {front['id']}")
        state["closures"][front["id"]] = closure
        _save(state_file, state)
        if closure["questions"]:
            return _persist_pause(
                state_file, state, "perguntas humanas no fechamento", closure["questions"], checkpoint
            )

    # Construtores executam respeitando dependências por frente e limites agregados.
    tasks_pending = {
        f"{front['id']}:{task['id']}": (front, task)
        for front, task in tasks_all
        if f"{front['id']}:{task['id']}" not in state["builds"]
    }
    completed = set(state["builds"])
    while tasks_pending:
        ready = []
        for key, (front, task) in tasks_pending.items():
            deps = {dep if ":" in dep else f"{front['id']}:{dep}" for dep in task["depends_on"]}
            front_deps_done = all(
                all(f"{dep}:{dependency_task['id']}" in completed for dependency_task in state["plans"][dep]["tasks"])
                for dep in front["dependencies"]
            )
            if deps <= completed and front_deps_done:
                ready.append((key, front, task))
        if not ready:
            return _persist_pause(state_file, state, "dependências pendentes ou ciclo no DAG de construtores")
        batch = ready[: limits["max_parallel"]]

        async def build_one(item: tuple[str, dict[str, Any], dict[str, Any]]) -> tuple[str, dict[str, Any], Path]:
            key, front, task = item
            repo = repos[front["id"]]
            context_paths = set(task["files"])
            for done_key in completed:
                if done_key.startswith(front["id"] + ":"):
                    done_id = done_key.split(":", 1)[1]
                    done_task = next(t for t in tasks_by_front[front["id"]] if t["id"] == done_id)
                    context_paths.update(done_task["files"])
            assignment = next(a for a in state["closures"][front["id"]]["assignments"] if a["task_id"] == task["id"])
            guidance_paths, guidance = _project_guidance(repo, task["files"])
            context_paths.update(guidance_paths)
            diff = _change_context(repo, sorted(context_paths))
            peer_notes = {
                participant: state["consultations"].get(front["id"], {}).get(participant, {})
                for participant in [task["id"], *task.get("pair_with", [])]
            }
            checkpoint = {"stage": "build", "front_id": front["id"], "task_id": task["id"]}
            revision = state.get("chief_revisions", {}).get(key, "")
            prompt = (
                "PAPEL: construtor. Implemente somente sua tarefa e arquivos atribuídos; execute as "
                "verificações solicitadas nos critérios recebidos e relate resultados reais. "
                "Não faça commit/push/merge. Incorpore sugestões dos construtores pareados quando "
                "compatíveis com a spec; reporte divergências ao supervisor. "
                'Responda somente JSON estrito: {"status":"completed","summary":"...",'
                '"files_changed":[],"checks":[],"risks":[],"questions":[]}. Status deve ser '
                "completed ou blocked. "
                "Se uma resposta humana for necessária, use status blocked e registre perguntas objetivas.\nTAREFA:\n"
                + json.dumps(task, ensure_ascii=False)
                + "\nCONTEXTO DO SUPERVISOR ("
                + front["specialty"]
                + "):\n"
                + assignment["builder_context"]
                + "\nPROJECT GUIDANCE:\n"
                + guidance
                + "\nCONSULTAS DOS PARES:\n"
                + json.dumps(peer_notes, ensure_ascii=False)
                + "\nINSTRUÇÃO DE REVISÃO DO CHEFE:\n"
                + revision
                + "\nDIFF LOCAL ATUAL:\n"
                + diff[-30000:]
                + _decision_context(state, checkpoint)
            )
            raw, worktree, observed_files = await _run_isolated_builder(
                root,
                repo,
                state,
                state_file,
                profile,
                task,
                front["id"],
                context_paths,
                prompt,
                f"build:{key}",
                timeout,
                semaphore,
            )
            report = _strict_json(
                raw,
                {"status", "summary", "files_changed", "checks", "risks", "questions"},
                f"retorno do construtor {key}",
            )
            if report["status"] not in {"completed", "blocked"} or not isinstance(report["summary"], str):
                _cleanup_task_worktree(repo, worktree)
                raise ValueError(f"retorno do construtor inválido em {key}")
            for field in ("files_changed", "checks", "risks", "questions"):
                _lista_texto(report, field, key)
            if not set(report["files_changed"]) <= set(task["files"]):
                _cleanup_task_worktree(repo, worktree)
                raise ValueError(f"construtor reportou arquivo fora do escopo em {key}")
            if report["questions"] and report["status"] != "blocked":
                _cleanup_task_worktree(repo, worktree)
                raise ValueError(f"construtor precisa marcar status blocked quando fizer perguntas em {key}")
            report["observed_files"] = sorted(observed_files)
            return key, report, worktree

        batch_snapshots = {front["id"]: _repo_snapshot(repos[front["id"]]) for _, front, _ in batch}
        results = await asyncio.gather(*(build_one(item) for item in batch), return_exceptions=True)
        successful = [result for result in results if not isinstance(result, BaseException)]
        touched_repos = {}
        for front_id, snapshot in batch_snapshots.items():
            current = _repo_snapshot(repos[front_id])
            if current != snapshot:
                touched_repos[front_id] = sorted(current[0] ^ snapshot[0]) + sorted(
                    name for name in current[1].keys() & snapshot[1].keys() if current[1][name] != snapshot[1][name]
                )
        if touched_repos:
            for result in successful:
                key, _, worktree = result
                front_id = key.split(":", 1)[0]
                _cleanup_task_worktree(repos[front_id], worktree)
            return _persist_pause(
                state_file, state, f"repositório principal mudou durante execução isolada: {touched_repos}"
            )
        failure = next(
            ((item[0], result) for item, result in zip(batch, results) if isinstance(result, BaseException)), None
        )
        if failure:
            for success_key, _, worktree in successful:
                _cleanup_task_worktree(repos[success_key.split(":", 1)[0]], worktree)
            return _persist_pause(state_file, state, f"construtor bloqueado em {failure[0]}: {failure[1]}")
        blocked: list[tuple[str, dict[str, Any], dict[str, Any], Path]] = []
        for item, result in zip(batch, results):
            key, report, worktree = result
            front, task = item[1], item[2]
            if report["status"] == "blocked":
                blocked.append((key, report, front, worktree))
                continue
            try:
                _integrate_task_files(repos[front["id"]], worktree, task)
            finally:
                _cleanup_task_worktree(repos[front["id"]], worktree)
            state["builds"][key] = report
            completed.add(key)
            del tasks_pending[key]
        _save(state_file, state)
        if blocked:
            for key, report, front, worktree in blocked:
                _cleanup_task_worktree(repos[front["id"]], worktree)
                state.setdefault("build_attempts", {})[key] = report
            key, report, front, _ = blocked[0]
            _save(state_file, state)
            checkpoint = {"stage": "build", "front_id": front["id"], "task_id": key.split(":", 1)[1]}
            if report["questions"]:
                return _persist_pause(
                    state_file, state, f"construtor precisa de decisão humana em {key}", report["questions"], checkpoint
                )
            return _persist_pause(state_file, state, f"construtor bloqueado em {key}: {report['summary']}")

    # Detecta alterações fora da lista declarada; permissões do CLI não isolam por arquivo.
    for front in fronts:
        new_paths = _changed_files(repos[front["id"]]) - set(state["initial_paths"][front["id"]])
        unexpected = sorted(new_paths - assigned_by_front[front["id"]])
        if unexpected:
            return _persist_pause(
                state_file, state, f"construtores alteraram arquivos fora do escopo em {front['id']}: {unexpected}"
            )

    # Supervisor audita somente diff/evidências; não executa testes.
    for front in fronts:
        if front["id"] in state["audits"]:
            continue
        checkpoint = {"stage": "audit", "front_id": front["id"]}
        repo = repos[front["id"]]
        specialty = _specialty_prompt(root, repo, front["specialty"])
        diff = _change_context(repo, front["scope"])
        spec_text = (repos[front["id"]] / front["spec"]).read_text(encoding="utf-8")
        prompt = (
            "PAPEL: supervisor auditor read-only. Audite a spec e o diff local desta frente. Não rode testes. "
            'Responda JSON estrito {"approved":true,"findings":[],"questions":[],"verification_evidence":[]}. '
            "Não alegue validações não observadas.\nESPECIALIDADE:\n"
            + specialty
            + "\nSPEC:\n"
            + front["spec"]
            + "\nPLANO:\n"
            + spec_text
            + "\nPLANO:\n"
            + json.dumps(state["plans"][front["id"]], ensure_ascii=False)
            + "\nRELATÓRIOS:\n"
            + json.dumps(
                {k: v for k, v in state["builds"].items() if k.startswith(front["id"] + ":")}, ensure_ascii=False
            )
            + "\nDIFF:\n"
            + diff[-50000:]
            + _decision_context(state, checkpoint)
        )
        raw, _ = await _invoke(
            root,
            state,
            state_file,
            profile,
            "supervisor",
            prompt,
            f"audit:{front['id']}",
            timeout,
            semaphore,
            repo,
            read_only=True,
        )
        audit = _strict_json(
            raw, {"approved", "findings", "questions", "verification_evidence"}, f"auditoria de {front['id']}"
        )
        if type(audit["approved"]) is not bool:
            raise ValueError("approved precisa ser booleano")
        for key in ("findings", "questions", "verification_evidence"):
            _lista_texto(audit, key, front["id"])
        state["audits"][front["id"]] = audit
        _save(state_file, state)
        if audit["questions"]:
            return _persist_pause(state_file, state, "perguntas humanas na auditoria", audit["questions"], checkpoint)
        if not audit["approved"]:
            return _persist_pause(
                state_file,
                state,
                "auditoria de supervisor reprovada; requer correção/reexecução",
                blockers=audit["findings"],
            )
    state["estado"] = "aguardando_auditoria_chefe"
    state["motivo"] = None
    _save(state_file, state)
    report_file = state_dir / "relatorio_para_chefe.json"
    report = {
        k: state[k]
        for k in (
            "initiative_id",
            "profile",
            "plans",
            "agreements",
            "consultations",
            "closures",
            "builds",
            "audits",
            "calls",
            "estado",
        )
    }
    report["chefe_auditoria"] = "pendente; chefe deve inspecionar o diff fora do runner, sem executar testes"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _fingerprint(data: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _persist_pause(
    path: Path,
    state: dict[str, Any],
    reason: str,
    questions: list[str] | None = None,
    checkpoint: dict[str, str] | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    result = _pause(state, reason, questions, checkpoint, blockers)
    _save(path, state)
    return result

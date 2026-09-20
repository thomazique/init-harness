"""Catálogo local e histórico de evolução das skills do projeto.

Esta primeira versão é deliberadamente conservadora: descobre skills e mantém
manifestos versionáveis, mas não altera uma skill ativa nem promove propostas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

REGISTRY_RELATIVE = Path(".init-harness") / "skills" / "registry.json"
QUEUE_RELATIVE = Path(".init-harness") / "skills" / "queue"
METHOD_SKILLS = {"init-harness", "spec", "pilares", "commit", "offboarding", "record", "evolve"}
OUTCOMES = {"success", "failure", "partial", "blocked"}
SOURCES = {"agent", "human", "test", "system"}
DEFAULT_EVALUATION_POLICY = {
    "metric": "task_success_rate",
    "higher_is_better": True,
    "minimum_improvement": 0.0,
    "max_regressions": 0,
    "max_guardrail_failures": 0,
    "dimensions": ["correctness", "scope_compliance", "safety"],
    "required_cases": [],
}
DEFAULT_USAGE_CONTRACT = {
    "when": [],
    "when_not": [],
    "tools": [],
    "surfaces": [],
    "expected_outcome": "",
    "risk": "medium",
}


def project_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def parse_frontmatter(text: str) -> dict[str, str]:
    """Lê o subconjunto plano usado pelos SKILL.md sem depender de PyYAML."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$", line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("\"'")
    return result


def discover_skills(root: Path) -> list[dict[str, Any]]:
    skills_root = root / ".claude" / "skills"
    if not skills_root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        name = skill_file.parent.name
        metadata = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        relative = skill_file.relative_to(root).as_posix()
        found.append(
            {
                "id": name,
                "name": metadata.get("name", name),
                "description": metadata.get("description", ""),
                "scope": "method" if name in METHOD_SKILLS else "project",
                "skill_path": relative,
            }
        )
    return found


def registry_path(root: Path) -> Path:
    return root / REGISTRY_RELATIVE


def experiences_path(root: Path, skill: str) -> Path:
    return root / ".init-harness" / "skills" / skill / "experiences.jsonl"


def suggestions_path(root: Path, skill: str) -> Path:
    return root / ".init-harness" / "skills" / skill / "suggestions.jsonl"


def queue_path(root: Path) -> Path:
    return root / QUEUE_RELATIVE


def _job_file(root: Path, job_id: str) -> Path:
    return queue_path(root) / f"{job_id}.json"


def _job_paths(root: Path) -> list[Path]:
    """Arquivos de job da fila; J-<id>.analysis.json e J-<id>.review.json são saídas de runners."""
    return sorted(path for path in queue_path(root).glob("J-*.json") if re.fullmatch(r"J-[0-9a-f]+\.json", path.name))


def enqueue_analysis_job(root: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Adiciona um job idempotente para análise assíncrona da experiência."""
    queue_path(root).mkdir(parents=True, exist_ok=True)
    for path in _job_paths(root):
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if existing.get("experience_event_id") == event.get("event_id"):
            return existing
    job = {
        "job_id": "J-" + uuid.uuid4().hex[:12],
        "type": "skill_experience_analysis",
        "status": "queued",
        "skill": event["skill"],
        "experience_event_id": event["event_id"],
        "experience": event,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "attempts": 0,
    }
    _job_file(root, job["job_id"]).write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return job


def read_jobs(root: Path, status: str | None = None) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for path in _job_paths(root):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"job inválido em {path}") from exc
        if status is None or job.get("status") == status:
            jobs.append(job)
    # O nome do arquivo é um UUID aleatório; a ordem de criação vem de created_at.
    return sorted(jobs, key=lambda job: str(job.get("created_at") or ""))


def update_job(root: Path, job_id: str, status: str, **updates: Any) -> dict[str, Any]:
    allowed = {
        "queued",
        "processing",
        "analyzed",
        "review_required",
        "review_approved",
        "human_required",
        "approved",
        "rejected",
        "promoted",
        "failed",
    }
    if status not in allowed:
        raise ValueError(f"status de job inválido: {status}")
    path = _job_file(root, job_id)
    if not path.is_file():
        raise ValueError(f"job não encontrado: {job_id}")
    job = json.loads(path.read_text(encoding="utf-8"))
    job["status"] = status
    job["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job.update(updates)
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return job


def claim_next_job(root: Path) -> dict[str, Any] | None:
    """Reivindica o próximo job queued; o lock evita dois workers locais simultâneos."""
    queue_path(root).mkdir(parents=True, exist_ok=True)
    lock = queue_path(root) / ".worker.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        return None
    try:
        jobs = read_jobs(root, "queued")
        if not jobs:
            return None
        return update_job(root, jobs[0]["job_id"], "processing", attempts=int(jobs[0].get("attempts", 0)) + 1)
    finally:
        handle.close()
        lock.unlink(missing_ok=True)


def decide_job(root: Path, job_id: str, decision: str, note: str) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decisão deve ser approved ou rejected")
    if not note.strip():
        raise ValueError("note é obrigatório para a decisão humana")
    current = next((job for job in read_jobs(root) if job.get("job_id") == job_id), None)
    if current is None or current.get("status") not in {"review_approved", "human_required"}:
        raise ValueError("job precisa estar em review_approved ou human_required para decisão humana")
    return update_job(
        root,
        job_id,
        decision,
        human_decision={"note": note.strip(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    )


def evolution_status(root: Path) -> dict[str, Any]:
    jobs = read_jobs(root)
    return {
        "queued": sum(job.get("status") == "queued" for job in jobs),
        "processing": sum(job.get("status") == "processing" for job in jobs),
        "analyzed": sum(job.get("status") == "analyzed" for job in jobs),
        "review_required": sum(job.get("status") == "review_required" for job in jobs),
        "review_approved": sum(job.get("status") == "review_approved" for job in jobs),
        "human_required": sum(job.get("status") == "human_required" for job in jobs),
        "approved": sum(job.get("status") == "approved" for job in jobs),
        "rejected": sum(job.get("status") == "rejected" for job in jobs),
        "promoted": sum(job.get("status") == "promoted" for job in jobs),
        "failed": sum(job.get("status") == "failed" for job in jobs),
        "total": len(jobs),
    }


def proposals_root(root: Path, skill: str) -> Path:
    return root / ".init-harness" / "skills" / skill / "proposals"


def proposal_directory(root: Path, skill: str, proposal_id: str) -> Path:
    return proposals_root(root, skill) / proposal_id


def _skill_ids(root: Path) -> set[str]:
    return {item["id"] for item in discover_skills(root)}


def _relative_paths(root: Path, values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"caminho deve ser relativo ao projeto: {value}")
        result.append(path.as_posix())
    return result


def _session_state_path(root: Path, session_id: str) -> Path:
    """Localiza o estado operacional da sessão no diretório Git do projeto."""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    git_dir = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else root / ".git"
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "sem-id")
    return git_dir / "init-harness" / f"sessao-{safe_id}.json"


def _load_session_state(root: Path, session_id: str) -> tuple[Path, dict[str, Any]]:
    path = _session_state_path(root, session_id)
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path, {}


def _save_session_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def activate_skill(root: Path, skill: str, session_id: str) -> dict[str, Any]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    if not session_id.strip():
        raise ValueError("session-id não pode ser vazio")
    path, state = _load_session_state(root, session_id)
    state["active_skill"] = skill
    state["active_skill_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save_session_state(path, state)
    return {"session_id": session_id, "active_skill": skill}


def deactivate_skill(root: Path, session_id: str) -> dict[str, Any]:
    if not session_id.strip():
        raise ValueError("session-id não pode ser vazio")
    path, state = _load_session_state(root, session_id)
    previous = state.pop("active_skill", None)
    state.pop("active_skill_at", None)
    _save_session_state(path, state)
    return {"session_id": session_id, "active_skill": None, "previous_skill": previous}


def active_skill(root: Path, session_id: str) -> dict[str, Any]:
    if not session_id.strip():
        raise ValueError("session-id não pode ser vazio")
    _, state = _load_session_state(root, session_id)
    return {"session_id": session_id, "active_skill": state.get("active_skill")}


def activate_from_tool_event(root: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Ativa a skill da sessão quando o cliente invoca a ferramenta Skill.

    Só reage a PreToolUse da ferramenta Skill e a skills presentes no catálogo do
    projeto; skills de outros escopos (plugins, usuário) são ignoradas. Ao trocar de
    skill, a observação acumulada da anterior vira uma experiência própria antes da
    troca, para que suas chamadas de ferramenta não sejam atribuídas à nova skill.
    """
    if str(payload.get("hook_event_name") or "") != "PreToolUse" or payload.get("tool_name") != "Skill":
        return None
    tool_input = payload.get("tool_input")
    name = str((tool_input or {}).get("skill") or "").strip().lstrip("/") if isinstance(tool_input, dict) else ""
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id or name not in _skill_ids(root):
        return None
    path, state = _load_session_state(root, session_id)
    previous = state.get("active_skill")
    observation = state.get("skill_observation")
    if previous and previous != name and isinstance(observation, dict) and observation.get("skill") == previous:
        consolidated = consolidate_hook_experience({"session_id": session_id, "active_skill": previous}, observation)
        if consolidated is not None:
            capture_hook_experience(root, {"session_id": session_id, "skill_experience": consolidated})
        state.pop("skill_observation", None)
        state.pop("skill_observation_seen", None)
        _save_session_state(path, state)
    return activate_skill(root, name, session_id)


def observe_tool_event(root: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Acumula sinais objetivos de uma ferramenta no estado da sessão."""
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None
    event_id = str(payload.get("tool_use_id") or payload.get("event_id") or "").strip()
    path, state = _load_session_state(root, session_id)
    skill = str(payload.get("active_skill") or payload.get("skill") or state.get("active_skill") or "").strip()
    if not skill or skill not in _skill_ids(root):
        return None
    seen = state.setdefault("skill_observation_seen", [])
    if event_id and event_id in seen:
        return state.get("skill_observation")
    if event_id:
        seen.append(event_id)
        del seen[:-200]
    failed = str(payload.get("hook_event_name") or payload.get("event") or "").lower() in {
        "posttoolusefailure",
        "tool_failure",
    }
    if payload.get("error") or payload.get("is_error") is True:
        failed = True
    tool = str(payload.get("tool_name") or payload.get("tool") or "unknown").strip() or "unknown"
    observation = state.setdefault(
        "skill_observation",
        {"skill": skill, "tool_calls": 0, "tool_failures": 0, "tools": {}, "files": [], "duration_ms": 0},
    )
    observation["skill"] = skill
    observation["tool_calls"] = int(observation.get("tool_calls", 0)) + 1
    if failed:
        observation["tool_failures"] = int(observation.get("tool_failures", 0)) + 1
    tools = observation.setdefault("tools", {})
    tool_stats = tools.setdefault(tool, {"calls": 0, "failures": 0})
    tool_stats["calls"] += 1
    if failed:
        tool_stats["failures"] += 1
    duration = payload.get("duration_ms")
    if isinstance(duration, (int, float)) and duration >= 0:
        observation["duration_ms"] = float(observation.get("duration_ms", 0)) + duration
    candidates = payload.get("files") or payload.get("file_paths") or []
    if isinstance(candidates, str):
        candidates = [candidates]
    files = observation.setdefault("files", [])
    for value in candidates if isinstance(candidates, list) else []:
        candidate = Path(str(value))
        if not candidate.is_absolute() and ".." not in candidate.parts and candidate.as_posix() not in files:
            files.append(candidate.as_posix())
    _save_session_state(path, state)
    return observation


def consolidate_hook_experience(payload: dict[str, Any], observation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Converte sinais objetivos do Stop em um evento factual mínimo."""
    nested = payload.get("skill_experience")
    experience = dict(nested) if isinstance(nested, dict) else {}
    skill = str(
        experience.get("skill") or payload.get("active_skill") or payload.get("skill")
        or (observation or {}).get("skill") or ""
    ).strip()
    session_id = str(experience.get("session_id") or payload.get("session_id") or "").strip() or None
    task_id = str(experience.get("task_id") or payload.get("task_id") or "").strip() or session_id
    calls = int((observation or {}).get("tool_calls", 0))
    failures = int((observation or {}).get("tool_failures", 0))
    if not skill or not task_id or calls <= 0:
        return None

    outcome = str(experience.get("outcome") or payload.get("outcome") or "").strip().lower()
    blocked = bool(experience.get("blocked") or payload.get("blocked") or payload.get("is_blocked"))
    stop_reason = str(payload.get("stop_reason") or "").strip().lower()
    if blocked or stop_reason in {"blocked", "timeout"}:
        outcome = "blocked"
    elif outcome not in OUTCOMES:
        outcome = "failure" if failures == calls else "partial" if failures else "success"

    summary = str(experience.get("summary") or payload.get("summary") or "").strip()
    if not summary:
        if outcome == "success":
            summary = f"Sessão concluiu com {calls} chamada(s) de ferramenta sem falhas observadas."
        elif outcome == "failure":
            summary = f"Sessão terminou com {failures} falha(s) de ferramenta em {calls} chamada(s)."
        elif outcome == "partial":
            summary = f"Sessão teve {failures} falha(s) em {calls} chamada(s) de ferramenta."
        else:
            summary = f"Sessão bloqueada após {calls} chamada(s), com {failures} falha(s) observada(s)."

    score = experience.get("score")
    if score is None:
        if outcome in {"failure", "blocked"}:
            score = 0.0
        elif outcome == "success":
            score = 1.0
        else:
            score = max(0.0, (calls - failures) / calls)
    result = {
        **experience,
        "skill": skill,
        "task_id": task_id,
        "session_id": session_id,
        "outcome": outcome,
        "summary": summary,
        "score": score,
    }
    if failures and not result.get("failure_type"):
        result["failure_type"] = "tool_failure"
    if observation:
        result.setdefault("tools", sorted((observation.get("tools") or {}).keys()))
        result.setdefault("files", observation.get("files") or [])
        result.setdefault("metrics", {
            "tool_calls": calls,
            "tool_failures": failures,
            "duration_ms": observation.get("duration_ms", 0),
        })
    return result


def _metrics(values: list[str]) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"métrica inválida, use nome=valor: {value}")
        name, raw = value.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
            raise ValueError(f"nome de métrica inválido: {name}")
        try:
            number: float | int = int(raw)
        except ValueError:
            try:
                number = float(raw)
            except ValueError as exc:
                raise ValueError(f"valor de métrica inválido: {value}") from exc
        result[name] = number
    return result


def _experience_from_args(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {args.skill}")
    if args.outcome not in OUTCOMES:
        raise ValueError(f"resultado inválido: {args.outcome}")
    if args.source not in SOURCES:
        raise ValueError(f"origem inválida: {args.source}")
    if args.score is not None and not 0 <= args.score <= 1:
        raise ValueError("score deve estar entre 0 e 1")
    summary = args.summary.strip()
    if not summary or "\n" in summary or "\r" in summary:
        raise ValueError("summary deve ser uma linha não vazia")
    return {
        "event_id": "E-" + uuid.uuid4().hex[:12],
        "skill": args.skill,
        "task_id": args.task_id,
        "session_id": args.session_id,
        "occurred_at": args.occurred_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": args.source,
        "outcome": args.outcome,
        "score": args.score,
        "failure_type": args.failure_type,
        "summary": summary,
        "human_correction": bool(args.human_correction),
        "tools": sorted(set(args.tool)),
        "files": _relative_paths(root, args.file),
        "metrics": _metrics(args.metric),
        "tags": sorted(set(args.tag)),
    }


def record_experience(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    event = _experience_from_args(root, args)
    path = experiences_path(root, args.skill)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    enqueue_analysis_job(root, event)
    identify_suggestions(root, args.skill)
    sync_registry(root)
    return event


def capture_hook_experience(root: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Registra somente um sinal estruturado de experiência recebido por um hook.

    Hooks não devem inferir qualidade a partir de prompts ou transcrições. Por isso,
    sem skill, resultado e resumo factual explícitos, a captura é silenciosamente
    ignorada. Eventos automáticos idempotentes evitam duplicação quando Stop roda
    mais de uma vez para a mesma sessão.
    """
    nested = payload.get("skill_experience")
    data = dict(nested) if isinstance(nested, dict) else dict(payload)
    if not data.get("skill") and payload.get("active_skill"):
        data["active_skill"] = payload["active_skill"]
    skill = str(data.get("skill") or data.get("active_skill") or "").strip()
    outcome = str(data.get("outcome") or "").strip().lower()
    summary = str(data.get("summary") or data.get("result_summary") or "").strip()
    session_id = str(data.get("session_id") or payload.get("session_id") or "").strip() or None
    task_id = str(data.get("task_id") or payload.get("task_id") or "").strip() or session_id
    if not skill or outcome not in OUTCOMES or not summary or not task_id:
        return None
    if skill not in _skill_ids(root):
        return None
    existing = read_experiences(root, skill)
    if any(
        event.get("source") == "system"
        and event.get("session_id") == session_id
        and event.get("task_id") == task_id
        and event.get("summary") == summary
        for event in existing
    ):
        return None

    def values(name: str) -> list[str]:
        value = data.get(name, [])
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value] if isinstance(value, list) else []

    score = data.get("score")
    args = argparse.Namespace(
        skill=skill,
        task_id=task_id,
        session_id=session_id,
        occurred_at=data.get("occurred_at"),
        source="system",
        outcome=outcome,
        score=float(score) if score is not None else None,
        failure_type=data.get("failure_type"),
        summary=summary,
        human_correction=bool(data.get("human_correction")),
        tool=values("tools"),
        file=values("files"),
        metric=values("metrics") if isinstance(data.get("metrics"), list) else [
            f"{key}={value}" for key, value in (data.get("metrics") or {}).items()
        ],
        tag=values("tags"),
    )
    return record_experience(root, args)


def capture_hook_stdin(root: Path, stream: Any) -> dict[str, Any]:
    """Adaptador de cliente: lê um evento JSON sem expor transcrição ao harness."""
    try:
        payload = json.load(stream)
    except (json.JSONDecodeError, TypeError):
        return {"captured": False, "reason": "entrada não é JSON válido"}
    if not isinstance(payload, dict):
        return {"captured": False, "reason": "evento precisa ser um objeto JSON"}
    event = capture_hook_experience(root, payload)
    return {"captured": event is not None, "experience": event}


def read_experiences(root: Path, skill: str, limit: int | None = None) -> list[dict[str, Any]]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    path = experiences_path(root, skill)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"experiência inválida em {path}:{number}") from exc
        if not isinstance(item, dict) or item.get("skill") != skill:
            raise ValueError(f"experiência inválida em {path}:{number}")
        rows.append(item)
    return rows[-limit:] if limit else rows


def read_suggestions(root: Path, skill: str, limit: int | None = None) -> list[dict[str, Any]]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    path = suggestions_path(root, skill)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sugestão inválida em {path}:{number}") from exc
        if not isinstance(item, dict) or item.get("skill") != skill:
            raise ValueError(f"sugestão inválida em {path}:{number}")
        rows.append(item)
    return rows[-limit:] if limit else rows


def read_proposals(root: Path, skill: str) -> list[dict[str, Any]]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    base = proposals_root(root, skill)
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/proposal.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(item, dict) or item.get("skill") != skill:
            raise ValueError(f"proposta inválida em {path}")
        rows.append(item)
    return rows


def _suggestion_key(event: dict[str, Any]) -> str:
    failure_type = str(event.get("failure_type") or "").strip().lower()
    tags = ",".join(event.get("tags") or [])
    return f"failure_type:{failure_type}" if failure_type else f"correction:{tags or 'unspecified'}"


def _suggestion_groups(experiences: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in experiences:
        if event.get("outcome") not in {"failure", "partial", "blocked"} and not event.get("human_correction"):
            continue
        groups.setdefault(_suggestion_key(event), []).append(event)
    return groups


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_suggestions(root: Path, skill: str, rows: list[dict[str, Any]]) -> None:
    """Reescreve o arquivo por inteiro: as sugestões são atualizadas no lugar."""
    path = suggestions_path(root, skill)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _suggestion_rationale(pattern: str, count: int, human_correction: bool) -> str:
    return (
        f"O padrão {pattern.split(':', 1)[1]!r} apareceu em {count} experiência(s)"
        + (" e houve correção humana." if human_correction else ".")
    )


def _build_suggestion(
    skill: str, pattern: str, events: list[dict[str, Any]], generation: int, origin: str | None = None
) -> dict[str, Any]:
    seed = f"{skill}\0{pattern}" if generation == 0 else f"{skill}\0{pattern}\0g{generation}"
    fingerprint = sha256(seed.encode("utf-8")).hexdigest()[:16]
    now = _now()
    suggestion = {
        "suggestion_id": "S-" + fingerprint[:12],
        "fingerprint": fingerprint,
        "skill": skill,
        "status": "proposed",
        "created_at": now,
        "updated_at": now,
        "pattern": pattern,
        "occurrences": len(events),
        "evidence_event_ids": [event["event_id"] for event in events],
        "summaries": [event["summary"] for event in events[-5:]],
        "rationale": _suggestion_rationale(pattern, len(events), any(e.get("human_correction") for e in events)),
        "proposed_action": (
            "Revisar a skill para tratar esse padrão e criar um caso de regressão "
            "antes de propor uma nova versão."
        ),
    }
    if origin:
        suggestion["origin"] = origin
    return suggestion


def _refresh_suggestion(
    suggestion: dict[str, Any], events: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]
) -> bool:
    """Acrescenta ocorrências novas a uma sugestão aberta; nunca remove evidência."""
    ids = list(suggestion.get("evidence_event_ids", []))
    new = [event["event_id"] for event in events if event["event_id"] not in ids]
    if not new:
        return False
    ids.extend(new)
    known = [by_id[item] for item in ids if item in by_id]
    suggestion["evidence_event_ids"] = ids
    suggestion["occurrences"] = len(ids)
    suggestion["summaries"] = [event["summary"] for event in known[-5:]]
    suggestion["rationale"] = _suggestion_rationale(
        suggestion["pattern"], len(ids), any(event.get("human_correction") for event in known)
    )
    suggestion["updated_at"] = _now()
    return True


def identify_suggestions(root: Path, skill: str) -> list[dict[str, Any]]:
    """Cria e mantém sugestões determinísticas a partir de padrões observados.

    O limiar evita transformar uma falha isolada em mudança de skill, mas uma
    correção humana explícita já é suficiente para sinalizar um padrão a revisar.
    Uma sugestão aberta (proposed ou in_progress) acumula as ocorrências novas. Depois
    que uma proposta a promove (addressed), a sugestão fica congelada como histórico e só
    as ocorrências posteriores podem abrir outra: é o sinal de que a correção não resolveu.
    """
    experiences = read_experiences(root, skill)
    by_id = {event["event_id"]: event for event in experiences if event.get("event_id")}
    rows = read_suggestions(root, skill)
    created: list[dict[str, Any]] = []
    changed = False
    for pattern, events in _suggestion_groups(experiences).items():
        versions = [row for row in rows if row.get("pattern") == pattern]
        consumed = {
            item for row in versions if row.get("status") == "addressed" for item in row.get("evidence_event_ids", [])
        }
        pending = [event for event in events if event["event_id"] not in consumed]
        if versions and versions[-1].get("status") != "addressed":
            changed = _refresh_suggestion(versions[-1], pending, by_id) or changed
            continue
        if len(pending) < 2 and not any(event.get("human_correction") for event in pending):
            continue
        suggestion = _build_suggestion(skill, pattern, pending, generation=len(versions))
        rows.append(suggestion)
        created.append(suggestion)
        changed = True
    if changed:
        _write_suggestions(root, skill, rows)
    return created


def _set_suggestion_status(root: Path, skill: str, suggestion_id: str | None, status: str, **extra: Any) -> None:
    rows = read_suggestions(root, skill)
    for row in rows:
        if row.get("suggestion_id") != suggestion_id:
            continue
        if status == "in_progress" and row.get("status") != "proposed":
            return
        row.update(status=status, updated_at=_now(), **extra)
        _write_suggestions(root, skill, rows)
        return


def create_proposal(root: Path, skill: str, suggestion_id: str, owner: str | None = None) -> dict[str, Any]:
    """Materializa uma sugestão como proposta revisável, sem editar a skill ativa."""
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    suggestions = read_suggestions(root, skill)
    suggestion = next((item for item in suggestions if item.get("suggestion_id") == suggestion_id), None)
    if suggestion is None:
        raise ValueError(f"sugestão não encontrada: {suggestion_id}")
    existing = read_proposals(root, skill)
    prior = next((item for item in existing if item.get("suggestion_id") == suggestion_id), None)
    if prior is not None:
        return prior
    skill_path = root / ".claude" / "skills" / skill / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8", errors="replace")
    base_hash = sha256(content.encode("utf-8")).hexdigest()
    proposal_id = "P-" + sha256(f"{skill}\0{suggestion_id}\0{base_hash}".encode("utf-8")).hexdigest()[:12]
    proposal_dir = proposals_root(root, skill) / proposal_id
    proposal_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir = proposal_dir / "candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    base_dir = proposal_dir / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    proposal = {
        "proposal_id": proposal_id,
        "skill": skill,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "owner": owner,
        "suggestion_id": suggestion_id,
        "base_version": next(
            (item.get("version", 1) for item in load_registry(root).get("skills", []) if item.get("id") == skill),
            1,
        ),
        "base_sha256": base_hash,
        "candidate_path": (candidate_dir / "SKILL.md").relative_to(root).as_posix(),
        "base_path": (base_dir / "SKILL.md").relative_to(root).as_posix(),
        "evidence_event_ids": suggestion.get("evidence_event_ids", []),
        "pattern": suggestion.get("pattern"),
        "rationale": suggestion.get("rationale"),
        "proposed_action": suggestion.get("proposed_action"),
        "change_summary": None,
        "evaluation": {"required": True, "regression_cases": [], "validation_score": None, "notes": None},
        "evaluation_policy": evaluation_policy(root, skill),
        "usage_contract": usage_contract(root, skill),
    }
    proposal_json = json.dumps(proposal, ensure_ascii=False, indent=2) + "\n"
    (proposal_dir / "proposal.json").write_text(proposal_json, encoding="utf-8")
    (candidate_dir / "SKILL.md").write_text(content, encoding="utf-8")
    (base_dir / "SKILL.md").write_text(content, encoding="utf-8")
    (proposal_dir / "proposal.md").write_text(
        "\n".join(
            [
                f"# Proposta {proposal_id}",
                "",
                f"- Skill: `{skill}`",
                f"- Sugestão: `{suggestion_id}`",
                f"- Versão base: `{proposal['base_version']}`",
                f"- SHA-256 base: `{base_hash}`",
                f"- Responsável: `{owner or 'não definido'}`",
                "",
                "## Evidência",
                "",
                suggestion.get("rationale", ""),
                "",
                "Experiências: " + ", ".join(suggestion.get("evidence_event_ids", [])),
                "",
                "## Mudança proposta",
                "",
                "Preencher antes da avaliação: descreva exatamente o que será alterado no SKILL.md.",
                "",
                "## Avaliação obrigatória",
                "",
                "- [ ] Adicionar casos de regressão.",
                "- [ ] Executar a suíte de validação.",
                "- [ ] Verificar ausência de regressões.",
                "- [ ] Confirmar que a mudança não enfraquece guardrails.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _set_suggestion_status(root, skill, suggestion_id, "in_progress")
    sync_registry(root)
    return proposal


def _load_proposal(root: Path, skill: str, proposal_id: str) -> tuple[dict[str, Any], Path]:
    path = proposal_directory(root, skill, proposal_id) / "proposal.json"
    if not path.is_file():
        raise ValueError(f"proposta não encontrada: {proposal_id}")
    proposal = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(proposal, dict) or proposal.get("skill") != skill:
        raise ValueError(f"proposta inválida: {proposal_id}")
    return proposal, path


def _save_proposal(path: Path, proposal: dict[str, Any]) -> None:
    path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def proposal_context(root: Path, skill: str, proposal_id: str) -> dict[str, Any]:
    """Reúne o que o autor de uma candidata precisa ler antes de editá-la; não altera nada."""
    proposal, _ = _load_proposal(root, skill, proposal_id)
    ids = set(proposal.get("evidence_event_ids") or [])
    fields = ("event_id", "source", "outcome", "score", "failure_type", "summary", "human_correction", "tools", "files", "tags")
    evidence = [
        {key: event.get(key) for key in fields}
        for event in read_experiences(root, skill)
        if event.get("event_id") in ids
    ]
    active = root / ".claude" / "skills" / skill / "SKILL.md"
    active_hash = sha256(active.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
    cases_dir = root / ".init-harness" / "skills" / skill / "eval" / "cases"
    contract = usage_contract(root, skill)
    return {
        "proposal_id": proposal_id,
        "skill": skill,
        "status": proposal.get("status"),
        "pattern": proposal.get("pattern"),
        "rationale": proposal.get("rationale"),
        "base_path": proposal["base_path"],
        "candidate_path": proposal["candidate_path"],
        "active_matches_base": active_hash == proposal.get("base_sha256"),
        "candidate_changed": (root / proposal["candidate_path"]).read_bytes() != (root / proposal["base_path"]).read_bytes(),
        "change_summary": proposal.get("change_summary"),
        "evidence": evidence,
        # Falha automática (source=system) só diz que houve falha, não o motivo.
        "explained_evidence": sum(1 for item in evidence if item.get("source") != "system" or item.get("human_correction")),
        "usage_contract": contract,
        "usage_contract_ready": bool(contract.get("when")) and bool(str(contract.get("expected_outcome") or "").strip()),
        "evaluation_policy": proposal.get("evaluation_policy") or evaluation_policy(root, skill),
        "case_files": sorted(p.name for p in cases_dir.glob("*.json") if p.name != "schema.json") if cases_dir.is_dir() else [],
    }


def submit_candidate(root: Path, skill: str, proposal_id: str, summary: str) -> dict[str, Any]:
    """Valida a candidata escrita para uma proposta e registra o que ela muda."""
    summary = summary.strip()
    if not summary:
        raise ValueError("summary é obrigatório: descreva o que mudou e por quê")
    proposal, path = _load_proposal(root, skill, proposal_id)
    if proposal.get("status") in {"evaluated", "promoted", "conflict"}:
        raise ValueError(f"proposta em status {proposal.get('status')} não aceita nova candidata; crie outra proposta")
    active = root / ".claude" / "skills" / skill / "SKILL.md"
    active_hash = sha256(active.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
    if active_hash != proposal.get("base_sha256"):
        proposal["status"] = "conflict"
        _save_proposal(path, proposal)
        raise ValueError("skill ativa mudou desde a criação da proposta; recrie a proposta")
    candidate = root / proposal["candidate_path"]
    if not candidate.is_file():
        raise ValueError(f"candidata ausente: {candidate}")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    metadata = parse_frontmatter(text)
    if metadata.get("name") != skill or not metadata.get("description"):
        raise ValueError("candidata precisa de frontmatter na linha 1 com name igual à skill e description não vazia")
    candidate_hash = sha256(text.encode("utf-8")).hexdigest()
    if candidate_hash == proposal.get("base_sha256"):
        raise ValueError("candidata não contém mudança em relação à skill ativa")
    proposal["status"] = "candidate"
    proposal["change_summary"] = summary
    proposal["candidate_sha256"] = candidate_hash
    proposal["candidate_submitted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    proposal["evaluation"] = {"required": True, "regression_cases": [], "validation_score": None, "notes": None}
    _save_proposal(path, proposal)
    markdown = path.parent / "proposal.md"
    if markdown.is_file():
        head, marker, rest = markdown.read_text(encoding="utf-8").partition("## Mudança proposta\n\n")
        _, separator, tail = rest.partition("\n\n## Avaliação obrigatória")
        if marker and separator:
            markdown.write_text(head + marker + summary + separator + tail, encoding="utf-8")
    return proposal


def evaluate_proposal(
    root: Path,
    skill: str,
    proposal_id: str,
    baseline_score: float,
    candidate_score: float,
    regressions: int = 0,
    guardrail_failures: int = 0,
    notes: str | None = None,
    minimum_improvement: float | None = None,
    max_regressions: int | None = None,
    max_guardrail_failures: int | None = None,
) -> dict[str, Any]:
    proposal, path = _load_proposal(root, skill, proposal_id)
    if not 0 <= baseline_score <= 1 or not 0 <= candidate_score <= 1:
        raise ValueError("scores devem estar entre 0 e 1")
    if regressions < 0 or guardrail_failures < 0:
        raise ValueError("regressões e falhas de guardrail não podem ser negativas")
    active = root / ".claude" / "skills" / skill / "SKILL.md"
    candidate = root / proposal["candidate_path"]
    if not candidate.is_file():
        raise ValueError(f"candidata ausente: {candidate}")
    active_hash = sha256(active.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
    if active_hash != proposal.get("base_sha256"):
        proposal["status"] = "conflict"
        _save_proposal(path, proposal)
        raise ValueError("skill ativa mudou desde a criação da proposta; recrie a proposta")
    candidate_text = candidate.read_text(encoding="utf-8", errors="replace")
    metadata = parse_frontmatter(candidate_text)
    if metadata.get("name", skill) != skill or not metadata.get("description"):
        raise ValueError("candidata precisa de frontmatter com name e description válidos")
    candidate_hash = sha256(candidate_text.encode("utf-8")).hexdigest()
    if candidate_hash == proposal.get("base_sha256"):
        raise ValueError("candidata não contém mudança em relação à skill ativa")
    policy = proposal.get("evaluation_policy") or evaluation_policy(root, skill)
    improvement = (
        candidate_score - baseline_score
        if policy.get("higher_is_better", True)
        else baseline_score - candidate_score
    )
    required_improvement = (
        minimum_improvement if minimum_improvement is not None else float(policy.get("minimum_improvement", 0.0))
    )
    allowed_regressions = max_regressions if max_regressions is not None else int(policy.get("max_regressions", 0))
    allowed_guardrails = (
        max_guardrail_failures
        if max_guardrail_failures is not None
        else int(policy.get("max_guardrail_failures", 0))
    )
    passed = (
        improvement >= required_improvement
        and regressions <= allowed_regressions
        and guardrail_failures <= allowed_guardrails
    )
    proposal["status"] = "evaluated" if passed else "rejected"
    proposal["evaluation"] = {
        "required": True,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "metric": policy.get("metric"),
        "improvement": improvement,
        "required_improvement": required_improvement,
        "regressions": regressions,
        "guardrail_failures": guardrail_failures,
        "allowed_regressions": allowed_regressions,
        "allowed_guardrail_failures": allowed_guardrails,
        "passed": passed,
        "candidate_sha256": candidate_hash,
        "notes": notes,
    }
    _save_proposal(path, proposal)
    return proposal


def _results_path(root: Path, value: str) -> Path:
    root = Path(os.path.abspath(root))
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("arquivo de resultados deve estar dentro do projeto")
    resolved = Path(os.path.abspath(root / path))
    relative = Path(os.path.relpath(resolved, root))
    if relative == Path("..") or ".." in relative.parts:
        raise ValueError("arquivo de resultados deve estar dentro do projeto")
    return resolved


def evaluate_results(
    root: Path, skill: str, proposal_id: str, results_file: str, notes: str | None = None
) -> dict[str, Any]:
    """Calcula a avaliação a partir de resultados por caso produzidos por um runner."""
    path = _results_path(root, results_file)
    if not path.is_file():
        raise ValueError(f"arquivo de resultados não encontrado: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("resultados precisam conter uma lista não vazia em 'cases'")
    policy = evaluation_policy(root, skill)
    required = set(policy.get("required_cases", []))
    seen: set[str] = set()
    baseline_scores: list[float] = []
    candidate_scores: list[float] = []
    regressions = 0
    guardrail_failures = 0
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise ValueError("cada caso precisa de case_id")
        case_id = case["case_id"]
        if case_id in seen:
            raise ValueError(f"caso duplicado: {case_id}")
        seen.add(case_id)
        baseline = case.get("baseline_score")
        candidate = case.get("candidate_score")
        if not isinstance(baseline, (int, float)) or not isinstance(candidate, (int, float)):
            raise ValueError(f"caso {case_id} precisa de baseline_score e candidate_score")
        if not 0 <= baseline <= 1 or not 0 <= candidate <= 1:
            raise ValueError(f"scores inválidos no caso {case_id}")
        baseline_scores.append(float(baseline))
        candidate_scores.append(float(candidate))
        if case.get("baseline_passed") is True and case.get("candidate_passed") is False:
            regressions += 1
        failures = case.get("guardrail_failures", 0)
        if not isinstance(failures, int) or failures < 0:
            raise ValueError(f"guardrail_failures inválido no caso {case_id}")
        guardrail_failures += failures
    missing = sorted(required - seen)
    if missing:
        raise ValueError("casos obrigatórios ausentes: " + ", ".join(missing))
    return evaluate_proposal(
        root,
        skill,
        proposal_id,
        sum(baseline_scores) / len(baseline_scores),
        sum(candidate_scores) / len(candidate_scores),
        regressions,
        guardrail_failures,
        notes or payload.get("notes"),
    )


def init_evaluation(root: Path, skill: str) -> Path:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    evaluation = root / ".init-harness" / "skills" / skill / "eval"
    cases = evaluation / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    readme = cases / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Casos de avaliação\n\n"
            "Cada caso deve ter um `case_id` correspondente a `required_cases` no manifesto.\n"
            "O runner do projeto recebe este diretório e produz resultados por caso.\n",
            encoding="utf-8",
        )
    schema = cases / "schema.json"
    if not schema.exists():
        schema.write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["case_id"],
                    "properties": {
                        "case_id": {"type": "string", "minLength": 1},
                        "task": {"type": "string"},
                        "input": {},
                        "expected": {},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": True,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    example = cases / "case-001.json"
    if not example.exists():
        example.write_text(
            json.dumps(
                {"case_id": "case-001", "example": True, "task": "Cenário de exemplo", "input": {}, "expected": {}, "tags": []},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return evaluation


def evaluation_cases(root: Path, skill: str, cases_dir: str | None = None) -> list[dict[str, Any]]:
    """Valida e retorna os casos JSON versionáveis do dataset da skill."""
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    directory = (
        _results_path(root, cases_dir)
        if cases_dir
        else Path(os.path.abspath(root / ".init-harness" / "skills" / skill / "eval" / "cases"))
    )
    if not directory.is_dir():
        raise ValueError(f"diretório de casos não encontrado: {directory}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        if path.name == "schema.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"caso inválido em {path}: JSON inválido") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"caso inválido em {path}: cada arquivo deve conter um objeto")
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise ValueError(f"caso inválido em {path}: case_id obrigatório")
        if case_id in seen:
            raise ValueError(f"case_id duplicado no dataset: {case_id}")
        seen.add(case_id)
        rows.append(payload)
    required = set(evaluation_policy(root, skill).get("required_cases", []))
    missing = sorted(required - seen)
    if missing:
        raise ValueError("casos obrigatórios ausentes: " + ", ".join(missing))
    return rows


def run_evaluation(
    root: Path,
    skill: str,
    proposal_id: str,
    runner_file: str,
    cases_dir: str | None = None,
    output_file: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    proposal, _ = _load_proposal(root, skill, proposal_id)
    runner = _results_path(root, runner_file)
    if runner.suffix.lower() != ".py" or not runner.is_file():
        raise ValueError("runner deve ser um arquivo .py dentro do projeto")
    cases = _results_path(root, cases_dir or f".init-harness/skills/{skill}/eval/cases")
    if not cases.is_dir():
        raise ValueError(f"diretório de casos não encontrado: {cases}")
    evaluation_cases(root, skill, cases_dir)
    output = output_file or f"{proposal_directory(root, skill, proposal_id).relative_to(root).as_posix()}/results.json"
    output_path = _results_path(root, output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(runner),
        "--skill",
        skill,
        "--base",
        str(root / proposal["base_path"]),
        "--candidate",
        str(root / proposal["candidate_path"]),
        "--cases",
        str(cases),
        "--output",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"runner excedeu o timeout de {timeout}s") from exc
    if completed.returncode != 0:
        raise ValueError(f"runner falhou ({completed.returncode}): {completed.stderr[-1000:]}")
    if not output_path.is_file():
        raise ValueError("runner terminou sem produzir o arquivo de resultados")
    return evaluate_results(
        root,
        skill,
        proposal_id,
        Path(os.path.relpath(output_path, root)).as_posix(),
        completed.stdout[-1000:],
    )


def _update_registry_skill(root: Path, skill: str, updates: dict[str, Any]) -> None:
    path = registry_path(root)
    data = load_registry(root)
    for item in data.get("skills", []):
        if item.get("id") == skill:
            item.update(updates)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = root / ".init-harness" / "skills" / skill / "manifest.json"
    if manifest.is_file():
        current = json.loads(manifest.read_text(encoding="utf-8"))
        current.update(updates)
        manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def accept_proposal(root: Path, skill: str, proposal_id: str) -> dict[str, Any]:
    proposal, path = _load_proposal(root, skill, proposal_id)
    evaluation = proposal.get("evaluation") or {}
    if proposal.get("status") != "evaluated" or not evaluation.get("passed"):
        raise ValueError("somente proposta avaliada com sucesso pode ser promovida")
    active = root / ".claude" / "skills" / skill / "SKILL.md"
    candidate = root / proposal["candidate_path"]
    active_hash = sha256(active.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
    if active_hash != proposal.get("base_sha256"):
        proposal["status"] = "conflict"
        _save_proposal(path, proposal)
        raise ValueError("skill ativa mudou desde a avaliação; promoção cancelada")
    candidate_hash = sha256(candidate.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
    if candidate_hash != evaluation.get("candidate_sha256"):
        raise ValueError("candidata mudou depois da avaliação; avalie novamente antes de promover")
    active.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
    registry = load_registry(root)
    current_version = next(
        (int(item.get("version", 1)) for item in registry.get("skills", []) if item.get("id") == skill), 1
    )
    new_version = current_version + 1
    history = root / ".init-harness" / "skills" / skill / "history"
    history.mkdir(parents=True, exist_ok=True)
    snapshot = history / f"version-{new_version:03d}.json"
    snapshot.write_text(
        json.dumps(
            {
                "version": new_version,
                "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "proposal_id": proposal_id,
                "skill_sha256": sha256(active.read_bytes()).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    proposal["status"] = "promoted"
    proposal["promoted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    proposal["promoted_version"] = new_version
    _save_proposal(path, proposal)
    _set_suggestion_status(
        root, skill, proposal.get("suggestion_id"), "addressed",
        addressed_by=proposal_id, addressed_at=proposal["promoted_at"],
    )
    _update_registry_skill(
        root,
        skill,
        {"version": new_version, "status": "active", "last_evaluated": proposal["promoted_at"]},
    )
    return proposal


def load_registry(root: Path) -> dict[str, Any]:
    path = registry_path(root)
    if not path.is_file():
        return {"schema_version": 1, "updated_at": None, "skills": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("skills", []), list):
        raise ValueError(f"catálogo inválido: {path}")
    return data


def evaluation_policy(root: Path, skill: str) -> dict[str, Any]:
    data = load_registry(root)
    item = next((entry for entry in data.get("skills", []) if entry.get("id") == skill), None)
    policy = dict(DEFAULT_EVALUATION_POLICY)
    if item and isinstance(item.get("evaluation_policy"), dict):
        policy.update(item["evaluation_policy"])
    return policy


def usage_contract(root: Path, skill: str) -> dict[str, Any]:
    data = load_registry(root)
    item = next((entry for entry in data.get("skills", []) if entry.get("id") == skill), None)
    contract = dict(DEFAULT_USAGE_CONTRACT)
    if item and isinstance(item.get("usage_contract"), dict):
        contract.update(item["usage_contract"])
    return contract


def configure_evaluation(root: Path, skill: str, args: argparse.Namespace) -> dict[str, Any]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    if not registry_path(root).is_file():
        sync_registry(root)
    policy = {
        "metric": args.metric,
        "higher_is_better": not args.lower_is_better,
        "minimum_improvement": args.minimum_improvement,
        "max_regressions": args.max_regressions,
        "max_guardrail_failures": args.max_guardrail_failures,
        "dimensions": sorted(set(args.dimension)),
        "required_cases": sorted(set(args.case)),
    }
    if policy["minimum_improvement"] < 0 or policy["max_regressions"] < 0 or policy["max_guardrail_failures"] < 0:
        raise ValueError("limiares não podem ser negativos")
    _update_registry_skill(root, skill, {"evaluation_policy": policy})
    return policy


def configure_usage(root: Path, skill: str, args: argparse.Namespace) -> dict[str, Any]:
    if skill not in _skill_ids(root):
        raise ValueError(f"skill não encontrada: {skill}")
    if not args.when or not args.expected_outcome.strip():
        raise ValueError("contrato precisa de pelo menos um --when e --expected-outcome")
    contract = {
        "when": sorted(set(args.when)),
        "when_not": sorted(set(args.when_not)),
        "tools": sorted(set(args.tool)),
        "surfaces": sorted(set(args.surface)),
        "expected_outcome": args.expected_outcome.strip(),
        "risk": args.risk,
    }
    if not registry_path(root).is_file():
        sync_registry(root)
    _update_registry_skill(root, skill, {"usage_contract": contract})
    return contract


def sync_registry(root: Path) -> dict[str, Any]:
    """Sincroniza descoberta com o catálogo, preservando metadados existentes."""
    current = load_registry(root)
    previous = {item.get("id"): item for item in current.get("skills", []) if isinstance(item, dict)}
    skills: list[dict[str, Any]] = []
    for discovered in discover_skills(root):
        old = previous.get(discovered["id"], {})
        item = dict(discovered)
        item["version"] = int(old.get("version", 1))
        item["status"] = old.get("status", "active")
        item["risk"] = old.get("risk", "medium" if item["scope"] == "project" else "high")
        item["evaluation_policy"] = old.get("evaluation_policy", dict(DEFAULT_EVALUATION_POLICY))
        item["usage_contract"] = old.get("usage_contract", dict(DEFAULT_USAGE_CONTRACT))
        item["last_evaluated"] = old.get("last_evaluated")
        experience_file = experiences_path(root, item["id"])
        item["experience_path"] = experience_file.relative_to(root).as_posix()
        experiences = read_experiences(root, item["id"]) if experience_file.is_file() else []
        item["experience_count"] = len(experiences)
        item["last_experience_at"] = old.get("last_experience_at")
        if experiences:
            last = experiences[-1]
            item["last_experience_at"] = last.get("occurred_at")
        suggestions = read_suggestions(root, item["id"]) if suggestions_path(root, item["id"]).is_file() else []
        item["suggestion_path"] = suggestions_path(root, item["id"]).relative_to(root).as_posix()
        item["suggestion_count"] = len(suggestions)
        proposals = read_proposals(root, item["id"])
        item["proposal_path"] = proposals_root(root, item["id"]).relative_to(root).as_posix()
        item["proposal_count"] = len(proposals)
        item["history_path"] = old.get(
            "history_path", f".init-harness/skills/{item['id']}/history/"
        )
        skills.append(item)
    result = {"schema_version": 1, "updated_at": date.today().isoformat(), "skills": skills}
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in skills:
        manifest = root / ".init-harness" / "skills" / item["id"] / "manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def format_listing(root: Path, *, sync: bool = False) -> str:
    data = sync_registry(root) if sync else {"skills": discover_skills(root)}
    rows = [f"{item['id']} [{item.get('scope', 'project')}] {item.get('skill_path', '')}" for item in data["skills"]]
    return "\n".join(rows) if rows else "Nenhuma skill encontrada."


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Catálogo local de skills do init-harness.")
    root.add_argument("--root", type=Path, default=Path.cwd())
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Lista skills descobertas.")
    commands.add_parser("sync", help="Atualiza registry.json e manifestos.")
    inspect = commands.add_parser("inspect", help="Mostra o manifesto de uma skill.")
    inspect.add_argument("skill")
    record = commands.add_parser("record", help="Registra uma experiência observada ao usar uma skill.")
    record.add_argument("skill")
    record.add_argument("--task-id", required=True)
    record.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    record.add_argument("--summary", required=True)
    record.add_argument("--score", type=float)
    record.add_argument("--failure-type")
    record.add_argument("--session-id", default=None)
    record.add_argument("--occurred-at", default=None)
    record.add_argument("--source", choices=sorted(SOURCES), default="agent")
    record.add_argument("--human-correction", action="store_true")
    record.add_argument("--tool", action="append", default=[])
    record.add_argument("--file", action="append", default=[])
    record.add_argument("--metric", action="append", default=[])
    record.add_argument("--tag", action="append", default=[])
    experiences = commands.add_parser("experiences", help="Lista experiências registradas de uma skill.")
    experiences.add_argument("skill")
    experiences.add_argument("--limit", type=int, default=None)
    suggestions = commands.add_parser("suggestions", help="Lista sugestões geradas a partir das experiências.")
    suggestions.add_argument("skill")
    suggestions.add_argument("--limit", type=int, default=None)
    proposals = commands.add_parser("proposals", help="Lista propostas versionadas de uma skill.")
    proposals.add_argument("skill")
    propose = commands.add_parser("propose", help="Transforma uma sugestão em proposta revisável.")
    propose.add_argument("skill")
    propose.add_argument("--suggestion", required=True)
    propose.add_argument("--owner", default=None)
    context = commands.add_parser("proposal-context", help="Mostra evidências e limites para escrever a candidata.")
    context.add_argument("skill")
    context.add_argument("--proposal", required=True)
    submit = commands.add_parser("submit-candidate", help="Valida a candidata escrita e registra o resumo da mudança.")
    submit.add_argument("skill")
    submit.add_argument("--proposal", required=True)
    submit.add_argument("--summary", required=True)
    evaluate = commands.add_parser("evaluate", help="Registra avaliação de uma proposta candidata.")
    evaluate.add_argument("skill")
    evaluate.add_argument("--proposal", required=True)
    evaluate.add_argument("--baseline-score", type=float, required=True)
    evaluate.add_argument("--candidate-score", type=float, required=True)
    evaluate.add_argument("--regressions", type=int, default=0)
    evaluate.add_argument("--guardrail-failures", type=int, default=0)
    evaluate.add_argument("--notes", default=None)
    evaluate.add_argument("--minimum-improvement", type=float, default=None)
    evaluate.add_argument("--max-regressions", type=int, default=None)
    evaluate.add_argument("--max-guardrail-failures", type=int, default=None)
    evaluate_results_parser = commands.add_parser(
        "evaluate-results", help="Calcula a avaliação a partir de resultados por caso em JSON."
    )
    evaluate_results_parser.add_argument("skill")
    evaluate_results_parser.add_argument("--proposal", required=True)
    evaluate_results_parser.add_argument("--results", required=True)
    evaluate_results_parser.add_argument("--notes", default=None)
    accept = commands.add_parser("accept", help="Promove uma proposta avaliada para a skill ativa.")
    accept.add_argument("skill")
    accept.add_argument("--proposal", required=True)
    configure = commands.add_parser("configure-evaluation", help="Define a política de avaliação contextual da skill.")
    configure.add_argument("skill")
    configure.add_argument("--metric", default="task_success_rate")
    configure.add_argument("--minimum-improvement", type=float, default=0.0)
    configure.add_argument("--max-regressions", type=int, default=0)
    configure.add_argument("--max-guardrail-failures", type=int, default=0)
    configure.add_argument("--lower-is-better", action="store_true")
    configure.add_argument("--dimension", action="append", default=[])
    configure.add_argument("--case", action="append", default=[])
    usage = commands.add_parser("configure-usage", help="Define o contrato contextual de uso da skill.")
    usage.add_argument("skill")
    usage.add_argument("--when", action="append", default=[])
    usage.add_argument("--when-not", action="append", default=[])
    usage.add_argument("--tool", action="append", default=[])
    usage.add_argument("--surface", action="append", default=[])
    usage.add_argument("--expected-outcome", required=True)
    usage.add_argument("--risk", choices=("low", "medium", "high", "critical"), default="medium")
    init_eval = commands.add_parser("init-evaluation", help="Cria a estrutura de casos de avaliação da skill.")
    init_eval.add_argument("skill")
    run_eval = commands.add_parser("run-evaluation", help="Executa o runner do projeto e avalia a proposta.")
    run_eval.add_argument("skill")
    run_eval.add_argument("--proposal", required=True)
    run_eval.add_argument("--runner", required=True)
    run_eval.add_argument("--cases", default=None)
    run_eval.add_argument("--output", default=None)
    run_eval.add_argument("--timeout", type=int, default=300)
    validate_cases = commands.add_parser("validate-cases", help="Valida o dataset JSON de uma skill.")
    validate_cases.add_argument("skill")
    validate_cases.add_argument("--cases", default=None)
    commands.add_parser("capture-hook", help="Lê um evento JSON estruturado do cliente via stdin.")
    activate = commands.add_parser("activate", help="Ativa uma skill no contexto de uma sessão.")
    activate.add_argument("skill")
    activate.add_argument("--session-id", required=True)
    deactivate = commands.add_parser("deactivate", help="Remove a skill ativa do contexto de uma sessão.")
    deactivate.add_argument("--session-id", required=True)
    active = commands.add_parser("active", help="Mostra a skill ativa no contexto de uma sessão.")
    active.add_argument("--session-id", required=True)
    jobs = commands.add_parser("jobs", help="Lista jobs assíncronos de evolução.")
    jobs.add_argument(
        "--status",
        choices=(
            "queued",
            "processing",
            "analyzed",
            "review_required",
            "review_approved",
            "human_required",
            "approved",
            "rejected",
            "promoted",
            "failed",
        ),
    )
    review_job = commands.add_parser("review-job", help="Registra decisão humana sobre um job revisado.")
    review_job.add_argument("job_id")
    review_job.add_argument("--decision", choices=("approved", "rejected"), required=True)
    review_job.add_argument("--note", required=True)
    commands.add_parser("status", help="Mostra o painel compacto da evolução.")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = project_root(args.root)
    if args.command == "list":
        print(format_listing(root))
        return 0
    if args.command == "sync":
        print(format_listing(root, sync=True))
        return 0
    if args.command == "record":
        before = {item["suggestion_id"]: item.get("occurrences") for item in read_suggestions(root, args.skill)}
        event = record_experience(root, args)
        rows = read_suggestions(root, args.skill)
        after = [item for item in rows if item["suggestion_id"] not in before]
        updated = [
            {"suggestion_id": item["suggestion_id"], "occurrences": item["occurrences"]}
            for item in rows
            if item["suggestion_id"] in before and item.get("occurrences") != before[item["suggestion_id"]]
        ]
        print(
            json.dumps(
                {"experience": event, "new_suggestions": after, "updated_suggestions": updated},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "experiences":
        print(json.dumps(read_experiences(root, args.skill, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "suggestions":
        print(json.dumps(read_suggestions(root, args.skill, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "proposals":
        print(json.dumps(read_proposals(root, args.skill), ensure_ascii=False, indent=2))
        return 0
    if args.command == "propose":
        print(json.dumps(create_proposal(root, args.skill, args.suggestion, args.owner), ensure_ascii=False, indent=2))
        return 0
    if args.command == "proposal-context":
        print(json.dumps(proposal_context(root, args.skill, args.proposal), ensure_ascii=False, indent=2))
        return 0
    if args.command == "submit-candidate":
        print(json.dumps(submit_candidate(root, args.skill, args.proposal, args.summary), ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate":
        print(
            json.dumps(
                evaluate_proposal(
                    root,
                    args.skill,
                    args.proposal,
                    args.baseline_score,
                    args.candidate_score,
                    args.regressions,
                    args.guardrail_failures,
                    args.notes,
                    args.minimum_improvement,
                    args.max_regressions,
                    args.max_guardrail_failures,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "accept":
        print(json.dumps(accept_proposal(root, args.skill, args.proposal), ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate-results":
        print(
            json.dumps(
                evaluate_results(root, args.skill, args.proposal, args.results, args.notes),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "configure-evaluation":
        print(json.dumps(configure_evaluation(root, args.skill, args), ensure_ascii=False, indent=2))
        return 0
    if args.command == "configure-usage":
        print(json.dumps(configure_usage(root, args.skill, args), ensure_ascii=False, indent=2))
        return 0
    if args.command == "init-evaluation":
        print(init_evaluation(root, args.skill).relative_to(root).as_posix())
        return 0
    if args.command == "run-evaluation":
        print(
            json.dumps(
                run_evaluation(root, args.skill, args.proposal, args.runner, args.cases, args.output, args.timeout),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "validate-cases":
        cases = evaluation_cases(root, args.skill, args.cases)
        print(
            json.dumps(
                {"skill": args.skill, "count": len(cases), "case_ids": [item["case_id"] for item in cases]},
                indent=2,
            )
        )
        return 0
    if args.command == "capture-hook":
        print(json.dumps(capture_hook_stdin(root, sys.stdin), ensure_ascii=False, indent=2))
        return 0
    if args.command == "activate":
        print(json.dumps(activate_skill(root, args.skill, args.session_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "deactivate":
        print(json.dumps(deactivate_skill(root, args.session_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "active":
        print(json.dumps(active_skill(root, args.session_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "jobs":
        print(json.dumps(read_jobs(root, args.status), ensure_ascii=False, indent=2))
        return 0
    if args.command == "review-job":
        print(json.dumps(decide_job(root, args.job_id, args.decision, args.note), ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(evolution_status(root), ensure_ascii=False, indent=2))
        return 0
    data = load_registry(root)
    item = next((skill for skill in data.get("skills", []) if skill.get("id") == args.skill), None)
    if item is None:
        print(f"Skill não encontrada: {args.skill}")
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

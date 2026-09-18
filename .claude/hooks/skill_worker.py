"""Worker econômico para processar jobs de evolução sem bloquear a sessão."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import skill_evolution as E  # noqa: E402


def process_once(root: Path, runner_file: str, timeout: int) -> dict | None:
    job = E.claim_next_job(root)
    if job is None:
        return None
    try:
        runner = E._results_path(root, runner_file)
    except ValueError:
        runner = Path()
    if runner.suffix.lower() != ".py" or not runner.is_file():
        return E.update_job(root, job["job_id"], "failed", error="worker runner inválido")
    output = root / ".init-harness" / "skills" / "queue" / f"{job['job_id']}.analysis.json"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(runner),
                "--job",
                str(E._job_file(root, job["job_id"])),
                "--output",
                str(output),
                "--root",
                str(root),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return E.update_job(root, job["job_id"], "failed", error=f"worker excedeu timeout de {timeout}s")
    if completed.returncode != 0 or not output.is_file():
        return E.update_job(
            root,
            job["job_id"],
            "failed",
            error=(completed.stderr or "runner não produziu análise")[-1000:],
        )
    try:
        analysis = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return E.update_job(root, job["job_id"], "failed", error=f"análise inválida: {exc}")
    needs_review = bool(analysis.get("needs_review", True)) if isinstance(analysis, dict) else True
    return E.update_job(root, job["job_id"], "review_required" if needs_review else "analyzed", analysis=analysis)


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker econômico de evolução de skills.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runner", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    while True:
        result = process_once(args.root, args.runner, args.timeout)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.once:
            return 0
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

"""Revisor caro configurável para jobs que exigem validação crítica."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import skill_evolution as E  # noqa: E402


def review_once(root: Path, runner_file: str, timeout: int) -> dict | None:
    E.recover_stale_jobs(root)
    jobs = E.read_jobs(root, "review_required")
    if not jobs:
        return None
    job = E.update_job(
        root, jobs[0]["job_id"], "processing", review_attempts=int(jobs[0].get("review_attempts") or 0) + 1
    )
    try:
        runner = E._results_path(root, runner_file)
    except ValueError:
        return E.update_job(root, job["job_id"], "failed", error="reviewer runner inválido")
    output = root / ".init-harness" / "skills" / "queue" / f"{job['job_id']}.review.json"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(runner),
                "--job",
                str(E._job_file(root, job["job_id"])),
                "--analysis",
                str(root / ".init-harness" / "skills" / "queue" / f"{job['job_id']}.analysis.json"),
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
        return E.update_job(root, job["job_id"], "failed", error=f"reviewer excedeu timeout de {timeout}s")
    if completed.returncode != 0 or not output.is_file():
        return E.update_job(
            root,
            job["job_id"],
            "failed",
            error=(completed.stderr or "reviewer não produziu decisão")[-1000:],
        )
    try:
        review = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return E.update_job(root, job["job_id"], "failed", error=f"revisão inválida: {exc}")
    if not isinstance(review, dict):
        return E.update_job(root, job["job_id"], "failed", error="revisão inválida: esperado um objeto JSON")
    if review.get("needs_human") is True:
        status = "human_required"  # o revisor não decide sozinho: o job segue visível para a decisão humana
    elif review.get("approved") is True:
        status = "review_approved"
    else:
        status = "rejected"
    return E.update_job(root, job["job_id"], status, review=review)


def main() -> int:
    parser = argparse.ArgumentParser(description="Revisor caro de evolução de skills.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runner", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    while True:
        result = review_once(args.root, args.runner, args.timeout)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.once:
            return 0
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

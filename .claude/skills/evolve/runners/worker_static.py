"""Runner de referência do worker econômico: triagem determinística, sem modelo.

Lê o job de uma experiência e decide se ela exige julgamento. O objetivo é impedir
que ruído chegue ao revisor caro: sucesso sem correção e falha automática sem
explicação são encerrados aqui. Correção humana, padrão recorrente e falha explicada
por um agente ou pelo humano seguem para revisão.

Contrato do `skill_worker.py`: `--job`, `--output`, `--root`. Escreve um objeto JSON com
`needs_review`. Não lê prompts nem transcrições, só o que o registro de experiência já
contém.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def read_experiences(root: Path, skill: str) -> list[dict]:
    path = root / ".init-harness" / "skills" / skill / "experiences.jsonl"
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def analyze(job: dict, experiences: list[dict]) -> dict:
    event = job.get("experience") or {}
    outcome = event.get("outcome")
    failure_type = str(event.get("failure_type") or "").strip().lower()
    human_correction = bool(event.get("human_correction"))
    explained = event.get("source") != "system" or human_correction
    recurrence = 0
    if failure_type:
        recurrence = sum(
            1
            for item in experiences
            if str(item.get("failure_type") or "").strip().lower() == failure_type and item.get("outcome") != "success"
        )
    signals = {
        "outcome": outcome,
        "source": event.get("source"),
        "failure_type": failure_type or None,
        "human_correction": human_correction,
        "explained": explained,
        "recurrence": recurrence,
    }
    if outcome == "success" and not human_correction:
        classification, needs_review, reasons = "no_action", False, ["sucesso sem correção humana"]
    elif human_correction:
        classification, needs_review, reasons = "needs_judgment", True, ["correção humana explícita"]
    elif recurrence >= 2:
        classification, needs_review, reasons = (
            "needs_judgment",
            True,
            [f"padrão recorrente ({recurrence} ocorrências)"],
        )
    elif explained:
        classification, needs_review, reasons = (
            "needs_judgment",
            True,
            ["falha com explicação registrada por agente ou humano"],
        )
    else:
        classification, needs_review = "unexplained_failure", False
        reasons = ["falha automática sem explicação e sem recorrência; aguardar /record ou nova ocorrência"]
    return {
        "analyzer": "worker_static",
        "skill": job.get("skill"),
        "experience_event_id": job.get("experience_event_id"),
        "classification": classification,
        "needs_review": needs_review,
        "reasons": reasons,
        "signals": signals,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Triagem determinística de uma experiência de skill.")
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    analysis = analyze(job, read_experiences(args.root, str(job.get("skill") or "")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Runner de referência para `skill_evolution.py run-evaluation`: verificação estrutural.

Mede se a candidata contém as instruções que os casos exigem e se preservou os
guardrails da base. Não executa nenhum agente: um caso aprovado aqui prova que o
texto da skill mudou como o caso pede, não que o comportamento do agente melhorou.
Para medir comportamento, use um runner do projeto que execute a skill.

Formato de `expected` em cada caso (comparação sem diferenciar caixa nem espaçamento):

  must_mention      trechos que a skill deve conter
  must_not_mention  trechos que a skill não deve conter
  guardrails        trechos que existem na base e não podem sumir da candidata

Casos com `"example": true` (o exemplo criado por `init-evaluation`) são ignorados.
Um caso sem nenhuma asserção, ou com guardrail ausente da base, é erro: um caso que
não verifica nada aprovaria qualquer candidata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

# O harness decodifica a saída como UTF-8; sem isso o console do Windows emite cp1252.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


class CaseError(ValueError):
    """Caso mal formado: o runner recusa em vez de aprovar sem verificar."""


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _phrases(case_id: str, expected: dict, key: str) -> list[str]:
    value = expected.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise CaseError(f"caso {case_id}: expected.{key} deve ser uma lista de textos não vazios")
    return [normalize(item) for item in value]


def evaluate_case(case: dict, base: str, candidate: str) -> dict:
    case_id = str(case.get("case_id") or "").strip()
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise CaseError(f"caso {case_id}: expected deve ser um objeto com must_mention, must_not_mention ou guardrails")
    mention = _phrases(case_id, expected, "must_mention")
    forbidden = _phrases(case_id, expected, "must_not_mention")
    guardrails = _phrases(case_id, expected, "guardrails")
    total = len(mention) + len(forbidden)
    if total == 0 and not guardrails:
        raise CaseError(f"caso {case_id}: sem asserções em expected; o caso aprovaria qualquer candidata")
    missing = [item for item in guardrails if item not in base]
    if missing:
        raise CaseError(f"caso {case_id}: guardrail ausente da base, corrija o caso: {missing[0]!r}")

    def score(text: str) -> float:
        if not total:
            return 1.0
        satisfied = sum(item in text for item in mention) + sum(item not in text for item in forbidden)
        return satisfied / total

    baseline, improved = score(base), score(candidate)
    return {
        "case_id": case_id,
        "baseline_score": baseline,
        "candidate_score": improved,
        "baseline_passed": baseline == 1.0,
        "candidate_passed": improved == 1.0,
        "guardrail_failures": sum(item not in candidate for item in guardrails),
    }


def load_cases(directory: Path) -> tuple[list[dict], int]:
    cases: list[dict] = []
    skipped = 0
    for path in sorted(directory.glob("*.json")):
        if path.name == "schema.json":
            continue
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CaseError(f"{path.name}: JSON inválido: {exc}") from exc
        if not isinstance(case, dict) or not str(case.get("case_id") or "").strip():
            raise CaseError(f"{path.name}: o caso precisa ser um objeto com case_id")
        if case.get("example") is True:
            skipped += 1
            continue
        cases.append(case)
    return cases, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Avaliação estrutural de uma candidata de skill.")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        cases, skipped = load_cases(args.cases)
        if not cases:
            raise CaseError("nenhum caso utilizável em " + str(args.cases) + " (exemplos são ignorados)")
        base = normalize(args.base.read_text(encoding="utf-8"))
        candidate = normalize(args.candidate.read_text(encoding="utf-8"))
        results = [evaluate_case(case, base, candidate) for case in cases]
    except CaseError as exc:
        print(f"static_eval: {exc}", file=sys.stderr)
        return 2
    summary = (
        f"static_eval: {len(results)} caso(s), {skipped} exemplo(s) ignorado(s); verificação estrutural do "
        "texto da skill, não mede comportamento do agente"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"cases": results, "notes": summary}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Testes unitários do contrato da orquestração hierárquica."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
RUNTIME = KIT / ".claude/skills/orquestrar/scripts/iniciativa_runtime.py"
SPEC = importlib.util.spec_from_file_location("iniciativa_runtime", RUNTIME)
assert SPEC is not None and SPEC.loader is not None
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def front(front_id: str, specialty: str, dependencies: list[str] | None = None) -> dict:
    return {
        "id": front_id,
        "team": f"team-{front_id}",
        "specialty": specialty,
        "spec": f"specs/{front_id}.md",
        "repository": ".",
        "branch": "main",
        "base_commit": "abc123",
        "dependencies": dependencies or [],
        "scope": ["src/"],
    }


class OrchestrationTest(unittest.TestCase):
    def manifest(self, first_front: dict | None = None) -> dict:
        return {
            "contract_version": 1,
            "initiative_id": "release-5",
            "profile": "hybrid",
            "limits": {
                "max_parallel": 2,
                "max_agents": 4,
                "max_calls": 10,
                "max_builders_per_supervisor": 2,
            },
            "fronts": [first_front or front("api", "backend")],
        }

    def test_manifest_requires_a_supported_specialty(self) -> None:
        data = self.manifest()
        self.assertEqual("api", runtime._validar_manifesto(data)[3][0]["id"])
        data["fronts"][0]["specialty"] = "general"
        with self.assertRaisesRegex(ValueError, "specialty inválida"):
            runtime._validar_manifesto(data)

    def test_frontend_preset_includes_existing_frontend_skill(self) -> None:
        content = runtime._specialty_prompt(KIT, KIT, "frontend")
        self.assertIn("Supervisor especialista: frontend", content)
        self.assertIn("# Frontend", content)
        self.assertIn("acessibilidade", content.lower())

    def test_chief_revision_invalidates_task_dependents_and_downstream_front(self) -> None:
        fronts = [front("api", "backend"), front("deploy", "deploy_cicd", ["api"])]
        state = {
            "plans": {
                "api": {"tasks": [{"id": "schema", "depends_on": []}, {"id": "route", "depends_on": ["schema"]}]},
                "deploy": {"tasks": [{"id": "pipeline", "depends_on": []}]},
            },
            "builds": {"api:schema": {}, "api:route": {}, "deploy:pipeline": {}},
            "build_attempts": {},
            "audits": {"api": {}, "deploy": {}},
        }

        runtime._apply_chief_decision(
            state,
            {
                "decision": "revise",
                "findings": [{"front_id": "api", "task_id": "schema", "instruction": "Corrija a migração."}],
            },
            fronts,
        )

        self.assertEqual("em_andamento", state["estado"])
        self.assertEqual({}, state["builds"])
        self.assertEqual({}, state["audits"])
        self.assertEqual({"api:schema", "api:route", "deploy:pipeline"}, set(state["chief_revisions"]))

    def test_chief_can_approve_or_pause_for_human_input(self) -> None:
        fronts = [front("api", "backend")]
        approved = {}
        runtime._apply_chief_decision(approved, {"decision": "approve", "summary": "Auditoria concluída."}, fronts)
        self.assertEqual("concluida", approved["estado"])

        paused = {}
        runtime._apply_chief_decision(paused, {"decision": "ask_human", "questions": ["Qual ambiente alvo?"]}, fronts)
        self.assertEqual("pausada", paused["estado"])
        self.assertEqual(["Qual ambiente alvo?"], paused["questions"])
        self.assertEqual("chief_review", paused["pending_checkpoint"]["stage"])


if __name__ == "__main__":
    unittest.main()

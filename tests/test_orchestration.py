"""Testes unitários do contrato da orquestração hierárquica."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_gate_scan_marks_relaxed_gates_in_front_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            (repo / "tests").mkdir()
            (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "base")
            (repo / "tests" / "test_a.py").write_text("", encoding="utf-8")
            self.assertIn("marcas={RH-1:1}", runtime._gate_scan(KIT, repo, ["tests/"]))
            self.assertIn("marcas={nenhuma}", runtime._gate_scan(KIT, repo, ["src/"]))
            self.assertIn("indisponível", runtime._gate_scan(repo, repo, ["tests/"]))


class CliCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "invocar_agentes_teste", KIT / ".claude/skills/orquestrar/scripts/invocar_agentes.py"
        )
        assert spec is not None and spec.loader is not None
        self.cli = importlib.util.module_from_spec(spec)
        scripts = str(RUNTIME.parent)
        sys.path.insert(0, scripts)  # o runner importa o runtime da própria pasta, como ao rodar como script
        try:
            spec.loader.exec_module(self.cli)
        finally:
            sys.path.remove(scripts)

    def comando(self, provedor: str, **agente: str) -> list[str]:
        with patch.object(self.cli.shutil, "which", side_effect=lambda nome: f"/bin/{nome}"):
            return self.cli.comando_para(provedor, {"modelo": "opus", "_papel": "executor", **agente})

    def test_claude_applies_configured_effort(self) -> None:
        comando = self.comando("claude", raciocinio="high")
        self.assertEqual("high", comando[comando.index("--effort") + 1])
        self.assertNotIn("--effort", self.comando("claude"))

    def test_codex_keeps_reasoning_config(self) -> None:
        self.assertIn('model_reasoning_effort="xhigh"', self.comando("codex", raciocinio="xhigh"))

    def test_effort_outside_the_schema_is_rejected(self) -> None:
        for provedor in ("claude", "codex"):
            with self.subTest(provedor=provedor), self.assertRaises(ValueError):
                self.comando(provedor, raciocinio="high; rm -rf /")


if __name__ == "__main__":
    unittest.main()

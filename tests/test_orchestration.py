"""Testes unitários do contrato da orquestração hierárquica."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
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


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


# CLI falso: responde por etapa conforme o início do prompt; FAKE_MODE escolhe o cenário do construtor.
FAKE_AGENT = r"""
import json, os, pathlib, sys

prompt = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"papel": sys.argv[1], "esquema": sys.argv[2], "inicio": prompt[:40]}) + "\n")
plano = {
    "tasks": [{"id": "T1", "objective": "criar a", "files": ["src/a.py"], "depends_on": [],
               "acceptance": [{"criterio": "a existe"}], "pair_with": []}],
    "interfaces": [{"rota": "GET /a"}],
    "questions": [],
}
cerca = chr(96) * 3
if prompt.startswith("PAPEL: reparo"):
    print(json.dumps(plano))
elif "Analise a spec" in prompt:
    print('{"tasks": [')
elif "Compare seu plano" in prompt:
    print(json.dumps({"agreements": [{"contrato": "GET /a"}], "conflicts": [], "questions": []}))
elif "Feche o plano" in prompt:
    fechamento = {"assignments": [{"task_id": "T1", "files": ["src/a.py"], "builder_context": "crie src/a.py"}],
                  "interfaces": [], "questions": []}
    print(cerca + "json\n" + json.dumps(fechamento) + "\n" + cerca)
elif prompt.startswith("PAPEL: construtor. Implemente"):
    pathlib.Path("src/a.py").write_text("x = 1\n", encoding="utf-8")
    pathlib.Path("src/__pycache__").mkdir(exist_ok=True)
    pathlib.Path("src/__pycache__/a.pyc").write_bytes(b"0")
    saida = pathlib.Path(os.environ["MAIN_REPO"]) / "graphify-out"
    saida.mkdir(exist_ok=True)
    (saida / "graph.json").write_text("{}", encoding="utf-8")
    arquivos = ["src/a.py", "src/__pycache__/a.pyc"]
    if os.environ.get("FAKE_MODE") == "fora":
        arquivos.append("src/b.py")
    print(json.dumps({"status": "completed", "summary": "ok", "files_changed": arquivos,
                      "checks": ["python -c 1"], "risks": [{"risco": "nenhum"}], "questions": []}))
elif "supervisor auditor" in prompt:
    print(json.dumps({"approved": True, "findings": [], "questions": [], "verification_evidence": ["diff lido"]}))
else:
    sys.exit("etapa desconhecida: " + prompt[:80])
"""


class InitiativeFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        repo = self.repo
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        (repo / ".init-harness" / "schema").mkdir(parents=True)
        shutil.copy(KIT / ".init-harness/schema/orquestracao.schema.json", repo / ".init-harness/schema")
        agente = {"provedor": "codex", "modelo": "gpt-5.6-luna", "modo": "cli"}
        perfil = {"id": "teste", "descricao": "d", "coordenador": agente, "executor": agente, "auditor": agente}
        (repo / ".init-harness/orquestracao.json").write_text(json.dumps({"perfis": [perfil]}), encoding="utf-8")
        (repo / ".init-harness/config.json").write_text("{}", encoding="utf-8")
        (repo / "specs").mkdir()
        (repo / "specs/api.md").write_text("# API\nCriar src/a.py.\n", encoding="utf-8")
        (repo / "src").mkdir()
        (repo / "src/base.py").write_text("", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        self.fake = Path(self.tmp.name) / "fake_agent.py"
        self.fake.write_text(FAKE_AGENT, encoding="utf-8")
        self.log = Path(self.tmp.name) / "chamadas.jsonl"
        self.manifest = {
            "contract_version": 1,
            "initiative_id": "fluxo",
            "profile": "teste",
            "limits": {"max_parallel": 1, "max_agents": 4, "max_calls": 5, "max_builders_per_supervisor": 2},
            "fronts": [
                {
                    **front("api", "backend"),
                    "branch": git(repo, "branch", "--show-current"),
                    "base_commit": git(repo, "rev-parse", "HEAD"),
                }
            ],
        }

    def tearDown(self) -> None:
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo, capture_output=True, check=False)
        self.tmp.cleanup()

    def run_initiative(self, manifest: dict, mode: str = "", **kwargs: object) -> dict:
        scripts = str(RUNTIME.parent)
        sys.path.insert(0, scripts)
        try:
            import invocar_agentes

            def comando(provedor: str, agente: dict, esquema: Path | None = None) -> list[str]:
                return [sys.executable, str(self.fake), agente["_papel"], str(esquema or "")]

            env = {"FAKE_LOG": str(self.log), "MAIN_REPO": str(self.repo), "FAKE_MODE": mode}
            with (
                patch.object(invocar_agentes, "comando_para", comando),
                patch.object(runtime.shutil, "which", return_value="/bin/codex"),
                patch.dict(os.environ, env),
            ):
                return asyncio.run(runtime.executar_iniciativa(self.repo, manifest, **kwargs))
        finally:
            sys.path.remove(scripts)

    def state(self) -> dict:
        return json.loads((self.repo / ".init-harness/state/orquestracao/fluxo/estado.json").read_text("utf-8"))

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_format_repair_is_free_and_environment_outputs_are_ignored(self) -> None:
        report = self.run_initiative(self.manifest)

        self.assertEqual("aguardando_auditoria_chefe", report["estado"])
        self.assertEqual("x = 1\n", (self.repo / "src/a.py").read_text(encoding="utf-8"))
        state = self.state()
        self.assertEqual(5, state["calls"])
        self.assertEqual(["plan:api:reparo"], state["repair_calls"])
        invalid = state["invalid_responses"]["plan:api"]
        self.assertTrue(invalid["repaired"])
        self.assertEqual('{"tasks": [', invalid["excerpt"].strip())
        self.assertIn("JSON estrito", invalid["error"])
        plan = state["plans"]["api"]
        self.assertEqual(['{"rota": "GET /a"}'], plan["interfaces"])
        self.assertEqual(['{"criterio": "a existe"}'], plan["tasks"][0]["acceptance"])
        self.assertEqual(['{"contrato": "GET /a"}'], state["agreements"]["api"]["agreements"])
        build = state["builds"]["api:T1"]
        self.assertEqual(["src/__pycache__/a.pyc"], build["generated_files_ignored"])
        self.assertEqual(['{"risco": "nenhum"}'], build["risks"])
        self.assertNotIn("graphify-out/graph.json", state["initial_paths"]["api"])
        saved = json.loads((self.repo / ".init-harness/state/orquestracao/fluxo/manifesto.json").read_text("utf-8"))
        self.assertEqual(self.manifest, saved)
        schemas = {call["esquema"] for call in self.calls()}
        self.assertNotIn("", schemas)
        plan_schema = json.loads(Path(next(s for s in schemas if s.endswith("plan.json"))).read_text("utf-8"))
        self.assertFalse(plan_schema["properties"]["tasks"]["items"]["additionalProperties"])

    def test_rejected_builder_keeps_details_and_resumes_by_initiative_id(self) -> None:
        self.manifest["limits"]["max_calls"] = 6
        paused = self.run_initiative(self.manifest, mode="fora")

        self.assertEqual("pausada", paused["estado"])
        self.assertIn("['src/b.py']", paused["motivo"])
        attempt = paused["build_attempts"]["api:T1"]
        self.assertEqual(["src/b.py"], attempt["out_of_scope"])
        self.assertEqual(['{"risco": "nenhum"}'], attempt["risks"])
        self.assertFalse((self.repo / "src/a.py").exists())

        saved = runtime.manifesto_salvo(self.repo, "fluxo")
        saved["limits"]["max_calls"] = 7  # só limits mudou: mesma iniciativa
        report = self.run_initiative(saved, retomar=True)

        self.assertEqual("aguardando_auditoria_chefe", report["estado"])
        state = self.state()
        self.assertEqual("api:T1", state["build_history"][0]["task"])
        self.assertEqual(7, state["limits"]["max_calls"])
        self.assertTrue((self.repo / "src/a.py").is_file())

    def test_budget_is_checked_right_after_planning(self) -> None:
        self.manifest["limits"]["max_calls"] = 3
        with self.assertRaisesRegex(ValueError, "são necessárias ao menos 5 chamadas"):
            self.run_initiative(self.manifest)
        self.assertIn("api", self.state()["plans"])
        self.assertEqual(1, self.state()["calls"])


class ContractHelpersTest(unittest.TestCase):
    def test_glob_and_arrow_paths_are_rejected_with_guidance(self) -> None:
        for name in ("reader/** -> apps/site/**", "reader/a.ts -> apps/a.ts", "src/*.py"):
            plan = {
                "tasks": [{"id": "T1", "objective": "o", "files": [name], "depends_on": [], "acceptance": ["a"]}],
                "interfaces": [],
                "questions": [],
            }
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "path explícito"):
                runtime._validar_plan({**front("api", "backend"), "scope": ["reader/", "apps/", "src/"]}, plan)

    def test_fenced_json_is_accepted_but_extra_text_is_not(self) -> None:
        self.assertEqual({"a": 1}, runtime._strict_json('```json\n{"a": 1}\n```', {"a"}, "x"))
        with self.assertRaises(ValueError):
            runtime._strict_json('Resposta: {"a": 1}', {"a"}, "x")

    def test_stage_schemas_follow_strict_structured_output_rules(self) -> None:
        contract = json.loads((KIT / ".init-harness/schema/orquestracao.schema.json").read_text(encoding="utf-8"))

        def check(node: dict, where: str) -> None:
            self.assertLessEqual(set(node), runtime._CHAVES_ESQUEMA, where)
            if "properties" in node:
                self.assertEqual(list(node["properties"]), node["required"], where)
                self.assertIs(False, node["additionalProperties"], where)
                for key, child in node["properties"].items():
                    check(child, f"{where}.{key}")
            if "items" in node:
                check(node["items"], f"{where}[]")

        for stage, name in runtime.ESQUEMAS.items():
            with self.subTest(stage=stage):
                check(runtime._esquema_estrito(contract["$defs"][name], contract["$defs"]), stage)

    def test_integration_copies_from_worktree_and_applies_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, worktree = Path(tmp) / "repo", Path(tmp) / "wt"
            (repo / "reader").mkdir(parents=True)
            (repo / "reader/a.ts").write_text("antigo\n", encoding="utf-8")
            (worktree / "apps/site").mkdir(parents=True)
            (worktree / "apps/site/a.ts").write_text("novo\n", encoding="utf-8")
            runtime._integrate_task_files(repo, worktree, {"files": ["reader/a.ts", "apps/site/a.ts"]})
            self.assertFalse((repo / "reader/a.ts").exists())
            self.assertEqual("novo\n", (repo / "apps/site/a.ts").read_text(encoding="utf-8"))

    def test_manifest_identity_ignores_limits(self) -> None:
        a = OrchestrationTest().manifest()
        b = {**a, "limits": {**a["limits"], "max_calls": 99}}
        self.assertEqual(runtime._manifest_fingerprint(a), runtime._manifest_fingerprint(b))
        self.assertNotEqual(runtime._fingerprint(a), runtime._fingerprint(b))

    def test_changed_files_reads_renames_and_skips_environment_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "t@t")
            git(repo, "config", "user.name", "t")
            (repo / "reader").mkdir()
            (repo / "reader/pagina.ts").write_text("x\n", encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "base")
            (repo / "apps/site").mkdir(parents=True)
            git(repo, "mv", "reader/pagina.ts", "apps/site/pagina.ts")
            for generated in ("graphify-out/graph.json", ".init-harness/skills/obs.jsonl", "src/__pycache__/a.pyc"):
                (repo / generated).parent.mkdir(parents=True, exist_ok=True)
                (repo / generated).write_text("{}", encoding="utf-8")
            self.assertEqual({"apps/site/pagina.ts", "reader/pagina.ts"}, runtime._changed_files(repo))
            self.assertIn("graphify-out/graph.json", runtime._changed_files(repo, ()))


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

    def test_codex_sets_approval_by_config_and_passes_output_schema(self) -> None:
        comando = self.comando("codex")
        self.assertNotIn("--ask-for-approval", comando)
        self.assertEqual('approval_policy="never"', comando[comando.index("--config") + 1])
        self.assertNotIn("--output-schema", comando)
        with patch.object(self.cli.shutil, "which", side_effect=lambda nome: f"/bin/{nome}"):
            comando = self.cli.comando_para("codex", {"modelo": "m", "_papel": "auditor"}, Path("plan.json"))
        self.assertEqual("plan.json", comando[comando.index("--output-schema") + 1])
        self.assertEqual("-", comando[-1])

    def test_effort_outside_the_schema_is_rejected(self) -> None:
        for provedor in ("claude", "codex"):
            with self.subTest(provedor=provedor), self.assertRaises(ValueError):
                self.comando(provedor, raciocinio="high; rm -rf /")


if __name__ == "__main__":
    unittest.main()

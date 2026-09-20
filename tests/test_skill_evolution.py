"""Testes do catálogo inicial de skills."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "skill_evolution.py"
SPEC = importlib.util.spec_from_file_location("skill_evolution", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
skill_evolution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill_evolution)


class SkillEvolutionTest(unittest.TestCase):
    def test_descobre_e_classifica_skills_do_metodo_e_do_projeto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, description in (("spec", "Método"), ("billing", "Rotina do projeto")):
                path = root / ".claude" / "skills" / name
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n",
                    encoding="utf-8",
                )

            skills = skill_evolution.discover_skills(root)

            self.assertEqual(["billing", "spec"], [item["id"] for item in skills])
            self.assertEqual("project", skills[0]["scope"])
            self.assertEqual("method", skills[1]["scope"])
            self.assertEqual("Rotina do projeto", skills[0]["description"])

    def test_sync_preserva_metadados_e_cria_manifestos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")
            registry = root / ".init-harness" / "skills" / "registry.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": [
                            {
                                "id": "billing",
                                "version": 7,
                                "status": "candidate",
                                "risk": "low",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = skill_evolution.sync_registry(root)

            item = result["skills"][0]
            self.assertEqual(7, item["version"])
            self.assertEqual("candidate", item["status"])
            self.assertEqual("low", item["risk"])
            self.assertTrue((root / ".init-harness/skills/billing/manifest.json").is_file())

    def test_registra_experiencia_append_only_e_atualiza_catalogo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")
            args = skill_evolution.parser().parse_args(
                [
                    "--root",
                    str(root),
                    "record",
                    "billing",
                    "--task-id",
                    "billing-001",
                    "--outcome",
                    "failure",
                    "--summary",
                    "A consulta usou a tabela errada.",
                    "--score",
                    "0.25",
                    "--failure-type",
                    "wrong-source",
                    "--human-correction",
                    "--tool",
                    "read_file",
                    "--file",
                    "src/billing.py",
                    "--metric",
                    "tool_calls=3",
                    "--tag",
                    "retrieval",
                ]
            )

            event = skill_evolution.record_experience(root, args)
            rows = skill_evolution.read_experiences(root, "billing")
            registry = skill_evolution.load_registry(root)

            self.assertEqual(event, rows[0])
            self.assertEqual("failure", event["outcome"])
            self.assertTrue(event["human_correction"])
            self.assertEqual(3, event["metrics"]["tool_calls"])
            self.assertEqual(1, registry["skills"][0]["experience_count"])
            jobs = skill_evolution.read_jobs(root, "queued")
            self.assertEqual(1, len(jobs))
            self.assertEqual(event["event_id"], jobs[0]["experience_event_id"])

    def test_identifica_padrao_recorrente_e_deduplica_sugestao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")
            for task in ("billing-001", "billing-002"):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        task,
                        "--outcome",
                        "failure",
                        "--summary",
                        "A consulta usou a tabela errada.",
                        "--failure-type",
                        "wrong-source",
                    ]
                )
                skill_evolution.record_experience(root, args)

            suggestions = skill_evolution.read_suggestions(root, "billing")

            self.assertEqual(1, len(suggestions))
            self.assertEqual(2, suggestions[0]["occurrences"])
            self.assertEqual("proposed", suggestions[0]["status"])
            self.assertEqual(2, len(suggestions[0]["evidence_event_ids"]))

    def test_captura_automatica_de_hook_exige_sinal_estruturado_e_e_idempotente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")
            payload = {
                "session_id": "sess-1",
                "skill_experience": {
                    "skill": "billing",
                    "task_id": "billing-001",
                    "outcome": "failure",
                    "summary": "A resposta usou uma fonte incorreta.",
                    "failure_type": "wrong-source",
                    "files": ["src/billing.py"],
                    "metrics": {"tool_calls": 2},
                },
            }

            event = skill_evolution.capture_hook_experience(root, payload)
            duplicate = skill_evolution.capture_hook_experience(root, payload)

            self.assertIsNotNone(event)
            self.assertIsNone(duplicate)
            self.assertEqual(1, len(skill_evolution.read_experiences(root, "billing")))
            self.assertIsNone(skill_evolution.capture_hook_experience(root, {"session_id": "sess-1"}))
            result = skill_evolution.capture_hook_stdin(root, io.StringIO("not-json"))
            self.assertFalse(result["captured"])

    def test_contexto_de_skill_e_persistido_por_sessao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")

            activated = skill_evolution.activate_skill(root, "billing", "sess-1")
            self.assertEqual("billing", activated["active_skill"])
            observed = skill_evolution.observe_tool_event(
                root,
                {
                    "session_id": "sess-1",
                    "tool_use_id": "tool-1",
                    "tool_name": "read_file",
                    "hook_event_name": "PostToolUseFailure",
                    "duration_ms": 12,
                    "files": ["src/billing.py"],
                },
            )
            self.assertEqual(1, observed["tool_calls"])
            self.assertEqual(1, observed["tool_failures"])
            duplicate = skill_evolution.observe_tool_event(
                root,
                {"session_id": "sess-1", "tool_use_id": "tool-1", "tool_name": "read_file"},
            )
            self.assertEqual(1, duplicate["tool_calls"])
            self.assertEqual("billing", skill_evolution.active_skill(root, "sess-1")["active_skill"])
            cleared = skill_evolution.deactivate_skill(root, "sess-1")
            self.assertEqual("billing", cleared["previous_skill"])
            self.assertIsNone(skill_evolution.active_skill(root, "sess-1")["active_skill"])

    def test_consolida_experiencia_a_partir_de_sinais_de_ferramenta(self) -> None:
        result = skill_evolution.consolidate_hook_experience(
            {"session_id": "sess-1", "active_skill": "billing"},
            {"skill": "billing", "tool_calls": 3, "tool_failures": 1, "duration_ms": 40},
        )

        self.assertEqual("partial", result["outcome"])
        self.assertAlmostEqual(2 / 3, result["score"])
        self.assertEqual("tool_failure", result["failure_type"])
        self.assertEqual(3, result["metrics"]["tool_calls"])
        self.assertIsNone(skill_evolution.consolidate_hook_experience({}, None))

    def test_materializa_sugestao_com_hash_e_checklist_sem_alterar_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: billing\n---\n# Billing\n", encoding="utf-8")
            for task in ("billing-001", "billing-002"):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        task,
                        "--outcome",
                        "failure",
                        "--summary",
                        "A consulta usou a tabela errada.",
                        "--failure-type",
                        "wrong-source",
                    ]
                )
                skill_evolution.record_experience(root, args)
            suggestion = skill_evolution.read_suggestions(root, "billing")[0]

            proposal = skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"], "teste")
            proposal_path = root / ".init-harness" / "skills" / "billing" / "proposals" / proposal["proposal_id"]

            self.assertEqual("draft", proposal["status"])
            self.assertEqual("teste", proposal["owner"])
            self.assertTrue(proposal["base_sha256"])
            self.assertTrue((proposal_path / "proposal.json").is_file())
            self.assertIn("Avaliação obrigatória", (proposal_path / "proposal.md").read_text(encoding="utf-8"))
            self.assertEqual("---\nname: billing\n---\n# Billing\n", skill_file.read_text(encoding="utf-8"))

    def test_avalia_e_promove_somente_com_melhoria_e_sem_regressao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: billing\ndescription: Skill de billing\n---\n# Billing\n",
                encoding="utf-8",
            )
            for task in ("billing-001", "billing-002"):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        task,
                        "--outcome",
                        "failure",
                        "--summary",
                        "A consulta usou a tabela errada.",
                        "--failure-type",
                        "wrong-source",
                    ]
                )
                skill_evolution.record_experience(root, args)
            suggestion = skill_evolution.read_suggestions(root, "billing")[0]
            proposal = skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"])
            candidate = root / proposal["candidate_path"]
            candidate.write_text(
                "---\nname: billing\ndescription: Skill de billing revisada\n---\n# Billing\n\nUse a tabela correta.\n",
                encoding="utf-8",
            )

            evaluated = skill_evolution.evaluate_proposal(root, "billing", proposal["proposal_id"], 0.70, 0.82)
            promoted = skill_evolution.accept_proposal(root, "billing", proposal["proposal_id"])

            self.assertEqual("evaluated", evaluated["status"])
            self.assertTrue(evaluated["evaluation"]["passed"])
            self.assertEqual("promoted", promoted["status"])
            self.assertIn("Use a tabela correta.", skill_file.read_text(encoding="utf-8"))
            self.assertTrue((root / ".init-harness/skills/billing/history/version-002.json").is_file())

    def test_promocao_recusa_candidata_alterada_depois_da_avaliacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            skill_file = root / ".claude" / "skills" / "billing" / "SKILL.md"
            for task in ("billing-001", "billing-002"):
                skill_evolution.record_experience(
                    root,
                    skill_evolution.parser().parse_args(
                        [
                            "--root",
                            str(root),
                            "record",
                            "billing",
                            "--task-id",
                            task,
                            "--outcome",
                            "failure",
                            "--summary",
                            "Fonte errada.",
                            "--failure-type",
                            "wrong-source",
                        ]
                    ),
                )
            suggestion = skill_evolution.read_suggestions(root, "billing")[0]
            proposal = skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"])
            candidate = root / proposal["candidate_path"]
            candidate.write_text("---\nname: billing\ndescription: billing\n---\n# avaliada\n", encoding="utf-8")
            skill_evolution.evaluate_proposal(root, "billing", proposal["proposal_id"], 0.5, 0.9)
            original = skill_file.read_text(encoding="utf-8")

            candidate.write_text("---\nname: billing\ndescription: billing\n---\n# nunca avaliada\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidata mudou depois da avaliação"):
                skill_evolution.accept_proposal(root, "billing", proposal["proposal_id"])

            self.assertEqual(original, skill_file.read_text(encoding="utf-8"))

    def test_politica_de_avaliacao_e_contextual_e_aplicada_na_proposta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: billing\ndescription: Skill de billing\n---\n# Billing\n",
                encoding="utf-8",
            )
            skill_evolution.sync_registry(root)
            args = skill_evolution.parser().parse_args(
                [
                    "--root",
                    str(root),
                    "configure-evaluation",
                    "billing",
                    "--metric",
                    "correctness",
                    "--minimum-improvement",
                    "0.05",
                    "--max-regressions",
                    "0",
                    "--dimension",
                    "correctness",
                    "--dimension",
                    "safety",
                    "--case",
                    "billing-001",
                ]
            )
            policy = skill_evolution.configure_evaluation(root, "billing", args)

            suggestion = {
                "suggestion_id": "S-manual",
                "skill": "billing",
                "evidence_event_ids": [],
                "pattern": "failure_type:test",
                "rationale": "teste",
                "proposed_action": "teste",
            }
            suggestion_path = root / ".init-harness" / "skills" / "billing" / "suggestions.jsonl"
            suggestion_path.parent.mkdir(parents=True, exist_ok=True)
            suggestion_path.write_text(json.dumps(suggestion) + "\n", encoding="utf-8")
            proposal = skill_evolution.create_proposal(root, "billing", "S-manual")

            self.assertEqual("correctness", policy["metric"])
            self.assertEqual(0.05, proposal["evaluation_policy"]["minimum_improvement"])
            self.assertEqual(["billing-001"], proposal["evaluation_policy"]["required_cases"])

    def test_avalia_resultados_por_caso_e_calcula_medias_regressoes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: billing\ndescription: Skill de billing\n---\n# Billing\n",
                encoding="utf-8",
            )
            for task in ("billing-001", "billing-002"):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        task,
                        "--outcome",
                        "failure",
                        "--summary",
                        "A consulta usou a tabela errada.",
                        "--failure-type",
                        "wrong-source",
                    ]
                )
                skill_evolution.record_experience(root, args)
            suggestion = skill_evolution.read_suggestions(root, "billing")[0]
            proposal = skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"])
            (root / proposal["candidate_path"]).write_text(
                "---\nname: billing\ndescription: Skill de billing revisada\n---\n# Billing\n\nMelhoria.\n",
                encoding="utf-8",
            )
            results = root / "eval" / "results.json"
            results.parent.mkdir()
            results.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "billing-001",
                                "baseline_score": 0.5,
                                "candidate_score": 0.8,
                                "baseline_passed": False,
                                "candidate_passed": True,
                                "guardrail_failures": 0,
                            },
                            {
                                "case_id": "billing-002",
                                "baseline_score": 0.8,
                                "candidate_score": 0.7,
                                "baseline_passed": True,
                                "candidate_passed": False,
                                "guardrail_failures": 0,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            evaluated = skill_evolution.evaluate_results(root, "billing", proposal["proposal_id"], "eval/results.json")

            self.assertEqual("rejected", evaluated["status"])
            self.assertEqual(1, evaluated["evaluation"]["regressions"])
            self.assertEqual(0.65, evaluated["evaluation"]["baseline_score"])
            self.assertEqual(0.75, evaluated["evaluation"]["candidate_score"])

    def test_contrato_de_uso_e_registrado_no_manifesto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: billing\ndescription: Skill de billing\n---\n# Billing\n",
                encoding="utf-8",
            )
            skill_evolution.sync_registry(root)
            args = skill_evolution.parser().parse_args(
                [
                    "--root",
                    str(root),
                    "configure-usage",
                    "billing",
                    "--when",
                    "tarefa pede conciliação de cobranças",
                    "--when-not",
                    "não usar para deploy",
                    "--tool",
                    "read_file",
                    "--surface",
                    "src/billing.py",
                    "--expected-outcome",
                    "produzir conciliação auditável",
                    "--risk",
                    "high",
                ]
            )
            contract = skill_evolution.configure_usage(root, "billing", args)

            self.assertEqual(["read_file"], contract["tools"])
            self.assertEqual("high", contract["risk"])
            self.assertEqual("tarefa pede conciliação de cobranças", contract["when"][0])

    def test_runner_do_projeto_produz_resultados_e_dispara_avaliacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: billing\ndescription: Skill de billing\n---\n# Billing\n",
                encoding="utf-8",
            )
            for task in ("billing-001", "billing-002"):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        task,
                        "--outcome",
                        "failure",
                        "--summary",
                        "A consulta usou a tabela errada.",
                        "--failure-type",
                        "wrong-source",
                    ]
                )
                skill_evolution.record_experience(root, args)
            suggestion = skill_evolution.read_suggestions(root, "billing")[0]
            proposal = skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"])
            (root / proposal["candidate_path"]).write_text(
                "---\nname: billing\ndescription: Skill revisada\n---\n# Billing\nMelhoria.\n",
                encoding="utf-8",
            )
            runner = root / "eval" / "runner.py"
            runner.parent.mkdir()
            runner.write_text(
                "import argparse, json\n"
                "p=argparse.ArgumentParser(); p.add_argument('--skill'); p.add_argument('--base'); "
                "p.add_argument('--candidate'); p.add_argument('--cases'); "
                "p.add_argument('--output'); a=p.parse_args()\n"
                "json.dump({'cases':[{'case_id':'billing-001','baseline_score':0.5,"
                "'candidate_score':0.8,'baseline_passed':False,'candidate_passed':True,"
                "'guardrail_failures':0}]}, open(a.output,'w'))\n",
                encoding="utf-8",
            )
            skill_evolution.init_evaluation(root, "billing")
            evaluated = skill_evolution.run_evaluation(root, "billing", proposal["proposal_id"], "eval/runner.py")

            self.assertEqual("evaluated", evaluated["status"])
            self.assertEqual(0.8, evaluated["evaluation"]["candidate_score"])

    def test_rejeita_caminho_absoluto_e_score_invalido(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".claude" / "skills" / "billing"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: billing\n---\n", encoding="utf-8")
            for extra in (("--score", "1.1"), ("--file", "..\\secret.txt")):
                args = skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        "billing-001",
                        "--outcome",
                        "success",
                        "--summary",
                        "ok",
                        *extra,
                    ]
                )
                with self.assertRaises(ValueError):
                    skill_evolution.record_experience(root, args)

    def test_skills_reais_do_kit_tem_frontmatter_legivel(self) -> None:
        kit = MODULE_PATH.parents[2]
        skills = skill_evolution.discover_skills(kit)

        self.assertGreaterEqual(len(skills), 5)
        for item in skills:
            with self.subTest(skill=item["id"]):
                text = (kit / item["skill_path"]).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---"), "frontmatter deve começar na linha 1")
                self.assertEqual(item["id"], item["name"])
                self.assertTrue(item["description"], "description vazia: o modelo não consegue acionar a skill")

    def _project_with_skills(self, root: Path, *names: str) -> None:
        for name in names:
            skill = root / ".claude" / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name}\n---\n", encoding="utf-8")

    def test_ativa_skill_do_projeto_ao_invocar_ferramenta_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            pre = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "Skill"}

            result = skill_evolution.activate_from_tool_event(root, {**pre, "tool_input": {"skill": "/billing"}})

            self.assertEqual("billing", result["active_skill"])
            self.assertEqual("billing", skill_evolution.active_skill(root, "s1")["active_skill"])
            for ignored in (
                {**pre, "tool_input": {"skill": "plugin:outra"}},
                {**pre, "tool_input": {}},
                {**pre, "tool_name": "Bash", "tool_input": {"skill": "billing"}},
                {**pre, "hook_event_name": "PostToolUse", "tool_input": {"skill": "billing"}},
                {**pre, "session_id": "", "tool_input": {"skill": "billing"}},
            ):
                self.assertIsNone(skill_evolution.activate_from_tool_event(root, ignored))

    def test_trocar_de_skill_fecha_experiencia_da_anterior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing", "reports")
            pre = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "Skill"}
            skill_evolution.activate_from_tool_event(root, {**pre, "tool_input": {"skill": "billing"}})
            for number in (1, 2):
                skill_evolution.observe_tool_event(
                    root, {"session_id": "s1", "tool_use_id": f"t{number}", "tool_name": "Read"}
                )

            skill_evolution.activate_from_tool_event(root, {**pre, "tool_input": {"skill": "reports"}})

            closed = skill_evolution.read_experiences(root, "billing")
            self.assertEqual(1, len(closed))
            self.assertEqual("success", closed[0]["outcome"])
            self.assertEqual(2, closed[0]["metrics"]["tool_calls"])
            self.assertEqual("reports", skill_evolution.active_skill(root, "s1")["active_skill"])
            fresh = skill_evolution.observe_tool_event(
                root, {"session_id": "s1", "tool_use_id": "t3", "tool_name": "Read"}
            )
            self.assertEqual(("reports", 1), (fresh["skill"], fresh["tool_calls"]))
            self.assertEqual([], skill_evolution.read_experiences(root, "reports"))

    def _proposal(self, root: Path, *sources: str) -> dict:
        """Cria a skill billing e uma proposta com uma falha recorrente por origem informada."""
        self._project_with_skills(root, "billing")
        for number, source in enumerate(sources or ("agent", "agent"), start=1):
            skill_evolution.record_experience(
                root,
                skill_evolution.parser().parse_args(
                    [
                        "--root",
                        str(root),
                        "record",
                        "billing",
                        "--task-id",
                        f"t{number}",
                        "--outcome",
                        "failure",
                        "--summary",
                        f"Fonte errada {number}.",
                        "--failure-type",
                        "wrong-source",
                        "--source",
                        source,
                    ]
                ),
            )
        suggestion = skill_evolution.read_suggestions(root, "billing")[0]
        return skill_evolution.create_proposal(root, "billing", suggestion["suggestion_id"])

    def _write_candidate(self, root: Path, proposal: dict, body: str) -> None:
        (root / proposal["candidate_path"]).write_text(
            f"---\nname: billing\ndescription: billing\n---\n{body}\n", encoding="utf-8"
        )

    def test_contexto_da_proposta_reune_evidencia_e_separa_falha_sem_explicacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "a"
            proposal = self._proposal(root, "system", "system")

            context = skill_evolution.proposal_context(root, "billing", proposal["proposal_id"])

            self.assertEqual(2, len(context["evidence"]))
            self.assertEqual(0, context["explained_evidence"])
            self.assertTrue(context["active_matches_base"])
            self.assertFalse(context["candidate_changed"])
            self.assertFalse(context["usage_contract_ready"])
            self.assertEqual([], context["case_files"])
            other = Path(tmp) / "b"
            mixed = self._proposal(other, "agent", "system")
            mixed_context = skill_evolution.proposal_context(other, "billing", mixed["proposal_id"])
            self.assertEqual(1, mixed_context["explained_evidence"])

    def test_submete_candidata_valida_e_registra_o_resumo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            self._write_candidate(root, proposal, "# Billing\n\nConsulte a tabela invoices.")

            submitted = skill_evolution.submit_candidate(
                root, "billing", proposal["proposal_id"], "Aponta a tabela invoices (E-001, E-002)."
            )

            self.assertEqual("candidate", submitted["status"])
            self.assertEqual("Aponta a tabela invoices (E-001, E-002).", submitted["change_summary"])
            proposal_dir = (root / proposal["candidate_path"]).parents[1]
            markdown = (proposal_dir / "proposal.md").read_text(encoding="utf-8")
            self.assertIn("Aponta a tabela invoices", markdown)
            self.assertNotIn("Preencher antes da avaliação", markdown)
            self.assertIn("## Avaliação obrigatória", markdown)
            context = skill_evolution.proposal_context(root, "billing", proposal["proposal_id"])
            self.assertTrue(context["candidate_changed"])

    def test_recusa_candidata_invalida_e_estados_que_nao_aceitam_nova_candidata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            pid = proposal["proposal_id"]
            with self.assertRaisesRegex(ValueError, "não contém mudança"):
                skill_evolution.submit_candidate(root, "billing", pid, "sem mudança")
            with self.assertRaisesRegex(ValueError, "summary é obrigatório"):
                skill_evolution.submit_candidate(root, "billing", pid, "   ")
            (root / proposal["candidate_path"]).write_text("# sem frontmatter\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frontmatter"):
                skill_evolution.submit_candidate(root, "billing", pid, "x")
            (root / proposal["candidate_path"]).write_text("---\nname: outra\ndescription: d\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "name igual à skill"):
                skill_evolution.submit_candidate(root, "billing", pid, "x")

            self._write_candidate(root, proposal, "# v2")
            skill_evolution.submit_candidate(root, "billing", pid, "v2")
            skill_evolution.evaluate_proposal(root, "billing", pid, 0.5, 0.9)
            self._write_candidate(root, proposal, "# v3")
            with self.assertRaisesRegex(ValueError, "não aceita nova candidata"):
                skill_evolution.submit_candidate(root, "billing", pid, "v3")

    def test_candidata_rejeitada_pode_ser_revisada_e_ressubmetida(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            pid = proposal["proposal_id"]
            self._write_candidate(root, proposal, "# v2")
            skill_evolution.submit_candidate(root, "billing", pid, "v2")
            rejected = skill_evolution.evaluate_proposal(root, "billing", pid, 0.9, 0.5)
            self.assertEqual("rejected", rejected["status"])

            self._write_candidate(root, proposal, "# v3")
            again = skill_evolution.submit_candidate(root, "billing", pid, "v3 corrige a regressão")
            self.assertEqual("candidate", again["status"])
            self.assertNotIn("baseline_score", again["evaluation"], "avaliação anterior deve ser descartada")
            evaluated = skill_evolution.evaluate_proposal(root, "billing", pid, 0.5, 0.9)
            promoted = skill_evolution.accept_proposal(root, "billing", pid)

            self.assertEqual("evaluated", evaluated["status"])
            self.assertEqual("promoted", promoted["status"])
            active = (root / ".claude/skills/billing/SKILL.md").read_text(encoding="utf-8")
            self.assertIn("# v3", active)

    def test_submissao_detecta_skill_ativa_alterada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            self._write_candidate(root, proposal, "# v2")
            (root / ".claude/skills/billing/SKILL.md").write_text(
                "---\nname: billing\ndescription: billing\n---\n# mudou por fora\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "skill ativa mudou"):
                skill_evolution.submit_candidate(root, "billing", proposal["proposal_id"], "v2")

            context = skill_evolution.proposal_context(root, "billing", proposal["proposal_id"])
            self.assertFalse(context["active_matches_base"])
            self.assertEqual("conflict", skill_evolution.read_proposals(root, "billing")[0]["status"])

    def test_todas_as_skills_do_kit_sao_classificadas_como_metodo(self) -> None:
        kit = MODULE_PATH.parents[2]
        for item in skill_evolution.discover_skills(kit):
            with self.subTest(skill=item["id"]):
                self.assertEqual("method", item["scope"], "registre a skill em METHOD_SKILLS")

    def test_fila_de_jobs_segue_a_ordem_de_criacao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            created = [
                skill_evolution.enqueue_analysis_job(root, {"event_id": f"E-{number}", "skill": "billing"})
                for number in range(12)
            ]

            queued = skill_evolution.read_jobs(root, "queued")
            claimed = skill_evolution.claim_next_job(root)

            self.assertEqual([job["job_id"] for job in created], [job["job_id"] for job in queued])
            self.assertEqual(created[0]["job_id"], claimed["job_id"])

    def _record(self, root: Path, task: str, failure_type: str | None = "wrong-source", *extra: str) -> dict:
        argv = [
            "--root",
            str(root),
            "record",
            "billing",
            "--task-id",
            task,
            "--outcome",
            "failure",
            "--summary",
            f"falha {task}",
            *extra,
        ]
        if failure_type:
            argv += ["--failure-type", failure_type]
        return skill_evolution.record_experience(root, skill_evolution.parser().parse_args(argv))

    def test_sugestao_aberta_acumula_ocorrencias_sem_duplicar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            self._record(root, "t1")
            self.assertEqual([], skill_evolution.read_suggestions(root, "billing"), "uma falha isolada não sugere nada")
            self._record(root, "t2")
            first = skill_evolution.read_suggestions(root, "billing")[0]

            for task in ("t3", "t4"):
                self._record(root, task)

            rows = skill_evolution.read_suggestions(root, "billing")
            self.assertEqual(1, len(rows))
            self.assertEqual(first["suggestion_id"], rows[0]["suggestion_id"])
            self.assertEqual(4, rows[0]["occurrences"])
            self.assertEqual(4, len(rows[0]["evidence_event_ids"]))
            self.assertEqual(first["evidence_event_ids"], rows[0]["evidence_event_ids"][:2], "evidência só cresce")
            self.assertIn("4 experiência", rows[0]["rationale"])
            self.assertEqual(["falha t2", "falha t3", "falha t4"], rows[0]["summaries"][-3:])
            self.assertGreaterEqual(rows[0]["updated_at"], rows[0]["created_at"])

    def test_correcoes_humanas_sem_tipo_acumulam_na_mesma_sugestao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")

            self._record(root, "t1", None, "--human-correction")
            self._record(root, "t2", None, "--human-correction")

            rows = skill_evolution.read_suggestions(root, "billing")
            self.assertEqual(1, len(rows))
            self.assertEqual("correction:unspecified", rows[0]["pattern"])
            self.assertEqual(2, rows[0]["occurrences"])
            self.assertIn("correção humana", rows[0]["rationale"])

    def test_sugestao_gravada_no_formato_antigo_tambem_e_atualizada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            self._record(root, "t1")
            self._record(root, "t2")
            path = skill_evolution.suggestions_path(root, "billing")
            legacy = json.loads(path.read_text(encoding="utf-8"))
            legacy.pop("updated_at")
            path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

            self._record(root, "t3")

            updated = skill_evolution.read_suggestions(root, "billing")[0]
            self.assertEqual(3, updated["occurrences"])
            self.assertIn("updated_at", updated)

    def test_sugestao_promovida_congela_e_so_reabre_com_ocorrencias_posteriores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            old_id = proposal["suggestion_id"]
            self.assertEqual("in_progress", skill_evolution.read_suggestions(root, "billing")[0]["status"])
            self._write_candidate(root, proposal, "# v2")
            skill_evolution.submit_candidate(root, "billing", proposal["proposal_id"], "v2")
            skill_evolution.evaluate_proposal(root, "billing", proposal["proposal_id"], 0.5, 0.9)
            skill_evolution.accept_proposal(root, "billing", proposal["proposal_id"])
            frozen = skill_evolution.read_suggestions(root, "billing")[0]
            self.assertEqual(("addressed", proposal["proposal_id"]), (frozen["status"], frozen["addressed_by"]))

            self._record(root, "t3")
            self.assertEqual(1, len(skill_evolution.read_suggestions(root, "billing")), "uma ocorrência não reabre")
            self._record(root, "t4")

            rows = skill_evolution.read_suggestions(root, "billing")
            self.assertEqual(2, len(rows))
            self.assertEqual(frozen, rows[0], "a sugestão promovida não muda mais")
            reopened = rows[1]
            self.assertNotEqual(old_id, reopened["suggestion_id"])
            self.assertEqual("proposed", reopened["status"])
            self.assertEqual(2, reopened["occurrences"])
            self.assertFalse(set(reopened["evidence_event_ids"]) & set(frozen["evidence_event_ids"]))

            self._record(root, "t5")
            self.assertEqual(3, skill_evolution.read_suggestions(root, "billing")[1]["occurrences"])
            self._record(root, "t6", "outro-tipo", "--human-correction")
            self.assertEqual(3, len(skill_evolution.read_suggestions(root, "billing")), "correção humana abre na hora")

    def test_criar_proposta_marca_sugestao_em_andamento_uma_vez(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = self._proposal(root)
            self._record(root, "t3")

            self.assertEqual(proposal, skill_evolution.create_proposal(root, "billing", proposal["suggestion_id"]))
            row = skill_evolution.read_suggestions(root, "billing")[0]

            self.assertEqual("in_progress", row["status"])
            self.assertEqual(3, row["occurrences"], "sugestão em andamento continua acumulando")

    def test_cli_record_informa_sugestoes_novas_e_atualizadas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")

            def run(task: str) -> dict:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    skill_evolution.main(
                        [
                            "--root",
                            str(root),
                            "record",
                            "billing",
                            "--task-id",
                            task,
                            "--outcome",
                            "failure",
                            "--summary",
                            "x",
                            "--failure-type",
                            "wrong-source",
                        ]
                    )
                return json.loads(out.getvalue())

            self.assertEqual(([], []), (run("t1")["new_suggestions"], run("t2")["updated_suggestions"]))
            third = run("t3")
            self.assertEqual([], third["new_suggestions"])
            self.assertEqual(
                [
                    {
                        "suggestion_id": skill_evolution.read_suggestions(root, "billing")[0]["suggestion_id"],
                        "occurrences": 3,
                    }
                ],
                third["updated_suggestions"],
            )

    def test_recusa_caminho_inseguro_com_qualquer_separador_em_qualquer_sistema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            unsafe = ("..\\segredo.txt", "../segredo.txt", "a/../b", "a\\..\\b", "C:\\x", "\\x", "/etc/x")
            for value in unsafe:
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        skill_evolution._relative_paths(root, [value])
                    with self.assertRaises(ValueError):
                        skill_evolution._results_path(root, value)
            self.assertEqual(
                ["src/a.py", "docs/b.md"], skill_evolution._relative_paths(root, ["src/a.py", "docs/b.md"])
            )

    def test_arquivos_observados_com_caminho_inseguro_sao_ignorados(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_skills(root, "billing")
            skill_evolution.activate_skill(root, "billing", "s1")

            observed = skill_evolution.observe_tool_event(
                root,
                {
                    "session_id": "s1",
                    "tool_use_id": "t1",
                    "tool_name": "Read",
                    "files": ["src/ok.py", "..\\fora.txt", "../fora.txt", "C:\\fora.txt"],
                },
            )

            self.assertEqual(["src/ok.py"], observed["files"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Testes de integração do instalador e migrador."""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import init_harness

KIT = Path(__file__).resolve().parents[1]
ORIGINAL_SUBPROCESS_RUN = subprocess.run


def run_process(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Decodifica a saída UTF-8 emitida pelos hooks, mesmo no console cp1252."""
    if kwargs.get("text"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    return ORIGINAL_SUBPROCESS_RUN(*args, **kwargs)  # type: ignore[arg-type,return-value]


subprocess.run = run_process  # type: ignore[assignment]


def git_init(path: Path) -> None:
    run_process(["git", "init", str(path)], check=True, capture_output=True)


class InstallerTest(unittest.TestCase):
    def test_instalacao_preserva_projeto_e_e_idempotente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "projeto"
            target.mkdir()
            git_init(target)
            (target / "CLAUDE.md").write_text("# configuração própria\n", encoding="utf-8")
            (target / ".claude").mkdir()
            (target / ".claude/settings.json").write_text(
                json.dumps({"permissions": {"allow": ["Read(src/**)"]}}), encoding="utf-8"
            )

            args = [
                "install",
                "--target",
                str(target),
                "--providers",
                "claude",
                "codex",
                "--graph",
                "manual",
            ]
            self.assertEqual(0, init_harness.main(args, KIT))
            self.assertEqual("# configuração própria\n", (target / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertTrue((target / "AGENTS.md").is_file())
            self.assertTrue((target / "INIT-HARNESS.md").is_file())
            config = json.loads((target / ".init-harness/config.json").read_text(encoding="utf-8"))
            self.assertEqual("3.0.0", config["harness_version"])
            self.assertFalse(config["memoria"]["mcp"])
            self.assertFalse(config["bootstrap"]["opt_in"])
            self.assertEqual("continuar", config["autonomia"]["tarefas_seguras"])
            settings = json.loads((target / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertIn("Read(src/**)", settings["permissions"]["allow"])
            self.assertIn("hooks", settings)
            doctor = subprocess.run(
                [sys.executable, str(target / ".claude/hooks/doctor.py")],
                cwd=target,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(0, doctor.returncode, doctor.stdout + doctor.stderr)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, init_harness.main(args, KIT))
            self.assertIn("Resultado: 0 mudança(s)", output.getvalue())

    def _install_and_doctor(self, target: Path, mutate) -> subprocess.CompletedProcess[str]:
        git_init(target)
        self.assertEqual(
            0,
            init_harness.main(["install", "--target", str(target), "--providers", "claude", "--graph", "manual"], KIT),
        )
        mutate(target)
        return subprocess.run(
            [sys.executable, str(target / ".claude/hooks/doctor.py")],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_doctor_reprova_skill_com_frontmatter_quebrado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:

            def quebrar(target: Path) -> None:
                skill = target / ".claude/skills/spec/SKILL.md"
                skill.write_bytes(b"\n" + skill.read_bytes())

            doctor = self._install_and_doctor(Path(tmp) / "projeto", quebrar)

            self.assertEqual(1, doctor.returncode, doctor.stdout)
            self.assertIn("skill inválida: spec", doctor.stdout)

    def test_doctor_reprova_settings_sem_ativacao_de_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:

            def remover(target: Path) -> None:
                path = target / ".claude/settings.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["hooks"]["PreToolUse"] = [x for x in data["hooks"]["PreToolUse"] if x.get("matcher") != "Skill"]
                path.write_text(json.dumps(data), encoding="utf-8")

            doctor = self._install_and_doctor(Path(tmp) / "projeto", remover)

            self.assertEqual(1, doctor.returncode, doctor.stdout)
            self.assertIn("matcher Skill", doctor.stdout)

    def test_toda_skill_do_kit_esta_nas_listas_de_metodo_do_instalador(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("kit_lib", KIT / ".claude/hooks/_lib.py")
        assert spec is not None and spec.loader is not None
        lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lib)
        for skill in sorted((KIT / ".claude/skills").iterdir()):
            with self.subTest(skill=skill.name):
                self.assertIn(f".claude/skills/{skill.name}", init_harness.MANAGED_TREES)
                self.assertIn(f".claude/skills/{skill.name}/", lib.METODO_CLIENTE)

    def test_instalador_nao_distribui_bytecode_das_arvores_gerenciadas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            runners = source / ".claude/skills/evolve/runners"
            (runners / "__pycache__").mkdir(parents=True)
            (runners / "static_eval.py").write_text("", encoding="utf-8")
            (runners / "__pycache__/static_eval.cpython-311.pyc").write_bytes(b"x")

            paths = init_harness.managed_paths(source)

            self.assertIn(".claude/skills/evolve/runners/static_eval.py", paths)
            self.assertFalse([path for path in paths if "__pycache__" in path or path.endswith(".pyc")])

    def test_upgrade_migra_nomes_legados(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "legado"
            target.mkdir()
            git_init(target)
            (target / ".claude").mkdir()
            legacy_config = {
                "harness_version": "2.0.0",
                "modo": "proprio",
                "instalado_em": "2026-09-12",
                "grafo": "manual",
                "frente_inativa_horas": None,
                "ambientes": {"se_indeterminado": "bloquear", "regras": []},
            }
            (target / ".claude/harness.json").write_text(json.dumps(legacy_config), encoding="utf-8")
            (target / "CLAUDE-HARNESS.md").write_text("legado\n", encoding="utf-8")
            (target / "CLAUDE.md").write_text("Ler CLAUDE-HARNESS.md e .claude/harness.json\n", encoding="utf-8")

            self.assertEqual(0, init_harness.main(["upgrade", "--target", str(target)], KIT))
            self.assertFalse((target / "CLAUDE-HARNESS.md").exists())
            self.assertFalse((target / ".claude/harness.json").exists())
            self.assertTrue((target / "INIT-HARNESS.md").is_file())
            config = json.loads((target / ".init-harness/config.json").read_text(encoding="utf-8"))
            self.assertEqual("3.0.0", config["harness_version"])
            self.assertEqual(["claude", "codex"], config["providers"])
            claude = (target / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("INIT-HARNESS.md", claude)
            self.assertIn(".init-harness/config.json", claude)

    def test_upgrade_nao_reescreve_referencia_historica_sem_migracao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "projeto"
            target.mkdir()
            git_init(target)
            self.assertEqual(0, init_harness.main(["install", "--target", str(target), "--graph", "manual"], KIT))
            decision = target / "docs" / "ai" / "DECISOES.md"
            historical = "A migração foi de .claude/harness.json para .init-harness/config.json.\n"
            decision.write_text(historical, encoding="utf-8")
            self.assertEqual(0, init_harness.main(["upgrade", "--target", str(target)], KIT))
            self.assertEqual(historical, decision.read_text(encoding="utf-8"))

    def test_merge_settings_preserva_hook_customizado_equivalente(self) -> None:
        required = {
            "hooks": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "uv", "args": ["run", "guard.py"]}],
                }
            ]
        }
        current = {
            "hooks": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "env UV=/opt/uv uv", "args": ["run", "guard.py"]}],
                }
            ]
        }
        merged = init_harness.merge_settings(current, required)
        self.assertEqual(1, len(merged["hooks"]))
        self.assertEqual("env UV=/opt/uv uv", merged["hooks"][0]["hooks"][0]["command"])

    def test_modo_cliente_deriva_exclusoes_da_politica_central(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cliente"
            target.mkdir()
            git_init(target)
            self.assertEqual(
                0,
                init_harness.main(["install", "--target", str(target), "--mode", "cliente", "--graph", "manual"], KIT),
            )
            exclude = (target / ".git" / "info" / "exclude").read_text(encoding="utf-8")
            policy = init_harness.client_method_paths(KIT)
            self.assertTrue(all(path in exclude.splitlines() for path in policy))

    def test_bootstrap_e_opt_in_e_nao_executa_graphify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "projeto"
            target.mkdir()
            git_init(target)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    0,
                    init_harness.main(["install", "--target", str(target), "--graph", "manual", "--bootstrap"], KIT),
                )
            config = json.loads((target / ".init-harness/config.json").read_text(encoding="utf-8"))
            self.assertTrue(config["bootstrap"]["opt_in"])
            self.assertIn("Bootstrap opcional:", output.getvalue())
            self.assertIn("graphify-out/graph.json ausente", output.getvalue())

    def test_memoria_indexa_contexto_e_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "projeto"
            target.mkdir()
            git_init(target)
            self.assertEqual(
                0, init_harness.main(["install", "--target", str(target), "--graph", "manual", "--memory-mcp"], KIT)
            )
            config = json.loads((target / ".init-harness/config.json").read_text(encoding="utf-8"))
            self.assertTrue(config["memoria"]["mcp"])
            frente = target / "docs" / "ai" / "frentes" / "memoria.md"
            frente.parent.mkdir(parents=True)
            frente.write_text(
                "---\nstatus: ativa\nbranch: master\ndono: teste\n"
                "specs: specs/memoria/1-indice.md\n"
                "depende_de: docs/ai/frentes/base.md\n"
                "modulos: memoria\nfiles: app/memory/index.py\ntags: contexto\n---\n\n"
                "# Memória\n\n## Próximo passo\n\nIndexar contexto de pagamentos.\n",
                encoding="utf-8",
            )
            base = target / "docs" / "ai" / "frentes" / "base.md"
            base.write_text("---\nstatus: concluida\nbranch: base\n---\n# Base\n", encoding="utf-8")
            painel = target / "docs" / "ai" / "frentes" / "painel.md"
            painel.write_text(
                "---\nstatus: bloqueada\nbranch: painel\nfiles: app/users/gateway.py\n---\n# Painel\n",
                encoding="utf-8",
            )
            (target / "docs" / "ai" / "DECISOES.md").write_text(
                "# Decisões\n\n## D-0002 — Índice\n\n- **Frente / spec:** docs/ai/frentes/memoria.md\n",
                encoding="utf-8",
            )
            spec = target / "specs" / "memoria" / "1-indice.md"
            spec.parent.mkdir(parents=True)
            spec.write_text(
                "---\nstatus: rascunho\nfrente: docs/ai/frentes/memoria.md\nmodule: memoria\n"
                "target_nodes:\n  - memory.index\nfiles:\n  - app/memory/index.py\n---\n# Índice\n",
                encoding="utf-8",
            )
            graph_dir = target / "graphify-out"
            graph_dir.mkdir()
            (graph_dir / "graph.json").write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "memory.index",
                                "label": "memory.index",
                                "source_file": "app/memory/index.py",
                                "community": 1,
                            },
                            {
                                "id": "users.gateway",
                                "label": "users.gateway",
                                "source_file": "app/users/gateway.py",
                                "community": 2,
                            },
                        ],
                        "links": [{"source": "memory.index", "target": "users.gateway", "relation": "calls"}],
                    }
                ),
                encoding="utf-8",
            )
            source = target / "app" / "memory" / "index.py"
            source.parent.mkdir(parents=True)
            source.write_text("def index():\n    return True\n", encoding="utf-8")
            script = target / ".claude" / "hooks" / "memory.py"
            indexed = subprocess.run([sys.executable, str(script), "index"], cwd=target, capture_output=True, text=True)
            self.assertEqual(0, indexed.returncode, indexed.stderr)
            found = subprocess.run(
                [sys.executable, str(script), "query", "pagamentos"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, found.returncode, found.stderr)
            self.assertIn("docs/ai/frentes/memoria.md", found.stdout)
            recovered = subprocess.run(
                [sys.executable, str(script), "retrieve", "memory"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, recovered.returncode, recovered.stderr)
            self.assertIn("Recuperação híbrida", recovered.stdout)
            self.assertIn("memory.index", recovered.stdout)
            graph_status = subprocess.run(
                [sys.executable, str(script), "graph-status"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, graph_status.returncode, graph_status.stderr)
            self.assertIn("Estado do Graphify: desconhecido", graph_status.stdout)
            graph = subprocess.run([sys.executable, str(script), "graph"], cwd=target, capture_output=True, text=True)
            self.assertEqual(0, graph.returncode, graph.stderr)
            graph_data = json.loads(
                (target / ".init-harness" / "memory" / "work-graph.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any(node["kind"] == "frente" for node in graph_data["nodes"]))
            self.assertIn(
                {
                    "from": "docs/ai/frentes/memoria.md",
                    "to": "docs/ai/frentes/base.md",
                    "kind": "depende_de",
                    "origin": "explicita",
                },
                graph_data["edges"],
            )
            self.assertIn(
                {
                    "from": "specs/memoria/1-indice.md",
                    "to": "arquivo:app/memory/index.py",
                    "kind": "altera",
                    "origin": "explicita",
                },
                graph_data["edges"],
            )
            ready = subprocess.run(
                [sys.executable, str(script), "work", "--ready"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, ready.returncode, ready.stderr)
            self.assertIn("docs/ai/frentes/memoria.md", ready.stdout)
            critical = subprocess.run(
                [sys.executable, str(script), "critical", "--branch", "master"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, critical.returncode, critical.stderr)
            self.assertIn("Contexto crítico: docs/ai/frentes/memoria.md", critical.stdout)
            self.assertIn("Specs: specs/memoria/1-indice.md", critical.stdout)
            self.assertIn("Arquivos declarados: app/memory/index.py", critical.stdout)
            self.assertIn("1 nó(s) correspondente(s)", critical.stdout)
            bootstrap = subprocess.run(
                [sys.executable, str(script), "bootstrap", "--min-files", "1"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, bootstrap.returncode, bootstrap.stderr)
            self.assertIn("Mapa inicial do projeto", bootstrap.stdout)
            bootstrap_id = re.search(r"(B-[a-f0-9]+)", bootstrap.stdout)
            self.assertIsNotNone(bootstrap_id)
            accepted_bootstrap = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "bootstrap",
                    "--accept",
                    bootstrap_id.group(1),
                    "--min-files",
                    "1",
                    "--note",
                    "Comunidade confirmada na arquitetura.",
                ],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted_bootstrap.returncode, accepted_bootstrap.stderr)
            feedback = target / "docs" / "ai" / "memoria" / "feedback-bootstrap.md"
            self.assertIn("resultado: aceita", feedback.read_text(encoding="utf-8"))
            bootstrap_history = subprocess.run(
                [sys.executable, str(script), "bootstrap", "--history", "--min-files", "1"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, bootstrap_history.returncode, bootstrap_history.stderr)
            self.assertIn(f"{bootstrap_id.group(1)} [aceita]", bootstrap_history.stdout)
            status = subprocess.run(
                [sys.executable, str(script), "status", "--branch", "master"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, status.returncode, status.stderr)
            self.assertIn("Painel operacional (somente leitura): branch master.", status.stdout)
            self.assertIn("## Frente atual", status.stdout)
            self.assertIn("## Atenção", status.stdout)
            self.assertIn("## Impacto confirmado", status.stdout)
            self.assertIn("## Revisão humana", status.stdout)
            self.assertIn("Nenhuma sugestão ou proposta foi aplicada", status.stdout)
            impact = subprocess.run(
                [sys.executable, str(script), "impact", "--branch", "master"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, impact.returncode, impact.stderr)
            self.assertIn("app/users/gateway.py", impact.stdout)
            self.assertIn("Comunidades adicionais no grafo: 2", impact.stdout)
            consolidation = subprocess.run(
                [sys.executable, str(script), "consolidate", "--branch", "master"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, consolidation.returncode, consolidation.stderr)
            self.assertIn("nenhum arquivo foi alterado automaticamente", consolidation.stdout)
            self.assertIn("app/memory/index.py", consolidation.stdout)
            consolidation_id = re.search(r"(C-[a-f0-9]+)", consolidation.stdout)
            self.assertIsNotNone(consolidation_id)
            accepted_consolidation = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "consolidate",
                    "--branch",
                    "master",
                    "--accept",
                    consolidation_id.group(1),
                    "--note",
                    "Escopo revisado e arquivos verificados.",
                ],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted_consolidation.returncode, accepted_consolidation.stderr)
            self.assertIn("## Consolidações", frente.read_text(encoding="utf-8"))
            blocked = subprocess.run(
                [sys.executable, str(script), "work", "--blocked"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, blocked.returncode, blocked.stderr)
            self.assertIn("docs/ai/frentes/painel.md", blocked.stdout)
            stale = subprocess.run(
                [sys.executable, str(script), "work", "--stale"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, stale.returncode, stale.stderr)
            self.assertIn("não está configurado", stale.stdout)
            risks = subprocess.run(
                [sys.executable, str(script), "work", "--risk"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, risks.returncode, risks.stderr)
            self.assertIn("Grafo de código pode estar desatualizado", risks.stdout)
            gaps = subprocess.run(
                [sys.executable, str(script), "work", "--gaps"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, gaps.returncode, gaps.stderr)
            self.assertIn("campos obrigatórios ausentes", gaps.stdout)
            suggestions = subprocess.run(
                [sys.executable, str(script), "suggest"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, suggestions.returncode, suggestions.stderr)
            self.assertIn("--decisoes-> D-0002", suggestions.stdout)
            relation_line = next(line for line in suggestions.stdout.splitlines() if "--relaciona_com->" in line)
            suggestion_id = re.search(r"(S-[a-f0-9]+)", relation_line)
            self.assertIsNotNone(suggestion_id)
            accepted_suggestion = subprocess.run(
                [sys.executable, str(script), "suggest", "--accept", suggestion_id.group(1)],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted_suggestion.returncode, accepted_suggestion.stderr)
            self.assertIn("relaciona_com: docs/ai/frentes/painel.md", frente.read_text(encoding="utf-8"))
            handoff = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "handoff",
                    "--summary",
                    "Índice pronto.",
                    "--next-step",
                    "Validar busca.",
                ],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, handoff.returncode, handoff.stderr)
            handoffs = list((target / "docs" / "ai" / "memoria" / "handoffs").glob("*.md"))
            self.assertEqual(1, len(handoffs))
            briefing = subprocess.run(
                [sys.executable, str(script), "briefing"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, briefing.returncode, briefing.stderr)
            self.assertIn("Handoff aberto", briefing.stdout)
            accepted = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "handoff",
                    "--accept",
                    handoffs[0].relative_to(target).as_posix(),
                    "--owner",
                    "agente-b",
                ],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertIn("status: aceito", handoffs[0].read_text(encoding="utf-8"))
            briefing_after_accept = subprocess.run(
                [sys.executable, str(script), "briefing"], cwd=target, capture_output=True, text=True
            )
            self.assertEqual(0, briefing_after_accept.returncode, briefing_after_accept.stderr)
            self.assertNotIn("Handoff aberto", briefing_after_accept.stdout)
            claimed_again = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "handoff",
                    "--accept",
                    handoffs[0].relative_to(target).as_posix(),
                    "--owner",
                    "agente-c",
                ],
                cwd=target,
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, claimed_again.returncode)

            mcp = target / ".claude" / "hooks" / "memory_mcp.py"
            mcp_result = subprocess.run(
                [sys.executable, str(mcp)],
                cwd=target,
                input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, mcp_result.returncode, mcp_result.stderr)
            self.assertIn("harness_memory_query", mcp_result.stdout)
            self.assertIn("harness_memory_retrieve", mcp_result.stdout)
            self.assertIn("harness_graph_status", mcp_result.stdout)
            self.assertIn("harness_work_status", mcp_result.stdout)
            self.assertIn("harness_project_bootstrap_feedback", mcp_result.stdout)

    def test_dry_run_nao_escreve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.assertEqual(
                0,
                init_harness.main(["install", "--target", str(target), "--graph", "manual", "--dry-run"], KIT),
            )
            self.assertFalse((target / ".init-harness").exists())
            self.assertFalse((target / "INIT-HARNESS.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

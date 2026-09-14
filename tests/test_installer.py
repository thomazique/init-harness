"""Testes de integração do instalador e migrador."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import init_harness

KIT = Path(__file__).resolve().parents[1]


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


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
            self.assertEqual("2.1.0", config["harness_version"])
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
            self.assertEqual("2.1.0", config["harness_version"])
            self.assertEqual(["claude", "codex"], config["providers"])
            claude = (target / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("INIT-HARNESS.md", claude)
            self.assertIn(".init-harness/config.json", claude)

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

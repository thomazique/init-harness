"""Testes de contrato do verificador estatico da skill frontend."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
VERIFIER = KIT / ".claude/skills/frontend/scripts/verificar_frontend.py"


def run_verifier(target: Path, *options: str) -> subprocess.CompletedProcess[str]:
    cwd = target if target.is_dir() else target.parent
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(target), *options],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class FrontendVerifierTest(unittest.TestCase):
    def test_achado_e_consultivo_por_padrao_e_bloqueia_com_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            css = Path(tmp) / "component.css"
            css.write_text(".card { transition: all 180ms ease; }\n", encoding="utf-8")

            consultivo = run_verifier(css)
            strict = run_verifier(css, "--strict")

            self.assertEqual(0, consultivo.returncode, consultivo.stderr)
            self.assertIn("[VIOLACAO] [transicao explicita]", consultivo.stdout)
            self.assertIn("modo consultivo", consultivo.stderr)
            self.assertEqual(1, strict.returncode)
            self.assertIn("[VIOLACAO] [transicao explicita]", strict.stdout)
            self.assertIn("modo strict", strict.stderr)

    def test_aviso_sem_violacao_nao_bloqueia_nem_com_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            css = Path(tmp) / "component.css"
            css.write_text(".link:hover { color: var(--ink); }\n", encoding="utf-8")

            result = run_verifier(css, "--strict")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("[AVISO] [estado de foco possivelmente ausente]", result.stdout)
            self.assertIn("Nenhuma violacao mecanica; 1 aviso(s)", result.stderr)

    def test_comentarios_css_nao_geram_diagnosticos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            css = Path(tmp) / "component.css"
            css.write_text(
                "/* .fake:hover { color: #123456; transition: all 180ms ease; } */\n"
                ".button { padding: 8px; } /* transition: all 180ms ease; */\n"
                "/*\n.panel:hover {\n  transition: all 180ms ease;\n}\n*/\n",
                encoding="utf-8",
            )

            result = run_verifier(css, "--strict")

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertNotIn("[VIOLACAO]", result.stdout)
            self.assertNotIn("[AVISO]", result.stdout)

    def test_scanner_ignora_arquivos_gerados_minificados_e_extensoes_nao_web(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "frontend"
            accepted = root / "src/component.css"
            accepted.parent.mkdir(parents=True)
            accepted.write_text(".card { transition: all 180ms ease; }\n", encoding="utf-8")

            ignored = (
                "node_modules/pkg/dependency.css",
                ".next/static/page.css",
                "dist/bundle.css",
                "src/vendor.min.css",
                "src/notes.txt",
            )
            for relative in ignored:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(".ignored { transition: all 180ms ease; }\n", encoding="utf-8")

            result = run_verifier(root)
            normalized_output = result.stdout.replace("\\", "/")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("src/component.css", normalized_output)
            self.assertIn("em 1 arquivo(s)", result.stderr)
            for relative in ignored:
                self.assertNotIn(relative, normalized_output)

    def test_cor_literal_no_componente_e_sinalizada_e_token_css_e_aceito(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "frontend"
            root.mkdir()
            (root / "tokens.css").write_text(":root { --brand-color: #123456; }\n", encoding="utf-8")
            (root / "card.css").write_text(".card { color: #123456; }\n", encoding="utf-8")

            result = run_verifier(root, "--strict")

            self.assertEqual(1, result.returncode)
            self.assertIn("card.css", result.stdout)
            self.assertIn("[VIOLACAO] [cor fora de token]", result.stdout)
            self.assertNotIn("tokens.css:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

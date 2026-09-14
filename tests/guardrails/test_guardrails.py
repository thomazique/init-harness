"""Testes unitários do núcleo portátil do harness."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / ".claude" / "hooks"))

L = importlib.import_module("_lib")
B = importlib.import_module("guard_bash")


class ClassificacaoDeArquivosTest(unittest.TestCase):
    def test_contexto_inclui_adaptadores_e_documentacao(self) -> None:
        for caminho in (
            "CLAUDE.md",
            "INIT-HARNESS.md",
            "AGENTS.md",
            "docs/ai/ESTADO.md",
            "specs/api/1-x.md",
        ):
            with self.subTest(caminho=caminho):
                self.assertTrue(L.e_contexto(caminho))
                self.assertFalse(L.e_codigo(caminho))

    def test_codigo_reconhece_fontes_manifests_e_hooks(self) -> None:
        for caminho in (
            "src/app.py",
            "web/main.tsx",
            "pyproject.toml",
            "Dockerfile",
            ".githooks/pre-commit",
        ):
            with self.subTest(caminho=caminho):
                self.assertTrue(L.e_codigo(caminho))

    def test_conteudo_e_artefatos_nao_sao_codigo(self) -> None:
        for caminho in (
            "roteiros/sem1.md",
            "posts/capa.png",
            "dados/amostra.csv",
            "README.md",
            "out/video.mp4",
        ):
            with self.subTest(caminho=caminho):
                self.assertFalse(L.e_codigo(caminho))


class SegredosEAmbienteTest(unittest.TestCase):
    def test_env_sensivel_e_templates_permitidos(self) -> None:
        self.assertTrue(L.e_env_sensivel(".env"))
        self.assertTrue(L.e_env_sensivel("deploy/.env.production"))
        self.assertFalse(L.e_env_sensivel(".env.example"))

    def test_placeholder_nao_e_segredo_generico(self) -> None:
        fortes, genericos = L.segredos('api_key="${API_KEY}"')
        self.assertEqual([], fortes)
        self.assertEqual([], genericos)

    def test_valor_literal_sensivel_e_detectado(self) -> None:
        conteudo = "pass" + 'word="valor-literal-longo"'
        _, genericos = L.segredos(conteudo)
        self.assertEqual(["password"], genericos)

    def test_ambiente_respeita_primeira_regra_compativel(self) -> None:
        raiz = Path("projeto")
        h = {
            "ambientes": {
                "se_indeterminado": "bloquear",
                "regras": [
                    {
                        "nome": "local",
                        "arquivo": ".env",
                        "chave": "APP_ENV",
                        "valores": ["local"],
                        "destrutivo": "confirmar",
                    }
                ],
            }
        }
        with (
            patch.object(Path, "is_file", return_value=True),
            patch.object(L, "ler_dotenv", return_value={"APP_ENV": "local"}),
        ):
            self.assertEqual(("local", "confirmar"), L.ambiente(raiz, h))


class ComandosPerigososTest(unittest.TestCase):
    def test_bloqueia_bypass_de_verificacao(self) -> None:
        self.assertIsNotNone(B.casa(B.BURLAR, "git commit --no-verify"))
        self.assertIsNotNone(B.casa(B.BURLAR, "git config core.hooksPath outro"))

    def test_detecta_destruicao_de_dados_sem_where(self) -> None:
        self.assertIsNotNone(B.casa(B.DADOS, "DELETE FROM usuarios"))
        self.assertIsNone(B.casa(B.DADOS, "DELETE FROM usuarios WHERE id = 1"))

    def test_detecta_destruicao_de_git_e_arquivos(self) -> None:
        self.assertIsNotNone(B.casa(B.GIT_ARQUIVOS, "git reset --hard HEAD~1"))
        self.assertIsNotNone(B.casa(B.GIT_ARQUIVOS, "Remove-Item pasta -Recurse"))


class FrentesTest(unittest.TestCase):
    def test_frontmatter_aceita_utf8_com_bom(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "frente.md"
            arquivo.write_text("\n---\nstatus: concluida\nbranch: main\n---\n", encoding="utf-8-sig")
            self.assertEqual(
                {"status": "concluida", "branch": "main"},
                L.frontmatter(arquivo),
            )

    def test_multiplas_frentes_na_mesma_branch_sao_ambiguas(self) -> None:
        raiz = Path("projeto")
        existentes = [
            (Path("uma.md"), {"status": "ativa", "branch": "main"}),
            (Path("duas.md"), {"status": "pausada", "branch": "main"}),
        ]
        with patch.object(L, "frentes", return_value=existentes):
            self.assertEqual(2, len(L.frentes_da_branch(raiz, "main")))
            self.assertIsNone(L.frente_da_branch(raiz, "main"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

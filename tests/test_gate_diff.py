"""Contrato do scanner de integridade de gates (.claude/hooks/gate_diff.py)."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / ".claude" / "hooks"))

G = importlib.import_module("gate_diff")


def diff(caminho: str, removidas: list[str], adicionadas: list[str], antigo: str | None = None) -> str:
    linhas = [
        f"diff --git a/{antigo or caminho} b/{caminho}",
        f"--- a/{antigo or caminho}",
        f"+++ b/{caminho}",
        f"@@ -1,{len(removidas)} +1,{len(adicionadas)} @@",
    ]
    linhas += [f"-{linha}" for linha in removidas] + [f"+{linha}" for linha in adicionadas]
    return "\n".join(linhas) + "\n"


def marcas(texto: str, novos: dict[str, str] | None = None, config: dict | None = None) -> dict[str, list[str]]:
    return {t["caminho"]: t["marcas"] for t in G.analisar(texto, novos, config)["trechos"]}


class ClassificacaoTest(unittest.TestCase):
    def test_piso_de_gates_por_caminho(self) -> None:
        casos = {
            "tests/test_x.py": "teste",
            "src/x.test.ts": "teste",
            "pkg/x_test.go": "teste",
            "web/__snapshots__/a.test.js.snap": "snapshot",
            "fixtures/saida.golden": "golden",
            ".github/workflows/ci.yml": "ci",
            ".gitlab-ci.yml": "ci",
            "ruff.toml": "config",
            "jest.config.js": "config",
            "src/app.py": None,
            "docs/guia.md": None,
        }
        for caminho, esperado in casos.items():
            with self.subTest(caminho=caminho):
                self.assertEqual(esperado, G.classificar(caminho))

    def test_caminhos_extras_do_projeto(self) -> None:
        config = {"caminhos_teste": ["qa/"], "caminhos_snapshot": ["saidas/*.txt"]}
        self.assertEqual("teste", G.classificar("qa/fluxo.py", config))
        self.assertEqual("golden", G.classificar("saidas/a.txt", config))


class MarcasTest(unittest.TestCase):
    def test_rh1_teste_removido_e_skip(self) -> None:
        self.assertIn(
            "RH-1", marcas(diff("tests/test_a.py", ["    def test_x(self):", "        pass"], []))["tests/test_a.py"]
        )
        self.assertIn(
            "RH-1", marcas(diff("web/a.test.js", ["it('x', () => {"], ["it.skip('x', () => {"]))["web/a.test.js"]
        )
        self.assertEqual([], marcas(diff("tests/test_a.py", [], ["    def test_novo(self):"]))["tests/test_a.py"])

    def test_rh3_snapshot_sem_dono(self) -> None:
        snap = "web/__snapshots__/a.test.js.snap"
        self.assertEqual(["RH-3"], marcas(diff(snap, ["1"], ["2"]))[snap])
        com_dono = diff(snap, ["1"], ["2"]) + diff("web/a.test.js", ["x"], ["y"])
        self.assertEqual([], marcas(com_dono)[snap])

    def test_rh4_rh12_rh16_so_em_codigo_de_produto(self) -> None:
        produto = ["raise NotImplementedError", "if process.env.CI) {", "except Exception: pass"]
        self.assertEqual(["RH-4", "RH-12", "RH-16"], marcas(diff("src/a.py", [], produto))["src/a.py"])
        self.assertEqual([], marcas(diff("tests/test_a.py", [], produto))["tests/test_a.py"])

    def test_rh16_em_varias_linhas(self) -> None:
        self.assertEqual(["RH-16"], marcas(diff("src/a.ts", [], ["} catch (e) {", "}"]))["src/a.ts"])
        self.assertEqual(
            ["RH-16"], marcas(diff("src/a.py", [], ["    except ValueError:", "        pass"]))["src/a.py"]
        )

    def test_rh13_e_rh14(self) -> None:
        self.assertEqual(["RH-13"], marcas(diff("src/a.ts", [], ["// @ts-ignore"]))["src/a.ts"])
        self.assertEqual(
            ["RH-14"],
            marcas(diff(".github/workflows/ci.yml", [], ["    continue-on-error: true"]))[".github/workflows/ci.yml"],
        )

    def test_rh15_direcao_do_afrouxamento(self) -> None:
        ci = ".github/workflows/ci.yml"
        self.assertEqual(["RH-15"], marcas(diff(ci, ["    timeout-minutes: 10"], ["    timeout-minutes: 30"]))[ci])
        self.assertEqual([], marcas(diff(ci, ["    timeout-minutes: 30"], ["    timeout-minutes: 10"]))[ci])
        resultado = G.analisar(diff(ci, ["    timeout-minutes: 30"], ["    timeout-minutes: 10"]))
        self.assertIn("apertado", resultado["trechos"][0]["notas"][0])

    def test_rh15_contagem_exata_vira_limite(self) -> None:
        caminho = "web/a.test.js"
        texto = diff(caminho, ["expect(lista).toHaveLength(3)"], ["expect(lista).toBeGreaterThan(0)"])
        self.assertEqual(["RH-15"], marcas(texto)[caminho])

    def test_valor_sem_par_so_em_ci_e_config(self) -> None:
        self.assertEqual(["RH-15?"], marcas(diff("ruff.toml", [], ["timeout = 5"]))["ruff.toml"])
        self.assertEqual([], marcas(diff("tests/test_a.py", [], ["run(timeout=5)"]))["tests/test_a.py"])

    def test_pyproject_entra_no_piso_so_em_secao_de_ferramenta(self) -> None:
        texto = (
            "diff --git a/pyproject.toml b/pyproject.toml\n--- a/pyproject.toml\n+++ b/pyproject.toml\n"
            "@@ -1,3 +1,3 @@\n [tool.coverage.report]\n-fail_under = 90\n+fail_under = 80\n"
        )
        self.assertEqual(["RH-15"], marcas(texto)["pyproject.toml"])
        fora = diff("pyproject.toml", ['version = "1.0"'], ['version = "1.1"'])
        self.assertNotIn("pyproject.toml", marcas(fora))

    def test_prosa_nao_recebe_marca_de_codigo(self) -> None:
        self.assertNotIn("docs/a.md", marcas(diff("docs/a.md", [], ["use --no-verify # noqa"])))

    def test_arquivo_novo_e_arquivo_apagado(self) -> None:
        self.assertEqual(
            ["RH-16"], marcas("", {"src/novo.py": "try:\n    x()\nexcept Exception: pass\n"})["src/novo.py"]
        )
        apagado = (
            "diff --git a/tests/test_b.py b/tests/test_b.py\n--- a/tests/test_b.py\n+++ /dev/null\n"
            "@@ -1 +0,0 @@\n-def test_b():\n"
        )
        self.assertEqual(["RH-1"], marcas(apagado)["tests/test_b.py"])


class ExcecoesVisiveisTest(unittest.TestCase):
    HOOK = [
        "#!/bin/sh",
        "# graphify-hook-start",
        "    except Exception:",
        "        pass",
        "# graphify-hook-end",
    ]

    def test_bloco_do_graphify_nao_e_marcado(self) -> None:
        trecho = G.analisar("", {".githooks/post-commit": "\n".join(self.HOOK) + "\n"})["trechos"]
        self.assertEqual([], trecho)
        fora = self.HOOK + ["try:", "    x()", "except Exception: pass"]
        self.assertEqual(["RH-16"], marcas("", {".githooks/post-commit": "\n".join(fora)})[".githooks/post-commit"])

    def test_hunk_sem_marcador_usa_o_arquivo(self) -> None:
        texto = diff(".githooks/post-commit", [], ["    except Exception:", "        pass"])
        self.assertEqual(["RH-16"], marcas(texto)[".githooks/post-commit"])
        resultado = G.analisar(texto, leitor=lambda caminho: "\n".join(self.HOOK))
        self.assertEqual([], resultado["trechos"])

    def test_gate_ok_vira_nota_no_lugar_da_marca(self) -> None:
        texto = diff("src/a.py", [], ["except OSError:  # gate-ok: hook não pode falhar", "    pass"])
        resultado = G.analisar(texto)
        self.assertEqual([], resultado["trechos"])
        ci = ".github/workflows/ci.yml"
        texto = diff(ci, ["    timeout-minutes: 10"], ["    timeout-minutes: 30  # gate-ok: build medido em 22 min"])
        trecho = G.analisar(texto)["trechos"][0]
        self.assertEqual([], trecho["marcas"])
        self.assertEqual("lido", trecho["nivel"])  # removeu linha em caminho de gate: o auditor lê a nota
        self.assertIn("gate-ok: build medido em 22 min", trecho["notas"])


class NiveisTest(unittest.TestCase):
    def test_teste_adicionado_e_inventario_nao_leitura(self) -> None:
        trecho = G.analisar(diff("tests/test_a.py", [], ["def test_novo():", "    assert f()"]))["trechos"][0]
        self.assertEqual("listado", trecho["nivel"])

    def test_codigo_de_produto_sem_marca_fica_fora(self) -> None:
        self.assertEqual([], G.analisar(diff("src/a.py", ["x = 1"], ["x = 2"]))["trechos"])

    def test_linha_removida_que_comeca_com_tres_hifens_nao_quebra_o_parser(self) -> None:
        texto = diff("db/a_test.sql", ["-- comentario", "x"], ["y"])
        self.assertEqual(["-- comentario", "x"], G.analisar(texto)["trechos"][0]["removidas"])


class VarreduraGitTest(unittest.TestCase):
    def test_staged_e_arvore_de_trabalho(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True)

            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            (raiz / "tests").mkdir()
            (raiz / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "base")
            (raiz / "tests" / "test_a.py").write_text("", encoding="utf-8")
            self.assertEqual({}, G.varrer(raiz, staged=True)["resumo"]["marcas"])
            self.assertEqual({"RH-1": 1}, G.varrer(raiz)["resumo"]["marcas"])
            git("add", "-A")
            self.assertEqual({"RH-1": 1}, G.varrer(raiz, staged=True)["resumo"]["marcas"])
            saida = G.formatar(G.varrer(raiz, staged=True))
            self.assertTrue(saida.startswith("GATES: listados=1 lidos=1 marcas={RH-1:1}"))

    def test_pre_commit_avisa_sem_falhar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True)

            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            for relativo in (".githooks/pre_commit.py", ".claude/hooks/_lib.py", ".claude/hooks/gate_diff.py"):
                (raiz / relativo).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(KIT / relativo, raiz / relativo)
            (raiz / "tests").mkdir()
            (raiz / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "base")
            (raiz / "tests" / "test_a.py").write_text("", encoding="utf-8")
            git("add", "-A")
            r = subprocess.run(
                [sys.executable, ".githooks/pre_commit.py"],
                cwd=raiz,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertIn("tests/test_a.py: gate RH-1", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

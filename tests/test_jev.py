"""Testes locais do reranking Jev e do fallback FTS5."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))

import jev  # noqa: E402
import memory  # noqa: E402


class JevTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        config_dir = self.root / ".init-harness"
        config_dir.mkdir()
        self.config_path = config_dir / "config.json"
        self.config_path.write_text(json.dumps({"jev": {"enabled": True}}), encoding="utf-8")
        self.candidates = [
            ("docs/ai/one.md", "contexto", "A short factual passage about the payment architecture."),
            ("specs/two.md", "spec", "A direct answer describing the payment retry contract."),
        ]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_sem_chave_preserva_fts5_sem_rede(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            rows, status = jev.rerank(self.root, "payment retries", self.candidates)
        self.assertEqual(rows, self.candidates)
        self.assertIn("JEVMODEL_API_KEY ausente", status)

    def test_desabilitado_preserva_fts5_mesmo_com_chave(self) -> None:
        self.config_path.write_text(json.dumps({"jev": {"enabled": False}}), encoding="utf-8")
        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev.urllib.request, "urlopen") as urlopen:
                rows, status = jev.rerank(self.root, "payment retries", self.candidates)
        self.assertEqual(rows, self.candidates)
        self.assertIn("desativado", status)
        urlopen.assert_not_called()

    def test_api_pontua_candidatos_em_uma_chamada_e_reordena(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "answers": {
                            "passage_0": {"score": 2, "confidence": 0.91},
                            "passage_1": {"score": 5, "confidence": 0.88},
                        }
                    }
                ).encode()

        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
                rows, status = jev.rerank(self.root, "payment retries", self.candidates)

        self.assertEqual(rows[0], self.candidates[1])
        self.assertEqual(status, "Jev + FTS5")
        args, kwargs = urlopen.call_args
        self.assertEqual(args[0].full_url, jev.ENDPOINT)
        self.assertEqual(kwargs["timeout"], jev.TIMEOUT_SECONDS)
        body = json.loads(args[0].data)
        self.assertEqual(len(body["questions"]), 2)
        self.assertEqual(body["state"]["query"], "payment retries")
        self.assertEqual(args[0].get_header("Authorization"), "Bearer sk-test")

    def test_resposta_inconclusiva_cai_para_fts5(self) -> None:
        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev, "_request", return_value=None):
                rows, status = jev.rerank(self.root, "payment retries", self.candidates)
        self.assertEqual(rows, self.candidates)
        self.assertIn("fallback", status)

    def test_triagem_do_orquestrador_retorna_rotulos_tipados(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "answers": {
                            "intent": {"choice": "implement_parallel", "confidence": 0.9},
                            "specialty": {"choice": "mixed", "confidence": 0.85},
                            "needs_clarification": {"noul": 0.1},
                            "risk": {"score": 3, "confidence": 0.88},
                        }
                    }
                ).encode()

        state = {"objective": "Split a backend feature and database migration into coordinated fronts."}
        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
                decision, status = jev.classify_task(self.root, state)
        self.assertEqual(status, "Jev")
        self.assertEqual(decision["intent"], "implement_parallel")
        self.assertEqual(decision["specialty"], "mixed")
        self.assertEqual(decision["risk_score"], 3)
        self.assertEqual(len(json.loads(urlopen.call_args.args[0].data)["questions"]), 4)

    def test_gate_devolve_recomendacao_sem_substituir_validacao_do_chefe(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "answers": {
                            "decision": {"choice": "targeted_review", "confidence": 0.84},
                            "confidence": {"score": 4.2},
                        }
                    }
                ).encode()

        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev.urllib.request, "urlopen", return_value=FakeResponse()):
                decision, status = jev.classify_gate(self.root, "auditoria", {"finding": "one task needs review"})
        self.assertEqual(status, "Jev")
        self.assertEqual(decision["decision"], "targeted_review")
        self.assertEqual(decision["evidence_score"], 4.2)

    def test_snippet_com_segredo_nao_e_enviado(self) -> None:
        candidates = [
            ("docs/ai/leak.md", "contexto", "token: sk-" + "a" * 40),
            self.candidates[1],
        ]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps({"answers": {"passage_0": {"score": 4, "confidence": 0.9}}}).encode()

        with patch.dict(os.environ, {"JEVMODEL_API_KEY": "sk-test"}):
            with patch.object(jev.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
                rows, status = jev.rerank(self.root, "payment retries", candidates)
        self.assertEqual(status, "Jev + FTS5")
        self.assertEqual(rows[0], self.candidates[1])
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("sk-" + "a" * 40, json.dumps(payload))

    def test_busca_fts5_real_com_opcao_desligada(self) -> None:
        self.config_path.write_text(json.dumps({"jev": {"enabled": False}}), encoding="utf-8")
        docs = self.root / "docs" / "ai"
        docs.mkdir(parents=True)
        (docs / "payments.md").write_text("# Payments\nRetry architecture and payment contracts.\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            rows, status = memory.search_with_status(self.root, "payment retry")
        self.assertTrue(rows)
        self.assertIn("desativado", status)


if __name__ == "__main__":
    unittest.main(verbosity=2)

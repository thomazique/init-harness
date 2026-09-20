"""A versão do kit precisa ser a mesma em todos os lugares que a declaram.

O schema de configuração ficou fixo em 2.3.0 por duas versões porque nada comparava esses
lugares: todo config.json instalado reprovava a validação do próprio schema.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import init_harness

KIT = Path(__file__).resolve().parents[1]
VERSION = init_harness.VERSION


def read(relative: str) -> str:
    return (KIT / relative).read_text(encoding="utf-8")


class VersionConsistencyTest(unittest.TestCase):
    def test_versao_e_semver(self) -> None:
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")

    def test_documentos_declaram_a_versao_do_instalador(self) -> None:
        core = read("INIT-HARNESS.md")
        self.assertIn(f"> **harness_version: {VERSION}**", core)
        self.assertEqual({VERSION}, set(re.findall(r'"harness_version": "([^"]+)"', core)))
        self.assertEqual(f"# init-harness {VERSION}", read("README.md").splitlines()[0])

    def test_template_do_config_usa_a_versao_do_instalador(self) -> None:
        template = json.loads(read(".claude/skills/init-harness/templates/config.template.json"))
        self.assertEqual(VERSION, template["harness_version"])

    def test_schema_aceita_a_versao_do_instalador_e_nao_a_fixa_em_outra(self) -> None:
        schema = json.loads(read(".init-harness/schema/config.schema.json"))
        prop = schema["properties"]["harness_version"]
        self.assertNotIn("const", prop, "uma versão fixa no schema envelhece a cada release")
        self.assertRegex(VERSION, prop["pattern"])

    def test_changelog_tem_a_secao_da_versao(self) -> None:
        self.assertRegex(read("CHANGELOG.md"), rf"(?m)^## {re.escape(VERSION)}\b")

    def test_servidor_mcp_de_memoria_nao_fixa_versao(self) -> None:
        source = read(".claude/hooks/memory_mcp.py")
        self.assertNotRegex(source, r'"version":\s*"\d')


if __name__ == "__main__":
    unittest.main(verbosity=2)

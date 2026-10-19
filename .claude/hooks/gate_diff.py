"""
.claude/hooks/gate_diff.py

Integridade de gates: lista os trechos do diff que podem afrouxar um gate (teste, asserção,
limiar, timeout, lint, CI, snapshot) em vez de satisfazê-lo. Adaptado do gate-diff do
gstack (MIT); os identificadores RH são os do catálogo original.

Três níveis, nunca misturados:
- listado: todo trecho em caminho de teste, CI, config de runner/lint, snapshot ou golden,
  ou com marca. Inventário, não achado.
- lido: trecho listado que carrega marca ou remove linhas em caminho de gate. Quem audita
  faz uma pergunta: o afrouxamento silencia a falha para a qual o gate existia, ou é
  justificado por medição ou decisão visível no diff?
- achado: trecho lido que falha na pergunta. Decisão humana, nunca correção automática.

A marca é factual e não julga nem suprime: teste apagado junto com o código que ele cobria
continua marcado; o julgamento é de quem audita.

  RH-1   teste removido ou desativado        RH-13  pragma de supressão adicionado
  RH-3   snapshot mudou sem o teste dono     RH-14  gate contornado
  RH-4   placeholder commitado               RH-15  valor de gate afrouxado (RH-15? sem par)
  RH-12  código de produto detecta teste/CI  RH-16  exceção engolida

Uso:
  python .claude/hooks/gate_diff.py                árvore de trabalho contra HEAD, com arquivos novos
  python .claude/hooks/gate_diff.py --staged       só o que está em stage
  python .claude/hooks/gate_diff.py --base main    main...HEAD (o diff de uma PR)
  python .claude/hooks/gate_diff.py --json
Caminhos extras de teste e snapshot: guardrails.gates em .init-harness/config.json.
Sai com 0 quando a varredura roda (com ou sem marcas) e 2 quando o git falha.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

COBERTURA = ("RH-1", "RH-3", "RH-4", "RH-12", "RH-13", "RH-14", "RH-15", "RH-16")
DESCRICAO = {
    "RH-1": "teste removido ou desativado",
    "RH-3": "snapshot mudou sem o teste dono",
    "RH-3?": "golden mudou (dono não resolvido)",
    "RH-4": "placeholder commitado",
    "RH-12": "código de produto detecta ambiente de teste/CI",
    "RH-13": "pragma de supressão adicionado",
    "RH-14": "gate contornado",
    "RH-15": "valor de gate afrouxado",
    "RH-15?": "valor de gate sem par para comparar",
    "RH-16": "exceção engolida",
}
PERGUNTA = (
    "Para cada trecho lido: o afrouxamento silencia a falha para a qual o gate existia, ou é "
    "justificado por medição ou decisão visível no diff? A marca não é veredito; a decisão é humana."
)

# ---------------------------------------------------------------- classificação de caminho

DIRS_TESTE = {"test", "tests", "__tests__"}
NOMES_TESTE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\.test\.[^.]+$",
        r"\.spec\.[^.]+$",
        r"_test\.[^.]+$",
        r"_spec\.[^.]+$",
        r"^test_.*\.py$",
        r"Test\.(java|kt|scala)$",
        r"Tests\.swift$",
    )
]
DIRS_CI = (".github/workflows/", ".gitlab/ci/", ".circleci/")
NOMES_CI = {".gitlab-ci.yml", "jenkinsfile", ".travis.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml"}
NOMES_CONFIG = {
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "bunfig.toml",
    ".rubocop.yml",
    ".mocharc.yml",
    ".mocharc.json",
    ".nycrc",
    "codecov.yml",
    ".codecov.yml",
    "karma.conf.js",
    "playwright.config.ts",
    "playwright.config.js",
    "cypress.config.ts",
    "cypress.config.js",
    "phpunit.xml",
    "phpunit.xml.dist",
    ".pre-commit-config.yaml",
    "lefthook.yml",
    ".lefthook.yml",
    "mypy.ini",
    ".flake8",
    "ruff.toml",
    ".ruff.toml",
    "biome.json",
    ".prettierrc",
}
PREFIXOS_CONFIG = ("vitest.config", "jest.config", ".eslintrc", "eslint.config", "tsconfig", "golangci", ".golangci")
CONFIG_SECIONADA = {"package.json", "pyproject.toml"}

PROSA = re.compile(r"\.(?:md|mdx|markdown|txt|rst|adoc|asciidoc)(?:\.tmpl)?$", re.IGNORECASE)
GERADO = re.compile(
    r"(?:^|/)(?:dist|build|vendor|node_modules|\.yarn)/|\.min\.(?:js|css)$|(?:^|/)[^/]*lock(?:\.json|\.yaml|b)?$",
    re.IGNORECASE,
)

DECLARACAO_TESTE = re.compile(
    r"^\s*(?:(?:export\s+)?(?:async\s+)?(?:test|it|describe|context|suite|specify|scenario|feature)\s*(?:\.\w+)?\s*\("
    r"|def\s+test_\w+|async\s+def\s+test_\w+|func\s+Test\w*\s*\(|@Test\b|@pytest\.mark\.parametrize|#\[test\]"
    r"|#\[tokio::test\]|func\s+test\w*\s*\(\)\s*(?:async\s+)?(?:throws\s+)?\{|RSpec\.describe|\bit\s+[\"'])"
)


def _partes(caminho: str) -> list[str]:
    return [p for p in caminho.replace("\\", "/").split("/") if p]


def _casa_glob(caminho: str, globs: list[str]) -> bool:
    norm = caminho.replace("\\", "/")
    for g in globs:
        g = g.strip().replace("\\", "/").removeprefix("./")
        if not g:
            continue
        if g.endswith("/"):
            if norm.startswith(g) or f"/{g}" in f"/{norm}":
                return True
        elif fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(norm, f"*/{g}") or norm.startswith(g.rstrip("/") + "/"):
            return True
    return False


def classificar(caminho: str, config: dict | None = None) -> str | None:
    """Classe do caminho no piso de gates, ou None quando está fora dele."""
    config = config or {}
    partes = _partes(caminho)
    if not partes:
        return None
    nome = partes[-1]
    dirs = [d.lower() for d in partes[:-1]]
    if "__snapshots__" in dirs or nome.lower().endswith(".snap"):
        return "snapshot"
    if (
        nome.lower().endswith(".golden")
        or "testdata" in dirs
        or _casa_glob(caminho, config.get("caminhos_snapshot", []))
    ):
        return "golden"
    if (
        any(d in DIRS_TESTE for d in dirs)
        or any(p.search(nome) for p in NOMES_TESTE)
        or (nome.endswith("_test.go"))
        or _casa_glob(caminho, config.get("caminhos_teste", []))
    ):
        return "teste"
    norm = "/".join(partes).lower()
    if any(norm.startswith(d) or f"/{d}" in norm for d in DIRS_CI) or nome.lower() in NOMES_CI:
        return "ci"
    baixo = nome.lower()
    if baixo in NOMES_CONFIG or any(baixo.startswith(p) and baixo != p + ".d.ts" for p in PREFIXOS_CONFIG):
        return "config"
    return None


def _trecho_em_secao_de_ferramenta(caminho: str, linhas: list[str]) -> bool:
    nome = _partes(caminho)[-1].lower()
    if nome == "package.json":
        return any(
            re.match(
                r'^\s*"(scripts|jest|vitest|eslintConfig|husky|lint-staged|mocha|ava|c8|nyc|prettier|browserslist)"\s*:',
                linha,
            )
            or re.match(r'^\s*"(pre)?(test|lint|typecheck|check|ci|push|commit|prepare|coverage)[^"]*"\s*:\s*"', linha)
            for linha in linhas
        )
    if nome == "pyproject.toml":
        return any(re.match(r"^\s*\[tool\.", linha) for linha in linhas)
    return False


# ---------------------------------------------------------------- marcas

IDIOMAS_SKIP = [
    re.compile(p)
    for p in (
        r"\b(?:test|it|describe|suite|context|specify|bench)\s*\.\s*(?:skip|only)\b",
        r"\bx(?:it|describe|test|context|specify)\s*\(",
        r"\bf(?:it|describe|test)\s*\(",
        r"@pytest\.mark\.skip",
        r"@unittest\.skip",
        r"\bself\.skipTest\(",
        r"#\[ignore\b",
        r"\bt\.Skip\w*\(",
        r"@Disabled\b",
        r"@Ignore\b",
        r"\bXCTSkip",
        r"@tag\s+:skip\b",
    )
]
IDIOMAS_SKIP_SO_TESTE = [re.compile(r"^\s*(?:skip|pending)\s*(?:\(|[\"']|$)")]
IDIOMAS_PLACEHOLDER = [
    re.compile(r"\btodo!\s*\("),
    re.compile(r"\bunimplemented!\s*\("),
    re.compile(r"\braise\s+NotImplementedError\b"),
    re.compile(r"throw\s+new\s+Error\s*\(\s*[\"'`][^\"'`]*not\s+implemented", re.IGNORECASE),
    re.compile(r"\bpass\s+#\s*TODO\b", re.IGNORECASE),
]
IDIOMAS_AMBIENTE = [
    re.compile(p)
    for p in (
        r"process\.env\.CI\b",
        r"\bNODE_ENV\s*[!=]==?\s*[\"']test[\"']",
        r"[\"']test[\"']\s*[!=]==?\s*process\.env\.NODE_ENV",
        r"\bRAILS_ENV\s*==\s*[\"']test[\"']",
        r"\bRails\.env\.test\?",
        r"\bPYTEST_CURRENT_TEST\b",
        r"\bGITHUB_ACTIONS\b",
    )
]
IDIOMAS_SUPRESSAO = [
    re.compile(p)
    for p in (
        r"eslint-disable",
        r"@ts-ignore\b",
        r"@ts-expect-error\b",
        r"#\s*type:\s*ignore\b",
        r"#\s*noqa\b",
        r"#\[allow\(",
        r"//\s*nolint\b",
        r"rubocop:disable\b",
        r"@SuppressWarnings\b",
        r"#\s*pragma:\s*no\s*cover\b",
    )
]
IDIOMAS_CONTORNO = [
    re.compile(p) for p in (r"\bcontinue-on-error:\s*true\b", r"\ballow_failure:\s*true\b", r"--no-verify\b")
]
IDIOMAS_ENGOLE = [
    re.compile(p)
    for p in (
        r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}",
        r"\bexcept(?:\s+[\w.,\s()]+)?\s*:\s*pass\b",
        r"\brescue\s+nil\b",
        r"(?:^|[^\w.])_\s*=\s*err\b",
    )
]

CHAVES_SOBE = ("timeout", "retries", "retry", "tolerance", "epsilon", "delta", "maxdiff", "jitter")
CHAVES_DESCE = ("threshold", "min_score", "minscore", "minimum", "coverage", "required", "fail_under")
NAO_CHAVE = {"settimeout", "cleartimeout", "setinterval", "clearinterval"}
NUMERO = re.compile(r"-?\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?")
CHAVE_VALOR = re.compile(
    r"(?:--([A-Za-z][A-Za-z0-9_-]*)[= ]|([A-Za-z_][A-Za-z0-9_-]*)\s*(?::|=>?|\()\s*)"
    r"['\"`]?(-?\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?)"
)
CHAVE_ABRE_ESTRUTURA = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)\s*(?::|=>?|\()\s*[\[{(]")
CONTAGEM_EXATA = re.compile(r"^(?P<sujeito>.*?)\.(?:toBe|toEqual|toStrictEqual|toHaveLength)\(\s*-?\d+(?:\.\d+)?\s*\)")
LIMITE = re.compile(
    r"^(?P<sujeito>.*?)\.(?:toBeGreaterThan|toBeGreaterThanOrEqual|toBeLessThan|toBeLessThanOrEqual|toBeTruthy|toBeDefined)\("
)


@dataclass
class Trecho:
    caminho: str
    cabecalho: str
    removidas: list[str] = field(default_factory=list)
    adicionadas: list[str] = field(default_factory=list)
    contexto: list[str] = field(default_factory=list)
    classe: str | None = None
    marcas: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    nivel: str | None = None


def _algum(linhas: list[str], idiomas: list[re.Pattern]) -> bool:
    return any(p.search(linha) for linha in linhas for p in idiomas)


def _engole_em_varias_linhas(adds: list[str]) -> bool:
    for i in range(len(adds) - 1):
        a, b = adds[i].strip(), adds[i + 1].strip()
        abre_catch = re.search(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*$", a)
        if abre_catch and b == "}":
            return True
        if abre_catch and re.match(r"^/[/*]", b) and i + 2 < len(adds) and adds[i + 2].strip() == "}":
            return True
        if re.match(r"^except\b[^:]*:\s*$", a) and re.match(r"^pass\b", b):
            return True
    return False


def _direcao(chave: str) -> str | None:
    baixo = chave.lower()
    if baixo in NAO_CHAVE:
        return None
    if any(k in baixo for k in CHAVES_SOBE):
        return "sobe"
    if any(k in baixo for k in CHAVES_DESCE):
        return "desce"
    return None


def _numero(texto: str) -> float:
    return float(texto.replace("_", ""))


def chave_de_gate(linha: str) -> tuple[str, str, float] | None:
    """(chave, direção que afrouxa, valor) do valor de gate atribuído na linha."""
    pares = [(m.group(1) or m.group(2), m.group(3), m.start()) for m in CHAVE_VALOR.finditer(linha)]
    for chave, valor, _ in pares:
        direcao = _direcao(chave)
        if direcao:
            return chave, direcao, _numero(valor)
    for m in CHAVE_ABRE_ESTRUTURA.finditer(linha):
        direcao = _direcao(m.group(1))
        if not direcao:
            continue
        interno = next((p for p in pares if p[2] > m.start()), None)
        if interno:
            return m.group(1), direcao, _numero(interno[1])
    return None


def _forma(linha: str) -> str:
    return re.sub(r"[,;]\s*$", "", re.sub(r"\s+", " ", NUMERO.sub("#", linha))).strip()


def detectar_afrouxamento(t: Trecho, sem_par: bool = True) -> tuple[list[str], list[str]]:
    """RH-15 dentro de um trecho: pares removido/adicionado com a mesma chave e forma."""

    def valores(linhas: list[str]) -> list[dict]:
        out = []
        for texto in linhas:
            k = chave_de_gate(texto)
            if k:
                out.append({"chave": k[0], "direcao": k[1], "valor": k[2], "forma": _forma(texto), "par": False})
        return out

    removidos, adicionados = valores(t.removidas), valores(t.adicionadas)
    marcas: set[str] = set()
    notas: list[str] = []
    for d in removidos:
        a = next(
            (x for x in adicionados if not x["par"] and x["chave"] == d["chave"] and x["forma"] == d["forma"]), None
        )
        if not a:
            continue
        d["par"] = a["par"] = True
        if d["valor"] == a["valor"]:
            continue
        afrouxou = a["valor"] > d["valor"] if d["direcao"] == "sobe" else a["valor"] < d["valor"]
        if afrouxou:
            marcas.add("RH-15")
        sentido = "afrouxado" if afrouxou else "apertado"
        regra = "maior afrouxa" if d["direcao"] == "sobe" else "menor afrouxa"
        notas.append(f"RH-15: {d['chave']} {d['valor']:g} -> {a['valor']:g} ({sentido}: {regra})")
    for removida in t.removidas:
        m = CONTAGEM_EXATA.match(removida.strip())
        if not m:
            continue
        sujeito = m.group("sujeito")
        for adicionada in t.adicionadas:
            limite = LIMITE.match(adicionada.strip())
            if limite and limite.group("sujeito") == sujeito:
                marcas.add("RH-15")
                notas.append(f"RH-15: asserção de contagem exata virou limite ({sujeito.strip()})")
                break
    if sem_par:
        for v in removidos + adicionados:
            if not v["par"]:
                marcas.add("RH-15?")
                notas.append(f"RH-15?: valor de gate sem par {v['chave']} = {v['valor']:g}")
    return sorted(marcas, key=_ordem), notas


def _dono_do_snapshot_mudou(caminho: str, todos: set[str]) -> bool:
    partes = _partes(caminho)
    nome = partes[-1]
    base = re.sub(r"\.snap$", "", nome, flags=re.IGNORECASE)
    pasta = partes[:-2] if len(partes) > 1 and partes[-2].lower() == "__snapshots__" else partes[:-1]
    radical = base.split(".")[0]
    for outro in todos:
        op = _partes(outro)
        if op[:-1] != pasta:
            continue
        if op[-1] == base or ("." not in base and op[-1].startswith(radical + ".")):
            return True
    return False


def _ordem(marca: str) -> tuple[int, str]:
    return int(re.sub(r"\D", "", marca) or 0), marca


def marcar(t: Trecho, todos: set[str]) -> None:
    marcas: set[str] = set()
    notas: list[str] = []
    produto = t.classe != "teste"
    if t.classe == "snapshot" and not _dono_do_snapshot_mudou(t.caminho, todos):
        marcas.add("RH-3")
    elif t.classe == "golden":
        marcas.add("RH-3?")
    if not (PROSA.search(t.caminho) or GERADO.search(t.caminho)):
        removidas = sum(1 for linha in t.removidas if DECLARACAO_TESTE.search(linha))
        adicionadas = sum(1 for linha in t.adicionadas if DECLARACAO_TESTE.search(linha))
        if removidas > adicionadas:
            marcas.add("RH-1")
            notas.append(f"RH-1: {removidas - adicionadas} declaração(ões) de teste removida(s)")
        if _algum(t.adicionadas, IDIOMAS_SKIP) or (
            t.classe == "teste" and _algum(t.adicionadas, IDIOMAS_SKIP_SO_TESTE)
        ):
            marcas.add("RH-1")
        if produto and _algum(t.adicionadas, IDIOMAS_PLACEHOLDER):
            marcas.add("RH-4")
        if produto and _algum(t.adicionadas, IDIOMAS_AMBIENTE):
            marcas.add("RH-12")
        if _algum(t.adicionadas, IDIOMAS_SUPRESSAO):
            marcas.add("RH-13")
        if _algum(t.adicionadas, IDIOMAS_CONTORNO):
            marcas.add("RH-14")
        # Valor sem par em arquivo de teste é quase sempre timeout de subprocesso: só CI e config.
        if t.classe in {"teste", "ci", "config"}:
            m, n = detectar_afrouxamento(t, sem_par=t.classe != "teste")
            marcas.update(m)
            notas.extend(n)
        if produto and (_algum(t.adicionadas, IDIOMAS_ENGOLE) or _engole_em_varias_linhas(t.adicionadas)):
            marcas.add("RH-16")
    t.marcas = sorted(marcas, key=_ordem)
    t.notas = notas


# ---------------------------------------------------------------- diff


def _caminho_do_cabecalho(texto: str) -> str | None:
    texto = texto.rstrip("\t").strip()
    if texto == "/dev/null":
        return None
    if texto.startswith('"') and texto.endswith('"'):
        texto = texto[1:-1]
        try:
            texto = texto.encode("latin-1").decode("unicode_escape").encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return texto[2:] if texto[:2] in {"a/", "b/"} else texto


def ler_diff(texto: str) -> list[Trecho]:
    trechos: list[Trecho] = []
    antigo = novo = None
    atual: Trecho | None = None
    no_cabecalho = False
    for linha in texto.splitlines():
        if linha.startswith("diff --git "):
            antigo = novo = None
            atual = None
            no_cabecalho = True
            continue
        if no_cabecalho:
            if linha.startswith("--- "):
                antigo = _caminho_do_cabecalho(linha[4:])
            elif linha.startswith("+++ "):
                novo = _caminho_do_cabecalho(linha[4:])
            elif linha.startswith("@@"):
                no_cabecalho = False
            else:
                continue
        if linha.startswith("@@"):
            caminho = novo or antigo
            if caminho is None:
                atual = None
                continue
            atual = Trecho(caminho=caminho, cabecalho=linha.split("@@")[1].strip() if "@@" in linha[2:] else linha)
            trechos.append(atual)
            continue
        if atual is None:
            continue
        if linha.startswith("+"):
            atual.adicionadas.append(linha[1:])
        elif linha.startswith("-"):
            atual.removidas.append(linha[1:])
        elif linha.startswith(" "):
            atual.contexto.append(linha[1:])
    return trechos


def analisar(texto_diff: str, novos: dict[str, str] | None = None, config: dict | None = None) -> dict:
    """Classifica e marca os trechos de um diff unificado e de arquivos novos não rastreados."""
    trechos = ler_diff(texto_diff)
    for caminho, corpo in (novos or {}).items():
        trechos.append(Trecho(caminho=caminho, cabecalho="arquivo novo", adicionadas=corpo.splitlines()))
    todos = {t.caminho for t in trechos}
    for t in trechos:
        t.classe = classificar(t.caminho, config)
        if t.classe is None and _partes(t.caminho)[-1].lower() in CONFIG_SECIONADA:
            if _trecho_em_secao_de_ferramenta(t.caminho, t.contexto + t.removidas + t.adicionadas):
                t.classe = "config"
        marcar(t, todos)
        removeu_declaracao = any(DECLARACAO_TESTE.search(linha) for linha in t.removidas)
        if t.classe or t.marcas or removeu_declaracao:
            t.nivel = "lido" if t.marcas or (t.classe and t.removidas) else "listado"
    listados = [t for t in trechos if t.nivel]
    contagem: dict[str, int] = {}
    for t in listados:
        for m in t.marcas:
            contagem[m] = contagem.get(m, 0) + 1
    return {
        "resumo": {
            "listados": len(listados),
            "lidos": sum(1 for t in listados if t.nivel == "lido"),
            "marcas": dict(sorted(contagem.items(), key=lambda kv: _ordem(kv[0]))),
            "cobertura": list(COBERTURA),
        },
        "trechos": [
            {
                "id": i,
                "caminho": t.caminho,
                "cabecalho": t.cabecalho,
                "classe": t.classe,
                "nivel": t.nivel,
                "marcas": t.marcas,
                "notas": t.notas,
                "removidas": t.removidas,
                "adicionadas": t.adicionadas,
            }
            for i, t in enumerate(listados, start=1)
        ],
    }


def _git(raiz: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=str(raiz),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} falhou")
    return r.stdout


def _novos(raiz: Path, caminhos: list[str]) -> dict[str, str]:
    novos = {}
    for nome in _git(raiz, "ls-files", "--others", "--exclude-standard", "--", *caminhos).splitlines():
        arquivo = raiz / nome
        try:
            if arquivo.is_file() and arquivo.stat().st_size <= 1_000_000:
                novos[nome] = arquivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return novos


def config_do_projeto(raiz: Path) -> dict:
    try:
        dados = json.loads((raiz / ".init-harness" / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return ((dados.get("guardrails") or {}).get("gates") or {}) if isinstance(dados, dict) else {}


def varrer(raiz: Path, staged: bool = False, base: str | None = None, caminhos: list[str] | None = None) -> dict:
    """Roda o git e analisa o diff escolhido. Sem base nem staged: árvore de trabalho contra HEAD."""
    caminhos = caminhos or []
    opcoes = ["diff", "--no-color", "--no-ext-diff", "--find-renames", "-U3"]
    novos: dict[str, str] = {}
    if staged:
        texto = _git(raiz, *opcoes, "--cached", "--", *caminhos)
    elif base:
        texto = _git(raiz, *opcoes, f"{base}...HEAD", "--", *caminhos)
    else:
        texto = _git(raiz, *opcoes, "HEAD", "--", *caminhos)
        novos = _novos(raiz, caminhos)
    return analisar(texto, novos, config_do_projeto(raiz))


def formatar(resultado: dict, max_linhas: int = 30) -> str:
    r = resultado["resumo"]
    marcas = ",".join(f"{k}:{v}" for k, v in r["marcas"].items()) or "nenhuma"
    saida = [
        f"GATES: listados={r['listados']} lidos={r['lidos']} marcas={{{marcas}}} cobertura={','.join(r['cobertura'])}"
    ]
    lidos = [t for t in resultado["trechos"] if t["nivel"] == "lido"]
    if lidos:
        saida.append(PERGUNTA)
    for t in lidos:
        rotulo = ",".join(t["marcas"]) or "sem marca"
        saida.append(f"[{t['id']}] {rotulo} {t['caminho']} @@ {t['cabecalho']} @@")
        corpo = [f"  -{linha}" for linha in t["removidas"]] + [f"  +{linha}" for linha in t["adicionadas"]]
        saida.extend(corpo[:max_linhas])
        if len(corpo) > max_linhas:
            saida.append(f"  ... {len(corpo) - max_linhas} linha(s) omitida(s)")
        saida.extend(f"  nota: {n}" for n in t["notas"])
    return "\n".join(saida)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lista trechos do diff que podem afrouxar gates (teste, CI, lint).")
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--staged", action="store_true", help="analisa só o que está em stage")
    modo.add_argument("--base", help="analisa <base>...HEAD, o diff de uma PR")
    p.add_argument("--json", action="store_true", help="saída JSON com todos os trechos listados")
    p.add_argument("--raiz", type=Path, default=Path.cwd())
    p.add_argument("caminhos", nargs="*", help="restringe a estes caminhos")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        resultado = varrer(args.raiz, args.staged, args.base, args.caminhos)
    except (RuntimeError, OSError, subprocess.SubprocessError) as erro:
        print(f"gate_diff: varredura indisponível ({erro}); isso é cobertura ausente, não ausência de marcas.")
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2) if args.json else formatar(resultado))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verificador estatico pequeno para as regras mecanicas da skill frontend."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXTENSOES = {
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".html",
    ".htm",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".dart",
    ".svelte",
    ".astro",
    ".mjs",
    ".cjs",
}
IGNORAR_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".dart_tool",
    ".idea",
    ".tmp-harness",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".astro",
    ".turbo",
    ".venv",
    "venv",
    ".pytest_cache",
    ".output",
    "vendor",
}

RE_TRANSICAO_CSS = re.compile(r"(?<![-\w])transition\s*:\s*[^;{}]*\ball\b", re.IGNORECASE)
RE_TRANSICAO_UTILITY = re.compile(r"(?<![\w-])transition-all(?![\w-])")
RE_ESCALA_HOVER = re.compile(r"(?<![\w-])hover:scale-(?:105|\[1\.05\])(?![\w-])")
RE_TRANSFORM_ESCALA = re.compile(r"\btransform\s*:[^;{}]*\bscale(?:x|y)?\s*\(", re.IGNORECASE)
RE_HEX = re.compile(r"#[0-9a-fA-F]{3,4}(?:[0-9a-fA-F]{2})?(?![0-9a-fA-F])")
RE_FUNCAO_COR = re.compile(r"\b(?:rgba?|hsla?|oklch)\s*\(", re.IGNORECASE)
RE_DART_COR = re.compile(r"\bColor\s*\(\s*0x[0-9a-fA-F]{6,8}\b")
RE_PROPRIEDADE_VISUAL = re.compile(
    r"(?:^|[\s{.(])(?:color|background|border|outline|box-shadow|text-shadow|fill|stroke|decoration|shadow)\b|"
    r"\b(?:background|color|border|outline|shadow|fill|stroke)\s*:",
    re.IGNORECASE,
)
RE_CUSTOM_PROPERTY = re.compile(r"--[a-zA-Z0-9_-]+\s*:")
RE_ESPACAMENTO = re.compile(
    r"\b(?P<propriedade>(?:padding|margin)(?:-[\w-]+)?|(?:grid-)?(?:row-|column-)?gap)\s*:\s*"
    r"(?P<valor>[^;{}]+)",
    re.IGNORECASE,
)
RE_VALOR_PX = re.compile(r"(?P<valor>-?(?:\d+(?:\.\d+)?|\.\d+)px\b)", re.IGNORECASE)
RE_FONTE_POPULAR = re.compile(
    r"\bfont-family\s*:\s*[^;{}\n]*\b(?:Inter|Poppins|Roboto|Open\s+Sans|Lato|Montserrat)\b",
    re.IGNORECASE,
)
RE_KEYFRAMES = re.compile(r"@(?:-webkit-)?keyframes\b", re.IGNORECASE)
RE_ANIMATION = re.compile(r"\banimation\s*:", re.IGNORECASE)
RE_REDUCAO_MOTION = re.compile(r"prefers-reduced-motion\s*:", re.IGNORECASE)
RE_GRADIENTE_LINEAR = re.compile(r"\blinear-gradient\s*\(", re.IGNORECASE)
RE_CLIP_TEXTO = re.compile(r"(?:-webkit-)?background-clip\s*:\s*text\b", re.IGNORECASE)


@dataclass(frozen=True)
class Diagnostico:
    arquivo: Path
    linha: int
    severidade: str
    regra: str
    mensagem: str


@dataclass(frozen=True)
class BlocoCss:
    cabecalho: str
    corpo: str
    inicio: int
    inicio_corpo: int
    fim: int


def arquivos_de_codigo(alvo: Path) -> list[Path]:
    if alvo.is_file():
        return [alvo] if alvo.suffix.lower() in EXTENSOES else []

    encontrados: list[Path] = []
    for caminho in alvo.rglob("*"):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES:
            continue
        if any(parte in IGNORAR_DIRS for parte in caminho.parts):
            continue
        if caminho.name.endswith(".min.css") or caminho.name.endswith(".min.js"):
            continue
        encontrados.append(caminho)
    return sorted(encontrados)


def sem_comentario(linha: str, dentro: bool) -> tuple[str, bool]:
    """Remove comentarios de bloco da linha sem alterar sua numeracao."""
    restante = linha
    saida: list[str] = []
    while restante:
        if dentro:
            fim = restante.find("*/")
            if fim < 0:
                return "".join(saida), True
            restante = restante[fim + 2 :]
            dentro = False
            continue
        inicio = restante.find("/*")
        if inicio < 0:
            saida.append(restante)
            break
        saida.append(restante[:inicio])
        restante = restante[inicio + 2 :]
        dentro = True
    return "".join(saida), dentro


def e_arquivo_de_token(caminho: Path) -> bool:
    partes = [parte.lower() for parte in caminho.parts]
    return any(
        any(pista in parte for pista in ("token", "theme", "design-system", "design_system", "designsystem"))
        for parte in partes
    )


def tem_cor_literal(codigo: str) -> bool:
    return bool(RE_HEX.search(codigo) or RE_FUNCAO_COR.search(codigo) or RE_DART_COR.search(codigo))


def cor_fora_do_token(codigo: str, caminho: Path) -> bool:
    if not tem_cor_literal(codigo):
        return False
    # Custom properties sao o ponto de declaracao do token no CSS. Em Dart,
    # arquivos explicitamente nomeados como tema/tokens cumprem o mesmo papel.
    if RE_CUSTOM_PROPERTY.search(codigo) or e_arquivo_de_token(caminho):
        return False
    return bool(RE_PROPRIEDADE_VISUAL.search(codigo) or RE_DART_COR.search(codigo))


def linha_do_offset(codigo: str, offset: int) -> int:
    return codigo.count("\n", 0, offset) + 1


def extrair_blocos_css(codigo: str) -> list[BlocoCss]:
    """Extrai blocos simples e aninhados o bastante para as heuristicas de CSS."""
    blocos: list[BlocoCss] = []
    for correspondencia in re.finditer(r"(?P<cabecalho>[^{}]+)\{", codigo):
        abertura = correspondencia.end() - 1
        profundidade = 1
        indice = abertura + 1
        while indice < len(codigo) and profundidade:
            if codigo[indice] == "{":
                profundidade += 1
            elif codigo[indice] == "}":
                profundidade -= 1
            indice += 1
        if profundidade == 0:
            blocos.append(
                BlocoCss(
                    cabecalho=correspondencia.group("cabecalho").strip(),
                    corpo=codigo[abertura + 1 : indice - 1],
                    inicio=correspondencia.start(),
                    inicio_corpo=abertura + 1,
                    fim=indice - 1,
                )
            )
    return blocos


def seletores(cabecalho: str) -> list[str]:
    cabecalho = cabecalho.strip()
    if not cabecalho or cabecalho.startswith("@") or "@media" in cabecalho.lower():
        return []
    return [re.sub(r"\s+", " ", parte.strip()) for parte in cabecalho.split(",") if parte.strip()]


def valores_fora_da_escala(valor: str) -> list[str]:
    invalidos: list[str] = []
    for correspondencia in RE_VALOR_PX.finditer(valor):
        texto = correspondencia.group("valor")
        try:
            numero = Decimal(texto[:-2])
        except InvalidOperation:
            continue
        if numero not in (Decimal("1"), Decimal("2")) and numero % Decimal("4") != 0:
            invalidos.append(texto)
    return invalidos


def adicionar_diagnostico(
    diagnosticos: list[Diagnostico],
    arquivo: Path,
    linha: int,
    severidade: str,
    regra: str,
    mensagem: str,
) -> None:
    diagnosticos.append(Diagnostico(arquivo, linha, severidade, regra, mensagem))


def verificar_arquivo(caminho: Path) -> list[Diagnostico]:
    diagnosticos: list[Diagnostico] = []
    dentro_comentario = False
    try:
        linhas_originais = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        adicionar_diagnostico(diagnosticos, caminho, 1, "VIOLACAO", "leitura", f"nao foi possivel ler o arquivo: {exc}")
        return diagnosticos

    linhas_codigo: list[str] = []
    for original in linhas_originais:
        codigo, dentro_comentario = sem_comentario(original, dentro_comentario)
        if codigo.lstrip().startswith("//"):
            codigo = ""
        linhas_codigo.append(codigo)
    codigo = "\n".join(linhas_codigo)

    for numero, linha in enumerate(linhas_codigo, start=1):
        trecho = linha.strip()
        if not trecho or trecho.startswith("//") or trecho.startswith("#"):
            continue

        if RE_TRANSICAO_CSS.search(linha):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                numero,
                "VIOLACAO",
                "transicao explicita",
                "nao use `transition: all`; liste as propriedades animadas",
            )
        if RE_TRANSICAO_UTILITY.search(linha):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                numero,
                "VIOLACAO",
                "transicao explicita",
                "nao use a utility `transition-all`; liste as propriedades animadas",
            )
        if RE_ESCALA_HOVER.search(linha):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                numero,
                "VIOLACAO",
                "escala generica",
                "`hover:scale-105` e um default de efeito; justifique e componha o estado",
            )
        if cor_fora_do_token(linha, caminho):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                numero,
                "VIOLACAO",
                "cor fora de token",
                "mova a cor literal para o modulo central de tokens/tema",
            )

    for correspondencia in RE_ESPACAMENTO.finditer(codigo):
        invalidos = valores_fora_da_escala(correspondencia.group("valor"))
        if invalidos:
            valores = ", ".join(dict.fromkeys(invalidos))
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                linha_do_offset(codigo, correspondencia.start()),
                "VIOLACAO",
                "escala de espacamento",
                f"valor(es) em px fora da heuristica de escala ({valores}); use multiplos de 4 ou 1px/2px. "
                "Quando a escala nomeada do projeto existir, esta checagem deve validar contra ela.",
            )

    for correspondencia in RE_FONTE_POPULAR.finditer(codigo):
        adicionar_diagnostico(
            diagnosticos,
            caminho,
            linha_do_offset(codigo, correspondencia.start()),
            "VIOLACAO",
            "fonte de display popular",
            "nao use Inter, Poppins, Roboto, Open Sans, Lato ou Montserrat como voz de display sem "
            "decisao explicita do produto",
        )

    blocos = extrair_blocos_css(codigo)
    blocos_hover = [bloco for bloco in blocos if any(":hover" in seletor for seletor in seletores(bloco.cabecalho))]
    seletores_focus = {
        re.sub(r"\s+", " ", seletor.strip())
        for bloco in blocos
        for seletor in seletores(bloco.cabecalho)
        if ":focus-visible" in seletor
    }

    avisos_hover: set[tuple[int, str]] = set()
    for bloco in blocos_hover:
        for seletor in seletores(bloco.cabecalho):
            if ":hover" not in seletor:
                continue
            correspondente = re.sub(":hover", ":focus-visible", seletor)
            correspondente = re.sub(r"\s+", " ", correspondente.strip())
            if correspondente in seletores_focus:
                continue
            chave = (linha_do_offset(codigo, bloco.inicio), seletor)
            if chave in avisos_hover:
                continue
            avisos_hover.add(chave)
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                linha_do_offset(codigo, bloco.inicio),
                "AVISO",
                "estado de foco possivelmente ausente",
                f"heuristica: `{seletor}` tem `:hover`, mas nao ha seletor correspondente com `:focus-visible` no "
                "arquivo; confirme o estado de teclado (pode haver excecao legitima)",
            )

        if RE_TRANSFORM_ESCALA.search(bloco.corpo):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                linha_do_offset(codigo, bloco.inicio_corpo),
                "VIOLACAO",
                "escala generica",
                "nao use `transform: scale(...)` em `:hover`; componha um estado funcional sem escala ornamental",
            )

    tem_motion = bool(RE_KEYFRAMES.search(codigo) or RE_ANIMATION.search(codigo))
    if tem_motion and not RE_REDUCAO_MOTION.search(codigo):
        correspondencia_motion = RE_KEYFRAMES.search(codigo) or RE_ANIMATION.search(codigo)
        assert correspondencia_motion is not None
        adicionar_diagnostico(
            diagnosticos,
            caminho,
            linha_do_offset(codigo, correspondencia_motion.start()),
            "VIOLACAO",
            "motion sem reducao",
            "`@keyframes`/`animation:` exige fallback com `prefers-reduced-motion` no mesmo arquivo",
        )

    linhas_gradiente_detectadas: set[int] = set()
    for bloco in blocos:
        if "{" in bloco.corpo or "}" in bloco.corpo:
            continue
        clip = RE_CLIP_TEXTO.search(bloco.corpo)
        gradiente = RE_GRADIENTE_LINEAR.search(bloco.corpo)
        if clip and gradiente:
            linha = linha_do_offset(codigo, bloco.inicio_corpo + clip.start())
            linhas_gradiente_detectadas.add(linha)
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                linha,
                "VIOLACAO",
                "gradiente em texto",
                "nao aplique `linear-gradient` ao texto com `background-clip: text`; use tinta sem efeito ornamental",
            )

    for numero, linha in enumerate(linhas_codigo, start=1):
        if numero in linhas_gradiente_detectadas:
            continue
        if RE_CLIP_TEXTO.search(linha) and RE_GRADIENTE_LINEAR.search(linha):
            adicionar_diagnostico(
                diagnosticos,
                caminho,
                numero,
                "VIOLACAO",
                "gradiente em texto",
                "nao aplique `linear-gradient` ao texto com `background-clip: text`; use tinta sem efeito ornamental",
            )

    return diagnosticos


def caminho_apresentacao(caminho: Path) -> str:
    try:
        return str(caminho.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(caminho.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analisa heuristicas opcionais da skill frontend; os achados sao consultivos por padrao."
    )
    parser.add_argument("caminho", type=Path, help="arquivo ou diretorio de frontend")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="retorna codigo 1 ao encontrar violacoes heuristicas",
    )
    args = parser.parse_args()

    alvo = args.caminho
    if not alvo.exists():
        print(f"Caminho nao encontrado: {alvo}", file=sys.stderr)
        return 2

    arquivos = arquivos_de_codigo(alvo)
    diagnosticos = [diagnostico for arquivo in arquivos for diagnostico in verificar_arquivo(arquivo)]
    violacoes = [diagnostico for diagnostico in diagnosticos if diagnostico.severidade == "VIOLACAO"]
    avisos = [diagnostico for diagnostico in diagnosticos if diagnostico.severidade == "AVISO"]

    for diagnostico in diagnosticos:
        print(
            f"{caminho_apresentacao(diagnostico.arquivo)}:{diagnostico.linha}: "
            f"[{diagnostico.severidade}] [{diagnostico.regra}] {diagnostico.mensagem}"
        )

    if violacoes:
        modo = "strict" if args.strict else "consultivo"
        print(
            f"{len(violacoes)} achado(s) heuristico(s) e {len(avisos)} aviso(s) em {len(arquivos)} arquivo(s) "
            f"(modo {modo}).",
            file=sys.stderr,
        )
        if args.strict:
            return 1
        print("Achados heurísticos são consultivos; avalie se as regras se aplicam ao projeto.")
        return 0
    if avisos:
        print(f"Nenhuma violacao mecanica; {len(avisos)} aviso(s) em {len(arquivos)} arquivo(s).", file=sys.stderr)
        return 0

    print(f"Nenhuma violacao mecanica encontrada em {len(arquivos)} arquivo(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

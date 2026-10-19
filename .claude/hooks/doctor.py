"""
.claude/hooks/doctor.py

Diagnóstico portátil da instalação do harness. Não altera arquivos.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import _lib as L  # noqa: E402
import skill_evolution as E  # noqa: E402

# Qualidade de roteamento de skill (adaptado das ferramentas do Anthropic-Cybersecurity-Skills, Apache-2.0):
# a description é o único texto que o agente vê para decidir carregar a skill.
DESCRICAO_MAX = 1024
CORPO_MAX_LINHAS = 500
LIMIAR_COLISAO = 0.5
GATILHO = re.compile(
    r"(?i)\b(?:use|usar)\s+(?:esta\s+skill\s+|this\s+skill\s+)?"
    r"(?:quando|sempre|em|na|no|nas|nos|antes|ao|após|depois|para|durante|when|whenever|for|before|after|during)\b"
)
NEGATIVO = re.compile(r"(?i)\b(?:não|nunca)\s+(?:use|usar)\b|\bdo\s+not\s+use\b|\bdon'?t\s+use\b|\bnot\s+for\b")
PALAVRAS_VAZIAS = set(
    """
    a o as os um uma de do da dos das e ou em no na nos nas por para com sem que se ao à é ser use usar quando
    sempre antes depois skill skills the an and or of to for in on with when this that is are be by from as it
    """.split()
)


def avisos_de_skill(nome: str, meta: dict, texto: str) -> list[str]:
    """Avisos de roteamento: gatilho positivo, gatilho negativo, tamanho da description e do corpo."""
    descricao = " ".join(str(meta.get("description") or "").split())
    avisos = []
    if len(descricao) > DESCRICAO_MAX:
        avisos.append(f"{nome}: description com {len(descricao)} caracteres (máximo {DESCRICAO_MAX})")
    if descricao and not GATILHO.search(descricao):
        avisos.append(f"{nome}: description sem gatilho ('Use quando ...')")
    if descricao and not NEGATIVO.search(descricao):
        avisos.append(f"{nome}: description sem gatilho negativo ('Não use para X, que é <outra-skill>.')")
    linhas = texto.count("\n") + 1
    if linhas > CORPO_MAX_LINHAS:
        avisos.append(f"{nome}: SKILL.md com {linhas} linhas (máximo {CORPO_MAX_LINHAS}; detalhe vai para references/)")
    return avisos


def _termos(descricao: str) -> dict[str, int]:
    descritiva = NEGATIVO.split(descricao, maxsplit=1)[0]
    termos: dict[str, int] = {}
    for palavra in re.findall(r"\w+", descritiva.lower()):
        if len(palavra) > 2 and palavra not in PALAVRAS_VAZIAS:
            termos[palavra] = termos.get(palavra, 0) + 1
    return termos


def colisoes(descricoes: dict[str, str], limiar: float = LIMIAR_COLISAO) -> list[tuple[str, str, float]]:
    """Pares de skills cuja parte descritiva concorre pelo mesmo pedido e que não se distinguem pelo nome."""
    vetores = {nome: _termos(d) for nome, d in descricoes.items()}
    nomes = sorted(vetores)
    pares = []
    for i, a in enumerate(nomes):
        for b in nomes[i + 1 :]:
            va, vb = vetores[a], vetores[b]
            norma = (sum(v * v for v in va.values()) * sum(v * v for v in vb.values())) ** 0.5
            if not norma:
                continue
            similaridade = sum(va[t] * vb.get(t, 0) for t in va) / norma
            distinguidas = b in descricoes[a] or a in descricoes[b]
            if similaridade >= limiar and not distinguidas:
                pares.append((a, b, round(similaridade, 2)))
    return pares


def _duplicate_ids(path: Path, pattern: str, first_column_only: bool = False) -> dict[str, list[int]]:
    """Encontra identificadores duplicados sem interpretar o restante do Markdown.

    Linhas dentro de comentário HTML (o modelo de entrada dos templates) não contam.
    """
    if not path.is_file():
        return {}
    matches: dict[str, list[int]] = {}
    em_comentario = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        visivel = ""
        resto = line
        while resto:
            if em_comentario:
                fim = resto.find("-->")
                if fim < 0:
                    break
                em_comentario, resto = False, resto[fim + 3 :]
            else:
                inicio = resto.find("<!--")
                if inicio < 0:
                    visivel += resto
                    break
                visivel, em_comentario, resto = visivel + resto[:inicio], True, resto[inicio + 4 :]
        line = visivel
        if first_column_only:
            subject = line.split("|", 2)[1] if line.lstrip().startswith("|") and "|" in line else ""
        else:
            subject = line
        found = re.search(pattern, subject)
        if found:
            matches.setdefault(found.group(1), []).append(line_number)
    return {identifier: lines for identifier, lines in matches.items() if len(lines) > 1}


def main() -> int:
    raiz = Path(__file__).resolve().parents[2]
    erros: list[str] = []
    avisos: list[str] = []
    ok: list[str] = []

    h = L.harness(raiz)
    if h is None:
        erros.append(".init-harness/config.json ausente")
        h = {}
    elif h.get("_erro"):
        erros.append(".init-harness/config.json inválido")
    else:
        ok.append(f"config.json versão {h.get('harness_version', '?')}")
        if h.get("modo") not in {"proprio", "cliente"}:
            erros.append(f"modo inválido em config.json: {h.get('modo', '?')}")
        if h.get("grafo") not in {"graphify", "manual"}:
            erros.append(f"grafo inválido em config.json: {h.get('grafo', '?')}")
        if h.get("instalado_em") in {None, "", "AAAA-MM-DD"}:
            erros.append("instalado_em não foi preenchido em config.json")
        providers = h.get("providers")
        if not isinstance(providers, list) or not providers or not set(providers) <= {"claude", "codex"}:
            erros.append("providers deve conter claude e/ou codex")
        autonomia = h.get("autonomia")
        chaves_autonomia = {
            "tarefas_seguras",
            "apos_checkpoint",
            "producao",
            "destrutivo",
            "politica_negocio",
        }
        if not isinstance(autonomia, dict) or set(autonomia) != chaves_autonomia:
            erros.append("bloco autonomia ausente ou incompleto")
        memoria = h.get("memoria")
        if not isinstance(memoria, dict) or not isinstance(memoria.get("mcp"), bool):
            erros.append("bloco memoria.mcp ausente ou inválido")
        jev = h.get("jev")
        if not isinstance(jev, dict) or not isinstance(jev.get("enabled"), bool):
            erros.append("bloco jev.enabled ausente ou inválido")
        elif jev["enabled"]:
            ok.append("Jev habilitado por opt-in (busca e triagem do orquestrador)")
            if not os.environ.get("JEVMODEL_API_KEY") and not L.ler_dotenv(raiz / ".env").get("JEVMODEL_API_KEY"):
                avisos.append("Jev habilitado, mas JEVMODEL_API_KEY não foi encontrada; busca usará FTS5")

    nucleo = raiz / "INIT-HARNESS.md"
    if not nucleo.exists():
        if h.get("modo") == "proprio":
            erros.append("INIT-HARNESS.md ausente no modo proprio")
    else:
        texto = nucleo.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"harness_version:\s*([\w.]+)", texto)
        versao_doc = m.group(1) if m else None
        if not versao_doc:
            erros.append("versão não encontrada em INIT-HARNESS.md")
        elif versao_doc != h.get("harness_version"):
            erros.append(f"versões divergentes: documento={versao_doc}, config.json={h.get('harness_version', '?')}")
        else:
            ok.append(f"documento e manifesto na versão {versao_doc}")

    obrigatorios = [
        "CLAUDE.md",
        "docs/ai/ESTADO.md",
        "docs/ai/ESTRUTURA.md",
        "docs/ai/DECISOES.md",
        "docs/ai/DEBITOS.md",
        ".claude/settings.json",
        ".claude/hooks/_lib.py",
        ".claude/hooks/session_start.py",
        ".claude/hooks/guard_bash.py",
        ".claude/hooks/guard_files.py",
        ".claude/hooks/memory.py",
        ".claude/hooks/memory_mcp.py",
        ".claude/hooks/pre_compact.py",
        ".claude/hooks/stop_check.py",
        ".claude/hooks/doctor.py",
        ".claude/hooks/skill_evolution.py",
        ".claude/hooks/skill_observe.py",
        ".claude/hooks/skill_worker.py",
        ".claude/hooks/skill_reviewer.py",
        ".claude/hooks/gate_diff.py",
        ".githooks/pre-commit",
        ".githooks/pre_commit.py",
        ".init-harness/schema/config.schema.json",
        ".init-harness/schema/orquestracao.schema.json",
        ".init-harness/orquestracao.json",
        ".claude/skills/orquestrar/scripts/invocar_agentes.py",
    ]
    providers = h.get("providers", [])
    if "codex" in providers:
        obrigatorios.extend(
            (
                "AGENTS.md",
                ".codex/agents/harness_executor.toml",
                ".codex/agents/harness_auditor.toml",
                ".codex/config.toml",
            )
        )
    if "claude" in providers:
        obrigatorios.extend((".claude/agents/executor.md", ".claude/agents/revisor.md"))
    if h.get("modo") != "cliente":
        obrigatorios.append("tests/guardrails/test_guardrails.py")
    ausentes = [c for c in obrigatorios if not (raiz / c).exists()]
    if ausentes:
        erros.append("arquivos obrigatórios ausentes: " + ", ".join(ausentes))
    else:
        ok.append("arquivos de enforcement presentes")

    perfis_path = raiz / ".init-harness" / "orquestracao.json"
    if perfis_path.is_file():
        try:
            perfis_config = json.loads(perfis_path.read_text(encoding="utf-8"))
            if not isinstance(perfis_config, dict):
                raise ValueError("raiz precisa ser um objeto")
            perfis = perfis_config.get("perfis")
            ids = [p.get("id") for p in perfis if isinstance(p, dict)] if isinstance(perfis, list) else []
            limites_validos = all(
                isinstance(perfis_config.get(chave), int) and perfis_config[chave] > 0
                for chave in ("limite_chamadas_cli_por_atividade", "timeout_segundos")
            )
            ids_validos = (
                isinstance(perfis, list)
                and bool(perfis)
                and len(ids) == len(perfis)
                and all(isinstance(identificador, str) and identificador for identificador in ids)
                and len(set(ids)) == len(ids)
            )
            if perfis_config.get("perguntar_a_cada_atividade") is not True or not ids_validos or not limites_validos:
                erros.append("orquestracao.json deve perguntar em cada atividade e conter perfis com IDs únicos")
            else:
                ok.append(f"{len(perfis)} perfil(is) de orquestração disponíveis")
            for perfil in perfis if isinstance(perfis, list) else []:
                if not isinstance(perfil, dict):
                    erros.append("orquestracao.json contém perfil inválido")
                    continue
                for papel in ("coordenador", "executor", "auditor"):
                    agente = perfil.get(papel)
                    if (
                        not isinstance(agente, dict)
                        or agente.get("provedor") not in {"claude", "codex"}
                        or not isinstance(agente.get("modelo"), str)
                        or agente.get("modo") not in {"sessao", "nativo", "cli"}
                    ):
                        erros.append(f"perfil {perfil.get('id', '?')} tem papel {papel} inválido")
                    elif agente.get("modo") == "cli":
                        executavel = "claude" if agente["provedor"] == "claude" else "codex"
                        if not shutil.which(executavel):
                            avisos.append(
                                f"perfil {perfil.get('id', '?')} requer '{executavel}' no PATH para chamadas CLI"
                            )
        except (OSError, json.JSONDecodeError, ValueError):
            erros.append(".init-harness/orquestracao.json inválido")

    settings = raiz / ".claude" / "settings.json"
    if "claude" in providers and not settings.exists():
        erros.append("provider claude configurado, mas .claude/settings.json está ausente")
    elif "claude" in providers:
        try:
            dados = json.loads(settings.read_text(encoding="utf-8"))
            serializado = json.dumps(dados)
            faltantes = [
                nome
                for nome in (
                    "session_start.py",
                    "guard_bash.py",
                    "guard_files.py",
                    "pre_compact.py",
                    "stop_check.py",
                    "skill_observe.py",
                )
                if nome not in serializado
            ]
            if faltantes:
                erros.append("hooks ausentes de settings.json: " + ", ".join(faltantes))
            else:
                ok.append("hooks registrados em settings.json")
            pre_tool_use = dados.get("hooks", {}).get("PreToolUse", [])
            ativa_skill = any(
                entrada.get("matcher") == "Skill" and "skill_observe.py" in json.dumps(entrada)
                for entrada in pre_tool_use
                if isinstance(entrada, dict)
            )
            if "skill_observe.py" in serializado and not ativa_skill:
                erros.append(
                    "settings.json sem PreToolUse com matcher Skill para skill_observe.py: "
                    "a skill ativa nunca é definida e nenhuma experiência é capturada"
                )
            if re.search(r'"command"\s*:\s*"(?:[A-Za-z]:[\\/]|/)', serializado):
                avisos.append("settings.json contém comando com caminho absoluto; a instalação pode não ser portátil")
        except (OSError, json.JSONDecodeError):
            erros.append(".claude/settings.json inválido")

    skills_dir = raiz / ".claude" / "skills"
    problemas_skills: list[str] = []
    descricoes: dict[str, str] = {}
    arquivos_skill = sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []
    for arquivo in arquivos_skill:
        nome_dir = arquivo.parent.name
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        kit = Path(".init-harness/updates/.claude/skills") / nome_dir / "SKILL.md.new"
        dica = f" (a versão do kit está em {kit.as_posix()})" if (raiz / kit).is_file() else ""
        if not texto.startswith("---"):
            problemas_skills.append(f"{nome_dir}: o frontmatter precisa começar na linha 1 com ---{dica}")
            continue
        meta = E.parse_frontmatter(texto)
        if meta.get("name") != nome_dir:
            problemas_skills.append(
                f"{nome_dir}: name do frontmatter ({meta.get('name') or 'ausente'}) difere do diretório{dica}"
            )
        if not meta.get("description"):
            problemas_skills.append(f"{nome_dir}: description ausente ou vazia no frontmatter{dica}")
            continue
        descricoes[nome_dir] = meta["description"]
        avisos.extend("skill: " + aviso for aviso in avisos_de_skill(nome_dir, meta, texto))
    for a, b, similaridade in colisoes(descricoes):
        avisos.append(
            f"skills {a} e {b} concorrem pelo mesmo pedido (similaridade {similaridade}); "
            "acrescente a uma delas 'Não use para X, que é <a outra>.'"
        )
    if problemas_skills:
        for problema in problemas_skills:
            erros.append("skill inválida: " + problema)
    elif arquivos_skill:
        ok.append(f"{len(arquivos_skill)} skill(s) com frontmatter válido")

    dentro_git = bool(L.git(["rev-parse", "--is-inside-work-tree"], raiz))
    if not dentro_git:
        erros.append("diretório não é um worktree Git")
    else:
        hooks_path = L.git(["config", "--get", "core.hooksPath"], raiz)
        if hooks_path.replace("\\", "/").rstrip("/") != ".githooks":
            erros.append(f"core.hooksPath esperado .githooks, encontrado {hooks_path or 'não definido'}")
        else:
            ok.append("pre-commit configurado em .githooks")

    if not shutil.which("uv"):
        avisos.append(
            "uv não está no PATH; instale-o e exponha seu diretório de binários ao cliente de IA e ao Git "
            "(Linux/macOS: ~/.local/bin ou ~/.cargo/bin; Windows: %USERPROFILE%\\.local\\bin)."
        )
    else:
        ok.append("uv disponível no PATH")

    updates = raiz / ".init-harness" / "updates"
    pending_updates = list(updates.rglob("*.new")) if updates.is_dir() else []
    if pending_updates:
        avisos.append(f"{len(pending_updates)} atualização(ões) de kit pendentes de revisão em .init-harness/updates/")

    if h.get("grafo") == "graphify":
        if shutil.which("graphify"):
            resultado = subprocess.run(
                ["graphify", "--version"],
                cwd=raiz,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            saida = (resultado.stdout + resultado.stderr).strip()
            if resultado.returncode:
                erros.append("graphify está no PATH, mas graphify --version falhou")
            else:
                versao = next(
                    (linha for linha in saida.splitlines() if linha.startswith("graphify ")),
                    "disponível",
                )
                ok.append(versao)
                if "warning:" in saida.lower():
                    avisos.append("graphify reportou deriva entre pacote e integração do projeto")
        else:
            erros.append("grafo configurado como graphify, mas o comando não está no PATH")

    por_branch: dict[str, list[str]] = {}
    for arq, fm in L.frentes(raiz):
        if fm.get("status") == "concluida":
            continue
        branch = str(fm.get("branch", "")).strip()
        if branch and branch not in {"-", "?"}:
            por_branch.setdefault(branch, []).append(arq.name)
    for branch, nomes in por_branch.items():
        if len(nomes) > 1:
            erros.append(f"branch {branch} tem múltiplas frentes não concluídas: {', '.join(nomes)}")

    duplicate_sources = (
        (raiz / "docs/ai/DECISOES.md", r"^##\s+(D-\d+)\b", False),
        (raiz / "docs/ai/DEBITOS.md", r"\b(DB-\d+)\b", True),
    )
    for path, pattern, first_column_only in duplicate_sources:
        for identifier, lines in _duplicate_ids(path, pattern, first_column_only).items():
            erros.append(
                f"ID duplicado {identifier} em {path.relative_to(raiz).as_posix()}: linhas {', '.join(map(str, lines))}"
            )

    for mensagem in ok:
        print(f"[OK] {mensagem}")
    for mensagem in avisos:
        print(f"[AVISO] {mensagem}")
    for mensagem in erros:
        print(f"[ERRO] {mensagem}")
    print(f"Resultado: {len(erros)} erro(s), {len(avisos)} aviso(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())

"""
.claude/hooks/session_start.py

SessionStart (startup, resume, clear, compact): injeta estado factual no contexto.
Nunca bloqueia. Texto em forma de fato, não de ordem.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True  # não gerar __pycache__ no projeto

import _lib as L  # noqa: E402
import memory as M  # noqa: E402
import skill_evolution as E  # noqa: E402


def horas_desde(valor: str) -> float | None:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return (datetime.now() - datetime.strptime(valor, fmt)).total_seconds() / 3600
        except ValueError:
            continue
    return None


def debitos_abertos(r: Path) -> int | None:
    arq = r / "docs" / "ai" / "DEBITOS.md"
    if not arq.exists():
        return None
    corpo = L.secao(arq, "Abertos")
    linhas = [linha for linha in corpo.splitlines() if linha.strip().startswith("|")]
    return max(0, len(linhas) - 2)


def main() -> None:
    e = L.ler_entrada()
    r = L.raiz(e)
    sid = e.get("session_id", "")
    origem = e.get("source", "startup")
    h = L.harness(r)
    linhas: list[str] = []

    if h is None:
        linhas.append(
            "Este projeto não tem .init-harness/config.json: a implantação do harness não foi feita "
            "(skill init-harness)."
        )
        L.emitir(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(linhas),
                }
            }
        )
        return

    arq_estado, estado = L.estado_sessao(r, sid)
    if origem == "startup" or "inicio" not in estado:
        estado["inicio"] = time.time()
    pend_compact = estado.pop("pendente_na_compactacao", None)
    L.salvar_estado(arq_estado, estado)

    versao = h.get("harness_version", "?")
    linhas.append(
        f"Harness {versao}, modo {h.get('modo', '?')}, grafo {h.get('grafo', '?')}. "
        f"Identificador desta sessão (campo dono das frentes): {sid or 'indisponível'}."
    )
    autonomia = h.get("autonomia") or {}
    linhas.append(
        "Autonomia: tarefas seguras "
        f"{autonomia.get('tarefas_seguras', 'não definida')}, após checkpoint "
        f"{autonomia.get('apos_checkpoint', 'não definida')}; produção "
        f"{autonomia.get('producao', 'não definida')}."
    )

    nucleo = r / "INIT-HARNESS.md"
    if nucleo.exists():
        m = re.search(r"harness_version:\s*([\w.]+)", nucleo.read_text(encoding="utf-8", errors="replace"))
        if m and m.group(1) != versao:
            linhas.append(f"Divergência de versão: config.json indica {versao} e INIT-HARNESS.md indica {m.group(1)}.")

    branch = L.branch_atual(r)
    nome_amb, politica = L.ambiente(r, h)
    linhas.append(f"Branch atual: {branch}. Ambiente detectado: {nome_amb} (comando destrutivo de dados: {politica}).")

    candidatas = L.frentes_da_branch(r, branch)
    fr = candidatas[0] if len(candidatas) == 1 else None
    if fr:
        arq, fm = fr
        prox = L.secao(arq, "Próximo passo") or "não registrado"
        linhas.append(
            f"Frente desta branch: {arq.relative_to(r).as_posix()} — status {fm.get('status', '?')}, "
            f"dono {fm.get('dono', '?')}, atualizado em {fm.get('atualizado_em', '?')}."
        )
        linhas.append(f"Próximo passo registrado: {prox}")
    elif not candidatas:
        linhas.append(f"Nenhuma frente registrada para a branch {branch}.")
    else:
        nomes = ", ".join(arq.relative_to(r).as_posix() for arq, _ in candidatas)
        linhas.append(f"Posse ambígua: há {len(candidatas)} frentes não concluídas na branch {branch}: {nomes}.")

    limite = h.get("frente_inativa_horas")
    outras = []
    for arq, fm in L.frentes(r):
        if fm.get("status") not in ("ativa", "pausada", "bloqueada") or (fr and arq == fr[0]):
            continue
        idade = horas_desde(fm.get("atualizado_em", ""))
        if fm.get("status") != "ativa":
            situacao = "pode ser assumida"
        elif limite is None or idade is None:
            situacao = "em uso (limite de inatividade não definido)"
        elif idade >= limite:
            situacao = f"inativa há {idade:.0f}h, pode ser assumida"
        else:
            situacao = "em uso"
        outras.append(f"{fm.get('slug', arq.stem)} ({fm.get('status')}, branch {fm.get('branch', '?')}, {situacao})")
    if outras:
        linhas.append("Outras frentes: " + "; ".join(outras) + ".")

    n = debitos_abertos(r)
    if n is not None:
        linhas.append(f"Débitos abertos em docs/ai/DEBITOS.md: {n}.")

    try:
        linhas.extend(M.briefing(r, branch))
    except Exception as exc:
        linhas.append(
            f"Memória local indisponível ({exc.__class__.__name__}); os documentos canônicos continuam no disco."
        )

    try:
        evolution = E.evolution_status(r)
        if evolution["total"]:
            linhas.append(
                "Evolução de skills: "
                f"{evolution['queued']} na fila, {evolution['review_required']} aguardando revisão, "
                f"{evolution['review_approved']} aguardando aprovação humana, {evolution['failed']} falhos."
            )
    except Exception:
        pass

    saude = []
    hooks_path = L.git(["config", "--get", "core.hooksPath"], r)
    saude.append(f"core.hooksPath={hooks_path or 'não definido'}")
    saude.append("pre-commit do harness " + ("presente" if (r / ".githooks" / "pre-commit").exists() else "ausente"))
    saude.append("graphify " + ("disponível" if shutil.which("graphify") else "não encontrado no PATH"))
    linhas.append("Enforcement: " + ", ".join(saude) + ".")

    if origem == "compact":
        linhas.append("A conversa foi compactada; o estado acima foi lido do disco agora.")
    if pend_compact:
        linhas.append("Antes da compactação havia registro pendente: " + pend_compact)

    L.emitir(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(linhas),
            }
        }
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # nunca derrubar a sessão
        L.emitir({"systemMessage": f"harness: session_start falhou ({exc.__class__.__name__})"})

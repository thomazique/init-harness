"""Executa tarefas delegadas nos CLIs configurados, sem persistir prompts ou respostas."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ler_config(raiz: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    caminho = raiz / ".init-harness" / "orquestracao.json"
    caminho_geral = raiz / ".init-harness" / "config.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        geral = json.loads(caminho_geral.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"não foi possível ler {caminho}: {exc}") from exc
    if not isinstance(dados, dict) or not isinstance(dados.get("perfis"), list) or not isinstance(geral, dict):
        raise ValueError("orquestracao.json precisa conter uma lista 'perfis'")
    return dados, geral


def obter_perfil(config: dict[str, Any], identificador: str) -> dict[str, Any]:
    encontrados = [p for p in config["perfis"] if isinstance(p, dict) and p.get("id") == identificador]
    if len(encontrados) != 1:
        raise ValueError(f"perfil '{identificador}' ausente ou duplicado em .init-harness/orquestracao.json")
    return encontrados[0]


def reservar_chamadas(
    raiz: Path,
    frente: str,
    perfil: str,
    papel: str,
    agente: dict[str, Any],
    quantidade: int,
    limite: int,
) -> None:
    banco = raiz / ".init-harness" / "state" / "orquestracao.sqlite3"
    banco.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(banco, timeout=10) as conexao:
        conexao.execute("PRAGMA busy_timeout = 10000")
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS chamadas ("
            "frente TEXT NOT NULL, sequencia INTEGER NOT NULL, perfil TEXT NOT NULL, "
            "papel TEXT NOT NULL, provedor TEXT NOT NULL, modelo TEXT NOT NULL, "
            "criado_em TEXT NOT NULL, PRIMARY KEY (frente, sequencia))"
        )
        conexao.execute("BEGIN IMMEDIATE")
        anteriores = conexao.execute(
            "SELECT COUNT(*), MIN(perfil) FROM chamadas WHERE frente = ?", (frente,)
        ).fetchone()
        atual = anteriores[0]
        if anteriores[1] is not None and anteriores[1] != perfil:
            raise ValueError("a frente já iniciou chamadas com outro perfil; mantenha um perfil por atividade")
        papel_anterior = conexao.execute(
            "SELECT COUNT(*), MIN(provedor), MIN(modelo) FROM chamadas "
            "WHERE frente = ? AND papel = ?",
            (frente, papel),
        ).fetchone()
        if papel_anterior[0] and (papel_anterior[1], papel_anterior[2]) != (agente["provedor"], agente["modelo"]):
            raise ValueError("o provedor/modelo deste papel mudou durante a atividade; mantenha a configuração inicial")
        if atual + quantidade > limite:
            raise ValueError(
                f"limite de {limite} chamadas CLI por atividade atingido; "
                "peça autorização para aumentar o limite no perfil"
            )
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conexao.executemany(
            "INSERT INTO chamadas (frente, sequencia, perfil, papel, provedor, modelo, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (frente, atual + indice + 1, perfil, papel, agente["provedor"], agente["modelo"], agora)
                for indice in range(quantidade)
            ],
        )
        conexao.commit()


def comando_para(provedor: str, agente: dict[str, Any]) -> list[str]:
    executavel = "claude" if provedor == "claude" else "codex"
    caminho_executavel = shutil.which(executavel)
    if not caminho_executavel:
        raise ValueError(f"CLI '{executavel}' não está disponível no PATH")
    modelo = agente["modelo"]
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", modelo):
        raise ValueError("o modelo precisa usar apenas letras ASCII, números, ponto, sublinhado, dois-pontos ou hífen")
    if provedor == "claude":
        papel = agente["_papel"]
        ferramentas = "Read,Glob,Grep" if papel == "auditor" else "Read,Edit,Write,Glob,Grep"
        modo = "plan" if papel == "auditor" else "acceptEdits"
        return [
            caminho_executavel,
            "-p",
            "--no-session-persistence",
            "Siga a tarefa delimitada recebida pela entrada padrão.",
            "--model",
            modelo,
            "--permission-mode",
            modo,
            "--tools",
            "Read,Glob,Grep" if papel == "auditor" else "Read,Edit,Write,Glob,Grep",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--disallowedTools",
            "mcp__*",
            "--allowedTools",
            ferramentas,
        ]

    sandbox = "read-only" if agente["_papel"] == "auditor" else "workspace-write"
    comando = [
        caminho_executavel,
        "exec",
        "--ephemeral",
        "--model",
        agente["modelo"],
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
        "--config",
        "mcp_servers={}",
    ]
    raciocinio = agente.get("raciocinio")
    if raciocinio:
        comando.extend(["--config", f'model_reasoning_effort="{raciocinio}"'])
    comando.append("-")
    return comando


async def executar_tarefa(
    tarefa: dict[str, Any], papel: str, agente: dict[str, Any], raiz: Path, timeout: int
) -> dict[str, Any]:
    comando = comando_para(agente["provedor"], {**agente, "_papel": papel})
    if papel == "executor":
        instrucoes = (
            "PAPEL INIT-HARNESS: Você é executor de uma subtarefa delimitada. "
            "Implemente somente os critérios e os arquivos autorizados abaixo. "
            "Não escolha perfil, não coordene nem delegue a outros agentes; não altere arquivos fora do escopo; "
            "não faça commit, push, merge, release ou deploy. "
            "Ao concluir, informe resultado, resumo, arquivos alterados, verificações, riscos e bloqueios.\n\n"
        )
    else:
        instrucoes = (
            "PAPEL INIT-HARNESS: Você é auditor independente, somente de leitura. "
            "Revise o diff agregado contra o pedido e os critérios abaixo. "
            "Não escolha perfil, não delegue e não altere arquivos. "
            "Responda APROVADA ou REPROVADA com achados arquivo:linha, escopo revisado e verificações observadas.\n\n"
        )
    prompt = instrucoes + tarefa["prompt"]
    processo = await asyncio.create_subprocess_exec(
        *comando,
        cwd=raiz,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        saida, erro = await asyncio.wait_for(processo.communicate(prompt.encode("utf-8")), timeout=timeout)
    except asyncio.TimeoutError:
        processo.kill()
        await processo.wait()
        return {
            "id": tarefa["id"],
            "resultado": "timeout",
            "provedor": agente["provedor"],
            "modelo": agente["modelo"],
            "saida": "",
            "erro": f"tempo limite de {timeout} segundos excedido",
        }
    return {
        "id": tarefa["id"],
        "resultado": "concluido" if processo.returncode == 0 else "falha",
        "provedor": agente["provedor"],
        "modelo": agente["modelo"],
        "saida": saida.decode("utf-8", errors="replace"),
        "erro": erro.decode("utf-8", errors="replace"),
        "codigo_saida": processo.returncode,
    }


async def executar_lote(raiz: Path, lote: dict[str, Any]) -> dict[str, Any]:
    config, config_geral = ler_config(raiz)
    perfil_id = lote.get("perfil")
    frente = lote.get("frente_id")
    papel = lote.get("papel")
    tarefas = lote.get("tarefas")
    frente_valida = isinstance(frente, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,99}", frente)
    if not isinstance(perfil_id, str) or not frente_valida:
        raise ValueError("informe 'perfil' e 'frente_id' válido no arquivo de lote")
    if papel not in {"executor", "auditor"}:
        raise ValueError("'papel' deve ser 'executor' ou 'auditor'")
    if not isinstance(tarefas, list) or not tarefas or any(
        not isinstance(tarefa, dict)
        or not isinstance(tarefa.get("id"), str)
        or not isinstance(tarefa.get("prompt"), str)
        or not tarefa["prompt"].strip()
        for tarefa in tarefas
    ):
        raise ValueError("'tarefas' deve conter objetos com 'id' e 'prompt' não vazios")
    if len({tarefa["id"] for tarefa in tarefas}) != len(tarefas):
        raise ValueError("cada tarefa do lote precisa de um id único")
    if papel == "auditor" and len(tarefas) != 1:
        raise ValueError("o auditor recebe uma única tarefa com o diff agregado")

    perfil = obter_perfil(config, perfil_id)
    agente = perfil.get(papel)
    if not isinstance(agente, dict) or agente.get("modo") != "cli":
        raise ValueError(f"o perfil '{perfil_id}' não configura o papel '{papel}' em modo cli")
    if agente.get("provedor") not in {"claude", "codex"} or not isinstance(agente.get("modelo"), str):
        raise ValueError(f"configuração inválida para papel '{papel}' no perfil '{perfil_id}'")
    executavel = "claude" if agente["provedor"] == "claude" else "codex"
    if not shutil.which(executavel):
        raise ValueError(f"CLI '{executavel}' não está disponível no PATH")

    max_executores = (config_geral.get("orquestracao") or {}).get("limite_executores", 1)
    max_chamadas = config.get("limite_chamadas_cli_por_atividade", 1)
    timeout = config.get("timeout_segundos", 1800)
    if any(not isinstance(valor, int) or valor < 1 for valor in (max_executores, max_chamadas, timeout)):
        raise ValueError("limites e timeout em orquestracao.json precisam ser inteiros positivos")
    concorrencia = min(max_executores, len(tarefas))
    reservar_chamadas(raiz, frente, perfil_id, papel, agente, len(tarefas), max_chamadas)

    semaforo = asyncio.Semaphore(concorrencia)

    async def protegida(tarefa: dict[str, Any]) -> dict[str, Any]:
        async with semaforo:
            try:
                return await executar_tarefa(tarefa, papel, agente, raiz, timeout)
            except OSError as exc:
                return {
                    "id": tarefa["id"],
                    "resultado": "falha",
                    "provedor": agente["provedor"],
                    "modelo": agente["modelo"],
                    "saida": "",
                    "erro": str(exc),
                }

    resultados = await asyncio.gather(*(protegida(tarefa) for tarefa in tarefas))
    return {
        "frente_id": frente,
        "perfil": perfil_id,
        "papel": papel,
        "concorrencia_usada": concorrencia,
        "resultados": resultados,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="raiz do projeto instalado")
    parser.add_argument("--lote", type=Path, required=True, help="JSON de tarefas e prompts; não é copiado ao log")
    parser.add_argument("--remover-lote", action="store_true", help="apaga o lote temporário depois de carregá-lo")
    args = parser.parse_args()
    raiz = args.root.resolve()
    caminho_lote = args.lote.resolve()
    try:
        lote = json.loads(caminho_lote.read_text(encoding="utf-8"))
        if args.remover_lote:
            temporarios = (raiz / ".init-harness" / "state" / "orquestracao").resolve()
            if not caminho_lote.is_relative_to(temporarios):
                raise ValueError("--remover-lote só pode apagar arquivos dentro de .init-harness/state/orquestracao/")
            caminho_lote.unlink(missing_ok=True)
        if not isinstance(lote, dict):
            raise ValueError("o arquivo de lote precisa conter um objeto JSON")
        resultado = asyncio.run(executar_lote(raiz, lote))
    except (OSError, json.JSONDecodeError, ValueError, sqlite3.Error) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if all(item["resultado"] == "concluido" for item in resultado["resultados"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

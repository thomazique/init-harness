"""Classificador opcional Jev para reordenar candidatos locais do FTS5."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import _lib as L

ENDPOINT = "https://jevmodel.org/v1/systemone"
MAX_CANDIDATES = 8
MAX_SNIPPET_CHARS = 420
MAX_STATE_CHARS = 8_000
TIMEOUT_SECONDS = 8
MIN_CONFIDENCE = 0.35
MIN_DECISION_CONFIDENCE = 0.60
SCORE_CRITERIA = ["irrelevante", "pouco relevante", "parcialmente relevante", "relevante", "diretamente útil"]
ROUTE_QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "Classifique a intenção operacional principal desta solicitação.",
        "criteria": {
            "research": "Pesquisar ou explicar sem alterar o projeto",
            "plan": "Planejar ou especificar trabalho futuro",
            "implement_single": "Implementar uma frente principal",
            "implement_parallel": "Implementar frentes independentes que exigem coordenação",
            "review": "Revisar ou auditar trabalho existente",
            "maintenance": "Diagnosticar, corrigir ou manter o harness/projeto",
        },
    },
    "specialty": {
        "type": "choice",
        "instructions": "Escolha a especialidade predominante para o primeiro supervisor.",
        "criteria": {
            "frontend": "Interface, acessibilidade, experiência e apresentação",
            "backend": "APIs, lógica, arquitetura e serviços",
            "security": "Segurança, ameaças, segredos e controles",
            "deploy_cicd": "Infraestrutura, implantação, CI e publicação",
            "database": "Modelo, consultas, migrações e desempenho de dados",
            "mixed": "Duas ou mais especialidades são igualmente centrais",
            "general": "Documentação, análise ou trabalho sem domínio técnico predominante",
        },
    },
    "needs_clarification": {
        "type": "noul",
        "instructions": "A solicitação contém ambiguidade material que exige resposta humana antes do planejamento?",
    },
    "risk": {
        "type": "score",
        "instructions": "Avalie risco operacional, de segurança ou de perda de dados desta solicitação.",
        "criteria": ["mínimo", "baixo", "moderado", "alto", "crítico"],
    },
}
GATE_QUESTIONS = {
    "decision": {
        "type": "choice",
        "instructions": "Qual deve ser a próxima ação do orquestrador com base neste relatório de fase?",
        "criteria": {
            "continue": "Evidências e contratos permitem avançar à próxima fase",
            "targeted_review": "Há uma lacuna corrigível que deve voltar ao supervisor ou construtor responsável",
            "ask_human": "Existe ambiguidade, conflito ou decisão de produto que exige o humano",
        },
    },
    "confidence": {
        "type": "score",
        "instructions": "Quão bem o relatório sustenta a decisão de próxima etapa?",
        "criteria": ["sem evidência", "fraca", "parcial", "forte", "muito forte"],
    },
}


def enabled(root: Path) -> bool:
    """A decisão opt-in fica na configuração do projeto, nunca é inferida da presença da chave."""
    config = L.harness(root) or {}
    return bool((config.get("jev") or {}).get("enabled", False))


def api_key(root: Path) -> str:
    """Lê apenas a chave do processo ou do .env local; nunca a devolve a mensagens/logs."""
    key = os.environ.get("JEVMODEL_API_KEY", "").strip()
    if key:
        return key
    return L.ler_dotenv(root / ".env").get("JEVMODEL_API_KEY", "").strip()


def status(root: Path) -> str:
    if not enabled(root):
        return "FTS5 (Jev desativado)"
    if not api_key(root):
        return "FTS5 (JEVMODEL_API_KEY ausente)"
    return "Jev habilitado; consulta usará FTS5 + reranking remoto"


def _request(root: Path, query: str, candidates: list[tuple[str, str, str]]) -> list[tuple[str, str, str]] | None:
    key = api_key(root)
    if not key or not candidates:
        return None
    if any(L.segredos(query)):
        return None

    safe_candidates = [candidate for candidate in candidates if not any(L.segredos(candidate[2]))]
    selected = safe_candidates[:MAX_CANDIDATES]
    if not selected:
        return None
    state = {
        "query": query[:1_200],
        "candidates": [
            {"id": f"passage_{index}", "path": path, "kind": kind, "text": snippet[:MAX_SNIPPET_CHARS]}
            for index, (path, kind, snippet) in enumerate(selected)
        ],
    }
    questions = {
        f"passage_{index}": {
            "type": "score",
            "instructions": (
                f"Avalie a relevância do trecho passage_{index} para responder à consulta. "
                "Considere correspondência direta, contexto de projeto e utilidade factual."
            ),
            "criteria": SCORE_CRITERIA,
        }
        for index in range(len(selected))
    }
    body = json.dumps({"model": "jev-latest", "state": state, "questions": questions}, ensure_ascii=False).encode(
        "utf-8"
    )
    if len(body) > MAX_STATE_CHARS:
        return None

    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return None

    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return None
    ranked: list[tuple[float, int, tuple[str, str, str]]] = []
    for index, candidate in enumerate(selected):
        answer = answers.get(f"passage_{index}")
        if not isinstance(answer, dict):
            return None
        try:
            score = float(answer["score"])
            confidence = float(answer["confidence"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (1 <= score <= len(SCORE_CRITERIA)) or not (0 <= confidence <= 1) or confidence < MIN_CONFIDENCE:
            return None
        ranked.append((score, -index, candidate))

    ranked.sort(reverse=True)
    selected_paths = {item[2][0] for item in ranked}
    return [item[2] for item in ranked] + [candidate for candidate in candidates if candidate[0] not in selected_paths]


def _decide(root: Path, state: dict[str, Any], questions: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    key = api_key(root)
    if not enabled(root):
        return None, "Jev desativado"
    if not key:
        return None, "JEVMODEL_API_KEY ausente"
    try:
        state_text = json.dumps(state, ensure_ascii=False)
        if any(L.segredos(state_text)):
            return None, "estado contém padrão de segredo; não enviado"
        body = json.dumps({"model": "jev-latest", "state": state, "questions": questions}, ensure_ascii=False).encode(
            "utf-8"
        )
        if len(body) > MAX_STATE_CHARS:
            return None, "estado excede o limite local"
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None, "Jev indisponível ou resposta inválida"
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return None, "resposta Jev sem answers"
    return answers, "Jev"


def classify_task(root: Path, state: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Classifica uma síntese preparada pelo chefe; nenhuma resposta vira despacho automático."""
    answers, result_status = _decide(root, state, ROUTE_QUESTIONS)
    if not answers:
        return None, result_status
    try:
        intent = answers["intent"]
        specialty = answers["specialty"]
        ambiguity = answers["needs_clarification"]
        risk = answers["risk"]
        if intent.get("choice") not in ROUTE_QUESTIONS["intent"]["criteria"]:
            raise ValueError
        if specialty.get("choice") not in ROUTE_QUESTIONS["specialty"]["criteria"]:
            raise ValueError
        confidence = min(float(intent["confidence"]), float(specialty["confidence"]), float(risk["confidence"]))
        risk_score = float(risk["score"])
        ambiguity_probability = float(ambiguity["noul"])
        if not (0 <= confidence <= 1 and 1 <= risk_score <= 5 and 0 <= ambiguity_probability <= 1):
            raise ValueError
    except (KeyError, AttributeError, TypeError, ValueError):
        return None, "resposta de triagem inconclusiva"
    if confidence < MIN_DECISION_CONFIDENCE:
        return None, "confiança de triagem abaixo do limite"
    return {
        "intent": intent["choice"],
        "specialty": specialty["choice"],
        "needs_clarification_probability": ambiguity_probability,
        "risk_score": risk_score,
        "confidence": confidence,
    }, result_status


def classify_gate(root: Path, phase: str, state: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Propõe continuar, revisar ou perguntar; o chefe valida o gate com as evidências reais."""
    answers, result_status = _decide(root, {"phase": phase, "report": state}, GATE_QUESTIONS)
    if not answers:
        return None, result_status
    try:
        decision = answers["decision"]
        confidence = float(decision["confidence"])
        score = float(answers["confidence"]["score"])
        if decision.get("choice") not in GATE_QUESTIONS["decision"]["criteria"]:
            raise ValueError
        if not (0 <= confidence <= 1 and 1 <= score <= 5) or confidence < MIN_DECISION_CONFIDENCE:
            raise ValueError
    except (KeyError, AttributeError, TypeError, ValueError):
        return None, "resposta do gate inconclusiva"
    return {"decision": decision["choice"], "confidence": confidence, "evidence_score": score}, result_status


def rerank(root: Path, query: str, candidates: list[tuple[str, str, str]]) -> tuple[list[tuple[str, str, str]], str]:
    """Reordena até oito candidatos em uma chamada; qualquer falha mantém integralmente a ordem FTS5."""
    if not enabled(root):
        return candidates, "FTS5 (Jev desativado)"
    if not api_key(root):
        return candidates, "FTS5 (JEVMODEL_API_KEY ausente)"
    try:
        ranked = _request(root, query, candidates)
    except Exception:
        ranked = None
    if ranked is None:
        return candidates, "FTS5 (fallback: Jev indisponível ou resposta inconclusiva)"
    return ranked, "Jev + FTS5"

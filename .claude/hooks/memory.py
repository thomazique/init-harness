"""Memoria local do init-harness: Markdown canônico + índice SQLite FTS5.

O índice nunca é fonte de verdade: pode ser removido e recriado a partir de
``docs/ai/``, ``specs/`` e dos documentos de instrução do projeto.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import _lib as L

INDEX_RELATIVE = Path(".init-harness") / "memory" / "index.sqlite"
WORK_GRAPH_RELATIVE = Path(".init-harness") / "memory" / "work-graph.json"
HANDOFFS_RELATIVE = Path("docs") / "ai" / "memoria" / "handoffs"
BOOTSTRAP_FEEDBACK_RELATIVE = Path("docs") / "ai" / "memoria" / "feedback-bootstrap.md"
RELATIONSHIP_FEEDBACK_RELATIVE = Path("docs") / "ai" / "memoria" / "feedback-sugestoes.md"
MAX_HANDOFF_FIELD = 2_000

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory in (root / "docs" / "ai", root / "specs"):
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*.md") if path.is_file())
    files.extend(
        path for path in (root / name for name in ("CLAUDE.md", "INIT-HARNESS.md", "AGENTS.md")) if path.is_file()
    )
    return sorted(set(files))


def _title(path: Path, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ")


def _kind(relative: str) -> str:
    relative = relative.replace("\\", "/")
    if relative.startswith("docs/ai/memoria/handoffs/"):
        return "handoff"
    if relative.startswith("docs/ai/frentes/"):
        return "frente"
    if relative.startswith("specs/"):
        return "spec"
    if relative.endswith("DECISOES.md"):
        return "decisao"
    if relative.endswith("DEBITOS.md"):
        return "debito"
    return "contexto"


def _references(value: str) -> list[str]:
    """Lê referências planas separadas por vírgula; ``-`` significa ausência."""
    return [item.strip() for item in value.split(",") if item.strip() and item.strip() != "-"]


def _frontmatter_list(text: str, field: str) -> list[str]:
    """Lê uma lista YAML simples do frontmatter sem depender de PyYAML."""
    match = re.search(rf"(?ms)^---\s*$.*?^{re.escape(field)}:\s*$\n((?:[ \t]+-\s*.+\n?)*)", text)
    if not match:
        return []
    values = []
    for line in match.group(1).splitlines():
        item = re.match(r"^\s+-\s+(.+)$", line)
        if item:
            values.append(item.group(1).strip())
    return values


def _add_node(nodes: dict[str, dict[str, str]], node_id: str, kind: str, **data: str) -> None:
    node = nodes.setdefault(node_id, {"id": node_id, "kind": kind})
    node.update({key: value for key, value in data.items() if value and value != "?"})


def _add_edge(edges: list[dict[str, str]], source: str, target: str, kind: str, origin: str = "explicita") -> None:
    edge = {"from": source, "to": target, "kind": kind, "origin": origin}
    if edge not in edges:
        edges.append(edge)


def _connect(root: Path) -> sqlite3.Connection:
    path = root / INDEX_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS pages ("
        "path TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, "
        "body TEXT NOT NULL, updated_at INTEGER NOT NULL)"
    )
    connection.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts "
        "USING fts5(path UNINDEXED, title, body, "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS handoffs ("
        "path TEXT PRIMARY KEY, status TEXT NOT NULL, branch TEXT NOT NULL, "
        "created_at TEXT, created_by TEXT, accepted_at TEXT, accepted_by TEXT)"
    )
    return connection


def _handoff_rows(root: Path) -> list[tuple[str, str, str, str, str, str | None, str | None]]:
    directory = root / HANDOFFS_RELATIVE
    if not directory.is_dir():
        return []
    rows = []
    for path in directory.glob("*.md"):
        frontmatter = L.frontmatter(path)
        status = frontmatter.get("status")
        branch = frontmatter.get("branch")
        if status in {"aberto", "aceito"} and branch:
            rows.append(
                (
                    path.relative_to(root).as_posix(),
                    status,
                    branch,
                    frontmatter.get("criado_em", ""),
                    frontmatter.get("criado_por", ""),
                    frontmatter.get("aceito_em"),
                    frontmatter.get("aceito_por"),
                )
            )
    return rows


def index(root: Path) -> int:
    """Sincroniza incrementalmente o índice a partir do conteúdo canônico."""
    paths = _markdown_files(root)
    metadata = {path.relative_to(root).as_posix(): path.stat().st_mtime_ns for path in paths}
    with _connect(root) as connection:
        existing = dict(connection.execute("SELECT path, updated_at FROM pages"))
        deleted = set(existing) - set(metadata)
        changed = [
            path
            for path in paths
            if existing.get(path.relative_to(root).as_posix()) != metadata[path.relative_to(root).as_posix()]
        ]
        for relative in deleted:
            connection.execute("DELETE FROM pages WHERE path = ?", (relative,))
            connection.execute("DELETE FROM pages_fts WHERE path = ?", (relative,))
        for path in changed:
            text = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(root).as_posix()
            connection.execute("DELETE FROM pages WHERE path = ?", (relative,))
            connection.execute("DELETE FROM pages_fts WHERE path = ?", (relative,))
            connection.execute(
                "INSERT INTO pages(path, title, kind, body, updated_at) VALUES (?, ?, ?, ?, ?)",
                (relative, _title(path, text), _kind(relative), text, metadata[relative]),
            )
            connection.execute(
                "INSERT INTO pages_fts(path, title, body) VALUES (?, ?, ?)", (relative, _title(path, text), text)
            )
        handoffs = _handoff_rows(root)
        source_paths = {row[0] for row in handoffs}
        for (relative,) in connection.execute("SELECT path FROM handoffs").fetchall():
            if relative not in source_paths:
                connection.execute("DELETE FROM handoffs WHERE path = ?", (relative,))
        connection.executemany(
            "INSERT INTO handoffs(path, status, branch, created_at, created_by, accepted_at, accepted_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET status=excluded.status, branch=excluded.branch, "
            "created_at=excluded.created_at, created_by=excluded.created_by, "
            "accepted_at=excluded.accepted_at, accepted_by=excluded.accepted_by",
            handoffs,
        )
    return len(paths)


def _fts_terms(query: str) -> str:
    terms = re.findall(r"[\wÀ-ÿ-]+", query, flags=re.UNICODE)
    return " AND ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:12])


def search(root: Path, query: str, limit: int = 8) -> list[tuple[str, str, str]]:
    index(root)
    terms = _fts_terms(query)
    if not terms:
        return []
    with _connect(root) as connection:
        rows = connection.execute(
            "SELECT pages.path, pages.kind, snippet(pages_fts, 2, '[', ']', '…', 18) "
            "FROM pages_fts JOIN pages ON pages.path = pages_fts.path "
            "WHERE pages_fts MATCH ? ORDER BY bm25(pages_fts) LIMIT ?",
            (terms, max(1, min(limit, 30))),
        ).fetchall()
    return [(str(path), str(kind), str(snippet).replace("\n", " ")) for path, kind, snippet in rows]


def graph_freshness(root: Path) -> tuple[str, list[str]]:
    """Classifica a atualidade do Graphify sem atualizá-lo nem supor que um grafo é atual."""
    graph_path = root / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return "ausente", ["Grafo de código: graphify-out/graph.json ausente.", "Ação sugerida: execute `graphify .`."]
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "ilegivel", ["Grafo de código: graph.json não pôde ser lido.", "Ação sugerida: execute `graphify .`."]
    built_at = str(graph.get("built_at_commit") or "")
    head = L.git(["rev-parse", "HEAD"], root)
    if not head:
        return "desconhecido", ["Grafo de código: não foi possível determinar o HEAD para verificar frescor."]
    if built_at and built_at == head:
        return "atual", ["Grafo de código: no mesmo commit do HEAD."]
    if not built_at:
        return "desconhecido", [
            "Grafo de código: built_at_commit ausente; o frescor não pode ser confirmado.",
            "Ação sugerida: execute `graphify update .` (ou `graphify .` se for o primeiro grafo).",
        ]
    changed = L.git(["diff", "--name-only", f"{built_at}..{head}"], root).splitlines()
    detail = (
        f"{len(changed)} arquivo(s) mudaram desde o commit do grafo."
        if changed
        else "o delta Git não pôde ser calculado."
    )
    return "desatualizado", [
        f"Grafo de código: desatualizado em relação ao HEAD; {detail}",
        "Ação sugerida: execute `graphify update .`.",
    ]


def graph_status(root: Path) -> list[str]:
    """Relata estado e próximo comando do Graphify, sem rodá-lo automaticamente."""
    state, details = graph_freshness(root)
    return [f"Estado do Graphify: {state}.", *details]


def hybrid_recovery(root: Path, query: str, limit: int = 8) -> list[str]:
    """Recupera contexto por FTS canônico e correspondências explícitas no grafo de código."""
    rows = search(root, query, limit)
    lines = ["Recuperação híbrida: FTS canônico + correspondências textuais confirmadas no Graphify."]
    if rows:
        lines.append("Documentos FTS:")
        lines.extend(f"- {path} [{kind}] {snippet}" for path, kind, snippet in rows)
    else:
        lines.append("Documentos FTS: nenhum resultado.")
    state, freshness = graph_freshness(root)
    lines.extend(freshness)
    graph_path = root / "graphify-out" / "graph.json"
    if state in {"ausente", "ilegivel"}:
        return lines
    try:
        nodes = json.loads(graph_path.read_text(encoding="utf-8")).get("nodes") or []
    except (OSError, ValueError):
        return lines
    tokens = [token.casefold() for token in re.findall(r"[\wÀ-ÿ-]+", query, flags=re.UNICODE) if len(token) > 1]
    matches = []
    for node in nodes:
        value = " ".join(str(node.get(key) or "") for key in ("id", "label", "norm_label", "source_file")).casefold()
        if tokens and all(token in value for token in tokens):
            matches.append(node)
    if matches:
        lines.append("Nós Graphify correspondentes:")
        for node in matches[:limit]:
            source_file = str(node.get("source_file") or "").replace("\\", "/")
            suffix = f" ({source_file})" if source_file else ""
            lines.append("- " + str(node.get("label") or node.get("id")) + suffix)
    else:
        lines.append("Nós Graphify correspondentes: nenhum; não foi inferida equivalência semântica.")
    return lines


def _open_handoffs(root: Path, branch: str) -> list[Path]:
    with _connect(root) as connection:
        rows = connection.execute(
            "SELECT path FROM handoffs WHERE status = 'aberto' AND branch IN (?, '*') ORDER BY created_at DESC",
            (branch,),
        ).fetchall()
    return [root / path for (path,) in rows]


def _spec_paths(root: Path, front: str, frontmatter: dict[str, str]) -> list[Path]:
    """Combina a relação declarada pela frente com a declarada pela spec."""
    paths = {root / reference for reference in _references(frontmatter.get("specs", ""))}
    for path in _markdown_files(root):
        if path.relative_to(root).as_posix().startswith("specs/") and L.frontmatter(path).get("frente") == front:
            paths.add(path)
    return sorted(path for path in paths if path.is_file())


def _checkpoint_summary(path: Path) -> str:
    rows = []
    for line in L.secao(path, "Checkpoints").splitlines():
        if line.strip().startswith("|") and "---" not in line and "Checkpoint" not in line:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[-1] != "feito":
                rows.append(f"{cells[0]} {cells[1]} ({cells[-1]})")
    return "; ".join(rows[:4]) or "nenhum pendente registrado"


def _graph_context(root: Path, files: set[str], targets: set[str]) -> list[str]:
    """Conecta alvos declarados ao grafo de código sem inferir equivalências."""
    graph_path = root / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return ["Grafo de código: graphify-out/graph.json ausente."]
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Grafo de código: graph.json não pôde ser lido."]
    commit = L.git(["rev-parse", "HEAD"], root)
    built_at = str(graph.get("built_at_commit") or "")
    freshness = (
        "no mesmo commit do HEAD" if built_at and built_at == commit else "pode estar desatualizado em relação ao HEAD"
    )
    nodes = graph.get("nodes") or []
    matched = []
    for node in nodes:
        source_file = str(node.get("source_file") or "").replace("\\", "/")
        values = {str(node.get(key) or "").casefold() for key in ("id", "label", "norm_label")}
        if source_file in files or any(target.casefold() in values for target in targets):
            matched.append(node)
    matched_ids = {str(node.get("id")) for node in matched}
    labels = [str(node.get("label") or node.get("id")) for node in matched[:8]]
    lines = [f"Grafo de código: {freshness}; {len(matched)} nó(s) correspondente(s)."]
    if labels:
        lines.append("Nós confirmados: " + ", ".join(labels) + ".")
    elif files or targets:
        lines.append("Sem correspondência exata para os arquivos/alvos declarados.")
    neighbors: list[str] = []
    labels_by_id = {str(node.get("id")): str(node.get("label") or node.get("id")) for node in nodes}
    for edge in graph.get("links") or []:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in matched_ids and target not in matched_ids:
            neighbors.append(labels_by_id.get(target, target))
        if target in matched_ids and source not in matched_ids:
            neighbors.append(labels_by_id.get(source, source))
    if neighbors:
        lines.append("Vizinhança arquitetural: " + ", ".join(sorted(set(neighbors))[:8]) + ".")
    return lines


def graph_impact(root: Path, branch: str, depth: int = 2) -> list[str]:
    """Expande alvos declarados pelas arestas existentes no Graphify, até uma profundidade limitada."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return [f"Impacto: nenhuma frente única para a branch {branch}."]
    front_path, frontmatter = current
    front = front_path.relative_to(root).as_posix()
    files = set(_references(frontmatter.get("files", "")))
    targets: set[str] = set()
    for spec in _spec_paths(root, front, frontmatter):
        text = spec.read_text(encoding="utf-8", errors="replace")
        files.update(_frontmatter_list(text, "files"))
        targets.update(_frontmatter_list(text, "target_nodes"))
    graph_path = root / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return ["Impacto: graphify-out/graph.json ausente."]
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Impacto: graph.json não pôde ser lido."]
    nodes = {str(node.get("id")): node for node in graph.get("nodes") or [] if node.get("id") is not None}
    roots: set[str] = set()
    for node_id, node in nodes.items():
        source_file = str(node.get("source_file") or "").replace("\\", "/")
        values = {str(node.get(key) or "").casefold() for key in ("id", "label", "norm_label")}
        if source_file in files or any(target.casefold() in values for target in targets):
            roots.add(node_id)
    if not roots:
        return ["Impacto: nenhum arquivo ou alvo declarado corresponde a um nó do Graphify."]
    adjacency: dict[str, list[tuple[str, str]]] = {node_id: [] for node_id in nodes}
    for edge in graph.get("links") or []:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in nodes and target in nodes:
            relation = str(edge.get("relation") or "relaciona")
            adjacency[source].append((target, relation))
            adjacency[target].append((source, relation))
    max_depth = max(1, min(int(depth), 4))
    distance = {node_id: 0 for node_id in roots}
    queue = list(roots)
    paths: list[tuple[str, str, str]] = []
    while queue:
        node_id = queue.pop(0)
        if distance[node_id] >= max_depth:
            continue
        for neighbor, relation in adjacency.get(node_id, []):
            if neighbor in distance:
                continue
            distance[neighbor] = distance[node_id] + 1
            queue.append(neighbor)
            paths.append((node_id, relation, neighbor))
    impacted = [nodes[node_id] for node_id in distance]

    def label(node: dict) -> str:
        return str(node.get("label") or node.get("id"))

    root_communities = {node.get("community") for node_id, node in nodes.items() if node_id in roots}
    extra_communities = {node.get("community") for node in impacted} - root_communities - {None}
    extra_files = sorted(
        {
            str(node.get("source_file")).replace("\\", "/")
            for node in impacted
            if node.get("source_file") and str(node.get("source_file")).replace("\\", "/") not in files
        }
    )
    built_at = str(graph.get("built_at_commit") or "")
    freshness = (
        "no mesmo commit do HEAD"
        if built_at and built_at == L.git(["rev-parse", "HEAD"], root)
        else "pode estar desatualizado"
    )
    lines = [f"Impacto Graphify de {front} (profundidade {max_depth}; grafo {freshness})."]
    lines.append("Raízes confirmadas: " + ", ".join(label(nodes[node_id]) for node_id in sorted(roots)) + ".")
    lines.append(f"Alcance: {len(impacted)} nó(s), {len(extra_files)} arquivo(s) fora da superfície declarada.")
    if extra_files:
        lines.append("Arquivos alcançados fora da superfície: " + ", ".join(extra_files[:12]) + ".")
    if extra_communities:
        lines.append(
            "Comunidades adicionais no grafo: " + ", ".join(str(item) for item in sorted(extra_communities)) + "."
        )
    if paths:
        examples = [
            f"{label(nodes[source])} --{relation}-> {label(nodes[target])}" for source, relation, target in paths[:8]
        ]
        lines.append("Conexões confirmadas: " + "; ".join(examples) + ".")
    return lines


def critical_briefing(root: Path, branch: str) -> list[str]:
    """Síntese factual e curta da frente atual, dos artefatos e do código afetado."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return [f"Contexto crítico: nenhuma frente única para a branch {branch}."]
    front_path, frontmatter = current
    front = front_path.relative_to(root).as_posix()
    lines = [f"Contexto crítico: {front} ({frontmatter.get('status', '?')})."]
    if frontmatter.get("objetivo"):
        lines.append("Objetivo: " + frontmatter["objetivo"])
    lines.append("Próximo passo: " + (L.secao(front_path, "Próximo passo") or "não registrado"))
    lines.append("Checkpoints pendentes: " + _checkpoint_summary(front_path) + ".")
    blocks = L.secao(front_path, "Bloqueios")
    if blocks and blocks.strip().casefold() not in {"- nenhum", "nenhum"}:
        lines.append("Bloqueios: " + " ".join(blocks.split()))
    for field, label in (
        ("depende_de", "Depende de"),
        ("bloqueia", "Bloqueia"),
        ("relaciona_com", "Coordena com"),
        ("decisoes", "Decisões"),
        ("debitos", "Débitos"),
    ):
        references = _references(frontmatter.get(field, ""))
        if references:
            lines.append(f"{label}: {', '.join(references)}.")
    files = set(_references(frontmatter.get("files", "")))
    targets: set[str] = set()
    specs = _spec_paths(root, front, frontmatter)
    if specs:
        summaries = []
        for spec in specs:
            text = spec.read_text(encoding="utf-8", errors="replace")
            metadata = L.frontmatter(spec)
            files.update(_frontmatter_list(text, "files"))
            targets.update(_frontmatter_list(text, "target_nodes"))
            risk_count = len(_frontmatter_list(text, "risks"))
            summaries.append(
                f"{spec.relative_to(root).as_posix()} ({metadata.get('status', '?')}, {risk_count} risco(s))"
            )
        lines.append("Specs: " + "; ".join(summaries) + ".")
    else:
        lines.append("Diagnóstico: nenhuma spec vinculada explicitamente à frente.")
    if files:
        lines.append("Arquivos declarados: " + ", ".join(sorted(files)) + ".")
    lines.extend(_graph_context(root, files, targets))
    if frontmatter.get("status") == "bloqueada" and not blocks:
        lines.append("Diagnóstico: frente bloqueada sem bloqueio descrito.")
    return lines


def _legacy_consolidation_proposal(root: Path, branch: str) -> list[str]:
    """Compara Git e artefatos da frente, sem alterar qualquer documento."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return [f"Consolidação: nenhuma frente única para a branch {branch}; nada foi alterado."]
    front_path, frontmatter = current
    front = front_path.relative_to(root).as_posix()
    changed = L.arquivos_alterados(root)
    code_files = sorted(path for path in changed if L.e_codigo(path))
    declared = set(_references(frontmatter.get("files", "")))
    for spec in _spec_paths(root, front, frontmatter):
        declared.update(_frontmatter_list(spec.read_text(encoding="utf-8", errors="replace"), "files"))
    code_files = sorted(code_files, key=lambda path: (path not in declared, path))
    lines = [f"Consolidação proposta para {front}: nenhum arquivo foi alterado."]
    if not code_files:
        return lines
    lines = [f"Consolidação proposta para {front}: nenhum arquivo foi alterado automaticamente."]
    lines.append(
        "Código alterado no Git: " + ", ".join(code_files[:20]) + (" e outros." if len(code_files) > 20 else ".")
    )
    lines.append("Checkpoint pendente a conferir: " + _checkpoint_summary(front_path) + ".")
    declared = set(_references(frontmatter.get("files", "")))
    for spec in _spec_paths(root, front, frontmatter):
        declared.update(_frontmatter_list(spec.read_text(encoding="utf-8", errors="replace"), "files"))
    outside = [path for path in code_files if path not in declared]
    if outside:
        lines.append(
            "Proposta: validar escopo antes de registrar; arquivos fora da superfície declarada: "
            + ", ".join(outside)
            + "."
        )
    else:
        lines.append(
            "Proposta: após verificação, registrar no checkpoint os arquivos cobertos e atualizar próximo passo."
        )
    if not _spec_paths(root, front, frontmatter):
        lines.append("Proposta: confirmar se a alteração continua trivial; não há spec vinculada.")
    return lines


def consolidation_items(root: Path, branch: str) -> list[dict[str, str]]:
    """Produz propostas estáveis de consolidação; não altera documentos."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return []
    front_path, frontmatter = current
    front = front_path.relative_to(root).as_posix()
    code_files = sorted(path for path in L.arquivos_alterados(root) if L.e_codigo(path))
    if not code_files:
        return []
    declared = _front_surface_files(root, front, frontmatter)
    outside = [path for path in code_files if path not in declared]
    kind = "validar_escopo" if outside else "registrar_checkpoint"
    files = outside or code_files
    details = (
        "validar arquivos fora da superfície declarada: " + ", ".join(files)
        if outside
        else "após verificação, registrar arquivos cobertos no checkpoint: " + ", ".join(files)
    )
    raw = "\0".join((front, kind, *files))
    items = [
        {
            "id": "C-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10],
            "front": front,
            "kind": kind,
            "details": details,
            "checkpoint": _checkpoint_summary(front_path),
        }
    ]
    if not _spec_paths(root, front, frontmatter):
        raw = "\0".join((front, "confirmar_trivialidade", *code_files))
        items.append(
            {
                "id": "C-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10],
                "front": front,
                "kind": "confirmar_trivialidade",
                "details": "confirmar se a alteração continua trivial; não há spec vinculada",
                "checkpoint": _checkpoint_summary(front_path),
            }
        )
    return items


def consolidation_proposal(root: Path, branch: str) -> list[str]:
    """Apresenta propostas de consolidação sem alterar qualquer documento."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return [f"Consolidação: nenhuma frente única para a branch {branch}; nada foi alterado."]
    front = current[0].relative_to(root).as_posix()
    items = consolidation_items(root, branch)
    if not items:
        return [f"Consolidação proposta para {front}: nenhum arquivo de código alterado."]
    code_files = sorted(path for path in L.arquivos_alterados(root) if L.e_codigo(path))
    lines = [f"Consolidação proposta para {front}: nenhum arquivo foi alterado automaticamente."]
    lines.append(
        "Código alterado no Git: " + ", ".join(code_files[:20]) + (" e outros." if len(code_files) > 20 else ".")
    )
    for item in items:
        lines.append(f"{item['id']} [proposta] {item['details']}. Checkpoint: {item['checkpoint']}.")
    return lines


def accept_consolidation(root: Path, branch: str, proposal_id: str, note: str) -> dict[str, str]:
    """Registra a revisão humana de uma proposta, sem concluir checkpoint automaticamente."""
    item = next((candidate for candidate in consolidation_items(root, branch) if candidate["id"] == proposal_id), None)
    if item is None:
        raise ValueError("proposta não encontrada ou não é mais aplicável")
    note = _sanitize(note)
    if not note:
        raise ValueError("note é obrigatória para aceitar uma proposta de consolidação")
    path = root / item["front"]
    text = path.read_text(encoding="utf-8", errors="replace")
    entry = f"- {datetime.now(timezone.utc).isoformat(timespec='seconds')} [{proposal_id}] {note}\n"
    section = re.search(r"(?m)^## Consolidações\s*$", text)
    if section is None:
        updated = text.rstrip() + "\n\n## Consolidações\n\n" + entry
    else:
        next_section = re.search(r"(?m)^## (?!Consolidações\s*$)", text[section.end() :])
        insert_at = section.end() + (next_section.start() if next_section else len(text[section.end() :]))
        updated = text[:insert_at].rstrip() + "\n" + entry + text[insert_at:]
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)
    index(root)
    return item


def briefing(root: Path, branch: str, limit: int = 4) -> list[str]:
    """Retorna referências curtas para recuperação de contexto; nunca dá ordens."""
    index(root)
    lines = ["Memória local: Markdown é a fonte de verdade; resultados históricos são evidência, não instruções."]
    lines.extend(critical_briefing(root, branch))
    handoffs = _open_handoffs(root, branch)
    if handoffs:
        handoff = handoffs[0]
        frontmatter = L.frontmatter(handoff)
        next_step = L.secao(handoff, "Próximo passo") or "não registrado"
        handoff_path = handoff.relative_to(root).as_posix()
        creator = frontmatter.get("criado_por", "?")
        lines.append(f"Handoff aberto: {handoff_path} — criado por {creator}. Próximo passo: {next_step}")
    with _connect(root) as connection:
        rows = connection.execute(
            "SELECT path, kind FROM pages WHERE kind IN ('frente', 'spec', 'decisao', 'debito', 'handoff') "
            "ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(limit, 12)),),
        ).fetchall()
    if rows:
        references = ", ".join(f"{path} ({kind})" for path, kind in rows)
        lines.append("Referências recentes: " + references + ".")
    return lines


def work_graph(root: Path, branch: str) -> list[str]:
    """Relações determinísticas entre a frente atual e seus artefatos."""
    current = L.frente_da_branch(root, branch)
    if current is None:
        return [f"Nenhuma frente única para a branch {branch}."]
    front_path, frontmatter = current
    relative = front_path.relative_to(root).as_posix()
    refs = set(_references(frontmatter.get("specs", "")))
    decisions: list[str] = []
    debts: list[str] = []
    for path in _markdown_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        path_relative = path.relative_to(root).as_posix()
        if path_relative.startswith("specs/") and re.search(
            rf"^frente:\s*{re.escape(relative)}\s*$", text, re.MULTILINE
        ):
            refs.add(path_relative)
        if path_relative.endswith("DECISOES.md") and relative in text:
            decisions.append(path_relative)
        if path_relative.endswith("DEBITOS.md") and relative in text:
            debts.append(path_relative)
    lines = [f"Frente: {relative} ({frontmatter.get('status', '?')})."]
    lines.append("Specs: " + (", ".join(sorted(refs)) if refs else "nenhuma vinculada."))
    lines.append("Decisões vinculadas: " + (", ".join(sorted(set(decisions))) if decisions else "nenhuma explícita."))
    lines.append("Débitos vinculados: " + (", ".join(sorted(set(debts))) if debts else "nenhum explícito."))
    return lines


def ready_fronts(root: Path) -> list[str]:
    """Aponta frentes abertas sem dependência explícita ainda em aberto."""
    fronts = {path.relative_to(root).as_posix(): frontmatter for path, frontmatter in L.frentes(root)}
    ready: list[str] = []
    waiting: list[str] = []
    for front, frontmatter in sorted(fronts.items()):
        if frontmatter.get("status") == "concluida":
            continue
        pending = [
            dependency
            for dependency in _references(frontmatter.get("depende_de", ""))
            if fronts.get(dependency, {}).get("status") != "concluida"
        ]
        if pending:
            waiting.append(f"{front} aguarda: {', '.join(pending)}.")
        else:
            ready.append(f"{front} ({frontmatter.get('status', '?')}).")
    lines = ["Frentes sem dependência explícita pendente:"]
    lines.extend(f"- {line}" for line in ready) if ready else lines.append("- nenhuma.")
    if waiting:
        lines.append("Dependências ainda abertas:")
        lines.extend(f"- {line}" for line in waiting)
    return lines


def _age_hours(value: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600


def _meaningful(value: str) -> bool:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(value and value.casefold() not in {"- nenhum", "nenhum", "não registrado"})


def operational_diagnostics(root: Path, category: str) -> list[str]:
    """Diagnósticos operacionais factuais; não mudam estado e não exigem metadados opcionais."""
    fronts = [(path.relative_to(root).as_posix(), path, metadata) for path, metadata in L.frentes(root)]
    open_fronts = [
        (relative, path, metadata) for relative, path, metadata in fronts if metadata.get("status") != "concluida"
    ]
    by_path = {relative: metadata for relative, _, metadata in fronts}
    lines: list[str] = []
    if category == "blocked":
        for relative, path, metadata in open_fronts:
            blocks = L.secao(path, "Bloqueios")
            if metadata.get("status") == "bloqueada":
                detail = "sem bloqueio descrito" if not _meaningful(blocks) else "bloqueio: " + " ".join(blocks.split())
                lines.append(f"{relative}: {detail}.")
            pending = [
                dependency
                for dependency in _references(metadata.get("depende_de", ""))
                if by_path.get(dependency, {}).get("status") != "concluida"
            ]
            if pending:
                lines.append(f"{relative}: depende de frente(s) ainda aberta(s): {', '.join(pending)}.")
    elif category == "stale":
        limit = (L.harness(root) or {}).get("frente_inativa_horas")
        if limit is None:
            return [
                "Inatividade: frente_inativa_horas não está configurado; nenhuma frente foi classificada como inativa."
            ]
        for relative, _, metadata in open_fronts:
            if metadata.get("status") != "ativa":
                continue
            age = _age_hours(metadata.get("atualizado_em", ""))
            if age is None:
                lines.append(f"{relative}: atualizado_em ausente ou inválido.")
            elif age >= float(limit):
                lines.append(f"{relative}: inativa há {age:.0f}h (limite: {limit}h).")
    elif category == "risk":
        for relative, _, metadata in open_fronts:
            specs = _spec_paths(root, relative, metadata)
            for spec in specs:
                risks = _frontmatter_list(spec.read_text(encoding="utf-8", errors="replace"), "risks")
                if risks:
                    lines.append(f"{relative}: {spec.relative_to(root).as_posix()} declara {len(risks)} risco(s).")
            debts = _references(metadata.get("debitos", ""))
            if debts:
                lines.append(f"{relative}: débitos associados: {', '.join(debts)}.")
        graph = root / "graphify-out" / "graph.json"
        if graph.is_file():
            try:
                built_at = str(json.loads(graph.read_text(encoding="utf-8")).get("built_at_commit") or "")
            except (OSError, ValueError):
                built_at = ""
            if not built_at or built_at != L.git(["rev-parse", "HEAD"], root):
                lines.append("Grafo de código pode estar desatualizado em relação ao HEAD.")
    elif category == "gaps":
        required = ("status", "dono", "atualizado_em", "branch", "objetivo")
        for relative, path, metadata in open_fronts:
            missing = [field for field in required if not _meaningful(metadata.get(field, ""))]
            if missing:
                lines.append(f"{relative}: campos obrigatórios ausentes: {', '.join(missing)}.")
            if not _meaningful(L.secao(path, "Próximo passo")):
                lines.append(f"{relative}: próximo passo ausente.")
            if metadata.get("status") == "bloqueada" and not _meaningful(L.secao(path, "Bloqueios")):
                lines.append(f"{relative}: bloqueada sem bloqueio descrito.")
            for spec in _references(metadata.get("specs", "")):
                if not (root / spec).is_file():
                    lines.append(f"{relative}: spec declarada não encontrada: {spec}.")
        suggestions = relationship_suggestions(root)
        if suggestions:
            lines.append(f"{len(suggestions)} sugestão(ões) de relação aguardam revisão em memory.py suggest.")
    titles = {"blocked": "Bloqueios", "stale": "Inatividade", "risk": "Riscos", "gaps": "Lacunas"}
    return (
        [f"{titles[category]}: nenhum diagnóstico."]
        if not lines
        else [f"{titles[category]}:", *[f"- {line}" for line in lines]]
    )


def operational_panel(root: Path, branch: str, depth: int = 2) -> list[str]:
    """Reúne leituras operacionais em ordem de prioridade, sem alterar estado."""
    lines = [f"Painel operacional (somente leitura): branch {branch}."]
    lines.extend(["", "## Frente atual", *critical_briefing(root, branch)])

    lines.extend(["", "## Atenção"])
    for category in ("blocked", "gaps", "risk", "stale"):
        diagnosis = operational_diagnostics(root, category)
        if len(diagnosis) > 1:
            lines.extend(diagnosis)

    handoffs = _open_handoffs(root, branch)
    if handoffs:
        paths = ", ".join(path.relative_to(root).as_posix() for path in handoffs[:4])
        suffix = " e outros." if len(handoffs) > 4 else "."
        lines.append(f"Handoffs abertos: {paths}{suffix}")

    lines.extend(["", "## Impacto confirmado", *graph_impact(root, branch, depth)])

    suggestions = relationship_suggestions(root)
    proposals = consolidation_items(root, branch)
    lines.extend(["", "## Revisão humana"])
    if suggestions:
        lines.append(f"Sugestões de relação aguardando revisão: {len(suggestions)}.")
        lines.extend(
            f"- {item['id']} {item['source']} --{item['field']}-> {item['target']} ({item['reason']})."
            for item in suggestions[:5]
        )
        if len(suggestions) > 5:
            lines.append("- Outras sugestões: consulte memory.py suggest.")
    else:
        lines.append("Sugestões de relação: nenhuma.")
    if proposals:
        lines.append(f"Propostas de consolidação aguardando revisão: {len(proposals)}.")
        lines.extend(f"- {item['id']} {item['details']}." for item in proposals)
    else:
        lines.append("Propostas de consolidação: nenhuma.")
    lines.append("Nenhuma sugestão ou proposta foi aplicada; aceite exige comando explícito.")
    return lines


def _bootstrap_feedback(root: Path) -> dict[str, str]:
    """Lê o último resultado humano de cada proposta inicial, a partir do Markdown canônico."""
    path = root / BOOTSTRAP_FEEDBACK_RELATIVE
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    outcomes: dict[str, str] = {}
    for match in re.finditer(r"(?ms)^##\s+(B-[a-f0-9]+)\s*$\n(.*?)(?=^##\s+|\Z)", text):
        outcome = re.search(r"(?m)^- resultado:\s*(aceita|rejeitada)\s*$", match.group(2))
        if outcome:
            outcomes[match.group(1)] = outcome.group(1)
    return outcomes


def bootstrap_proposals(root: Path, min_files: int = 3, include_docs: bool = False) -> list[dict[str, str]]:
    """Propõe um mapa inicial a partir de comunidades já extraídas pelo Graphify."""
    graph_path = root / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        return []
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    groups: dict[str, dict[str, object]] = {}
    for node in graph.get("nodes") or []:
        source_file = str(node.get("source_file") or "").replace("\\", "/")
        if not source_file:
            continue
        community = str(node.get("community") if node.get("community") is not None else "sem-comunidade")
        group = groups.setdefault(
            community,
            {"files": set(), "name": str(node.get("community_name") or f"Comunidade {community}")},
        )
        files = group["files"]
        if isinstance(files, set):
            files.add(source_file)

    proposals: list[dict[str, str]] = []
    for community, group in groups.items():
        files = sorted(group["files"]) if isinstance(group["files"], set) else []
        code_files = [path for path in files if not path.startswith(("docs/", ".claude/", ".github/"))]
        selected = files if include_docs else code_files
        if len(selected) < max(1, min_files):
            continue
        title = str(group["name"])
        raw = "\0".join(("comunidade_graphify", community, *selected))
        proposals.append(
            {
                "id": "B-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10],
                "kind": "comunidade_graphify",
                "title": title,
                "files": ", ".join(selected[:12]) + (" e outros" if len(selected) > 12 else ""),
                "file_count": str(len(selected)),
            }
        )
    return sorted(proposals, key=lambda item: (-int(item["file_count"]), item["title"], item["id"]))


def bootstrap_learning(
    root: Path, include_reviewed: bool = False, min_files: int = 3, include_docs: bool = False
) -> list[str]:
    """Mostra hipóteses iniciais revisáveis, derivadas somente do grafo já existente."""
    proposals = bootstrap_proposals(root, min_files=min_files, include_docs=include_docs)
    if not proposals:
        return [
            "Mapa inicial: graphify-out/graph.json ausente ou sem nós com arquivo-fonte; "
            "execute ou atualize o Graphify antes."
        ]
    feedback = _bootstrap_feedback(root)
    pending = [item for item in proposals if item["id"] not in feedback]
    lines = [
        "Mapa inicial do projeto: hipóteses derivadas do Graphify; nenhuma frente, relação ou documento foi criado.",
        f"Propostas aguardando revisão: {len(pending)} de {len(proposals)} (mínimo: {min_files} arquivo(s)).",
    ]
    for item in pending:
        lines.append(f"{item['id']} [proposta] {item['title']}: {item['file_count']} arquivo(s) — {item['files']}.")
    if include_reviewed:
        for item in proposals:
            outcome = feedback.get(item["id"])
            if outcome:
                lines.append(f"{item['id']} [{outcome}] {item['title']}.")
    if not pending:
        lines.append("Nenhuma hipótese inédita; consulte --history para o mapa já revisado.")
    lines.append("Use --accept ou --reject com uma nota factual para registrar o aprendizado local.")
    return lines


def record_bootstrap_feedback(
    root: Path, proposal_id: str, outcome: str, note: str, min_files: int = 3, include_docs: bool = False
) -> dict[str, str]:
    """Registra aceite ou rejeição explícitos; nunca transforma hipótese em estrutura canônica automática."""
    if outcome not in {"aceita", "rejeitada"}:
        raise ValueError("resultado deve ser aceita ou rejeitada")
    proposal = next(
        (
            item
            for item in bootstrap_proposals(root, min_files=min_files, include_docs=include_docs)
            if item["id"] == proposal_id
        ),
        None,
    )
    if proposal is None:
        raise ValueError("proposta inicial não encontrada ou não é mais aplicável")
    previous = _bootstrap_feedback(root)
    if proposal_id in previous:
        raise ValueError("proposta inicial já recebeu feedback; gere um novo mapa se o código mudou")
    note = _sanitize(note)
    if not note:
        raise ValueError("note é obrigatória para registrar feedback do mapa inicial")
    path = root / BOOTSTRAP_FEEDBACK_RELATIVE
    header = (
        "# Feedback do mapa inicial\n\n"
        "> Registro append-only de hipóteses derivadas do Graphify e revisadas por uma pessoa. "
        "Não cria frentes, relações ou decisões automaticamente.\n"
    )
    entry = (
        f"\n## {proposal_id}\n\n"
        f"- resultado: {outcome}\n"
        f"- registrado_em: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"- tipo: {proposal['kind']}\n"
        f"- hipótese: {proposal['title']}\n"
        f"- arquivos: {proposal['files']}\n"
        f"- nota: {note}\n"
    )
    current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else header
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(current.rstrip() + "\n" + entry, encoding="utf-8")
    temporary.replace(path)
    index(root)
    return proposal


def conflict_suggestions(root: Path) -> list[str]:
    """Sugere coordenação quando frentes abertas declaram o mesmo alvo."""
    owners: dict[tuple[str, str], list[str]] = {}
    for path, frontmatter in L.frentes(root):
        if frontmatter.get("status") == "concluida":
            continue
        front = path.relative_to(root).as_posix()
        for field in ("modulos", "files"):
            for reference in _references(frontmatter.get(field, "")):
                owners.setdefault((field, reference), []).append(front)
    suggestions = [
        f"Sugestão (relação derivada): {field[:-1]} `{reference}` aparece em {', '.join(sorted(fronts))}."
        for (field, reference), fronts in sorted(owners.items())
        if len(fronts) > 1
    ]
    return suggestions or ["Nenhum possível conflito declarado entre frentes abertas."]


def _front_surface_files(root: Path, front: str, metadata: dict[str, str]) -> set[str]:
    files = set(_references(metadata.get("files", "")))
    for spec in _spec_paths(root, front, metadata):
        files.update(_frontmatter_list(spec.read_text(encoding="utf-8", errors="replace"), "files"))
    return files


def _graph_reachable_files(root: Path, files: set[str], depth: int = 2) -> set[str]:
    """Arquivos alcançáveis no Graphify; só retorna fatos presentes no JSON."""
    graph_path = root / "graphify-out" / "graph.json"
    if not graph_path.is_file() or not files:
        return set()
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    nodes = {str(node.get("id")): node for node in graph.get("nodes") or [] if node.get("id") is not None}
    roots = {
        node_id for node_id, node in nodes.items() if str(node.get("source_file") or "").replace("\\", "/") in files
    }
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in graph.get("links") or []:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in nodes and target in nodes:
            adjacency[source].add(target)
            adjacency[target].add(source)
    distance = {node_id: 0 for node_id in roots}
    queue = list(roots)
    while queue:
        node_id = queue.pop(0)
        if distance[node_id] >= depth:
            continue
        for neighbor in adjacency[node_id]:
            if neighbor not in distance:
                distance[neighbor] = distance[node_id] + 1
                queue.append(neighbor)
    return {
        str(nodes[node_id].get("source_file")).replace("\\", "/")
        for node_id in distance
        if nodes[node_id].get("source_file")
    }


def _evidence(text: str, signals: set[str], path: Path, start_line: int = 1) -> dict[str, str] | None:
    """Retorna a primeira ocorrência revisável, com arquivo, linha e termo."""
    for offset, line in enumerate(text.splitlines()):
        for signal in sorted(signals, key=lambda value: (-len(value), value.casefold())):
            if signal and signal.casefold() in line.casefold():
                return {
                    "evidence_path": path.as_posix(),
                    "evidence_line": str(start_line + offset),
                    "matched_term": signal,
                    "evidence_excerpt": " ".join(line.strip().split())[:240],
                }
    return None


def _document_reference_suggestions(root: Path, front: str, metadata: dict[str, str]) -> list[dict[str, str]]:
    signals = {front, *_front_surface_files(root, front, metadata), *_references(metadata.get("modulos", ""))}
    suggestions: list[dict[str, str]] = []
    decisions = root / "docs" / "ai" / "DECISOES.md"
    if decisions.is_file():
        text = decisions.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"(?ms)^##\s+(D-\d+)\b(.*?)(?=^##\s+|\Z)", text):
            decision, body = match.group(1), match.group(2)
            evidence = _evidence(body, signals, decisions, text[: match.start(2)].count("\n") + 1)
            if evidence is not None and decision not in _references(metadata.get("decisoes", "")):
                suggestions.append(
                    {
                        "source": front,
                        "target": decision,
                        "field": "decisoes",
                        "reason": "decisão cita a frente ou sua superfície",
                        **evidence,
                    }
                )
    debts = root / "docs" / "ai" / "DEBITOS.md"
    if debts.is_file():
        for line_number, line in enumerate(debts.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            debt = re.search(r"\b(DB-\d+)\b", line)
            evidence = _evidence(line, signals, debts, line_number)
            if debt and evidence is not None:
                debt_id = debt.group(1)
                if debt_id not in _references(metadata.get("debitos", "")):
                    suggestions.append(
                        {
                            "source": front,
                            "target": debt_id,
                            "field": "debitos",
                            "reason": "débito cita a frente ou sua superfície",
                            **evidence,
                        }
                    )
    return suggestions


def relationship_suggestions(root: Path) -> list[dict[str, str]]:
    """Propõe relações a partir de evidência local, sem torná-las canônicas."""
    fronts = [(path.relative_to(root).as_posix(), path, metadata) for path, metadata in L.frentes(root)]
    open_fronts = [
        (relative, path, metadata) for relative, path, metadata in fronts if metadata.get("status") != "concluida"
    ]
    suggestions: list[dict[str, str]] = []
    for source, path, metadata in open_fronts:
        blocks = L.secao(path, "Bloqueios")
        for target, _, _ in open_fronts:
            if target != source and target in blocks and target not in _references(metadata.get("depende_de", "")):
                suggestions.append(
                    {
                        "source": source,
                        "target": target,
                        "field": "depende_de",
                        "reason": "a seção Bloqueios cita a outra frente",
                    }
                )
    for index, (source, _, metadata) in enumerate(open_fronts):
        for target, _, other in open_fronts[index + 1 :]:
            for field, label in (("files", "arquivo"), ("modulos", "módulo")):
                shared = sorted(set(_references(metadata.get(field, ""))) & set(_references(other.get(field, ""))))
                if shared and target not in _references(metadata.get("relaciona_com", "")):
                    suggestions.append(
                        {
                            "source": source,
                            "target": target,
                            "field": "relaciona_com",
                            "reason": f"compartilham {label}: {', '.join(shared)}",
                        }
                    )
            source_files = _front_surface_files(root, source, metadata)
            target_files = _front_surface_files(root, target, other)
            reached = _graph_reachable_files(root, source_files)
            shared_graph = sorted((reached & target_files) - source_files)
            if shared_graph and target not in _references(metadata.get("relaciona_com", "")):
                suggestions.append(
                    {
                        "source": source,
                        "target": target,
                        "field": "relaciona_com",
                        "reason": "Graphify alcança arquivo declarado pela outra frente: " + ", ".join(shared_graph),
                    }
                )
    for source, _, metadata in open_fronts:
        suggestions.extend(_document_reference_suggestions(root, source, metadata))
    for suggestion in suggestions:
        raw = "\0".join(suggestion[key] for key in ("source", "target", "field", "reason"))
        suggestion["id"] = "S-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    reviewed = _relationship_feedback(root)
    return sorted((item for item in suggestions if item["id"] not in reviewed), key=lambda item: item["id"])


def _relationship_feedback(root: Path) -> dict[str, str]:
    path = root / RELATIONSHIP_FEEDBACK_RELATIVE
    if not path.is_file():
        return {}
    outcomes: dict[str, str] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"(?ms)^##\s+(S-[a-f0-9]+)\s*$\n(.*?)(?=^##\s+|\Z)", text):
        outcome = re.search(r"(?m)^- resultado:\s*(rejeitada)\s*$", match.group(2))
        if outcome:
            outcomes[match.group(1)] = outcome.group(1)
    return outcomes


def reject_relationship_suggestion(root: Path, suggestion_id: str, note: str) -> dict[str, str]:
    """Registra uma rejeição factual e retira somente essa hipótese da fila."""
    suggestion = next((item for item in relationship_suggestions(root) if item["id"] == suggestion_id), None)
    if suggestion is None:
        raise ValueError("sugestão não encontrada ou não é mais aplicável")
    note = _sanitize(note)
    if not note:
        raise ValueError("note é obrigatória para rejeitar uma sugestão")
    path = root / RELATIONSHIP_FEEDBACK_RELATIVE
    header = (
        "# Feedback de sugestões de relação\n\n"
        "> Registro append-only de hipóteses revisadas. "
        "Uma rejeição não cria relação canônica.\n"
    )
    evidence = ""
    if suggestion.get("evidence_path"):
        evidence = (
            f"- evidência: {suggestion['evidence_path']}:{suggestion['evidence_line']} "
            f"(termo: {suggestion['matched_term']})\n"
        )
    entry = (
        f"\n## {suggestion_id}\n\n- resultado: rejeitada\n"
        f"- registrado_em: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"- relação: {suggestion['source']} --{suggestion['field']}-> {suggestion['target']}\n"
        f"{evidence}- nota: {note}\n"
    )
    current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else header
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(current.rstrip() + "\n" + entry, encoding="utf-8")
    temporary.replace(path)
    index(root)
    return suggestion


def accept_relationship_suggestion(root: Path, suggestion_id: str) -> dict[str, str]:
    """Aceita uma sugestão corrente e a registra no frontmatter canônico."""
    suggestion = next((item for item in relationship_suggestions(root) if item["id"] == suggestion_id), None)
    if suggestion is None:
        raise ValueError("sugestão não encontrada ou não é mais aplicável")
    path = root / suggestion["source"]
    metadata = L.frontmatter(path)
    references = _references(metadata.get(suggestion["field"], ""))
    if suggestion["target"] not in references:
        references.append(suggestion["target"])
    updated = _replace_frontmatter(
        path.read_text(encoding="utf-8", errors="replace"), {suggestion["field"]: ", ".join(references)}
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)
    return suggestion


def export_work_graph(root: Path) -> Path:
    """Exporta relações explícitas do trabalho como JSON reconstruível."""
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    for front_path, frontmatter in L.frentes(root):
        front = front_path.relative_to(root).as_posix()
        _add_node(nodes, front, "frente", status=frontmatter.get("status", "?"), branch=frontmatter.get("branch", ""))
        for spec in _references(frontmatter.get("specs", "")):
            _add_node(nodes, spec, "spec", status="referenciada")
            _add_edge(edges, front, spec, "governa")
        for dependency in _references(frontmatter.get("depende_de", "")):
            _add_node(nodes, dependency, "frente", status="referenciada")
            _add_edge(edges, front, dependency, "depende_de")
        for blocked in _references(frontmatter.get("bloqueia", "")):
            _add_node(nodes, blocked, "frente", status="referenciada")
            _add_edge(edges, front, blocked, "bloqueia")
        for related in _references(frontmatter.get("relaciona_com", "")):
            _add_node(nodes, related, "frente", status="referenciada")
            _add_edge(edges, front, related, "relaciona_com")
        for decision in _references(frontmatter.get("decisoes", "")):
            node = f"decisao:{decision}"
            _add_node(nodes, node, "decisao", reference=decision)
            _add_edge(edges, front, node, "referencia_decisao")
        for debt in _references(frontmatter.get("debitos", "")):
            node = f"debito:{debt}"
            _add_node(nodes, node, "debito", reference=debt)
            _add_edge(edges, front, node, "referencia_debito")
        for module in _references(frontmatter.get("modulos", "")):
            node = f"modulo:{module}"
            _add_node(nodes, node, "modulo", name=module)
            _add_edge(edges, front, node, "atua_em")
        for file_path in _references(frontmatter.get("files", "")):
            node = f"arquivo:{file_path}"
            _add_node(nodes, node, "arquivo", path=file_path)
            _add_edge(edges, front, node, "altera")
        for tag in _references(frontmatter.get("tags", "")):
            node = f"tag:{tag}"
            _add_node(nodes, node, "tag", name=tag)
            _add_edge(edges, front, node, "classificada_com")
    for path in _markdown_files(root):
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("specs/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = L.frontmatter(path)
        front = frontmatter.get("frente")
        _add_node(nodes, relative, "spec", status=frontmatter.get("status", "?"), module=frontmatter.get("module", ""))
        if front and front != "-":
            _add_node(nodes, front, "frente", status="referenciada")
            _add_edge(edges, front, relative, "governa")
        for module in _references(frontmatter.get("module", "")):
            node = f"modulo:{module}"
            _add_node(nodes, node, "modulo", name=module)
            _add_edge(edges, relative, node, "atua_em")
        for file_path in _frontmatter_list(text, "files"):
            node = f"arquivo:{file_path}"
            _add_node(nodes, node, "arquivo", path=file_path)
            _add_edge(edges, relative, node, "altera")
        for target in _frontmatter_list(text, "target_nodes"):
            node = f"codigo:{target}"
            _add_node(nodes, node, "codigo", name=target)
            _add_edge(edges, relative, node, "alvo_no_codigo")
    output = root / WORK_GRAPH_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"nodes": list(nodes.values()), "edges": edges}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _sanitize(value: str) -> str:
    value = " ".join(value.strip().split())[:MAX_HANDOFF_FIELD]
    strong, _ = L.segredos(value)
    if strong:
        raise ValueError("handoff contém padrão de segredo: " + ", ".join(strong))
    return value


def begin_handoff(root: Path, branch: str, owner: str, summary: str, next_step: str, questions: str = "") -> Path:
    summary, next_step, questions = (_sanitize(value) for value in (summary, next_step, questions))
    if not summary or not next_step:
        raise ValueError("summary e next-step são obrigatórios")
    now = datetime.now(timezone.utc)
    directory = root / HANDOFFS_RELATIVE
    directory.mkdir(parents=True, exist_ok=True)
    path = (
        directory
        / f"{now.strftime('%Y%m%d-%H%M%S')}-{re.sub(r'[^a-z0-9]+', '-', branch.lower()).strip('-') or 'branch'}.md"
    )
    path.write_text(
        "---\n"
        "tipo: handoff\n"
        "status: aberto\n"
        f"criado_em: {now.isoformat(timespec='seconds')}\n"
        f"criado_por: {owner or 'desconhecido'}\n"
        f"branch: {branch}\n"
        "---\n\n"
        "# Handoff\n\n"
        "## Resumo\n\n"
        f"{summary}\n\n"
        "## Próximo passo\n\n"
        f"{next_step}\n\n"
        "## Questões abertas\n\n"
        f"{questions or 'Nenhuma registrada.'}\n",
        encoding="utf-8",
    )
    index(root)
    return path


def list_handoffs(root: Path, branch: str | None = None) -> list[tuple[str, str, str, str, str]]:
    index(root)
    query = "SELECT path, status, branch, created_by, accepted_by FROM handoffs"
    values: tuple[str, ...] = ()
    if branch:
        query += " WHERE branch IN (?, '*')"
        values = (branch,)
    query += " ORDER BY created_at DESC"
    with _connect(root) as connection:
        rows = connection.execute(query, values).fetchall()
    return [tuple(str(value or "") for value in row) for row in rows]


def _handoff_path(root: Path, raw_path: str) -> Path:
    path = (root / raw_path).resolve()
    directory = (root / HANDOFFS_RELATIVE).resolve()
    if not path.is_relative_to(directory) or path.suffix != ".md":
        raise ValueError("handoff precisa apontar para docs/ai/memoria/handoffs/*.md")
    return path


def _replace_frontmatter(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if line.lstrip("\ufeff").strip()), None)
    if start is None or lines[start].lstrip("\ufeff").strip() != "---":
        raise ValueError("handoff sem frontmatter válido")
    end = next((index for index in range(start + 1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        raise ValueError("handoff sem fechamento de frontmatter")
    found = set()
    for index in range(start + 1, end):
        if ":" not in lines[index]:
            continue
        key = lines[index].split(":", 1)[0].strip()
        if key in updates:
            lines[index] = f"{key}: {updates[key]}\n"
            found.add(key)
    for key, value in updates.items():
        if key not in found:
            lines.insert(end, f"{key}: {value}\n")
            end += 1
    return "".join(lines)


def accept_handoff(root: Path, raw_path: str, owner: str) -> Path:
    """Aceita uma vez o handoff, mantendo o arquivo como registro auditável."""
    owner = _sanitize(owner)
    if not owner:
        raise ValueError("owner é obrigatório para aceitar um handoff")
    index(root)
    path = _handoff_path(root, raw_path)
    directory = (root / HANDOFFS_RELATIVE).resolve()
    relative = (HANDOFFS_RELATIVE / path.relative_to(directory)).as_posix()
    accepted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(root) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT status FROM handoffs WHERE path = ?", (relative,)).fetchone()
        if row is None:
            raise ValueError("handoff não encontrado no índice")
        if row[0] != "aberto":
            raise ValueError("handoff não está aberto para aceite")
        updated = _replace_frontmatter(
            path.read_text(encoding="utf-8", errors="replace"),
            {"status": "aceito", "aceito_em": accepted_at, "aceito_por": owner},
        )
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(updated, encoding="utf-8")
        temporary.replace(path)
        result = connection.execute(
            "UPDATE handoffs SET status = 'aceito', accepted_at = ?, accepted_by = ? "
            "WHERE path = ? AND status = 'aberto'",
            (accepted_at, owner, relative),
        )
        if result.rowcount != 1:
            raise ValueError("handoff já foi aceito por outro agente")
    index(root)
    return root / relative


def _command(root: Path, args: argparse.Namespace) -> int:
    if args.command == "index":
        print(f"Índice reconstruído: {index(root)} página(s).")
        return 0
    if args.command == "query":
        for path, kind, snippet in search(root, args.query, args.limit):
            print(f"{path} [{kind}]\n  {snippet}")
        return 0
    if args.command == "retrieve":
        for line in hybrid_recovery(root, args.query, args.limit):
            print(line)
        return 0
    if args.command == "graph-status":
        for line in graph_status(root):
            print(line)
        return 0
    if args.command == "briefing":
        for line in briefing(root, args.branch or L.branch_atual(root), args.limit):
            print(line)
        return 0
    if args.command == "critical":
        for line in critical_briefing(root, args.branch or L.branch_atual(root)):
            print(line)
        return 0
    if args.command == "status":
        for line in operational_panel(root, args.branch or L.branch_atual(root), args.depth):
            print(line)
        return 0
    if args.command == "bootstrap":
        if args.accept or args.reject:
            outcome = "aceita" if args.accept else "rejeitada"
            proposal = record_bootstrap_feedback(
                root, args.accept or args.reject, outcome, args.note or "", args.min_files, args.include_docs
            )
            print(f"Feedback registrado: {proposal['id']} [{outcome}] em {BOOTSTRAP_FEEDBACK_RELATIVE.as_posix()}")
            return 0
        for line in bootstrap_learning(root, args.history, args.min_files, args.include_docs):
            print(line)
        return 0
    if args.command == "consolidate":
        branch = args.branch or L.branch_atual(root)
        if args.accept:
            item = accept_consolidation(root, branch, args.accept, args.note or "")
            print(f"Consolidação registrada: {item['id']} em {item['front']}")
            return 0
        for line in consolidation_proposal(root, branch):
            print(line)
        return 0
    if args.command == "impact":
        for line in graph_impact(root, args.branch or L.branch_atual(root), args.depth):
            print(line)
        return 0
    if args.command == "work":
        if args.ready:
            lines = ready_fronts(root)
        elif args.conflicts:
            lines = conflict_suggestions(root)
        elif args.blocked:
            lines = operational_diagnostics(root, "blocked")
        elif args.stale:
            lines = operational_diagnostics(root, "stale")
        elif args.risk:
            lines = operational_diagnostics(root, "risk")
        elif args.gaps:
            lines = operational_diagnostics(root, "gaps")
        else:
            lines = work_graph(root, args.branch or L.branch_atual(root))
        for line in lines:
            print(line)
        return 0
    if args.command == "graph":
        print(export_work_graph(root).relative_to(root).as_posix())
        return 0
    if args.command == "suggest":
        if args.accept:
            suggestion = accept_relationship_suggestion(root, args.accept)
            print(f"Sugestão aceita: {suggestion['id']} -> {suggestion['field']} em {suggestion['source']}")
            return 0
        if args.reject:
            suggestion = reject_relationship_suggestion(root, args.reject, args.note or "")
            print(f"Sugestão rejeitada: {suggestion['id']} registrada em {RELATIONSHIP_FEEDBACK_RELATIVE.as_posix()}")
            return 0
        suggestions = relationship_suggestions(root)
        if not suggestions:
            print("Nenhuma sugestão de relação no momento.")
        for suggestion in suggestions:
            print(
                f"{suggestion['id']} [sugestão] {suggestion['source']} --{suggestion['field']}-> "
                f"{suggestion['target']} ({suggestion['reason']})."
            )
            if suggestion.get("evidence_path"):
                print(
                    f"  Evidência: {suggestion['evidence_path']}:{suggestion['evidence_line']} "
                    f"termo `{suggestion['matched_term']}` — {suggestion['evidence_excerpt']}"
                )
        return 0
    if args.command == "handoff":
        branch = args.branch or L.branch_atual(root)
        if args.list:
            for path, status, handoff_branch, created_by, accepted_by in list_handoffs(root, branch):
                recipient = f", aceito por {accepted_by}" if accepted_by else ""
                print(f"{path} [{status}, branch {handoff_branch}, criado por {created_by}{recipient}]")
            return 0
        if args.accept:
            path = accept_handoff(root, args.accept, args.owner)
            print(f"Handoff aceito: {path.relative_to(root).as_posix()}")
            return 0
        path = begin_handoff(root, branch, args.owner, args.summary or "", args.next_step or "", args.questions)
        print(f"Handoff aberto: {path.relative_to(root).as_posix()}")
        return 0
    raise AssertionError(args.command)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Memória local do init-harness.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Reconstrói o índice FTS a partir do Markdown.")
    query = commands.add_parser("query", help="Pesquisa docs/ai, specs e handoffs.")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=8)
    retrieve = commands.add_parser(
        "retrieve", help="Recupera contexto por FTS e correspondências confirmadas do Graphify."
    )
    retrieve.add_argument("query")
    retrieve.add_argument("--limit", type=int, default=8)
    commands.add_parser("graph-status", help="Mostra frescor do Graphify e o comando de atualização sugerido.")
    briefing = commands.add_parser("briefing", help="Mostra referências para retomar o trabalho.")
    briefing.add_argument("--branch")
    briefing.add_argument("--limit", type=int, default=4)
    work = commands.add_parser("work", help="Mostra relações e diagnósticos do grafo de trabalho.")
    work.add_argument("--branch")
    work.add_argument("--ready", action="store_true", help="Lista frentes sem dependência explícita pendente.")
    work.add_argument("--conflicts", action="store_true", help="Sugere coordenação para alvos declarados em comum.")
    diagnostics = work.add_mutually_exclusive_group()
    diagnostics.add_argument(
        "--blocked", action="store_true", help="Mostra bloqueios declarados e dependências abertas."
    )
    diagnostics.add_argument(
        "--stale", action="store_true", help="Mostra frentes ativas além do limite de inatividade."
    )
    diagnostics.add_argument(
        "--risk", action="store_true", help="Mostra riscos e débitos declarados, além da saúde do grafo."
    )
    diagnostics.add_argument(
        "--gaps", action="store_true", help="Mostra lacunas de registro obrigatório e relações para revisão."
    )
    commands.add_parser("graph", help="Exporta o grafo de trabalho reconstruível em JSON.")
    suggest = commands.add_parser("suggest", help="Lista, aceita ou rejeita sugestões revisáveis de relações.")
    review = suggest.add_mutually_exclusive_group()
    review.add_argument("--accept", metavar="ID", help="Aceita uma sugestão corrente e grava a relação canônica.")
    review.add_argument("--reject", metavar="ID", help="Rejeita uma sugestão corrente e registra o critério factual.")
    suggest.add_argument("--note", help="Fato verificado obrigatório ao rejeitar uma sugestão.")
    critical = commands.add_parser("critical", help="Mostra contexto crítico da frente e do grafo de código.")
    critical.add_argument("--branch")
    status = commands.add_parser("status", help="Reúne o painel operacional factual e somente leitura.")
    status.add_argument("--branch")
    status.add_argument("--depth", type=int, default=2, help="Profundidade do impacto Graphify (máximo: 4).")
    bootstrap = commands.add_parser("bootstrap", help="Propõe e aprende o mapa inicial do projeto via Graphify.")
    bootstrap.add_argument("--history", action="store_true", help="Inclui hipóteses iniciais já aceitas ou rejeitadas.")
    bootstrap.add_argument("--min-files", type=int, default=3, help="Mínimo de arquivos por comunidade (padrão: 3).")
    bootstrap.add_argument(
        "--include-docs", action="store_true", help="Inclui comunidades somente de documentação e metadados."
    )
    feedback = bootstrap.add_mutually_exclusive_group()
    feedback.add_argument("--accept", metavar="ID", help="Registra que uma hipótese inicial foi aceita.")
    feedback.add_argument("--reject", metavar="ID", help="Registra que uma hipótese inicial foi rejeitada.")
    bootstrap.add_argument(
        "--note", help="Fato verificado que justifica o feedback; obrigatório ao aceitar ou rejeitar."
    )
    consolidate = commands.add_parser("consolidate", help="Propõe ou registra revisão de consolidação de sessão.")
    consolidate.add_argument("--branch")
    consolidate.add_argument("--accept", metavar="ID", help="Registra a revisão de uma proposta corrente.")
    consolidate.add_argument("--note", help="Fato verificado que justifica o aceite; obrigatório com --accept.")
    impact = commands.add_parser("impact", help="Mostra blast radius factual da frente a partir do Graphify.")
    impact.add_argument("--branch")
    impact.add_argument("--depth", type=int, default=2)
    handoff = commands.add_parser("handoff", help="Cria, lista ou aceita handoffs versionáveis.")
    handoff.add_argument("--branch")
    handoff.add_argument("--owner", default="")
    action = handoff.add_mutually_exclusive_group()
    action.add_argument("--list", action="store_true")
    action.add_argument("--accept", metavar="PATH")
    handoff.add_argument("--summary")
    handoff.add_argument("--next-step")
    handoff.add_argument("--questions", default="")
    return root


if __name__ == "__main__":
    try:
        raise SystemExit(_command(Path.cwd(), parser().parse_args()))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"[ERRO] memória: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

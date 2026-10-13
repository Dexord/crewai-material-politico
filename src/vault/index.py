import re

import networkx as nx

from .vault import all_notes

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
REL_KEYS = ["entidades", "relacionadas", "mencionado_em", "notas_relacionadas"]


def _clean_link(link: str) -> str:
    link = str(link).strip()
    m = WIKILINK_RE.search(link)
    if m:
        link = m.group(1)
    return link.strip().lower().replace(" ", "-")


def _links_from_frontmatter(fm: dict) -> list[str]:
    links: list[str] = []
    for key in REL_KEYS:
        value = fm.get(key) or []
        if isinstance(value, str):
            value = [value]
        links.extend(str(v) for v in value)
    for vinculo in fm.get("vinculos") or []:
        if isinstance(vinculo, dict) and vinculo.get("alvo"):
            links.append(str(vinculo["alvo"]))
    return [_clean_link(link) for link in links if link]


def build_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    for fm, body, _ in all_notes():
        note_id = fm.get("id")
        if not note_id:
            continue
        graph.add_node(
            note_id,
            tipo=fm.get("tipo"),
            label=fm.get("titulo") or fm.get("nome") or note_id,
        )
        for target in _links_from_frontmatter(fm):
            graph.add_edge(note_id, target)
        for target in WIKILINK_RE.findall(body):
            graph.add_edge(note_id, _clean_link(target))
    return graph


def neighbors(note_id: str) -> dict:
    graph = build_graph()
    if note_id not in graph:
        return {"erro": f"nota nao encontrada no grafo: {note_id}"}
    return {
        "nota": note_id,
        "aponta_para": sorted(graph.successors(note_id)),
        "apontado_por": sorted(graph.predecessors(note_id)),
    }


def shortest_path(origem: str, destino: str) -> list | None:
    graph = build_graph()
    try:
        return nx.shortest_path(graph, origem, destino)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def most_connected(limit: int = 10) -> list:
    graph = build_graph()
    scores = {n: graph.degree(n) for n in graph.nodes}
    top = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
    return [{"id": n, "conexoes": d, "tipo": graph.nodes[n].get("tipo")} for n, d in top]


JUNK_LINKS = {"editar", "editar-secao", "redirecionar", "wikilinks", "fonte", "link"}


def _humaniza(note_id: str) -> str:
    s = re.sub(r"^(pessoa|org|organizacao|noticia|fato|tema|fila|log)-", "", note_id)
    s = s.replace("-", " ").strip()
    if not s:
        return note_id
    if " " not in s and len(s) <= 5:
        return s.upper()
    return s[:1].upper() + s[1:]


def _is_junk(target: str) -> bool:
    if len(target) < 4 or target.isdigit() or target in JUNK_LINKS:
        return True
    return False


def dangling(limite: int = 40) -> list[dict]:
    notes = all_notes()
    ids = {fm.get("id") for fm, _, _ in notes if fm.get("id")}
    counts: dict[str, int] = {}
    for fm, body, _ in notes:
        targets = set(_links_from_frontmatter(fm))
        targets.update(_clean_link(t) for t in WIKILINK_RE.findall(body or ""))
        for target in targets:
            if not target or target in ids:
                continue
            counts[target] = counts.get(target, 0) + 1
    out = [
        {"id": t, "nome": _humaniza(t), "citacoes": c}
        for t, c in counts.items()
        if not _is_junk(t)
    ]
    out.sort(key=lambda x: (-x["citacoes"], x["id"]))
    return out[:limite]

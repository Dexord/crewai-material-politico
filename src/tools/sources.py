from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser
import yaml
from bs4 import BeautifulSoup
from crewai.tools import tool

SOURCES_PATH = Path("config/sources.yaml")
MAX_WORKERS = 8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def load_sources() -> dict:
    if not SOURCES_PATH.exists():
        return {"search": {}, "rss": [], "portais": []}
    with SOURCES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _active(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("ativo", True)]


def _rss_limits(cfg: dict) -> tuple[int, int]:
    rss_cfg = cfg.get("rss_cfg", {}) or {}
    try:
        por_feed = int(rss_cfg.get("limite_por_feed", 5) or 5)
    except (TypeError, ValueError):
        por_feed = 5
    try:
        total = int(rss_cfg.get("limite_total", 0) or 0)
    except (TypeError, ValueError):
        total = 0
    return max(1, por_feed), max(0, total)


def _round_robin_keep(groups: list[list], total: int) -> list[set[int]]:
    keep = [set() for _ in groups]
    if not total:
        return [set(range(len(g))) for g in groups]
    count = 0
    i = 0
    while True:
        progressed = False
        for idx, group in enumerate(groups):
            if i < len(group):
                keep[idx].add(i)
                count += 1
                progressed = True
                if count >= total:
                    return keep
        if not progressed:
            break
        i += 1
    return keep


def _flatten_round_robin(groups: list[list[dict]], total: int) -> list[dict]:
    keep = _round_robin_keep(groups, total)
    out: list[dict] = []
    for group, picked in zip(groups, keep):
        for idx, item in enumerate(group):
            if idx in picked:
                out.append(item)
    return out


def _fetch_feeds(rss: list[dict], max_items: int) -> list[tuple[str, list[dict]]]:
    if not rss:
        return []
    workers = max(1, min(len(rss), MAX_WORKERS))

    def _one(source: dict) -> tuple[str, list[dict]]:
        return _load_entries(source["nome"], source["url"], max_items)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_one, rss))


@tool("listar_fontes")
def list_sources() -> str:
    """Lista os feeds RSS e portais configurados em config/sources.yaml.

    Returns:
        Lista em markdown com nome, url e tipo de cada fonte ativa.
    """
    cfg = load_sources()
    lines = ["## Fontes configuradas\n"]

    rss = _active(cfg.get("rss", []))
    lines.append("### RSS")
    lines.append("\n".join(f"- {s['nome']}: {s['url']}" for s in rss) or "- (nenhum)")

    portais = _active(cfg.get("portais", []))
    lines.append("\n### Portais")
    lines.append("\n".join(f"- {s['nome']}: {s['url']}" for s in portais) or "- (nenhum)")

    search = cfg.get("search", {})
    lines.append(f"\n### Busca web habilitada: {search.get('enabled', True)}")
    return "\n".join(lines)


def _clean_summary(text: str, limite: int = 400) -> str:
    if not text:
        return ""
    limpo = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    return " ".join(limpo.split())[:limite]


def _load_entries(nome: str, url: str, max_items: int) -> tuple[str, list[dict]]:
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
    except Exception as exc:  # noqa: BLE001
        return f"Erro ao ler feed: {exc}", []

    if getattr(feed, "bozo", 0) and not feed.entries:
        return "Feed invalido ou inacessivel.", []

    itens = [
        {
            "fonte": nome,
            "titulo": entry.get("title", "Sem titulo"),
            "link": entry.get("link", ""),
            "resumo": _clean_summary(entry.get("summary", "")),
        }
        for entry in feed.entries[:max_items]
    ]
    return "", itens


def _render_feed(nome: str, url: str, erro: str, itens: list[dict], max_resumo: int = 300) -> str:
    lines = [f"### {nome} ({url})"]
    if erro:
        lines.append(erro)
    for item in itens:
        lines.append(
            f"- **{item['titulo']}**\n  - {item['link']}\n  - {item['resumo'][:max_resumo]}"
        )
    return "\n".join(lines)


def _feed_to_markdown(nome: str, url: str, max_items: int) -> str:
    erro, itens = _load_entries(nome, url, max_items)
    return _render_feed(nome, url, erro, itens)


@tool("ler_rss")
def read_rss(url: str, max_items: int = 10) -> str:
    """Le um feed RSS e retorna os itens mais recentes em markdown.

    Args:
        url: URL do feed RSS.
        max_items: Quantidade maxima de itens (padrao 10).

    Returns:
        Itens do feed em markdown com titulo, link e resumo.
    """
    return _feed_to_markdown(url, url, max_items)


@tool("ler_rss_ativos")
def read_active_rss(max_items: int = 0) -> str:
    """Le todos os feeds RSS ativos definidos em config/sources.yaml.

    Args:
        max_items: Itens por feed. 0 (padrao) usa rss_cfg.limite_por_feed do
            sources.yaml. O total e limitado por rss_cfg.limite_total.

    Returns:
        Itens de todos os feeds ativos em markdown.
    """
    cfg = load_sources()
    por_feed, total = _rss_limits(cfg)
    n = max_items or por_feed
    rss = _active(cfg.get("rss", []))
    if not rss:
        return "Nenhum feed RSS ativo configurado em config/sources.yaml."
    results = _fetch_feeds(rss, n)
    keep = _round_robin_keep([itens for _, itens in results], total)
    blocks: list[str] = []
    for idx, (src, (erro, itens)) in enumerate(zip(rss, results)):
        if not itens:
            blocks.append(f"### {src['nome']} ({src['url']})\n{erro or 'Sem itens.'}")
            continue
        if keep[idx]:
            blocks.append(_render_keep(src, itens, keep[idx]))
    return "\n\n".join(blocks)


def _render_keep(src: dict, itens: list[dict], picked: set[int]) -> str:
    filtrados = [item for idx, item in enumerate(itens) if idx in picked]
    return _render_feed(src["nome"], src["url"], "", filtrados)


def carregar_itens_rss(max_items: int = 0) -> list[dict]:
    cfg = load_sources()
    por_feed, total = _rss_limits(cfg)
    n = max_items or por_feed
    rss = _active(cfg.get("rss", []))
    groups = _fetch_feeds(rss, n)
    return _flatten_round_robin([itens for _, itens in groups], total)


def filtrar_relevantes(itens: list[dict], nomes: list[str], min_tokens: int = 2) -> list[dict]:
    from ..vault.vault import normalize

    refs: list[tuple[str, str]] = []
    for nome in nomes:
        nn = normalize(nome).strip()
        if len(nn) >= 6 and len(nn.split()) >= min_tokens:
            refs.append((nome, nn))
    if not refs:
        return []
    out: list[dict] = []
    for item in itens:
        titulo = normalize(item.get("titulo", ""))
        matched = sorted({orig for orig, nn in refs if nn in titulo})
        if matched:
            novo = dict(item)
            novo["entidades"] = matched
            out.append(novo)
    return out

from pathlib import Path

import feedparser
import yaml
from bs4 import BeautifulSoup
from crewai.tools import tool

SOURCES_PATH = Path("config/sources.yaml")


def load_sources() -> dict:
    if not SOURCES_PATH.exists():
        return {"search": {}, "rss": [], "portais": []}
    with SOURCES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _active(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("ativo", True)]


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


def _feed_to_markdown(nome: str, url: str, max_items: int) -> str:
    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        return f"### {nome} ({url})\nErro ao ler feed: {exc}\n"

    if getattr(feed, "bozo", 0) and not feed.entries:
        return f"### {nome} ({url})\nFeed invalido ou inacessivel.\n"

    lines = [f"### {nome} ({url})"]
    for entry in feed.entries[:max_items]:
        title = entry.get("title", "Sem titulo")
        link = entry.get("link", "")
        summary = entry.get("summary", "")
        if summary:
            summary = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
        summary = " ".join(summary.split())[:300]
        lines.append(f"- **{title}**\n  - {link}\n  - {summary}")
    return "\n".join(lines)


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
def read_active_rss(max_items: int = 10) -> str:
    """Le todos os feeds RSS ativos definidos em config/sources.yaml.

    Args:
        max_items: Quantidade maxima de itens por feed (padrao 10).

    Returns:
        Itens de todos os feeds ativos em markdown.
    """
    cfg = load_sources()
    rss = _active(cfg.get("rss", []))
    if not rss:
        return "Nenhum feed RSS ativo configurado em config/sources.yaml."
    blocks = [_feed_to_markdown(s["nome"], s["url"], max_items) for s in rss]
    return "\n\n".join(blocks)

from crewai.tools import tool
from ddgs import DDGS


@tool("buscar_na_web")
def search_web(query: str, max_results: int = 8) -> str:
    """Busca na web (DuckDuckGo metasearch) e retorna os resultados em markdown.

    Args:
        query: Texto da busca em português.
        max_results: Quantidade máxima de resultados (padrão 8).

    Returns:
        Lista de resultados em markdown com título, link e descrição.
    """
    try:
        results = DDGS().text(
            query, region="br-pt", safesearch="off", max_results=max_results
        )
    except Exception as exc:  # noqa: BLE001
        return f"Erro ao buscar: {exc}"

    if not results:
        return "Nenhum resultado encontrado."

    try:
        from ..vault.log import log_event

        log_event(f"buscar_na_web: '{query}' -> {len(results)} resultados", "pesquisa")
    except Exception:  # noqa: BLE001
        pass

    lines = ["## Resultados da busca\n"]
    for r in results:
        title = r.get("title") or "Sem título"
        href = r.get("href") or ""
        body = r.get("body") or ""
        lines.append(f"- **{title}** — {body}\n  - {href}")
    return "\n".join(lines)

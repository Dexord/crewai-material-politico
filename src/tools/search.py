from crewai.tools import tool
from duckduckgo_search import DDGS


@tool("buscar_na_web")
def search_web(query: str, max_results: int = 8) -> str:
    """Busca na web (DuckDuckGo) e retorna os resultados formatados em markdown.

    Args:
        query: Texto da busca em português.
        max_results: Quantidade máxima de resultados (padrão 8).

    Returns:
        Lista de resultados em markdown com título, link e descrição.
    """
    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(query, region="br-pt", safesearch="off", max_results=max_results)
            )
    except Exception as exc:  # noqa: BLE001
        return f"Erro ao buscar: {exc}"

    if not results:
        return "Nenhum resultado encontrado."

    lines = ["## Resultados da busca\n"]
    for r in results:
        title = r.get("title") or "Sem título"
        href = r.get("href") or ""
        body = r.get("body") or ""
        lines.append(f"- **{title}** — {body}\n  - {href}")
    return "\n".join(lines)

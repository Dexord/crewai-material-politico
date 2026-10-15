import time

import requests
from bs4 import BeautifulSoup
from crewai.tools import tool
from markdownify import markdownify as md

from ..config import get_settings

try:
    from curl_cffi import requests as cffi_requests
except ImportError:  # pragma: no cover
    cffi_requests = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

_last_request = 0.0


def _throttle() -> None:
    global _last_request
    interval = 1.0 / get_settings().scrape_rate_limit
    elapsed = time.monotonic() - _last_request
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request = time.monotonic()


def _download(url: str) -> tuple[object | None, str]:
    if cffi_requests is not None:
        try:
            resp = cffi_requests.get(url, impersonate="chrome", timeout=25)
            if resp.status_code < 400:
                return resp, ""
        except Exception:  # noqa: BLE001
            pass

    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        return resp, ""
    except requests.HTTPError as exc:
        return None, f"Erro HTTP {exc.response.status_code} ao acessar {url}."
    except requests.RequestException as exc:
        return None, f"Erro de rede ao acessar {url}: {exc}"


@tool("extrair_markdown")
def extract_markdown(url: str, max_chars: int = 6000) -> str:
    """Baixa uma página e converte o conteúdo principal para markdown.

    Tenta primeiro curl_cffi (fingerprint de Chrome) e cai para requests +
    BeautifulSoup. Remove scripts, estilos, navegação e rodapés, e converte o
    conteúdo restante para markdown.

    Args:
        url: URL da página a ser extraída.
        max_chars: Limite de caracteres do conteúdo retornado (padrão 6000).

    Returns:
        Conteúdo da página em markdown, com título e URL de origem.
    """
    _throttle()
    resp, erro = _download(url)
    if erro:
        return erro

    if not getattr(resp, "apparent_encoding", None):
        resp.encoding = resp.encoding or "utf-8"
    else:
        resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "form"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    content = soup.find("article") or soup.find("main") or soup.body or soup

    body_md = md(str(content), heading_style="ATX", strip=["img", "iframe"])
    body_md = " ".join(body_md.split())

    if len(body_md) > max_chars:
        body_md = body_md[:max_chars] + "..."

    header = f"# {title}\n\nFonte: {url}\n\n" if title else f"Fonte: {url}\n\n"

    try:
        from ..vault.log import log_event

        log_event(f"extrair_markdown: {url}", "scraping")
    except Exception:  # noqa: BLE001
        pass

    return header + body_md

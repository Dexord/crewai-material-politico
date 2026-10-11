import hashlib
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from ..config import get_settings

MAX_SLUG = 70

TIPO_DIR = {
    "log": "log",
    "noticia": "noticias",
    "fato": "fatos",
    "pessoa": "pessoas",
    "organizacao": "organizacoes",
    "tema": "temas",
    "fila": "fila",
}


def vault_dir() -> Path:
    return Path(get_settings().vault_dir)


def ensure_vault() -> None:
    root = vault_dir()
    root.mkdir(parents=True, exist_ok=True)
    for sub in TIPO_DIR.values():
        (root / sub).mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def make_id(tipo: str, text: str, dated: bool = False) -> str:
    prefix = {
        "noticia": "noticia",
        "fato": "fato",
        "pessoa": "pessoa",
        "organizacao": "org",
        "tema": "tema",
        "fila": "fila",
        "log": "log",
    }.get(tipo, tipo)
    base = slugify(text) or "sem-titulo"
    if len(base) > MAX_SLUG:
        digest = hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:6]
        base = base[:MAX_SLUG].rstrip("-") + "-" + digest
    if dated:
        return f"{prefix}-{datetime.now():%Y%m%d}-{base}"
    return f"{prefix}-{base}"


def _serialize(fm: dict, body: str) -> str:
    header = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n\n{body.strip()}\n"


def parse_note(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            return fm, parts[2].strip()
    return {}, text.strip()


def note_path(tipo: str, note_id: str) -> Path:
    sub = TIPO_DIR.get(tipo, tipo)
    return vault_dir() / sub / f"{note_id}.md"


def save_note(fm: dict, body: str = "") -> Path:
    ensure_vault()
    tipo = fm.get("tipo", "nota")
    note_id = fm.get("id") or make_id(tipo, fm.get("titulo") or fm.get("nome", ""))
    fm["id"] = note_id
    path = note_path(tipo, note_id)
    content = _serialize(fm, body)

    last_exc: OSError | None = None
    for attempt in range(4):
        tmp = path.with_suffix(".md.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
            return path
        except OSError as exc:  # noqa: PERF203
            last_exc = exc
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(0.2 * (attempt + 1))

    try:
        path.write_text(content, encoding="utf-8")
        return path
    except OSError:
        if last_exc is not None:
            raise last_exc
        raise


def find_note(note_id: str) -> Path | None:
    ensure_vault()
    for sub in set(TIPO_DIR.values()):
        candidate = vault_dir() / sub / f"{note_id}.md"
        if candidate.exists():
            return candidate
    return None


def read_note(note_id: str) -> tuple[dict, str] | None:
    path = find_note(note_id)
    if not path:
        return None
    return parse_note(path.read_text(encoding="utf-8"))


def update_frontmatter(note_id: str, **fields) -> bool:
    found = read_note(note_id)
    if not found:
        return False
    fm, body = found
    fm.update(fields)
    save_note(fm, body)
    return True


def all_notes(tipo: str | None = None) -> list[tuple[dict, str, Path]]:
    ensure_vault()
    subs = [TIPO_DIR[tipo]] if tipo in TIPO_DIR else list(set(TIPO_DIR.values()))
    out: list[tuple[dict, str, Path]] = []
    for sub in subs:
        for path in sorted((vault_dir() / sub).glob("*.md")):
            fm, body = parse_note(path.read_text(encoding="utf-8"))
            out.append((fm, body, path))
    return out


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def search_notes(term: str, tipo: str | None = None, limite: int = 20) -> list[dict]:
    term_n = normalize(term).strip()
    if not term_n:
        return []

    pesos = {"titulo": 3, "nome": 3, "afirmacao": 3, "tags": 2, "fonte": 1, "source_url": 1, "id": 1}
    hits: list[dict] = []
    for fm, body, path in all_notes(tipo):
        score = 0
        campos: list[str] = []
        for campo, peso in pesos.items():
            valor = fm.get(campo)
            if not valor:
                continue
            if term_n in normalize(valor):
                score += peso
                campos.append(campo)
        if term_n in normalize(body):
            score += 1
            campos.append("corpo")
        if score:
            hits.append(
                {
                    "id": fm.get("id"),
                    "tipo": fm.get("tipo"),
                    "titulo": fm.get("titulo") or fm.get("nome") or fm.get("afirmacao"),
                    "score": score,
                    "campos": campos,
                    "path": str(path),
                }
            )
    hits.sort(key=lambda h: -h["score"])
    return hits[:limite]

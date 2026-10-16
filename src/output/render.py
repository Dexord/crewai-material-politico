import re
from datetime import datetime
from pathlib import Path


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9à-ú]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "saida"


def save_output(text: str, output_dir: str, tema: str, subdir: str = "") -> Path:
    out = Path(output_dir)
    if subdir:
        out = out / subdir
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out / f"{stamp}-{_slug(tema)}.md"
    path.write_text(f"# Tema: {tema}\n\n{text}\n", encoding="utf-8")
    return path

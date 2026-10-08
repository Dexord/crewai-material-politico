from datetime import datetime

from .vault import find_note, parse_note, save_note, note_path


def log_event(message: str, categoria: str = "acao") -> None:
    stamp = datetime.now()
    note_id = f"log-{stamp:%Y%m%d}"
    path = note_path("log", note_id)

    body = ""
    if path.exists():
        _, body = parse_note(path.read_text(encoding="utf-8"))
    elif (found := find_note(note_id)):
        _, body = parse_note(found.read_text(encoding="utf-8"))

    line = f"- `{stamp:%H:%M:%S}` [{categoria}] {message}"
    body = f"{body}\n{line}".strip() if body else line

    fm = {"id": note_id, "tipo": "log", "data": f"{stamp:%Y-%m-%d}"}
    save_note(fm, body)

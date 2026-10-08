from datetime import datetime

from .vault import all_notes, make_id, save_note, update_frontmatter, slugify


def _normalize_alvo(alvo: str) -> str:
    alvo = str(alvo).strip()
    if alvo.startswith("[[") and alvo.endswith("]]"):
        alvo = alvo[2:-2]
    return alvo.strip()


def existing_alvos() -> set[str]:
    return {
        _normalize_alvo(fm.get("alvo", "")).lower()
        for fm, _, _ in all_notes("fila")
        if fm.get("alvo")
    }


def add_item(
    alvo: str, motivo: str = "", prioridade: int = 3, profundidade: int = 0, origem: str = ""
) -> str | None:
    alvo = _normalize_alvo(alvo)
    if not alvo:
        return None
    if alvo.lower() in existing_alvos():
        return None

    try:
        prioridade = int(prioridade)
    except (TypeError, ValueError):
        prioridade = 3
    try:
        profundidade = int(profundidade)
    except (TypeError, ValueError):
        profundidade = 0

    note_id = make_id("fila", alvo, dated=True)
    fm = {
        "id": note_id,
        "tipo": "fila",
        "status": "pendente",
        "prioridade": prioridade,
        "profundidade": profundidade,
        "alvo": alvo,
        "motivo": motivo or "",
        "origem": origem or "",
        "criado_em": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
    }
    body = f"# Pesquisar: {alvo}\n\n**Motivo:** {motivo or '(nao informado)'}\n"
    save_note(fm, body)
    return note_id


def list_items(status: str | None = None) -> list[dict]:
    items = []
    for fm, _, _ in all_notes("fila"):
        if status and fm.get("status") != status:
            continue
        items.append(fm)
    return items


def next_item() -> dict | None:
    pendentes = list_items("pendente")
    if not pendentes:
        return None
    pendentes.sort(
        key=lambda fm: (
            -int(fm.get("prioridade", 3)),
            int(fm.get("profundidade", 0)),
            fm.get("criado_em", ""),
        )
    )
    return pendentes[0]


def mark_status(note_id: str, status: str) -> bool:
    return update_frontmatter(note_id, status=status)


def pending_count() -> int:
    return len(list_items("pendente"))

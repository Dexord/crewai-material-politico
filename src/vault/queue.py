import re
from datetime import datetime

from ..config import get_settings
from . import entidades
from .vault import all_notes, make_id, normalize, read_note, save_note, update_frontmatter

ID_RE = re.compile(r"^(pessoa|org|organizacao|noticia|fato|tema)-")


def _normalize_alvo(alvo: str) -> str:
    alvo = str(alvo).strip()
    if alvo.startswith("[[") and alvo.endswith("]]"):
        alvo = alvo[2:-2]
    return alvo.strip()


def _chave(alvo: str) -> str:
    a = _normalize_alvo(alvo)
    if ID_RE.match(a):
        found = read_note(a)
        if found:
            a = found[0].get("nome") or found[0].get("titulo") or a
    return entidades.chave(a)


def _blacklist() -> set[str]:
    raw = get_settings().blacklist_alvos or ""
    return {normalize(x).strip() for x in raw.split(",") if x.strip()}


def _blacklisted(alvo: str) -> bool:
    return normalize(alvo).strip() in _blacklist()


def existing_alvos() -> set[str]:
    return {
        _chave(fm.get("alvo", ""))
        for fm, _, _ in all_notes("fila")
        if fm.get("alvo")
    }


def add_item(
    alvo: str,
    motivo: str = "",
    prioridade: int = 3,
    profundidade: int = 0,
    origem: str = "",
    forcar: bool = False,
) -> str | None:
    alvo = _normalize_alvo(alvo)
    if not alvo:
        return None
    chave = _chave(alvo)
    if not chave:
        return None
    if not forcar:
        if _blacklisted(alvo):
            return None
        if chave in existing_alvos():
            return None
        if entidades.coberto(alvo):
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


def reset_em_andamento() -> int:
    total = 0
    for fm, _, _ in all_notes("fila"):
        if fm.get("status") == "em_andamento":
            update_frontmatter(fm["id"], status="pendente")
            total += 1
    return total


def limpar(aplicar: bool = False) -> dict:
    itens = list_items()
    refs_ent = entidades.chaves_entidades()
    concluidos = {_chave(i["alvo"]) for i in itens if i.get("status") == "concluido"}
    vistos: dict[str, str] = {}
    plano: list[dict] = []
    for item in sorted(itens, key=lambda x: x.get("criado_em", "")):
        if item.get("status") != "pendente":
            continue
        alvo = item.get("alvo", "")
        chave = _chave(alvo)
        motivos: list[str] = []
        if ID_RE.match(_normalize_alvo(alvo)):
            motivos.append("alvo e um id")
        if entidades.coberto(alvo, refs_ent):
            motivos.append("ja pesquisado (entidade existe no vault)")
        if chave in concluidos:
            motivos.append("ja concluido")
        if chave in vistos:
            motivos.append(f"duplicado de {vistos[chave]}")
        else:
            vistos[chave] = item["id"]
        if motivos:
            plano.append({"id": item["id"], "alvo": alvo, "motivos": motivos})
    if aplicar:
        for p in plano:
            mark_status(p["id"], "ignorado")
    pendentes = sum(1 for i in itens if i.get("status") == "pendente")
    return {"plano": plano, "pendentes": pendentes, "aplicado": aplicar}

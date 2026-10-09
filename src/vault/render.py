import re

from .vault import all_notes, normalize, read_note, save_note

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
LINK_KEYS = ["entidades", "relacionadas", "mencionado_em", "notas_relacionadas"]
ENTIDADES = ("pessoa", "organizacao")


def _canon(value) -> str:
    m = WIKILINK_RE.search(str(value))
    raw = m.group(1) if m else str(value)
    return normalize(raw).strip()


def _links_in(fm: dict, body: str) -> set[str]:
    ids: set[str] = set()
    for key in LINK_KEYS:
        value = fm.get(key) or []
        if isinstance(value, str):
            value = [value]
        ids.update(_canon(v) for v in value)
    for vinculo in fm.get("vinculos") or []:
        if isinstance(vinculo, dict) and vinculo.get("alvo"):
            ids.add(_canon(vinculo["alvo"]))
    if fm.get("tipo") not in ENTIDADES:
        for target in WIKILINK_RE.findall(body or ""):
            ids.add(_canon(target))
    return {i for i in ids if i}


def render_entidade(fm: dict) -> str:
    nome = fm.get("nome") or fm.get("titulo") or fm.get("id", "")
    linhas = [f"# {nome}"]

    if fm.get("tipo") == "organizacao":
        cats = fm.get("tipo_org") or fm.get("cargos") or []
        rotulo = "Tipo"
    else:
        cats = fm.get("cargos") or fm.get("tipo_org") or []
        rotulo = "Cargos/Funções"
    if cats:
        linhas.append("")
        linhas.append(f"**{rotulo}:** " + "; ".join(str(c) for c in cats))

    vinculos = fm.get("vinculos") or []
    if vinculos:
        linhas.append("")
        linhas.append("## Vínculos")
        for v in vinculos:
            if not isinstance(v, dict):
                continue
            linha = f"- {v.get('tipo', '')} → {v.get('alvo', '')}"
            if v.get("fonte"):
                linha += f" — fonte: {v['fonte']}"
            linhas.append(linha)

    menc = fm.get("mencionado_em") or []
    if menc:
        linhas.append("")
        linhas.append("## Mencionado em")
        for m in menc:
            linhas.append(f"- {m}")

    rel = fm.get("relacionadas") or []
    if rel:
        linhas.append("")
        linhas.append("## Relações")
        for r in rel:
            linhas.append(f"- {r}")

    return "\n".join(linhas) + "\n"


def _normalize_fm(fm: dict) -> dict:
    if fm.get("tipo") == "organizacao":
        cats = fm.get("tipo_org") or fm.get("cargos") or []
        fm["tipo_org"] = list(cats)
        fm.pop("cargos", None)
    else:
        cats = fm.get("cargos") or fm.get("tipo_org") or []
        fm["cargos"] = list(cats)
        fm.pop("tipo_org", None)
    return fm


def sync_entidade(note_id: str) -> bool:
    found = read_note(note_id)
    if not found:
        return False
    fm, _ = found
    if fm.get("tipo") not in ENTIDADES:
        return False
    save_note(_normalize_fm(fm), render_entidade(fm))
    return True


def registrar_mencao(entity_ids, source_id: str) -> None:
    link = f"[[{source_id}]]"
    for eid in entity_ids:
        found = read_note(eid)
        if not found:
            continue
        fm, body = found
        if fm.get("tipo") not in ENTIDADES:
            continue
        menc = fm.get("mencionado_em") or []
        if link not in menc:
            menc.append(link)
        fm["mencionado_em"] = menc
        save_note(fm, render_entidade(fm))


def backfill_mencionado_em() -> int:
    inbound: dict[str, set[str]] = {}
    for fm, body, _ in all_notes():
        src = fm.get("id")
        if not src:
            continue
        for target in _links_in(fm, body):
            inbound.setdefault(target, set()).add(src)

    updated = 0
    for fm, body, _ in all_notes():
        if fm.get("tipo") not in ENTIDADES:
            continue
        nid = _canon(fm.get("id", ""))
        refs = sorted(s for s in inbound.get(nid, set()) if s != fm.get("id"))
        mentioned = [f"[[{s}]]" for s in refs]
        if (fm.get("mencionado_em") or []) != mentioned:
            fm["mencionado_em"] = mentioned
            save_note(_normalize_fm(fm), render_entidade(fm))
            updated += 1
    return updated


def sync_entidades() -> int:
    total = 0
    for fm, _, _ in all_notes():
        if fm.get("tipo") not in ENTIDADES:
            continue
        total += 1
        _normalize_fm(fm)
        save_note(fm, render_entidade(fm))
    return total


def atualizar_entidades() -> dict:
    menc = backfill_mencionado_em()
    total = sync_entidades()
    return {"mencionado_atualizado": menc, "entidades": total}

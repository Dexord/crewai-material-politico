import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from ..config import get_settings
from . import entidades
from .vault import all_notes, make_id, normalize, read_note

ID_RE = re.compile(r"^(pessoa|org|organizacao|noticia|fato|tema)-")
DATA_FMT = "%Y-%m-%d %H:%M:%S"
STATUS_ATIVOS = ("pendente", "em_andamento")


def _path() -> Path:
    return Path(get_settings().estado_dir) / "pesquisa.json"


def _load() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("itens", [])
    except json.JSONDecodeError:
        return []


def _save(itens: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"itens": itens}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def salvar_itens(itens: list[dict]) -> None:
    _save(itens)


def carregar_itens() -> list[dict]:
    return _load()


def _dt(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, DATA_FMT)
    except (TypeError, ValueError):
        return None


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
    return {_chave(i.get("alvo", "")) for i in _load() if i.get("alvo")}


def add_item(
    alvo: str,
    motivo: str = "",
    prioridade: int = 3,
    profundidade: int = 0,
    origem: str = "",
    forcar: bool = False,
    revisitar: bool = False,
    desde: str = "",
) -> str | None:
    alvo = _normalize_alvo(alvo)
    if not alvo:
        return None
    chave = _chave(alvo)
    if not chave:
        return None

    itens = _load()
    if not forcar:
        if _blacklisted(alvo):
            return None
        if any(
            i.get("status") in STATUS_ATIVOS and _chave(i.get("alvo", "")) == chave
            for i in itens
        ):
            return None
        limite = datetime.now() - timedelta(days=int(get_settings().frescor_dias))
        for i in itens:
            if i.get("status") != "concluido" or _chave(i.get("alvo", "")) != chave:
                continue
            dt = _dt(i.get("concluido_em") or i.get("criado_em") or "")
            if dt and dt >= limite:
                return None
        if not revisitar and entidades.coberto(alvo):
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
    itens.append(
        {
            "id": note_id,
            "tipo": "fila",
            "status": "pendente",
            "prioridade": prioridade,
            "profundidade": profundidade,
            "alvo": alvo,
            "motivo": motivo or "",
            "origem": origem or "",
            "criado_em": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            "concluido_em": "",
            "tentativas": 0,
            "desde": desde or "",
        }
    )
    _save(itens)
    return note_id


def list_items(status: str | None = None) -> list[dict]:
    itens = _load()
    if status:
        itens = [i for i in itens if i.get("status") == status]
    return itens


def next_item() -> dict | None:
    pendentes = list_items("pendente")
    if not pendentes:
        return None
    pendentes.sort(
        key=lambda i: (
            -int(i.get("prioridade", 3)),
            int(i.get("profundidade", 0)),
            i.get("criado_em", ""),
        )
    )
    return pendentes[0]


def mark_status(note_id: str, status: str) -> bool:
    itens = _load()
    for item in itens:
        if item.get("id") != note_id:
            continue
        item["status"] = status
        if status == "concluido":
            item["concluido_em"] = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        if status == "em_andamento":
            item["tentativas"] = int(item.get("tentativas", 0)) + 1
        _save(itens)
        return True
    return False


def pending_count() -> int:
    return len(list_items("pendente"))


def reset_em_andamento() -> int:
    itens = _load()
    total = 0
    for item in itens:
        if item.get("status") == "em_andamento":
            item["status"] = "pendente"
            total += 1
    if total:
        _save(itens)
    return total


def limpar(aplicar: bool = False) -> dict:
    itens = _load()
    refs_ent = entidades.chaves_entidades()
    concluidos = {
        _chave(i.get("alvo", "")) for i in itens if i.get("status") == "concluido"
    }
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
        alvos = {p["id"] for p in plano}
        for item in itens:
            if item.get("id") in alvos:
                item["status"] = "ignorado"
        _save(itens)
    pendentes = sum(1 for i in itens if i.get("status") == "pendente")
    return {"plano": plano, "pendentes": pendentes, "aplicado": aplicar}


def revisitar(
    dias: int | None = None,
    top: int | None = None,
    aleatorio: int | None = None,
) -> list[dict]:
    from . import index as gi

    settings = get_settings()
    dias = int(settings.frescor_dias if dias is None else dias)
    top = int(settings.revisitar_top if top is None else top)
    aleatorio = int(settings.revisitar_aleatorio if aleatorio is None else aleatorio)

    itens = _load()
    ativos = {
        _chave(i.get("alvo", "")) for i in itens if i.get("status") in STATUS_ATIVOS
    }
    ultima: dict[str, str] = {}
    for i in itens:
        if i.get("status") != "concluido":
            continue
        k = _chave(i.get("alvo", ""))
        if not k:
            continue
        ce = i.get("concluido_em") or i.get("criado_em") or ""
        if k not in ultima or ce > ultima[k]:
            ultima[k] = ce

    limite = datetime.now() - timedelta(days=dias)
    conexoes = {x["id"]: x["conexoes"] for x in gi.most_connected(limit=10**9)}

    candidatos: list[dict] = []
    for fm, _, _ in all_notes():
        if fm.get("tipo") not in ("pessoa", "organizacao"):
            continue
        nome = fm.get("nome") or ""
        k = _chave(nome)
        if not nome or not k or k in ativos:
            continue
        ce = ultima.get(k, "")
        if ce:
            dt = _dt(ce)
            if dt and dt >= limite:
                continue
        candidatos.append(
            {"alvo": nome, "desde": ce, "conexoes": conexoes.get(fm.get("id", ""), 0)}
        )

    candidatos.sort(key=lambda c: -c["conexoes"])
    escolhidos = candidatos[: max(0, top)]
    resto = candidatos[len(escolhidos) :]
    if aleatorio and resto:
        escolhidos += random.sample(resto, min(aleatorio, len(resto)))

    criados: list[dict] = []
    for c in escolhidos:
        novo_id = add_item(
            c["alvo"],
            motivo=f"revisita (ultima coleta: {c['desde'] or 'nunca'})",
            prioridade=3,
            profundidade=0,
            origem="revisita",
            revisitar=True,
            desde=c["desde"],
        )
        if novo_id:
            criados.append({"id": novo_id, "alvo": c["alvo"], "desde": c["desde"]})
    return criados

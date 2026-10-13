import re
from difflib import SequenceMatcher

from .render import render_entidade
from .vault import all_notes, find_note, normalize, read_note, save_note

ENTIDADES = ("pessoa", "organizacao")
AUTO_LIMIAR = 0.95
REPORTAR_LIMIAR = 0.8

HONORIFICOS = {
    "pastor", "pastora", "dr", "dra", "sr", "sra", "senador", "senadora",
    "deputado", "deputada", "ministro", "ministra", "presidente", "ex",
}
PARTICULAS = {"da", "de", "do", "dos", "das", "e"}
SUFIXOS = {"s", "a", "sa", "ltda", "me", "eireli", "epp"}


def tokens(nome) -> list[str]:
    nome = str(nome or "").split(",")[0]
    nome = normalize(nome)
    toks = re.findall(r"[a-z0-9]+", nome)
    return [t for t in toks if t not in HONORIFICOS and t not in PARTICULAS]


def canonico(nome) -> str:
    return " ".join(tokens(nome))


def chave(nome) -> str:
    sem_parenteses = re.sub(r"\(.*?\)", " ", str(nome or ""))
    return " ".join(t for t in tokens(sem_parenteses) if t not in SUFIXOS)


def chaves_entidades() -> set[str]:
    return {chave(fm.get("nome") or "") for fm in _entidades()}


def nomes_entidades() -> list[str]:
    return [fm.get("nome") for fm in _entidades() if fm.get("nome")]


def coberto(nome: str, refs: set[str] | None = None) -> bool:
    at = chave(nome).split()
    if not at:
        return False
    for b in refs if refs is not None else chaves_entidades():
        bt = b.split()
        if not bt:
            continue
        if at == bt:
            return True
        n = min(len(at), len(bt))
        if at[:n] == bt[:n]:
            return True
    return False


def score(nome: str, alvo_fm: dict) -> tuple[float, str]:
    a = tokens(nome)
    b = tokens(alvo_fm.get("nome") or "")

    for alias in alvo_fm.get("aliases") or []:
        if a and set(a) == set(tokens(alias)):
            return 1.0, "alias"
    if not a or not b:
        return 0.0, ""
    if a == b:
        return 1.0, "nome igual"
    if sorted(a) == sorted(b):
        return 1.0, "tokens iguais (ordem)"

    sa, sb = set(a), set(b)
    if a[0] == b[0] and a[-1] == b[-1]:
        if (len(a) >= 2 and sa < sb) or (len(b) >= 2 and sb < sa):
            return 0.90, "subconjunto (mesmo primeiro/ultimo) — REVISAR"

    if len(a) == 1 and a[0] in sb and len(a[0]) <= 6:
        return 0.8, f"sigla? ('{a[0]}')"
    if len(b) == 1 and b[0] in sa and len(b[0]) <= 6:
        return 0.8, f"sigla? ('{b[0]}')"

    if sa < sb and len(a) >= 2 and a[0] == b[0]:
        return 0.82, "prefixo subconjunto"

    ratio = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    if ratio >= 0.90:
        return 0.85, f"string similar ({ratio:.2f})"
    if a[0] == b[0] and a[-1] == b[-1] and len(sa & sb) >= 2:
        return 0.80, "mesmo primeiro/ultimo"
    return 0.0, ""


def _entidades(tipo: str | None = None):
    tipos = (tipo,) if tipo else ENTIDADES
    return [fm for fm, _, _ in all_notes() if fm.get("tipo") in tipos]


def candidatos(nome: str, tipo: str | None = None) -> list[dict]:
    out = []
    for fm in _entidades(tipo):
        s, motivo = score(nome, fm)
        if s >= REPORTAR_LIMIAR:
            out.append({"id": fm.get("id"), "nome": fm.get("nome"), "score": s, "motivo": motivo})
    out.sort(key=lambda x: -x["score"])
    return out


def resolver(nome: str, tipo: str | None = None, limiar: float = AUTO_LIMIAR) -> dict | None:
    for cand in candidatos(nome, tipo):
        if cand["score"] >= limiar:
            return cand
    return None


def candidatos_pares(limiar: float = REPORTAR_LIMIAR) -> list[dict]:
    ents = [(fm["id"], fm.get("nome") or "", fm.get("tipo")) for fm in _entidades()]
    pares = []
    for i in range(len(ents)):
        for j in range(i + 1, len(ents)):
            id1, n1, t1 = ents[i]
            id2, n2, t2 = ents[j]
            if t1 != t2:
                continue
            s, motivo = score(n1, {"nome": n2})
            if s >= limiar:
                pares.append(
                    {"a": id1, "nome_a": n1, "b": id2, "nome_b": n2, "score": s, "motivo": motivo}
                )
    return pares


def _clusters(pares: list[dict]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    nomes = {}
    for p in pares:
        nomes[p["a"]] = p["nome_a"]
        nomes[p["b"]] = p["nome_b"]
        union(p["a"], p["b"])
    grupos: dict[str, set] = {}
    for nid in nomes:
        grupos.setdefault(find(nid), set()).add(nid)
    return [sorted(v) for v in grupos.values() if len(v) > 1]


def _peso(fm: dict) -> int:
    return len(fm.get("vinculos") or []) + len(fm.get("mencionado_em") or []) + len(fm.get("aliases") or [])


def _reescrever_links(antigo: str, novo: str) -> int:
    alvo = f"[[{antigo}]]"
    novo_link = f"[[{novo}]]"
    total = 0
    for _, _, path in all_notes():
        text = path.read_text(encoding="utf-8")
        if alvo in text:
            path.write_text(text.replace(alvo, novo_link), encoding="utf-8")
            total += 1
    return total


def fundir(id_a: str, id_b: str) -> str:
    if id_a == id_b:
        return "ids iguais"
    fa = read_note(id_a)
    fb = read_note(id_b)
    if not fa or not fb:
        return "nota nao encontrada"
    fma, _ = fa
    fmb, _ = fb
    if fma.get("tipo") != fmb.get("tipo"):
        return "tipos diferentes"

    chave = "tipo_org" if fma.get("tipo") == "organizacao" else "cargos"
    fma[chave] = sorted(set((fma.get(chave) or []) + (fmb.get(chave) or [])))
    fma["aliases"] = sorted(
        set((fma.get("aliases") or []) + [fmb.get("nome")] + (fmb.get("aliases") or []))
    )
    vinculados = list(fma.get("vinculos") or [])
    for v in fmb.get("vinculos") or []:
        if v not in vinculados:
            vinculados.append(v)
    fma["vinculos"] = vinculados
    fma["relacionadas"] = sorted(set((fma.get("relacionadas") or []) + (fmb.get("relacionadas") or [])))
    fma["mencionado_em"] = sorted(set((fma.get("mencionado_em") or []) + (fmb.get("mencionado_em") or [])))
    save_note(fma, render_entidade(fma))

    _reescrever_links(id_b, id_a)
    caminho_b = find_note(id_b)
    if caminho_b:
        caminho_b.unlink()
    return f"fundido: {id_b} -> {id_a}"


def deduplicar(aplicar: bool = False, limiar: float = REPORTAR_LIMIAR) -> dict:
    pares = candidatos_pares(limiar)
    clusters = _clusters(pares)
    plano = []
    for grupo in clusters:
        notas = [read_note(i) for i in grupo]
        notas = [n for n in notas if n]
        if not notas:
            continue
        fm_por_id = {n[0].get("id"): n[0] for n in notas}
        canonico_id = max(grupo, key=lambda i: (_peso(fm_por_id[i]), len(fm_por_id[i].get("nome") or "")))
        auto = min(
            score(fm_por_id[o].get("nome") or "", fm_por_id[canonico_id])[0]
            for o in grupo
            if o != canonico_id
        )
        plano.append({"canonico": canonico_id, "membros": grupo, "auto": auto >= AUTO_LIMIAR})

    resultado = {"pares": pares, "clusters": clusters, "plano": plano, "migrados": [], "aplicado": aplicar}
    if aplicar:
        for item in plano:
            if not item["auto"]:
                continue
            for membro in item["membros"]:
                if membro != item["canonico"]:
                    fundir(item["canonico"], membro)
                    resultado["migrados"].append(membro)
    return resultado

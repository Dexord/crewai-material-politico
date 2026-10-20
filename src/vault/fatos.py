import re
import unicodedata

from .vault import all_notes, find_note, save_note

_STOP = frozenset(
    {
        "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "no", "na",
        "nos", "nas", "que", "para", "com", "por", "um", "uma", "ao", "aos", "se",
        "foi", "ser", "pelo", "pela", "sobre", "como", "mais", "nao", "seu", "sua",
        "the", "of", "and",
    }
)
_REL_FIELDS = ("entidades", "relacionadas", "mencionado_em", "notas_relacionadas")


def _tokens(text: str) -> frozenset[str]:
    s = (
        unicodedata.normalize("NFKD", str(text))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return frozenset(
        t for t in re.findall(r"[a-z0-9]+", s) if len(t) >= 2 and t not in _STOP
    )


def _similaridade(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    jaccard = inter / len(a | b)
    menor = min(len(a), len(b))
    contencao = inter / menor
    if menor >= 8 and contencao >= 0.90:
        return max(jaccard, contencao)
    return jaccard


def _merge_fontes(dest: dict, src: dict) -> None:
    fontes = dest.get("fontes")
    if not isinstance(fontes, list):
        fontes = []
    if (dest.get("fonte") or dest.get("source_url")) and not fontes:
        fontes.append({"fonte": dest.get("fonte", ""), "url": dest.get("source_url", "")})

    src_fontes = src.get("fontes")
    if isinstance(src_fontes, list):
        candidatos = src_fontes
    elif src.get("fonte") or src.get("source_url"):
        candidatos = [{"fonte": src.get("fonte", ""), "url": src.get("source_url", "")}]
    else:
        candidatos = []
    for novo in candidatos:
        if not isinstance(novo, dict):
            continue
        if not _fonte_existe(fontes, novo):
            fontes.append(novo)
    dest["fontes"] = fontes

    urls = dest.get("source_urls")
    if not isinstance(urls, list):
        urls = []
    for url in [dest.get("source_url"), src.get("source_url")] + list(
        src.get("source_urls") or []
    ):
        if url and url not in urls:
            urls.append(url)
    dest["source_urls"] = urls


def _fonte_existe(fontes: list, novo: dict) -> bool:
    for f in fontes:
        if not isinstance(f, dict):
            continue
        if novo.get("url"):
            if f.get("url") == novo.get("url"):
                return True
        elif not f.get("url") and f.get("fonte") == novo.get("fonte"):
            return True
    return False


def _merge_lista(dest: dict, src: dict, campo: str) -> None:
    atual = dest.get(campo)
    if not isinstance(atual, list):
        atual = []
    for item in src.get(campo) or []:
        if item and item not in atual:
            atual.append(item)
    dest[campo] = atual


def _rewrite_links(mapping: dict[str, str]) -> int:
    if not mapping:
        return 0
    padrao = re.compile(
        r"\[\[(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")(\|[^\]]*)?\]\]"
    )

    def troca(texto: str) -> str:
        return padrao.sub(lambda m: f"[[{mapping[m.group(1)]}{m.group(2) or ''}]]", texto)

    alterados = 0
    for fm, body, _ in all_notes():
        mudou = False
        for campo in _REL_FIELDS:
            valor = fm.get(campo)
            if not isinstance(valor, list):
                continue
            novo = [troca(str(v)) if isinstance(v, str) else v for v in valor]
            if novo != valor:
                fm[campo] = novo
                mudou = True
        vinculos = fm.get("vinculos")
        if isinstance(vinculos, list):
            for vinculo in vinculos:
                if not isinstance(vinculo, dict):
                    continue
                alvo = vinculo.get("alvo")
                if isinstance(alvo, str) and troca(alvo) != alvo:
                    vinculo["alvo"] = troca(alvo)
                    mudou = True
        novo_body = troca(body) if body else body
        if novo_body != body:
            body = novo_body
            mudou = True
        if mudou:
            save_note(fm, body)
            alterados += 1
    return alterados


def deduplicar_fatos(limiar: float = 0.85, aplicar: bool = False) -> dict:
    fatos = [(fm, body, path) for fm, body, path in all_notes("fato") if fm.get("afirmacao")]
    tokens = [_tokens(fm.get("afirmacao", "")) for fm, _, _ in fatos]

    indice: dict[str, list[int]] = {}
    for i, tks in enumerate(tokens):
        for t in tks:
            indice.setdefault(t, []).append(i)

    ordem = sorted(
        range(len(fatos)),
        key=lambda i: (-len(fatos[i][0].get("afirmacao") or ""), i),
    )
    atribuido = [False] * len(fatos)
    clusters: list[dict] = []
    for i in ordem:
        if atribuido[i]:
            continue
        candidatos: set[int] = set()
        for t in tokens[i]:
            lista = indice.get(t, [])
            if len(lista) <= 500:
                candidatos.update(lista)
        membros = []
        ents_canonico = {str(x) for x in (fatos[i][0].get("entidades") or [])}
        for j in candidatos:
            if j == i or atribuido[j]:
                continue
            ta, tb = tokens[i], tokens[j]
            inter = len(ta & tb)
            if not inter:
                continue
            jaccard = inter / len(ta | tb)
            menor = min(len(ta), len(tb))
            contencao = inter / menor
            ok = jaccard >= limiar
            if not ok and menor >= 8 and contencao >= 0.90:
                ents_membro = {str(x) for x in (fatos[j][0].get("entidades") or [])}
                ok = ents_membro <= ents_canonico
            if ok:
                membros.append(j)
        if not membros:
            continue
        atribuido[i] = True
        for j in membros:
            atribuido[j] = True
        clusters.append(
            {
                "canonico": fatos[i][0].get("id", ""),
                "membros": [fatos[k][0].get("id", "") for k in membros],
                "tamanho": len(membros) + 1,
            }
        )

    aplicado = {"mesclados": 0, "removidos": 0, "links_reescritos": 0}
    if aplicar and clusters:
        mapping: dict[str, str] = {}
        for cluster in clusters:
            canonico = cluster["canonico"]
            achado = None
            for fm, body, path in fatos:
                if fm.get("id") == canonico:
                    achado = (fm, body, path)
                    break
            if not achado:
                continue
            fm_dest, body_dest, _ = achado
            for membro_id in cluster["membros"]:
                src = next((fm for fm, _, _ in fatos if fm.get("id") == membro_id), None)
                if not src:
                    continue
                _merge_fontes(fm_dest, src)
                for campo in ("entidades", "relacionadas"):
                    _merge_lista(fm_dest, src, campo)
                if not fm_dest.get("data_fato") and src.get("data_fato"):
                    fm_dest["data_fato"] = src["data_fato"]
                if len(src.get("afirmacao") or "") > len(fm_dest.get("afirmacao") or ""):
                    fm_dest["afirmacao"] = src["afirmacao"]
                    body_dest = src["afirmacao"]
                mapping[membro_id] = canonico
            save_note(fm_dest, body_dest)
            aplicado["mesclados"] += 1

        aplicado["links_reescritos"] = _rewrite_links(mapping)

        for membro_id in mapping:
            caminho = find_note(membro_id)
            if caminho:
                caminho.unlink()
                aplicado["removidos"] += 1

    return {
        "clusters": clusters,
        "pares": sum(c["tamanho"] - 1 for c in clusters),
        "aplicado": aplicar,
        **aplicado,
    }

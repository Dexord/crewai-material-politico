import re
import unicodedata
from datetime import datetime

from crewai.tools import tool

from ..config import get_settings
from ..vault import entidades
from ..vault import index as graph_index
from ..vault import queue as fila
from ..vault.render import registrar_mencao, render_entidade
from ..vault.vault import (
    all_notes,
    find_note,
    make_id,
    parse_note,
    read_note,
    save_note,
    slugify,
)


def _split(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _link(note_id: str) -> str:
    return f"[[{note_id}]]"


def _compact_fm(fm: dict, max_menc: int = 5) -> dict:
    out = dict(fm)
    menc = out.get("mencionado_em")
    if isinstance(menc, list) and len(menc) > max_menc:
        out["mencionado_em"] = menc[:max_menc] + [f"... (+{len(menc) - max_menc})"]
    return out


def _compact_body(body: str, max_chars: int = 2000) -> str:
    marcador = "## Mencionado em"
    if marcador in body:
        antes, _, depois = body.partition(marcador)
        total = sum(1 for l in depois.splitlines() if l.strip().startswith("- "))
        body = (
            antes.rstrip()
            + f"\n\n{marcador}\n- ({total} referencias omitidas; abra a nota no vault)\n"
        )
    if len(body) > max_chars:
        body = body[:max_chars] + "\n..."
    return body


def _resolve_id(nome: str, guess_tipo: str = "pessoa") -> str:
    nome = str(nome).strip()
    nome = nome[2:-2] if nome.startswith("[[") and nome.endswith("]]") else nome
    if not nome:
        return ""
    if find_note(nome):
        return nome
    hit = entidades.resolver(nome)
    if hit:
        return hit["id"]
    alvo_slug = slugify(nome)
    for fm, _, _ in all_notes():
        note_id = fm.get("id", "")
        nome_nota = fm.get("nome") or fm.get("titulo") or ""
        if slugify(nome_nota) == alvo_slug or slugify(note_id) == alvo_slug:
            return note_id
    return make_id(guess_tipo, nome)


def _merge_alias(fm: dict, nome: str) -> None:
    if entidades.canonico(nome) != entidades.canonico(fm.get("nome") or ""):
        aliases = set(fm.get("aliases") or [])
        aliases.add(nome)
        fm["aliases"] = sorted(aliases)


@tool("salvar_noticia")
def salvar_noticia(
    titulo: str,
    conteudo: str,
    fonte: str = "",
    source_url: str = "",
    tags: str = "",
    entidades: str = "",
    data_fato: str = "",
) -> str:
    """Salva uma noticia no vault como nota markdown.

    Args:
        titulo: Titulo da noticia.
        conteudo: Resumo/conteudo em markdown.
        fonte: Nome do veiculo/fonte.
        source_url: URL da materia.
        tags: Tags separadas por virgula.
        entidades: Pessoas/instituicoes separadas por virgula.
        data_fato: Data do acontecimento (AAAA-MM-DD), quando a materia informar.

    Returns:
        O id da nota salva no vault.
    """
    note_id = make_id("noticia", titulo, dated=True)
    entity_ids = [_resolve_id(e) for e in _split(entidades)]
    fm = {
        "id": note_id,
        "tipo": "noticia",
        "titulo": titulo,
        "data": f"{datetime.now():%Y-%m-%d}",
        "fonte": fonte,
        "source_url": source_url,
        "tags": _split(tags),
        "entidades": [_link(e) for e in entity_ids],
        "relacionadas": [],
    }
    if str(data_fato).strip():
        fm["data_fato"] = str(data_fato).strip()
    save_note(fm, conteudo)
    registrar_mencao(entity_ids, note_id)
    return f"Noticia salva: {note_id}"


_STOP_FATO = frozenset(
    {
        "de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "em", "no", "na",
        "nos", "nas", "que", "para", "com", "por", "um", "uma", "ao", "aos", "se",
        "foi", "ser", "pelo", "pela", "sobre", "como", "mais", "nao", "seu", "sua",
        "the", "of", "and",
    }
)


def _tokens_fato(text: str) -> frozenset[str]:
    s = (
        unicodedata.normalize("NFKD", str(text))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return frozenset(
        t for t in re.findall(r"[a-z0-9]+", s) if len(t) >= 2 and t not in _STOP_FATO
    )


_FATOS_CACHE: list[tuple[frozenset[str], str]] | None = None


def _cache_fatos() -> list[tuple[frozenset[str], str]]:
    global _FATOS_CACHE
    if _FATOS_CACHE is None:
        _FATOS_CACHE = [
            (_tokens_fato(fm.get("afirmacao", "")), fm.get("id", ""))
            for fm, _, _ in all_notes("fato")
            if fm.get("afirmacao")
        ]
    return _FATOS_CACHE


def _fato_similar(tokens: frozenset[str]) -> tuple[str, float]:
    if not tokens:
        return "", 0.0
    melhor_id, melhor = "", 0.0
    for outros, note_id in _cache_fatos():
        if not outros:
            continue
        inter = len(tokens & outros)
        if not inter:
            continue
        jaccard = inter / len(tokens | outros)
        menor = min(len(tokens), len(outros))
        contencao = inter / menor
        score = jaccard
        if menor >= 8 and contencao >= 0.90:
            score = max(score, contencao)
        if score > melhor:
            melhor, melhor_id = score, note_id
    return melhor_id, melhor


def _fonte_ja_incluida(fontes: list, novo: dict) -> bool:
    for f in fontes:
        if not isinstance(f, dict):
            continue
        if novo.get("url"):
            if f.get("url") == novo["url"]:
                return True
        elif not f.get("url") and f.get("fonte") == novo.get("fonte"):
            return True
    return False


@tool("salvar_fato")
def salvar_fato(
    afirmacao: str, fonte: str, source_url: str = "", entidades: str = "", data_fato: str = ""
) -> str:
    """Salva um fato verificado (afirmacao + fonte) no vault.

    Factos muito parecidos (similaridade >= DEDUPE_FATOS_LIMIAR) NAO criam nota nova:
    sao fundidos no fato existente, acumulando as fontes/URLs e entidades.

    Args:
        afirmacao: O fato, de forma objetiva (de preferencia com a DATA dentro do texto).
        fonte: Fonte que sustenta o fato.
        source_url: URL da fonte.
        entidades: Pessoas/instituicoes envolvidas, separadas por virgula.
        data_fato: Data do acontecimento (AAAA-MM-DD), quando a fonte informar.

    Returns:
        O id da nota de fato (ou do fato existente que recebeu a nova referencia).
    """
    entity_ids = [_resolve_id(e) for e in _split(entidades)]
    tokens = _tokens_fato(afirmacao)
    similar_id, score = _fato_similar(tokens)
    limiar = float(get_settings().dedupe_fatos_limiar)

    if similar_id and score >= limiar:
        existente = read_note(similar_id)
        if existente:
            fm, body = existente
            fontes = fm.get("fontes")
            if not isinstance(fontes, list):
                fontes = []
            if (fm.get("fonte") or fm.get("source_url")) and not fontes:
                fontes.append({"fonte": fm.get("fonte", ""), "url": fm.get("source_url", "")})
            novo = {"fonte": fonte or "", "url": source_url or ""}
            if (novo["fonte"] or novo["url"]) and not _fonte_ja_incluida(fontes, novo):
                fontes.append(novo)
            fm["fontes"] = fontes

            urls = fm.get("source_urls")
            if not isinstance(urls, list):
                urls = []
            for url in (fm.get("source_url"), source_url):
                if url and url not in urls:
                    urls.append(url)
            fm["source_urls"] = urls

            atuais = list(fm.get("entidades") or [])
            for e in entity_ids:
                link = _link(e)
                if link not in atuais:
                    atuais.append(link)
            fm["entidades"] = atuais

            if not fm.get("data_fato") and str(data_fato).strip():
                fm["data_fato"] = str(data_fato).strip()

            if len(afirmacao) > len(fm.get("afirmacao") or ""):
                fm["afirmacao"] = afirmacao
                body = afirmacao

            save_note(fm, body)
            registrar_mencao(entity_ids, similar_id)
            return (
                f"Fato similar ja existente ({similar_id}, similaridade {score:.2f}); "
                f"referencia adicionada ({len(fontes)} fonte(s))."
            )

    note_id = make_id("fato", afirmacao, dated=True)
    fm = {
        "id": note_id,
        "tipo": "fato",
        "afirmacao": afirmacao,
        "fonte": fonte,
        "source_url": source_url,
        "fontes": ([{"fonte": fonte or "", "url": source_url or ""}] if (fonte or source_url) else []),
        "source_urls": ([source_url] if source_url else []),
        "data": f"{datetime.now():%Y-%m-%d}",
        "entidades": [_link(e) for e in entity_ids],
        "relacionadas": [],
    }
    if str(data_fato).strip():
        fm["data_fato"] = str(data_fato).strip()
    save_note(fm, afirmacao)
    registrar_mencao(entity_ids, note_id)
    _cache_fatos().append((tokens, note_id))
    return f"Fato salvo: {note_id}"


@tool("salvar_pessoa")
def salvar_pessoa(nome: str, cargos: str = "") -> str:
    """Cria/atualiza a nota de uma pessoa no vault.

    Args:
        nome: Nome da pessoa.
        cargos: Cargos/funcoes separados por virgula.

    Returns:
        O id da nota da pessoa.
    """
    hit = entidades.resolver(nome, "pessoa")
    if hit:
        note_id = hit["id"]
        fm, _ = read_note(note_id)
        fm["tipo"] = "pessoa"
        fm["cargos"] = sorted(set((fm.get("cargos") or []) + _split(cargos)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
        _merge_alias(fm, nome)
        save_note(fm, render_entidade(fm))
        return f"Pessoa salva: {note_id} (reaproveitada)"

    note_id = make_id("pessoa", nome)
    existing = read_note(note_id)
    if existing:
        fm, _ = existing
        fm["tipo"] = "pessoa"
        fm["cargos"] = sorted(set((fm.get("cargos") or []) + _split(cargos)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
        _merge_alias(fm, nome)
    else:
        fm = {
            "id": note_id,
            "tipo": "pessoa",
            "nome": nome,
            "cargos": _split(cargos),
            "aliases": [],
            "vinculos": [],
            "mencionado_em": [],
        }
    save_note(fm, render_entidade(fm))
    return f"Pessoa salva: {note_id}"


@tool("salvar_organizacao")
def salvar_organizacao(nome: str, tipo_org: str = "") -> str:
    """Cria/atualiza a nota de uma ORGANIZACAO no vault.

    Use para instituicoes: empresas, bancos, partidos, orgaos publicos, tribunais,
    delegacias, associacoes, fundacoes, faccoes/organizacoes criminosas, etc.
    Para pessoas fisicas, use salvar_pessoa.

    Args:
        nome: Nome da organizacao.
        tipo_org: Categoria(s) separadas por virgula (ex: empresa, banco, partido,
            orgao publico, faccao, associacao).

    Returns:
        O id da nota da organizacao.
    """
    hit = entidades.resolver(nome, "organizacao")
    if hit:
        note_id = hit["id"]
        fm, _ = read_note(note_id)
        fm["tipo"] = "organizacao"
        fm["tipo_org"] = sorted(set((fm.get("tipo_org") or []) + _split(tipo_org)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
        _merge_alias(fm, nome)
        save_note(fm, render_entidade(fm))
        return f"Organizacao salva: {note_id} (reaproveitada)"

    note_id = make_id("organizacao", nome)
    existing = read_note(note_id)
    if existing:
        fm, _ = existing
        fm["tipo"] = "organizacao"
        fm["tipo_org"] = sorted(set((fm.get("tipo_org") or []) + _split(tipo_org)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
        _merge_alias(fm, nome)
    else:
        fm = {
            "id": note_id,
            "tipo": "organizacao",
            "nome": nome,
            "tipo_org": _split(tipo_org),
            "aliases": [],
            "vinculos": [],
            "mencionado_em": [],
        }
    save_note(fm, render_entidade(fm))
    return f"Organizacao salva: {note_id}"


@tool("registrar_vinculo")
def registrar_vinculo(pessoa: str, tipo: str, alvo: str, fonte: str) -> str:
    """Registra um vinculo documentado entre uma pessoa e um alvo (pessoa, org, evento).

    A fonte e obrigatoria. Nao registre inferencia sem documento; use apenas
    status documentado (ex.: assessor, socio, condenado, reu, investigado).

    Args:
        pessoa: Nome/id da pessoa (vinculo sai dela).
        tipo: Tipo do vinculo.
        alvo: Nome/id do alvo do vinculo.
        fonte: URL ou referencia que documenta o vinculo.

    Returns:
        Confirmacao do registro.
    """
    if not str(fonte).strip():
        return "REJEITADO: vinculo sem fonte. Registre apenas vinculos documentados."

    pessoa_id = _resolve_id(pessoa, guess_tipo="pessoa")
    if not find_note(pessoa_id):
        salvar_pessoa.run(nome=pessoa)
    alvo_id = _resolve_id(alvo, guess_tipo="pessoa")

    fm, _ = read_note(pessoa_id)
    vinculos = fm.get("vinculos") or []
    entry = {"tipo": tipo, "alvo": _link(alvo_id), "fonte": fonte}
    if entry not in vinculos:
        vinculos.append(entry)
    fm["vinculos"] = vinculos
    save_note(fm, render_entidade(fm))
    return f"Vinculo registrado: {pessoa_id} --{tipo}--> {alvo_id}"


@tool("relacionar")
def relacionar(origem: str, destino: str, tipo_relacao: str = "", fonte: str = "") -> str:
    """Relaciona duas notas do vault (link bidirecional).

    Args:
        origem: Id/nome da nota de origem.
        destino: Id/nome da nota de destino.
        tipo_relacao: Rotulo da relacao (ex.: mesmo-tema, contradiz, confirma).
        fonte: Fonte que justifica a relacao (opcional).

    Returns:
        Confirmacao do relacionamento.
    """
    origem_id = _resolve_id(origem)
    destino_id = _resolve_id(destino)
    if not origem_id or not destino_id or origem_id == destino_id:
        return "Relacao invalida."

    for a, b in ((origem_id, destino_id), (destino_id, origem_id)):
        found = read_note(a)
        if not found:
            continue
        fm, body = found
        relacionadas = fm.get("relacionadas") or []
        link = _link(b)
        if link not in relacionadas:
            relacionadas.append(link)
        fm["relacionadas"] = relacionadas
        if fm.get("tipo") in ("pessoa", "organizacao"):
            body = render_entidade(fm)
        save_note(fm, body)
    return f"Relacionado: {origem_id} <-> {destino_id}"


@tool("ler_nota")
def ler_nota(id: str) -> str:
    """Le uma nota do vault pelo seu id.

    Args:
        id: Id da nota.

    Returns:
        Conteudo da nota (frontmatter + corpo) ou aviso de nao encontrada.
    """
    found = read_note(id)
    if not found:
        return f"Nota nao encontrada: {id}"
    fm, body = found
    return f"# frontmatter\n{_compact_fm(fm)}\n\n# corpo\n{_compact_body(body)}"


@tool("buscar_notas")
def buscar_notas(termo: str, tipo: str = "") -> str:
    """Busca notas no vault por termo (titulo/nome/corpo/frontmatter).

    Args:
        termo: Termo de busca.
        tipo: Filtrar por tipo (noticia, fato, pessoa, organizacao, tema, fila). Vazio = todos.

    Returns:
        Lista de notas encontradas.
    """
    from ..vault.vault import search_notes

    hits = search_notes(termo, tipo or None, limite=8)
    if not hits:
        return f"Nenhuma nota encontrada para: {termo}"
    lines = [
        f"- [{h['tipo']}] {h['titulo']} ({h['id']}) — score {h['score']} "
        f"[{'/'.join(h['campos'])}]"
        for h in hits
    ]
    return f"Resultados para '{termo}' (mais relevantes primeiro):\n" + "\n".join(lines)


@tool("consultar_grafo")
def consultar_grafo(id: str) -> str:
    """Mostra as conexoes de uma nota no grafo (quem aponta para ela e para quem ela aponta).

    Args:
        id: Id da nota.

    Returns:
        Vizinhos no grafo.
    """
    data = graph_index.neighbors(_resolve_id(id) or id)
    if "erro" in data:
        return data["erro"]
    return (
        f"Nota: {data['nota']}\n"
        f"Aponta para: {', '.join(data['aponta_para']) or '(nenhum)'}\n"
        f"Apontada por: {', '.join(data['apontado_por']) or '(nenhum)'}"
    )


@tool("listar_dangling")
def listar_dangling(limite: int = 40) -> str:
    """Lista alvos (pessoas/instituicoes) citados no grafo SEM nota — lacunas a pesquisar.

    Ordenado por centralidade (numero de notas que citam o alvo). Use para enfileirar
    alvos como SEMENTES (profundidade 0) e aprofundar o grafo. Siglas e nomes que ja
    resolvem para uma entidade existente (ou cobertos por ela) sao filtrados.

    Args:
        limite: Quantidade maxima de alvos (padrao 40).

    Returns:
        Lista de alvos sem nota, com id e numero de citacoes.
    """
    brutos = graph_index.dangling(max(limite * 4, limite))
    alvos = [a for a in brutos if not _alvo_coberto(a)][:limite]
    if not alvos:
        return "Nenhum alvo novo citado sem nota (apos filtrar siglas/cobertos)."
    lines = [
        f"- {a['nome']} (id: {a['id']}) — citado em {a['citacoes']} notas" for a in alvos
    ]
    return "Alvos citados sem nota (candidatos a pesquisa como semente):\n" + "\n".join(lines)


def _alvo_coberto(alvo: dict) -> bool:
    for chave in (alvo.get("nome", ""), alvo.get("id", "")):
        if not chave:
            continue
        if entidades.coberto(chave):
            return True
        if entidades.resolver(chave):
            return True
    return False


@tool("adicionar_fila")
def adicionar_fila(
    alvo: str, motivo: str, prioridade: int = 3, profundidade: int = 0, origem: str = ""
) -> str:
    """Adiciona um alvo (pessoa/tema) a fila de pesquisa, se ainda nao existir.

    Args:
        alvo: Pessoa, instituicao ou tema a pesquisar.
        motivo: Por que vale pesquisar.
        prioridade: 1 (baixa) a 5 (alta).
        profundidade: Nivel de expansao (0 = semente).
        origem: Id da nota que originou este item.

    Returns:
        Confirmacao ou aviso de item duplicado.
    """
    note_id = fila.add_item(alvo, motivo, prioridade, profundidade, origem)
    if not note_id:
        return f"Ignorado (ja existe na fila ou alvo na blacklist): {alvo}"
    return f"Adicionado a fila: {alvo} ({note_id})"


@tool("consultar_fila")
def consultar_fila(status: str = "") -> str:
    """Lista os itens da fila de pesquisa.

    Args:
        status: Filtrar por status (pendente, em_andamento, concluido, ignorado). Vazio = todos.

    Returns:
        Itens da fila.
    """
    items = fila.list_items(status or None)
    if not items:
        return "Fila vazia."
    lines = [
        f"- [{i.get('status')}] p{i.get('prioridade')} d{i.get('profundidade')} "
        f"{i.get('alvo')} ({i.get('id')})"
        for i in items
    ]
    return "\n".join(lines)


@tool("marcar_concluido")
def marcar_concluido(id: str) -> str:
    """Marca um item da fila (ou nota) como concluido.

    Args:
        id: Id da nota de fila.

    Returns:
        Confirmacao.
    """
    if fila.mark_status(id, "concluido"):
        return f"Concluido: {id}"
    return f"Nao foi possivel marcar: {id}"

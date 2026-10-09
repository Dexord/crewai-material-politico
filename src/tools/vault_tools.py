from datetime import datetime

from crewai.tools import tool

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


def _resolve_id(nome: str, guess_tipo: str = "pessoa") -> str:
    nome = str(nome).strip()
    nome = nome[2:-2] if nome.startswith("[[") and nome.endswith("]]") else nome
    if not nome:
        return ""
    if find_note(nome):
        return nome
    alvo_slug = slugify(nome)
    for fm, _, _ in all_notes():
        note_id = fm.get("id", "")
        nome_nota = fm.get("nome") or fm.get("titulo") or ""
        if slugify(nome_nota) == alvo_slug or slugify(note_id) == alvo_slug:
            return note_id
    return make_id(guess_tipo, nome)


@tool("salvar_noticia")
def salvar_noticia(
    titulo: str, conteudo: str, fonte: str = "", source_url: str = "", tags: str = "", entidades: str = ""
) -> str:
    """Salva uma noticia no vault como nota markdown.

    Args:
        titulo: Titulo da noticia.
        conteudo: Resumo/conteudo em markdown.
        fonte: Nome do veiculo/fonte.
        source_url: URL da materia.
        tags: Tags separadas por virgula.
        entidades: Pessoas/instituicoes separadas por virgula.

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
    save_note(fm, conteudo)
    registrar_mencao(entity_ids, note_id)
    return f"Noticia salva: {note_id}"


@tool("salvar_fato")
def salvar_fato(
    afirmacao: str, fonte: str, source_url: str = "", entidades: str = ""
) -> str:
    """Salva um fato verificado (afirmacao + fonte) no vault.

    Args:
        afirmacao: O fato, de forma objetiva.
        fonte: Fonte que sustenta o fato.
        source_url: URL da fonte.
        entidades: Pessoas/instituicoes envolvidas, separadas por virgula.

    Returns:
        O id da nota de fato.
    """
    note_id = make_id("fato", afirmacao, dated=True)
    entity_ids = [_resolve_id(e) for e in _split(entidades)]
    fm = {
        "id": note_id,
        "tipo": "fato",
        "afirmacao": afirmacao,
        "fonte": fonte,
        "source_url": source_url,
        "data": f"{datetime.now():%Y-%m-%d}",
        "entidades": [_link(e) for e in entity_ids],
        "relacionadas": [],
    }
    save_note(fm, afirmacao)
    registrar_mencao(entity_ids, note_id)
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
    note_id = make_id("pessoa", nome)
    existing = read_note(note_id)
    if existing:
        fm, _ = existing
        fm["tipo"] = "pessoa"
        fm["cargos"] = sorted(set((fm.get("cargos") or []) + _split(cargos)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
    else:
        fm = {
            "id": note_id,
            "tipo": "pessoa",
            "nome": nome,
            "cargos": _split(cargos),
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
    note_id = make_id("organizacao", nome)
    existing = read_note(note_id)
    if existing:
        fm, _ = existing
        fm["tipo"] = "organizacao"
        fm["tipo_org"] = sorted(set((fm.get("tipo_org") or []) + _split(tipo_org)))
        fm.setdefault("vinculos", [])
        fm.setdefault("mencionado_em", [])
    else:
        fm = {
            "id": note_id,
            "tipo": "organizacao",
            "nome": nome,
            "tipo_org": _split(tipo_org),
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
    return f"# frontmatter\n{fm}\n\n# corpo\n{body}"


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

    hits = search_notes(termo, tipo or None)
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

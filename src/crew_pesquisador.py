from crewai import Agent, Crew, LLM, Process, Task

from .config import Settings
from .tools.scraper import extract_markdown
from .tools.search import search_web
from .tools.sources import list_sources, read_active_rss
from .tools.vault_tools import (
    adicionar_fila,
    buscar_notas,
    ler_nota,
    registrar_vinculo,
    relacionar,
    salvar_fato,
    salvar_noticia,
    salvar_organizacao,
    salvar_pessoa,
)


def build_pesquisador_crew(settings: Settings) -> Crew:
    llm = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.1,
    )

    pesquisador = Agent(
        role="Pesquisador de Campo",
        goal=(
            "Pesquisar um alvo (tema, pessoa ou instituicao) e persistir no vault os "
            "fatos com fonte e as entidades (pessoas/instituicoes) envolvidas."
        ),
        backstory=(
            "Voce e um pesquisador de campo rigoroso. Nomes de PESSOAS e INSTITUICOES "
            "sao dados de primeira classe para voce: toda materia rende entidades e "
            "vinculos, sempre com fonte. Voce nao inventa e nao infere: registra apenas "
            "o que a fonte sustenta. Status juridico (condenado, reu, investigado) so "
            "entra com documento."
        ),
        tools=[
            search_web,
            extract_markdown,
            read_active_rss,
            list_sources,
            salvar_noticia,
            salvar_fato,
            salvar_pessoa,
            salvar_organizacao,
            registrar_vinculo,
            relacionar,
            adicionar_fila,
            ler_nota,
            buscar_notas,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    tarefa = Task(
        description=(
            "Pesquise o alvo: {alvo}\n"
            "Motivo/contexto: {motivo}\n"
            "Profundidade atual na arvore de pesquisa: {profundidade} "
            "(maximo permitido: {max_depth}).\n\n"
            "Passos:\n"
            "1. Use buscar_na_web e/ou ler_rss_ativos para levantar material sobre o alvo.\n"
            "2. Use extrair_markdown para ler as paginas mais relevantes.\n"
            "3. salvar_fato para cada fato (com fonte) e salvar_noticia para materias relevantes.\n"
            "4. Nomes de PESSOAS e INSTITUICOES sao prioritarios:\n"
            "   - salvar_pessoa para cada PESSOA FISICA citada;\n"
            "   - salvar_organizacao para cada INSTITUICAO citada (empresa, banco, "
            "partido, orgao publico, tribunal, delegacia, associacao, faccao etc.);\n"
            "   - registrar_vinculo (SEMPRE com fonte) para cada relacao "
            "(assessor, socio, aliado, parente, condenado, reu, investigado, etc.);\n"
            "   - inclua as entidades no campo 'entidades' de salvar_fato/salvar_noticia.\n"
            "5. Expanda com moderacao: para cada pessoa/instituicao relevante ainda nao "
            "pesquisada, use adicionar_fila com profundidade = {profundidade} + 1 "
            "(NAO adicione se essa soma passar de {max_depth}).\n"
            "   - Enfileire o NOME da entidade (nunca um id como 'pessoa-...') e nao "
            "re-enfileire quem ja tem nota no vault (buscar_notas).\n"
            "6. Nunca invente fato ou vinculo sem fonte."
        ),
        agent=pesquisador,
        expected_output=(
            "Resumo em markdown do que foi persistido no vault: fatos salvos, materias "
            "salvas, pessoas/instituicoes criadas, vinculos registrados e itens "
            "adicionados a fila de pesquisa."
        ),
    )

    return Crew(agents=[pesquisador], tasks=[tarefa], process=Process.sequential, verbose=True)

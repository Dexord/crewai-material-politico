from crewai import Agent, Crew, LLM, Process, Task

from .config import Settings
from .tools.vault_tools import (
    adicionar_fila,
    buscar_notas,
    consultar_fila,
    consultar_grafo,
    ler_nota,
    registrar_vinculo,
    relacionar,
    salvar_pessoa,
)


def build_investigador_crew(settings: Settings) -> Crew:
    llm = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.1,
    )

    investigador = Agent(
        role="Investigador de Relacoes",
        goal=(
            "Estruturar o vault: extrair entidades, classificar e registrar vinculos e "
            "relacionar as notas; e manter a fila de pesquisa com o que ainda falta investigar."
        ),
        backstory=(
            "Voce e um analista de OSINT que organiza informacao ja coletada. Voce NAO "
            "pesquisa na web: seu trabalho e ler o vault, ligar pessoas, instituicoes e "
            "noticias, e apontar lacunas. Nunca infere culpa: vinculos e status juridico "
            "(condenado, reu, investigado) so entram com fonte documental."
        ),
        tools=[
            ler_nota,
            buscar_notas,
            salvar_pessoa,
            registrar_vinculo,
            relacionar,
            consultar_grafo,
            adicionar_fila,
            consultar_fila,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    tarefa = Task(
        description=(
            "Estruture o vault e mantenha a fila de pesquisa. NAO pesquise na web.\n\n"
            "Passos:\n"
            "1. Revise as notas recentes com buscar_notas e ler_nota (noticias, fatos).\n"
            "2. Para cada pessoa/instituicao citada: salvar_pessoa e registrar_vinculo "
            "(SEMPRE com fonte) para ligar as pessoas entre si e ao candidato/tema.\n"
            "   - Registre apenas vinculos DOCUMENTADOS. Nunca infira.\n"
            "   - Status juridico (condenado, reu, investigado) so com fonte.\n"
            "3. Use relacionar para conectar noticias entre si (mesmo tema, contradicao, "
            "mesma pessoa) e noticias com pessoas.\n"
            "4. Atualize a fila: adicionar_fila para pessoas/temas relevantes que ainda "
            "nao foram pesquisados (com motivo e prioridade).\n"
            "5. Use consultar_grafo e consultar_fila para identificar lacunas do grafo."
        ),
        agent=investigador,
        expected_output=(
            "Resumo em markdown: entidades criadas/atualizadas, vinculos registrados, "
            "relacoes criadas entre notas e itens adicionados a fila de pesquisa."
        ),
    )

    return Crew(agents=[investigador], tasks=[tarefa], process=Process.sequential, verbose=True)

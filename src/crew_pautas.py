from crewai import Agent, Crew, LLM, Process, Task

from .config import Settings
from .crew import TOM_ENQUADRAMENTO
from .tools.scraper import extract_markdown
from .tools.search import search_web
from .tools.vault_tools import buscar_notas, consultar_grafo, ler_nota


def build_pautas_crew(settings: Settings, step_callback=None) -> Crew:
    llm = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.7,
    )

    criador = Agent(
        role="Criador de Pauta",
        goal=(
            "A partir de manchetes atuais dos jornais, cruzar com o grafo de conhecimento e "
            "propor pautas de oposicao ancoradas em fonte."
        ),
        backstory=(
            "Voce e editor de pautas de campanha de oposicao. Le o noticiario, cruza com o "
            "que ja sabemos no grafo e propoe angulos factuais, sempre com fonte. Nao inventa "
            "e nao forca ligacao: se a noticia nao conecta a Flavio/familia/partido/amigos, "
            "ela nao vira pauta."
        ),
        tools=[buscar_notas, ler_nota, consultar_grafo, search_web, extract_markdown],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    tarefa = Task(
        description=(
            "Voce recebe manchetes ATUAIS dos jornais (RSS), ja filtradas por relevancia ao "
            "nosso grafo de conhecimento:\n\n"
            "{noticias}\n\n"
            "Para cada noticia relevante, cruze com o grafo (buscar_notas/ler_nota/"
            "consultar_grafo) e proponha UMA pauta com:\n"
            "- Manchete (ate 12 palavras)\n"
            "- Angulo (a contradicao ou consequencia concreta a explorar)\n"
            "- Entidades ligadas (do grafo)\n"
            "- source_url (a materia)\n"
            "Use buscar_na_web/extrair_markdown se faltar contexto. DESCARTE a noticia se o "
            "ASSUNTO principal for o adversario (ex.: Lula) e Flavio Bolsonaro/familia/"
            "aliados aparecerem apenas de mencao. A pauta tem que ser sobre um problema de "
            "Flavio Bolsonaro, da familia Bolsonaro ou de pessoas proximas do partido e "
            "amigos.\n\n"
            f"{TOM_ENQUADRAMENTO}\n"
            "No maximo 8 pautas. Nao invente; toda pauta precisa de fonte."
        ),
        agent=criador,
        expected_output=(
            "Lista em markdown de ate 8 pautas, cada uma com manchete, angulo, entidades "
            "ligadas e source_url."
        ),
    )

    return Crew(
        agents=[criador],
        tasks=[tarefa],
        process=Process.sequential,
        verbose=True,
        step_callback=step_callback,
    )

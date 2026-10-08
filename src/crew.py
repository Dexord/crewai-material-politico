from crewai import Agent, Crew, LLM, Process, Task

from .config import Settings
from .profiles import profiles_as_markdown
from .tools.scraper import extract_markdown
from .tools.search import search_web
from .tools.sources import list_sources, read_active_rss, read_rss

TOM_ENQUADRAMENTO = (
    "## TOM E ENQUADRAMENTO (obrigatorio)\n"
    "Todo material e de OPOSICAO. O objetivo e ELUCIDAR UM PROBLEMA concreto para o "
    "cidadao — nunca elogiar, nunca descrever a posicao dele de forma neutra.\n\n"
    "Regras de ouro:\n"
    "- Foque na CONSEQUENCIA e na CONTRADICAO, nao na opiniao dele.\n"
    "- Comece pelo DADO/FATO incomodo, nao pelo nome dele.\n"
    "- Use numeros concretos sempre que existirem na fonte (projetos, anos, valores, votos).\n"
    "- Contraste PROMESSA x REALIDADE sempre que a fonte permitir.\n"
    "- Verbos-guia: travou, parou, nao saiu do papel, custou, deixou, ignorou, "
    "mudou de posicao, ficou parado.\n"
    "- PROIBIDO manchete cujo verbo principal seja 'critica', 'defende', 'propõe', 'diz', "
    "'declara' — isso coloca o foco no que ele pensa, nao no problema. Se a fonte so tem "
    "a fala dele, transforme a fala em CONSEQUENCIA (o que aquilo custa/gera para o eleitor).\n"
    "- Manchete: no maximo 12 palavras, concreta, sem adjetivo vazio.\n"
    "- NUNCA invente numero ou fato que nao esteja no dossie/fonte.\n"
    "- PROIBIDO argumento de AUSENCIA/SILENCIO: nada de 'nao ha registro', 'nao "
    "encontramos', 'zero registros', 'nenhum voto', 'silencio no Senado'. Isso nao e "
    "fato verificavel e pode enganar. Toda manchete precisa de um FATO AFIRMATIVO da "
    "fonte: algo que a fonte diz que aconteceu/existe (um numero, uma votacao, uma "
    "retirada, uma contradicao documentada).\n"
    "- PROIBIDO usar materia de fact-check/desmentido ('e fake', 'e falso', 'boato', "
    "'G1 confirma que nao') como base — essas materias geralmente DEFENDEM ele e "
    "invertem o enquadramento para o lado dele.\n\n"
    "Exemplos (ilustrativos):\n"
    "- RUIM: \"Flavio critica PEC e diz que Lula e oportunista\" (foca na opiniao dele; neutro)\n"
    "- BOM: \"7 anos, 433 projetos, 2 aprovados — e nenhum virou lei\"\n"
    "- RUIM: \"Flavio defende liberdade de carga horaria\"\n"
    "- BOM: \"A proposta que trava a mudanca da escala 6x1\"\n"
)


def build_crew(settings: Settings) -> Crew:
    llm_preciso = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.1,
    )
    llm_analista = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.3,
    )
    llm_criativo = LLM(
        model=f"ollama/{settings.ollama_model}",
        base_url=settings.ollama_base_url,
        temperature=0.7,
    )

    pesquisador = Agent(
        role="Pesquisador Politico",
        goal=(
            "Levantar fatos concretos e verificaveis sobre acoes, votos, projetos, "
            "declaracoes e promessas de Flavio Bolsonaro, priorizando as fontes "
            "configuradas (RSS e portais). Toda afirmacao deve ter uma URL de origem. "
            "De prioridade a numeros, datas, votacoes e contradicoes entre discurso e pratica."
        ),
        backstory=(
            "Voce e um pesquisador rigoroso e cetico. Nao inventa informacao: registra "
            "apenas o que encontra nas fontes, citando o link de cada alegacao. Voce sabe "
            "que o material mais util e o fato incomodo: um projeto parado, uma promessa "
            "nao cumprida, um numero que expoe a contradicao."
        ),
        tools=[list_sources, read_active_rss, read_rss, search_web, extract_markdown],
        llm=llm_preciso,
        verbose=True,
        allow_delegation=False,
    )

    analista = Agent(
        role="Analista de Impacto por Perfil",
        goal=(
            "Avaliar, para cada pauta coletada, o potencial de persuasao sobre cada um "
            "dos perfis demograficos configurados, numa logica de mudanca de voto."
        ),
        backstory=(
            "Voce e um estrategista de comunicacao politica. Nao mede apenas 'ressonancia': "
            "mede se a informacao move o eleitor do perfil a agir. Voce pontua cada pauta "
            "de 0 a 10 por perfil e sugere o ANGULO NARRATIVO mais forte (a contradicao ou "
            "consequencia que fala direto com aquele perfil)."
        ),
        llm=llm_analista,
        verbose=True,
        allow_delegation=False,
    )

    roteirista = Agent(
        role="Roteirista de Manchetes",
        goal=(
            "Transformar as pautas de maior impacto em manchetes e roteiros curtos, "
            "impactantes e engajantes, para Facebook e TikTok — sempre elucidando um "
            "problema concreto, sem distorcer fato ou fonte."
        ),
        backstory=(
            "Voce e redator publicitario de campanha de oposicao, especializado em conteudo "
            "viral para Facebook e TikTok. Escreve manchetes que fazem parar o scroll, mas "
            "cada palavra e rastreavel ate a fonte. Voce nao elogia e nao fica em cima do "
            "muro: expoe o problema."
        ),
        llm=llm_criativo,
        verbose=True,
        allow_delegation=False,
    )

    revisor = Agent(
        role="Revisor de Fatos e Enquadramento",
        goal=(
            "Verificar se cada afirmacao esta sustentada por fonte citavel E se o material "
            "mantem o enquadramento de oposicao, restaurando o impacto quando o texto ficou "
            "neutro — sem nunca inventar fato."
        ),
        backstory=(
            "Voce e checador de fatos e editor de enquadramento. Flavio Bolsonaro e figura "
            "publica: alegacao sem fonte expoe o material a risco juridico, entao voce nunca "
            "deixa passar nada sem lastro. Mas voce tambem sabe que um texto neutro nao "
            "serve: se a manchete virou 'ele defende X', voce reescreve para a consequencia."
        ),
        tools=[search_web, extract_markdown],
        llm=llm_preciso,
        verbose=True,
        allow_delegation=False,
    )

    tarefa_pesquisa = Task(
        description=(
            "Pesquise o tema: {tema}.\n\n"
            "Passos:\n"
            "1. Use listar_fontes para ver as fontes configuradas e ler_rss_ativos para "
            "ler os feeds RSS ativos (quando fizer sentido para o tema).\n"
            "2. Use buscar_na_web para complementar com materia de portais.\n"
            "3. Use extrair_markdown para baixar e converter as paginas mais relevantes.\n"
            "4. Produza um dossie em markdown com fatos numerados. Cada fato deve ter: "
            "afirmacao, contexto e source_url. Registre falhas de acesso em vez de inventar.\n"
            "5. Priorize fatos com NUMERO, DATA, VOTACAO ou CONTRADICAO entre discurso e "
            "pratica. Ausencia de informacao NAO e fato: se o tema tiver poucos resultados, "
            "tente termos alternativos (siglas, anos, numeros de projeto) em vez de concluir "
            "que 'nao ha registro'."
        ),
        agent=pesquisador,
        expected_output=(
            "Dossie em markdown com fatos numerados, cada um com afirmacao, contexto e "
            "source_url. Priorizou fatos concretos (numeros/votacoes/contradicoes). "
            "Nenhuma afirmacao sem fonte."
        ),
    )

    tarefa_analise = Task(
        description=(
            "Com base no dossie do pesquisador, avalie cada pauta/fato para os perfis "
            "abaixo, atribuindo nota de impacto de 0 a 10 por perfil (logica de persuasao "
            "e mudanca de voto) e uma justificativa curta.\n\n"
            f"{profiles_as_markdown()}\n\n"
            "Para cada pauta, aponte tambem o ANGULO NARRATIVO mais forte: qual contradicao "
            "ou consequencia concreta fala direto com o perfil-alvo.\n\n"
            "Entregue: uma tabela (pauta x perfil) com as notas e, em seguida, um ranking "
            "das 5 pautas com maior potencial, com o perfil-alvo e o angulo de cada uma."
        ),
        agent=analista,
        expected_output=(
            "Tabela de notas (pauta x perfil) com justificativas e ranking das 5 melhores "
            "pautas, cada uma com perfil-alvo e angulo narrativo."
        ),
        context=[tarefa_pesquisa],
    )

    tarefa_roteiro = Task(
        description=(
            "Com base no dossie e na analise de impacto, crie exatamente 5 manchetes "
            "impactantes e engajantes que elucidem um problema concreto ligado a acoes ou "
            "promessas de Flavio Bolsonaro.\n\n"
            f"{TOM_ENQUADRAMENTO}\n"
            "Se o dossie nao tiver 5 fatos fortes distintos, varie o ANGULO/PERFIL sobre "
            "os fatos mais fortes — nunca preencha com argumento de ausencia nem com "
            "desmentido.\n"
            "Para cada manchete, entregue:\n"
            "- Perfil-alvo (do ranking do analista)\n"
            "- Manchete (curta, ate 12 palavras, pronta para Facebook/TikTok)\n"
            "- Roteiro curto: hook (2s) -> problema -> evidencia -> CTA\n"
            "- source_url que sustenta a afirmacao\n\n"
            "Nao distorca fatos e nao invente alegacoes ausentes do dossie."
        ),
        agent=roteirista,
        expected_output=(
            "5 manchetes em markdown, cada uma com perfil-alvo, roteiro (hook->problema->"
            "evidencia->CTA) e source_url. Enquadramento de oposicao, sem inventar fatos."
        ),
        context=[tarefa_pesquisa, tarefa_analise],
    )

    tarefa_revisao = Task(
        description=(
            "Revise o material do roteirista comparando cada afirmacao com o dossie e, se "
            "necessario, com as fontes (buscar_na_web / extrair_markdown).\n\n"
            "Regras de fato:\n"
            "- Se uma afirmacao nao tiver fonte que a sustente, remova ou reescreva para "
            "algo sustentado.\n"
            "- REJEITE argumento de AUSENCIA/SILENCIO ('nao ha registro', 'nao encontramos', "
            "'zero registros', 'nenhum voto'). Ausencia de informacao NAO e fato verificavel. "
            "Marque como REJEITADO e substitua por um fato AFIRMATIVO do dossie; se nao "
            "houver, troque a pauta.\n"
            "- Confirme que cada manchete final tem um source_url valido.\n\n"
            f"{TOM_ENQUADRAMENTO}\n"
            "Regras de enquadramento:\n"
            "- Se alguma manchete ficou neutra, elogiosa ou focada na opiniao dele "
            "(ex: 'Flavio critica X', 'Flavio defende Y'), REESCREVA para a consequencia/"
            "problema, SEM inventar fato novo.\n"
            "- Rejeite manchete cujo teor DEFENDA/ABSOLVA ele (ex: 'e fake que ele propos X', "
            "'G1 confirma que e boato'). Substitua por um fato afirmativo do dossie.\n"
            "- Se nao houver fato suficiente para um enquadramento forte, substitua a pauta "
            "por outra do dossie ou varie o angulo sobre os fatos mais fortes.\n\n"
            "Entregue a versao final PRIMEIRO (as 5 manchetes com roteiro e fonte), e so "
            "depois, como apendice, a tabela de validacao (afirmacao -> fonte -> status)."
        ),
        agent=revisor,
        expected_output=(
            "Versao final com 5 manchetes fortes (enquadramento de oposicao) e roteiros, "
            "cada uma com source_url; apendice com tabela de validacao. Terminar com: "
            "'Conteudo gerado por IA - verificar antes de publicar.'"
        ),
        context=[tarefa_pesquisa, tarefa_roteiro],
    )

    return Crew(
        agents=[pesquisador, analista, roteirista, revisor],
        tasks=[tarefa_pesquisa, tarefa_analise, tarefa_roteiro, tarefa_revisao],
        process=Process.sequential,
        verbose=True,
    )

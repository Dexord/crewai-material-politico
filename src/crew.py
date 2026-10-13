from crewai import Agent, Crew, LLM, Process, Task

from .config import Settings
from .output.entregaveis import PacoteRedesMulti, PacoteVideos, Reportagem
from .profiles import profiles_as_markdown
from .tools.scraper import extract_markdown
from .tools.search import search_web
from .tools.sources import list_sources, read_active_rss, read_rss
from .tools.vault_tools import (
    buscar_notas,
    consultar_grafo,
    ler_nota,
    salvar_fato,
    salvar_noticia,
)

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
    "invertem o enquadramento para o lado dele.\n"
    "- NUNCA cite fontes internas ('o Vault', 'o banco de dados', 'as notas'); as unicas "
    "fontes publicaveis sao as materias/URLs. Escreva o fato direto, nunca 'o Vault mostra'.\n"
    "- Cada manchete precisa ter vinculo com Flavio Bolsonaro, a familia Bolsonaro, ou "
    "pessoas proximas do partido e amigos; se o fato nao conecta a nenhum deles, troque por "
    "outra pauta. Esse vinculo precisa estar na FONTE — NUNCA invente ligacao.\n"
    "- Use POUCOS emojis (no maximo 1 por peca, opcional), para nao parecer texto feito por IA.\n\n"
    "Exemplos (ilustrativos):\n"
    "- RUIM: \"Flavio critica PEC e diz que Lula e oportunista\" (foca na opiniao dele; neutro)\n"
    "- BOM: \"7 anos, 433 projetos, 2 aprovados — e nenhum virou lei\"\n"
    "- RUIM: \"Flavio defende liberdade de carga horaria\"\n"
    "- BOM: \"A proposta que trava a mudanca da escala 6x1\"\n"
)


def build_crew(settings: Settings, saidas: list[str] | None = None, step_callback=None) -> Crew:
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
            "declaracoes e promessas de Flavio Bolsonaro, reaproveitando o que ja existe "
            "no vault e persistindo o que encontrar de novo (com fonte). Toda afirmacao "
            "deve ter uma URL de origem. De prioridade a numeros, datas, votacoes e "
            "contradicoes entre discurso e pratica."
        ),
        backstory=(
            "Voce e um pesquisador rigoroso e cetico. Antes de pesquisar, voce consulta o "
            "vault pelo tema (buscar_notas/ler_nota/consultar_grafo) para nao refazer "
            "trabalho. Nao inventa informacao: registra apenas o que encontra nas fontes, "
            "citando o link de cada alegacao, e salva o que for novo via salvar_fato/"
            "salvar_noticia. Voce sabe que o material mais util e o fato incomodo."
        ),
        tools=[
            list_sources,
            read_active_rss,
            read_rss,
            search_web,
            extract_markdown,
            buscar_notas,
            ler_nota,
            consultar_grafo,
            salvar_fato,
            salvar_noticia,
        ],
        llm=llm_preciso,
        max_iter=15,
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
        tools=[buscar_notas, consultar_grafo],
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
        tools=[search_web, extract_markdown, ler_nota, buscar_notas],
        llm=llm_preciso,
        verbose=True,
        allow_delegation=False,
    )

    tarefa_pesquisa = Task(
        description=(
            "Pesquise o tema: {tema}.\n\n"
            "Passos:\n"
            "1. Consulte PRIMEIRO o vault pelo tema: use buscar_notas e ler_nota para ver "
            "o que ja foi pesquisado (reaproveite e nao refaca trabalho). Use "
            "consultar_grafo se quiser ver entidades ja ligadas ao tema.\n"
            "2. Use listar_fontes/ler_rss_ativos para ler os feeds e buscar_na_web para "
            "complementar com materia de portais.\n"
            "3. Use extrair_markdown para baixar e converter as paginas mais relevantes.\n"
            "4. PERSISTA no vault o que for novo: salvar_fato para cada fato (com fonte) e "
            "salvar_noticia para materias relevantes, informando as entidades.\n"
            "5. Produza um dossie em markdown com fatos numerados (afirmacao, contexto e "
            "source_url). Registre falhas de acesso em vez de inventar.\n"
            "6. Priorize fatos com NUMERO, DATA, VOTACAO ou CONTRADICAO entre discurso e "
            "pratica. Ausencia de informacao NAO e fato: se o tema tiver poucos resultados, "
            "tente termos alternativos (siglas, anos, numeros de projeto).\n"
            "7. Use PELO MENOS 2 fontes diferentes (idealmente 3 ou mais) para sustentar o "
            "dossie; nunca apoie o material em uma unica materia."
        ),
        agent=pesquisador,
        expected_output=(
            "Dossie em markdown com fatos numerados, cada um com afirmacao, contexto e "
            "source_url. Fatos/materias novos foram salvos no vault. Nenhuma afirmacao sem fonte."
        ),
    )

    tarefa_analise = Task(
        description=(
            "Com base no dossie do pesquisador, avalie cada pauta/fato para os perfis "
            "abaixo, atribuindo nota de impacto de 0 a 10 por perfil (logica de persuasao "
            "e mudanca de voto) e uma justificativa curta.\n\n"
            "Antes de pontuar, voce PODE consultar o vault (buscar_notas) e o grafo "
            "(consultar_grafo) para medir quantas pessoas/relacoes a pauta toca — pauta "
            "com mais conexoes documentadas tende a ter mais alcance.\n\n"
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
            "Com base no dossie e na analise de impacto, crie EXATAMENTE UMA manchete para "
            "CADA perfil demografico abaixo (sao 5 perfis, portanto 5 manchetes, uma por "
            "perfil), impactantes e engajantes, que elucidem um problema concreto ligado a "
            "acoes ou promessas de Flavio Bolsonaro.\n\n"
            f"{profiles_as_markdown()}\n\n"
            f"{TOM_ENQUADRAMENTO}\n"
            "Regras das 5 manchetes:\n"
            "- UMA manchete por perfil: cubra os 5 perfis, sem repetir perfil.\n"
            "- As 5 devem tratar de FATOS DIFERENTES entre si. NUNCA repita o mesmo fato/"
            "angulo (nem uma variacao dele) em duas manchetes; se faltar, use outro fato "
            "do dossie — mas o FATO destacado tem que mudar.\n"
            "- Cada manchete: NO MAXIMO 12 palavras (conte antes de entregar).\n"
            "- PROIBIDO premissa inventada ('o dinheiro deveria ter ido para X', 'nao foi "
            "para Y') — use apenas o que a fonte afirma.\n"
            "- PROIBIDO enquadramento que o absolva ou sugira que ele e limpo / que 'so e "
            "investigado em um caso'.\n"
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
            "Revise o material do roteirista comparando cada afirmacao com o dossie e com "
            "as notas do vault (ler_nota/buscar_notas); se necessario, confirme na web "
            "(buscar_na_web / extrair_markdown).\n\n"
            "Regras de ADERENCIA:\n"
            "- Cada manchete tem que ter a ver com o TEMA: {tema}.\n"
            "- Garanta 5 manchetes, UMA por perfil (cubra os 5 perfis); se algum perfil "
            "ficar sem manchete, reescreva/troque para cobri-lo.\n"
            "- Cada manchete tem que tocar em alguma DOR ou gatilho de um dos perfis abaixo; "
            "se nao tocar, reescreva ou troque por outra pauta do dossie.\n\n"
            f"{profiles_as_markdown()}\n\n"
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
            "'denuncia foi rejeitada', 'foi absolvido', 'investigacao arquivada'). Enquadre o "
            "PROBLEMA, nao a 'vitoria' dele. Substitua por um fato afirmativo do dossie.\n"
            "- Rejeite citacao a fontes internas ('o Vault', 'o banco de dados', 'as notas'); "
            "as fontes publicaveis sao apenas as materias/URLs.\n"
            "- Cada manchete precisa ter vinculo com Flavio Bolsonaro, a familia Bolsonaro, ou "
            "pessoas proximas do partido e amigos; sem isso, troque a pauta.\n"
            "- REJEITE qualquer ligacao a Flavio/familia/governo que a FONTE nao sustente "
            "(ex.: 'igreja sob gestao de Flavio' quando a materia nao diz isso). O vinculo "
            "tem que estar na fonte.\n"
            "- Se nao houver fato suficiente para um enquadramento forte, substitua a pauta "
            "por outra do dossie ou varie o angulo sobre os fatos mais fortes.\n"
            "- REJEITE manchetes repetidas: as 5 precisam tratar de FATOS distintos; "
            "substitua as repetidas por outro fato do dossie.\n"
            "- REJEITE premissa inventada e enquadramento que o absolva/sugira que ele e "
            "limpo ou 'so investigado em um caso'.\n"
            "- Corrija erros obvios de ortografia/gramatica (ex.: 'imparidade' -> "
            "'imparcialidade').\n\n"
            "Entregue a versao final PRIMEIRO (as 5 manchetes com roteiro e fonte), e so "
            "depois, como apendice, a tabela de validacao com as colunas: Afirmacao | "
            "Referencia (id da nota no vault e/ou source_url) | Status."
        ),
        agent=revisor,
        expected_output=(
            "Versao final com 5 manchetes fortes (enquadramento de oposicao) e roteiros, "
            "cada uma com source_url; apendice com tabela de validacao (Afirmacao | "
            "Referencia | Status). Terminar com: "
            "'Conteudo gerado por IA - verificar antes de publicar.'"
        ),
        context=[tarefa_pesquisa, tarefa_roteiro],
    )

    agents = [pesquisador, analista, roteirista, revisor]
    tasks = [tarefa_pesquisa, tarefa_analise, tarefa_roteiro, tarefa_revisao]
    saidas = saidas or []

    if "video" in saidas:
        roteirista_video = Agent(
            role="Roteirista de Video Curto",
            goal=(
                "Escrever um roteiro de video curto (aproximadamente 1m30s) sobre o tema, "
                "a partir da versao aprovada pelo revisor, com gancho, cenas cronometradas, "
                "narracao e texto de tela."
            ),
            backstory=(
                "Voce e roteirista de video curto de campanha de oposicao. Prende nos "
                "primeiros segundos e sustenta cada afirmacao em fato com fonte, sem distorcer."
            ),
            llm=llm_criativo,
            verbose=True,
            allow_delegation=False,
        )
        tarefa_video = Task(
            description=(
                "A partir da versao final aprovada pelo revisor (5 manchetes, uma por perfil), "
                "escreva UM roteiro de video curto (~1m30s) PARA CADA manchete/perfil "
                "(portanto 5 roteiros).\n"
                "Cada roteiro deve ter: 'perfil_alvo', 'titulo', 'gancho', cenas cronometradas "
                "('narracao' + 'texto_tela') e 'CTA', mantendo o enquadramento do perfil.\n\n"
                f"{TOM_ENQUADRAMENTO}\n"
                "Nao invente fatos. Preencha 'source_urls' com as fontes usadas."
            ),
            agent=roteirista_video,
            expected_output="Pacote com 5 roteiros de video (um por perfil).",
            output_pydantic=PacoteVideos,
            context=[tarefa_revisao],
        )
        agents.append(roteirista_video)
        tasks.append(tarefa_video)

    if "redes" in saidas:
        copywriter_redes = Agent(
            role="Copywriter de Redes",
            goal=(
                "Escrever a publicacao para Facebook, um fio para o Bluesky e o texto de uma "
                "imagem (titulo + subtitulo), respeitando o formato de cada um."
            ),
            backstory=(
                "Voce e copywriter de redes sociais de campanha de oposicao. Adapta o material "
                "aprovado ao formato de cada rede: Facebook mais longo (gancho e CTA); Bluesky "
                "em formato de fio (ate 4 posts de ~300 caracteres, com o link em cada post "
                "quando houver). Voce tambem cria titulo e subtitulo curtos de imagem. Nao muda "
                "fato nem enquadramento."
            ),
            llm=llm_criativo,
            verbose=True,
            allow_delegation=False,
        )
        tarefa_redes = Task(
            description=(
                "A partir da versao final aprovada pelo revisor (5 manchetes, uma por perfil), "
                "produza UM item de redes PARA CADA manchete/perfil (portanto 5 itens).\n"
                "Cada item deve ter:\n"
                "- 'perfil_alvo'\n"
                "- 'facebook': texto mais longo (gancho, desenvolvimento, CTA) + 'hashtags' "
                "(3 a 5).\n"
                "- 'bluesky': um FIO de 1 a 4 posts, em ordem, cada um com no maximo ~300 "
                "caracteres; quando houver link/fonte, INCLUA o link no proprio post.\n"
                "- 'imagem': 'titulo' (ate ~6 palavras) e 'subtitulo' (uma linha curta) para "
                "arte no Canva.\n\n"
                f"{TOM_ENQUADRAMENTO}\n"
                "Nao mude fatos nem fontes."
            ),
            agent=copywriter_redes,
            expected_output="Pacote com 5 itens de redes (um por perfil), no schema definido.",
            output_pydantic=PacoteRedesMulti,
            context=[tarefa_revisao],
        )
        agents.append(copywriter_redes)
        tasks.append(tarefa_redes)

    if "reportagem" in saidas:
        redator_jornalista = Agent(
            role="Redator Jornalista",
            goal=(
                "Escrever uma reportagem/noticia extensa (formato blog) sobre o tema, com "
                "titulo, linha fina, lide e corpo com secoes."
            ),
            backstory=(
                "Voce e jornalista de oposicao. Escreve materia aprofundada, com enquadramento "
                "por fato e consequencia, hierarquizando dados e citando as fontes."
            ),
            llm=llm_analista,
            verbose=True,
            allow_delegation=False,
        )
        tarefa_reportagem = Task(
            description=(
                "A partir da versao final aprovada pelo revisor e do dossie, escreva uma "
                "reportagem/noticia extensa (formato blog) sobre o tema, com: 'titulo', "
                "'linha_fina', 'lead' (lide) e 'corpo' em markdown com secoes (## ...).\n\n"
                f"{TOM_ENQUADRAMENTO}\n"
                "Nao invente fatos. Preencha 'fontes' com as URLs usadas."
            ),
            agent=redator_jornalista,
            expected_output="Reportagem no schema definido (titulo, linha fina, lide, corpo, fontes).",
            output_pydantic=Reportagem,
            context=[tarefa_revisao],
        )
        agents.append(redator_jornalista)
        tasks.append(tarefa_reportagem)

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        step_callback=step_callback,
    )

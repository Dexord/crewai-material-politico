# AGENTS.md

Guia para agentes de código (e humanos) que forem mexer neste repositório.

## 1. O que é este projeto

Sistema multi-agente **100% local** que faz scraping de portais/feeds de notícias e
sites oficiais, e gera **manchetes e roteiros curtos** para Facebook e TikTok.

Objetivo editorial: **conteúdo de oposição a Flávio Bolsonaro**, que **elucide
problemas concretos** ligados a ações que ele já fez ou prometeu. O material é sempre
**ancorado em fatos com fonte citável** — nunca em opinião, boato ou argumento de
ausência.

## 2. Stack

| Camada | Tecnologia |
|---|---|
| Orquestração | `crewai` 1.15.x (sem litellm; provider nativo Ollama/OpenAI-compatível) |
| LLM | Ollama local, modelo `qwen3.5:9b` (Q4_K_M, 9B, nativo 262144 ctx, tools+thinking) |
| Scraping | `requests` + `BeautifulSoup` + `markdownify` |
| RSS | `feedparser` + `PyYAML` |
| Busca | `ddgs` (metasearch; backend `auto`, region `br-pt`) |
| Config | `pydantic-settings` (`.env`) |
| Gerenciador | `uv` (Python 3.13) |

Grafo de conhecimento: `networkx` (em memória). Persistência do conteúdo: notas Markdown
no vault (Obsidian). **Sem** SQLite/RAG por decisão do projeto (mais auditável, escala
pequena) — ver seção F2b.

## 3. Comandos

```powershell
uv sync                                          # instalar/atualizar deps

# Fluxo de conteudo (pipeline sequencial de 4 agentes)
uv run python -m src.main run --tema "<tema>"

# Grafo de conhecimento (F2a)
uv run python -m src.main investigar             # estrutura o vault + mantem a fila
uv run python -m src.main pesquisar --limite N   # consome a fila (0 = esvazia)
uv run python -m src.main enfileirar "<alvo>" [--motivo "..."] [--prioridade 3]

# Migracao de entidades (pessoa -> organizacao); dry-run por padrao
uv run python -m src.main migrar-organizacoes [--aplicar] [--duvidosos]

# Renderiza o corpo das entidades (roda automatico em run/investigar/pesquisar)
uv run python -m src.main render-entidades

# Dedupe de entidades (auto-merge conservador na escrita; limpeza do historico e manual)
uv run python -m src.main deduplicar [--aplicar]   # dry-run lista clusters
uv run python -m src.main fundir <id_a> <id_b>      # funde b -> a (reescreve links)

# Loop autonomo (roda investigar<->pesquisar por N horas, saida ao vivo)
uv run python -m src.main pesquisar --horas 6 --lote 10
.\scripts\loop-noite.ps1 -Horas 6               # wrapper: powercfg + aquece + daemon

# Export por plataforma + fila de postagem (F3, export-only)
uv run python -m src.main run --tema "<tema>" --plataformas facebook,tiktok
uv run python -m src.main agenda [--status rascunho]   # lista a fila de postagem
uv run python -m src.main aprovar <id>                 # rascunho -> aprovado
uv run python -m src.main publicar <id>                # aprovado -> publicado
```

Saída do `run`: markdown timestampado em `data/output/` (gitignored).
Vault (grafo): `data/vault/` (gitignored) — abra como vault no Obsidian.

Checagem rápida do provider / VRAM:
```powershell
ollama ps        # mostra CONTEXT e PROCESSOR do modelo carregado
```

## 4. Mapa de arquivos

```
config/
  sources.yaml      # fontes do pesquisador (RSS + portais) — EDITE AQUI para adicionar blogs
  profiles.yaml     # 5 perfis demográficos (dores, valores, canais, gatilhos, objeções)
src/
  config.py         # Settings (lê .env): ollama_base_url, ollama_model, output_dir,
                    # scrape_rate_limit, vault_dir, max_depth
  crew.py           # pipeline de conteudo: 4 agentes + 4 tasks (TOM_ENQUADRAMENTO)
  crew_pesquisador.py  # pesquisa um alvo e persiste fato/entidade no vault (consome a fila)
  crew_investigador.py # estrutura o vault e mantem a fila (NAO pesquisa na web)
  profiles.py       # carrega profiles.yaml e injeta no analista
  main.py           # CLI: run / investigar / pesquisar / agenda / aprovar / publicar
  output/render.py  # salva saída em data/output/
  output/postagem.py # schema Peca/Pacote (pydantic), fila de postagem (JSON) e .txt por plataforma
  vault/
    vault.py        # ler/escrever notas c/ frontmatter (PyYAML), id/slug, escrita atômica
    log.py          # append no log/<data>.md
    queue.py        # fila de pesquisa (status, prioridade, profundidade, dedupe)
    index.py        # grafo em memória (networkx): vizinhos, caminho, mais conectados
    migrar.py       # reclassifica notas pessoa -> organizacao (dry-run + aplicar)
    render.py       # "bibliotecario" deterministico: corpo das entidades + mencionado_em
    entidades.py    # resolucao de entidades: score, aliases, fundir/merge, deduplicar
  tools/
    search.py       # buscar_na_web (ddgs -> markdown) + auto-log
    scraper.py      # extrair_markdown (requests+bs4 -> markdown) + auto-log
    sources.py      # listar_fontes, ler_rss, ler_rss_ativos (config/sources.yaml)
    vault_tools.py  # salvar_fato/noticia/pessoa/organizacao, registrar_vinculo, relacionar, fila, grafo
data/
  output/           # saidas do run (gitignored)
  vault/            # grafo de conhecimento, estilo Obsidian (gitignored)
scripts/
  loop-noite.ps1    # wrapper do daemon: powercfg + aquece Ollama + pesquisar --horas
```

## 5. Pipeline (sequencial)

1. **Pesquisador** (`tools: listar_fontes, ler_rss_ativos, ler_rss, buscar_na_web, extrair_markdown`)
   → dossiê de fatos numerados, cada um com `source_url`. Prioriza número/votação/data/contradição.
2. **Analista de Impacto** → nota 0–10 por perfil (lógica de persuasão/mudança de voto) + ângulo narrativo.
3. **Roteirista** → 5 manchetes (≤12 palavras) + roteiro `hook→problema→evidência→CTA` + `source_url`.
4. **Revisor** → gate de fato **e** de enquadramento; entrega versão final + tabela de validação.

Temperaturas separadas por agente: precisão `0.1` (pesquisador/revisor), `0.3` (analista),
criativo `0.7` (roteirista).

### Fluxo do grafo de conhecimento (F2a)

Separação de papéis (modelo pequeno não acumula funções):

- **Pesquisador de Campo** (`crew_pesquisador.py`) — o único que pesquisa na web.
  Persiste no vault `fato`/`noticia`/`pessoa`/`organizacao` e registra `vinculo` (com fonte).
  Nomes de pessoas/instituições são dados de primeira classe (`salvar_pessoa` para pessoa
  física, `salvar_organizacao` para empresa/banco/partido/órgão/facção etc.). Enfileira
  pessoas novas (expansão recursiva com `profundidade+1`, limitada por `MAX_DEPTH`).
- **Investigador de Relações** (`crew_investigador.py`) — NÃO pesquisa na web. Lê o vault,
  liga entidades, classifica vínculos e mantém a fila.

Loop noturno: `investigar` (estrutura + fila) → `pesquisar --limite N` (driver determinístico
consome a fila: pega item pendente de maior prioridade/menor profundidade, roda o pesquisador,
marca `concluido`). Dedupe automático por `alvo`; itens acima de `MAX_DEPTH` são ignorados.

Vault em `data/vault/` (Obsidian): `log/`, `noticias/`, `fatos/`, `pessoas/`, `organizacoes/`,
`temas/`, `fila/`. Toda nota tem frontmatter YAML + `[[wikilinks]]` (Graph View do Obsidian).

### Integração do vault ao `run` (F2b)

Sem RAG: o vault é a fonte única da verdade e os agentes leem/escrevem via tools.

- **Pesquisador** consulta o vault antes (`buscar_notas`/`ler_nota`/`consultar_grafo`) e
  **persiste** o que achar de novo (`salvar_fato`/`salvar_noticia`).
- **Analista** usa `buscar_notas`/`consultar_grafo` para contextualizar a nota de impacto.
- **Revisor** valida contra as notas (`ler_nota`/`buscar_notas`); a tabela de validação
  cita a **referência** (id da nota e/ou `source_url`), sem trecho literal.
- `buscar_notas` é on-demand e ranqueado por campo (`titulo`/`nome`/`afirmacao` > `tags` >
  `fonte` > `corpo`), case/accent-insensitive. **Sem embeddings/ChromaDB** por decisão do
  projeto (mais auditável, escala pequena). Revisitar só se surgir necessidade de busca
  semântica/paráfrase ou agrupar notícias similares — nesse caso usar `fastembed` (CPU,
  fora do Ollama, que tem `OLLAMA_MAX_LOADED_MODES=1`).

### Bibliotecário determinístico (corpo das entidades)

Notas de `pessoa`/`organizacao` são **stubs**: cargos, vínculos e "mencionado em" ficam no
frontmatter. Para ficarem legíveis no Obsidian, `src/vault/render.py` gera o **corpo** a
partir do frontmatter (determinístico, **sem LLM**):

- `render_entidade(fm)` — monta o markdown (Cargos/Tipo, `## Vínculos` com fonte, `## Mencionado em`).
- `backfill_mencionado_em()` — preenche `mencionado_em` a partir dos links de entrada
  (`entidades`/`vinculos`/wikilinks dos fatos e notícias).
- `atualizar_entidades()` — backfill + re-render de todas as entidades.

**Automático** ao fim de `run`, `investigar` e de cada item de `pesquisar`; também ao
escrever (`salvar_pessoa`/`salvar_organizacao`/`registrar_vinculo` renderizam o corpo;
`salvar_fato`/`salvar_noticia` atualizam o `mencionado_em` das entidades citadas). Comando
manual `render-entidades` só para reparo. Frontmatter continua sendo a **fonte da verdade**;
o corpo é derivado e idempotente.

### Resolução de entidades (aliases e dedupe)

`src/vault/entidades.py` resolve se uma pessoa/organização **já existe** antes de criar
(determinístico, **sem LLM**): normaliza (sem acento/honorífico/partícula, remove apelido
após vírgula) e compara por token — **igualdade de tokens** (ignora ordem) e subconjunto com
mesmo primeiro/último.

- **Auto-merge na escrita**: `salvar_pessoa`/`salvar_organizacao` reaproveitam a nota
  existente quando o match é de **alta confiança** (tokens idênticos) e gravam o nome novo em
  `aliases`. Subconjunto (nome do meio a menos) fica como **revisar** (nunca automático —
  ex.: `jair-bolsonaro` × `jair-renan-bolsonaro` são pai e filho).
- **`aliases`** no frontmatter: novas grafias/apelidos apontam para o canônico
  (`_resolve_id` consulta).
- **Histórico**: `deduplicar` (dry-run) lista clusters (AUTO/revisar); `fundir a b` faz o
  merge manual — junta `cargos`/`vinculos`/`mencionado_em`, adiciona alias, **reescreve os
  `[[id_b]]`→`[[id_a]]`** no vault e apaga a nota B. Confirmação manual por decisão.

### Export por plataforma e fila de postagem (F3)

Export-only (sem auto-post). Com `run --plataformas facebook,tiktok`, um **Redator de
Plataforma** (5º agente, só quando a flag é usada) adapta a versão aprovada pelo revisor e
emite um `Pacote` (saída estruturada `Peca`/`Pacote` em `src/output/postagem.py`).

- **Facebook**: `texto_publicacao` + `hashtags`.
- **TikTok**: `titulo`, `texto_publicacao`, `texto_tela` (por cena) e texto da **imagem**
  (`imagem_titulo` + `imagem_subtitulo`, padrão de mídia profissional) — a imagem é feita
  à mão pelo usuário.
- Todas as peças saem com `source_url` e `disclosure` de IA.

Fila local em `data/output/fila-postagem.json` (ciclo `rascunho -> aprovado -> publicado`)
e arquivos de copiar-e-colar em `data/output/postagens/<id>.txt`. Comandos: `agenda`,
`aprovar <id>`, `publicar <id>`. **Sem** `.ics`, Task Scheduler ou auto-post (deixados
como plugáveis no futuro).

### Loop autonomo (`pesquisar --horas N`)

O daemon roda no mesmo processo e imprime tudo **ao vivo no terminal** (stdout com
`line_buffering`), gravando tambem um log resumido em `data/output/loop-<stamp>.log`.

- Ao iniciar, roda `reset_em_andamento()` — itens `em_andamento` órfãos de uma interrupção
  voltam para `pendente`.
- Ciclo: fila vazia → roda o investigador; senão → processa um lote (`--lote`, default 10).
- Encerra ao fim do tempo (`--horas`) ou após 3 ciclos sem novidades (saturação).
- `BLACKLIST_ALVOS` (`.env`) evita o auto-enfileiramento de alvos como o próprio candidato;
  `enfileirar` explícito ignora a blacklist.
- `scripts/loop-noite.ps1 -Horas 6 [-Logar]`: ajusta `powercfg`, aquece o Ollama e chama o
  daemon; `-Logar` usa Tee para também salvar o transcript do console.

Nota: `--horas` é um orçamento **aproximado** — um item em execução pode passar do prazo até
terminar (o tempo é checado entre itens/lotes).

## 6. Regras editoriais (NÃO REMOVER)

Definidas em `TOM_ENQUADRAMENTO` (`src/crew.py`) e replicadas no revisor:

- Enquadrar por **consequência/contradição**, não pela opinião dele.
- Começar pelo **dado incômodo**, não pelo nome dele.
- **Proibido** verbo principal `critica`, `defende`, `propõe`, `diz`, `declara`.
- **Proibido argumento de ausência/silêncio** ("não há registro", "zero", "não encontramos").
- **Proibido** usar matéria de **fact-check/desmentido** ("é fake", "G1 confirma") — defende ele.
- **Nunca inventar** número/fato. Toda afirmação tem `source_url`.

## 7. Conformidade

- Toda saída termina com: `Conteúdo gerado por IA - verificar antes de publicar.`
- Disciplina legal: propaganda eleitoral gerada por IA tem regra de identificação
  (TSE Res. 23.610/2019); Flávio Bolsonaro é figura pública, então afirmação factual falsa
  gera risco de difamação/calúnia. Por isso o revisor é um **gate**, não enfeite.
- Respeitar `robots.txt`, usar `User-Agent` identificado e rate-limit (`SCRAPE_RATE_LIMIT`).

## 8. Configuração (.env)

Copie `.env.example` → `.env`. Defaults que levantam o projeto:

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
OUTPUT_DIR=data/output
SCRAPE_RATE_LIMIT=1.5
VAULT_DIR=data/vault
MAX_DEPTH=2
BLACKLIST_ALVOS=Flavio Bolsonaro
```

## 9. Contexto do modelo (importante)

O endpoint **OpenAI-compatível** do Ollama (usado pelo crewAI nativo) **não aceita
`num_ctx`** por requisição — `num_ctx`, `extra_body.options` e `context_window_size` são
rejeitados/ignorados. Portanto o contexto é controlado **do lado do Ollama**:

- `ollama ps` mostra o CONTEXT efetivo (hoje o modelo carrega por volta de 16384).
- Para aumentar, no Windows:
  ```powershell
  [Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH","32768","User")
  # sair do Ollama (bandeja) e abrir de novo
  ```
  ou via Modelfile:
  ```
  FROM qwen3.5:9b
  PARAMETER num_ctx 32768
  ```
  `ollama create qwen3.5-32k -f Modelfile` e depois ajustar `OLLAMA_MODEL` no `.env`.
- Limite prático: RX 6700 XT = 12 GB. `ollama ps` deve manter `PROCESSOR=100% GPU`;
  se cair para CPU, reduza o `num_ctx`.

## 10. Problemas conhecidos

- **UOL devolve 403** (anti-bot) no scraping por `requests`. Ignorado por decisão do projeto;
  trocar por RSS ou adicionar `httpx[http2]` + warmup de sessão no futuro.
- **Busca web**: usa `ddgs` no backend `auto`. Os backends individuais (`duckduckgo`,
  `google`, `bing`, `brave`) costumam devolver `DDGSException: No results found` (bloqueio de
  IP/rate-limit) — por isso não fixar `backend`. `region="br-pt"` é respeitado no `auto`
  quando há fonte brasileira; temas muito cobertos no exterior trazem páginas em espanhol.
- **G1** responde por `requests` puro. **Senado RSS** correto: `https://www12.senado.leg.br/noticias/rss`.
- **Console Windows**: emojis/acentos causam ruído de `charmap` no crewAI. `src/main.py`
  reconfigura stdout/stderr para utf-8; rode com `$env:PYTHONUTF8=1` se necessário.
- **Espaço em branco/fonte única**: quando o tema tem pouca cobertura, o modelo tende a
  voltar a argumento de ausência — as regras da seção 6 existem para barrar isso.
- **Entidades (pessoa x organização)**: `migrar-organizacoes` move notas para
  `organizacoes/` mantendo o **mesmo `id`** (ex.: `pessoa-banco-master`) para não quebrar
  os `[[wikilinks]]`. Dedupe via `entidades.py` (`deduplicar`/`fundir`); subconjunto de
  nome só mescla sob confirmação (nunca automático).

## 11. Roadmap

- **F0 (feito):** pesquisador + busca/scraping → manchetes citadas.
- **F1 (feito):** 4 agentes, fontes parametrizáveis (RSS/portais), perfis, revisor.
- **F2a (feito):** vault estilo Obsidian (notas + wikilinks), log automático, fila de
  pesquisa com expansão recursiva, agente investigador (estrutura + mantém fila).
- **F2b (feito):** vault integrado ao `run` (sem RAG): pesquisador lê/persiste, analista
  consulta o grafo, revisor cita por referência; `buscar_notas` ranqueado por campo.
- **F3 (feito):** export por plataforma (Facebook/TikTok) via agente redator com saída
  estruturada, fila de postagem local com ciclo de status. Export-only, sem auto-post.
- **Futuro:** auto-post via APIs (Meta/TikTok), `.ics`/Task Scheduler; embeddings
  (`fastembed`) se a busca semântica virar necessidade.

## 12. Convenções de código

- Sem comentários no código, salvo quando pedido.
- Texto de prompts e mensagens em português (sem acento em strings de prompt, por segurança de encoding).
- Config nova de fontes/perfis vai em `config/*.yaml`; parâmetros de ambiente em `.env`/`config.py`.
- Ao alterar `crew.py`, preserve as regras da seção 6.

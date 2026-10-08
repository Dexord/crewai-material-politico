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
| Busca | `duckduckgo-search` |
| Config | `pydantic-settings` (`.env`) |
| Gerenciador | `uv` (Python 3.13) |

Planejado para fases futuras: `chromadb` + embeddings Ollama (RAG), SQLite (persistência).

## 3. Comandos

```powershell
uv sync                                          # instalar/atualizar deps
uv run python -m src.main run --tema "<tema>"    # rodar o pipeline completo
```

Saída: arquivo markdown timestampado em `data/output/` (gitignored).

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
  config.py         # Settings (lê .env): ollama_base_url, ollama_model, output_dir, scrape_rate_limit
  crew.py           # monta os 4 agentes + 4 tasks. REGRAS DE TOM vivem aqui (TOM_ENQUADRAMENTO)
  profiles.py       # carrega profiles.yaml e injeta no analista
  main.py           # CLI (reconfigura stdout/stderr p/ utf-8 no Windows)
  output/render.py  # salva saída em data/output/
  tools/
    search.py       # buscar_na_web (DuckDuckGo -> markdown)
    scraper.py      # extrair_markdown (requests+bs4 -> markdown, com rate-limit e headers)
    sources.py      # listar_fontes, ler_rss, ler_rss_ativos (config/sources.yaml)
data/               # saidas e (futuro) indice — gitignored
```

## 5. Pipeline (sequencial)

1. **Pesquisador** (`tools: listar_fontes, ler_rss_ativos, ler_rss, buscar_na_web, extrair_markdown`)
   → dossiê de fatos numerados, cada um com `source_url`. Prioriza número/votação/data/contradição.
2. **Analista de Impacto** → nota 0–10 por perfil (lógica de persuasão/mudança de voto) + ângulo narrativo.
3. **Roteirista** → 5 manchetes (≤12 palavras) + roteiro `hook→problema→evidência→CTA` + `source_url`.
4. **Revisor** → gate de fato **e** de enquadramento; entrega versão final + tabela de validação.

Temperaturas separadas por agente: precisão `0.1` (pesquisador/revisor), `0.3` (analista),
criativo `0.7` (roteirista).

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
- **G1** responde por `requests` puro. **Senado RSS** correto: `https://www12.senado.leg.br/noticias/rss`.
- **Console Windows**: emojis/acentos causam ruído de `charmap` no crewAI. `src/main.py`
  reconfigura stdout/stderr para utf-8; rode com `$env:PYTHONUTF8=1` se necessário.
- **Espaço em branco/fonte única**: quando o tema tem pouca cobertura, o modelo tende a
  voltar a argumento de ausência — as regras da seção 6 existem para barrar isso.

## 11. Roadmap

- **F0 (feito):** pesquisador + busca/scraping → manchetes citadas.
- **F1 (feito):** 4 agentes, fontes parametrizáveis (RSS/portais), perfis, revisor.
- **F2:** RAG (ChromaDB + `nomic-embed-text`), análise por perfil com corpus indexado,
  citação literal do trecho-fonte na tabela de validação.
- **F3:** export por plataforma, fila/agendamento de postagem.

## 12. Convenções de código

- Sem comentários no código, salvo quando pedido.
- Texto de prompts e mensagens em português (sem acento em strings de prompt, por segurança de encoding).
- Config nova de fontes/perfis vai em `config/*.yaml`; parâmetros de ambiente em `.env`/`config.py`.
- Ao alterar `crew.py`, preserve as regras da seção 6.

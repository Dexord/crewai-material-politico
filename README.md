# crewai-material-politico

Sistema **multi-agente local** (roda 100% na sua máquina, sem nuvem) que pesquisa
notícias e fontes oficiais na web, monta um **grafo de conhecimento** estilo Obsidian e
gera **manchetes e roteiros curtos** para Facebook e TikTok.

O objetivo editorial do material é **oposição a Flávio Bolsonaro**, sempre **ancorado em
fatos com fonte citável** (número, votação, projeto, documento). Nada é escrito "de
cabeça": cada afirmação precisa de uma `source_url`.

> ⚠️ **Aviso importante (leia antes de usar).**
> - **Todo conteúdo é gerado por IA e PRECISA de verificação humana** antes de publicar.
> - Afirmação factual **falsa** sobre pessoa pública pode gerar **difamação/calúnia**.
>   O sistema tem um "revisor" justamente para barrar o que não tem fonte — mas ele **não
>   substitui** a checagem humana.
> - Propaganda eleitoral gerada por IA tem regra de identificação
>   (**TSE, Resolução 23.610/2019**). Mantenha o aviso *"Conteúdo gerado por IA — verificar
>   antes de publicar"* em tudo que for publicado.
> - Respeite os **Termos de Uso** e o `robots.txt` dos sites, além da **LGPD**.
> - Este repositório **não faz publicação automática** em nenhuma rede social.

---

## 1. Funcionalidades

- **Pesquisa web + scraping** de portais, feeds RSS e sites oficiais, convertendo páginas
  para markdown.
- **Pipeline de conteúdo** com 4 agentes: pesquisador → analista de impacto (por perfil
  demográfico) → roteirista → revisor (gate de fato e de enquadramento).
- **Grafo de conhecimento** em arquivos Markdown com links `[[wikilinks]]` (abre no
  Obsidian). Guarda notícias, fatos, pessoas e organizações com **fonte** em cada relação.
- **Agente investigador** que liga pessoas/instituições, mantém uma **fila de pesquisa** e
  **aprofunda o grafo** enfileirando alvos citados que ainda não têm nota (sementes).
- **Criador de Pauta**: cruza as **manchetes atuais dos RSS** com o grafo e propõe pautas
  (manchete + ângulo + fonte).
- **Loop autônomo** (ex.: por 6 horas) que alterna investigar e pesquisar sozinho.
- **Entregáveis extras** (opcionais, com `--saidas`): **roteiro de vídeo curto** (~1m30s),
  **posts para Facebook e Bluesky** e uma **reportagem/notícia** extensa — além da **fila de
  postagem** local com status.
- **Resolução de entidades** determinística: evita duplicar pessoas/organizações e
  oferece dedupe (`deduplicar`/`fundir`).
- **"Bibliotecário" determinístico** que gera o corpo legível de cada entidade
  (cargos, vínculos com fonte, onde é citada) — sem gastar o modelo.

---

## 2. Como funciona (visão geral)

```
             ┌─────────────┐
   pesquisa  │ Pesquisador │  busca web + RSS + scraping → salva fatos/entidades no vault
             └──────┬──────┘
                    │ dossiê de fatos (com fonte)
             ┌──────▼──────┐
             │  Analista   │  nota 0–10 por perfil demográfico + ângulo narrativo
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │ Roteirista  │  5 manchetes + roteiro (hook→problema→evidência→CTA)
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │  Revisor    │  gate de FATO e de ENQUADRAMENTO (corta o que não tem fonte)
             └──────┬──────┘
                    │ (opcional, com --saidas)
        ┌───────────┼───────────────────────────┐
 ┌──────▼──────┐ ┌──▼────────────┐ ┌────────────▼────────┐
 │ Roteirista  │ │ Copywriter de │ │ Redator Jornalista  │
 │ de Vídeo    │ │ Redes (FB/BS) │ │ (reportagem/notícia)│
 │ (~1m30s)    │ │               │ │                     │
 └─────────────┘ └───────────────┘ └─────────────────────┘ --> fila de postagem / arquivos
```

Em paralelo, há um segundo fluxo — o **grafo de conhecimento**:

- **Investigador** (`investigar`): não pesquisa na web. Lê o que já existe, liga
  entidades e **monta a fila** de quem falta pesquisar.
- **Pesquisador de Campo** (`pesquisar`): consome a fila, pesquisa na web e **salva** no
  vault (fatos, notícias, pessoas, organizações), expandindo o grafo em profundidade.

---

## 3. Requisitos

Para **rodar**, é preciso ter algum conhecimento técnico. Você vai precisar de:

- **Windows** (o projeto foi feito/testado nele), **Python 3.11+** e o gerenciador
  [**uv**](https://docs.astral.sh/uv/).
- [**Ollama**](https://ollama.com/) instalado e rodando, com o modelo baixado:
  ```powershell
  ollama pull qwen3.5:9b
  ```
- Uma **GPU** com VRAM suficiente (o autor usa uma **AMD RX 6700 XT, 12 GB**). Modelos 9B
  quantizados (Q4) rodam bem; GPUs fracas vão para o CPU e ficam lentas.
- (Opcional) [**Obsidian**](https://obsidian.md/) para navegar o grafo.

---

## 4. Instalação

```powershell
# 1. Clone o repositório e entre na pasta
git clone <url-do-repo>
cd crewai-material-politico

# 2. Instale as dependências
uv sync

# 3. Crie seu arquivo de configuração
Copy-Item .env.example .env
```

Confira se o Ollama está de pé e com o modelo carregado:

```powershell
ollama ps
```

---

## 5. Configuração

### 5.1 `.env` (parâmetros gerais)

```ini
OLLAMA_BASE_URL=http://localhost:11434   # onde o Ollama está rodando
OLLAMA_MODEL=qwen3.5:9b                   # modelo usado
OUTPUT_DIR=data/output                    # saída dos textos
SCRAPE_RATE_LIMIT=1.5                     # requisições por segundo no scraping
VAULT_DIR=data/vault                      # grafo de conhecimento (Obsidian)
MAX_DEPTH=2                               # profundidade máxima da expansão da fila
BLACKLIST_ALVOS=Flavio Bolsonaro          # alvos que NÃO devem ser auto-enfileirados
```

### 5.2 `config/sources.yaml` (de onde pesquisar)

Edite aqui para adicionar/remover **feeds RSS** e **portais**:

```yaml
rss:
  - nome: "Agencia Brasil"
    url: "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"
    ativo: true
portais:
  - nome: "Meu blog"
    url: "https://exemplo.com"
    ativo: false
```

### 5.3 `config/profiles.yaml` (perfis demográficos)

Define os públicos que o **analista de impacto** avalia (dores, valores, canais,
gatilhos, objeções). Ajuste conforme sua estratégia.

---

## 6. Uso — manual dos comandos

Todos os comandos rodam com `uv run python -m src.main <comando>`.

### 6.1 Gerar conteúdo (pipeline de 4 agentes)

```powershell
uv run python -m src.main run --tema "votações de Flávio Bolsonaro no Senado"
```

Gera 5 manchetes (**uma por perfil demográfico**) com roteiro e `source_url`, e salva um `.md`
em `data/output/`.

Com `--saidas`, também gera entregáveis extras (agentes especializados). Valores:
`video`, `redes`, `reportagem` (ou `todas`):

```powershell
uv run python -m src.main run --tema "..." --saidas todas
```

- **video** → roteiro de vídeo curto (~1m30s) **por perfil** em `data/output/entregaveis/`.
- **redes** → **um item por perfil** (post de **Facebook** + **fio do Bluesky**, com link) na
  **fila de postagem**; e o **título/subtítulo da imagem** (Canva) em `data/output/entregaveis/`.
- **reportagem** → reportagem/notícia extensa em `data/output/entregaveis/`.

### 6.2 Fila de postagem (export-only, sem postar sozinho)

```powershell
uv run python -m src.main agenda                 # lista as peças
uv run python -m src.main agenda --status rascunho
uv run python -m src.main aprovar <id>           # rascunho -> aprovado
uv run python -m src.main publicar <id>          # aprovado -> publicado
```

### 6.3 Grafo de conhecimento (Obsidian)

```powershell
uv run python -m src.main investigar             # estrutura o vault + monta a fila
uv run python -m src.main pesquisar --limite 10  # pesquisa 10 itens da fila
uv run python -m src.main enfileirar "Banco Master" --prioridade 5 --motivo "caso"
uv run python -m src.main pautas                 # pautas a partir das manchetes atuais dos RSS
```

### 6.4 Loop autônomo (rodar sozinho por horas)

```powershell
uv run python -m src.main pesquisar --horas 6 --lote 10
```

Roda `investigar ↔ pesquisar` por 6 horas, **imprimindo tudo ao vivo no terminal** e
salvando um resumo em `data/output/loop-*.log`. Para na hora ou quando satura.

Há um atalho que também evita o PC dormir e aquece o Ollama:

```powershell
.\scripts\loop-noite.ps1 -Horas 6
```

### 6.5 Manutenção do grafo

```powershell
uv run python -m src.main render-entidades        # regenera o corpo das entidades
uv run python -m src.main migrar-organizacoes     # dry-run: pessoa -> organizacao
uv run python -m src.main migrar-organizacoes --aplicar
uv run python -m src.main deduplicar              # dry-run: lista duplicatas
uv run python -m src.main fundir <id_a> <id_b>    # funde b -> a (reescreve os links)
```

---

## 7. O grafo no Obsidian

Abra a pasta **`data/vault/`** no Obsidian (ela já vem com um `.obsidian`).

- Cada **notícia** e **fato** é uma nota com o texto e a fonte.
- Cada **pessoa** e **organização** é uma nota com **Cargos/Tipo**, **Vínculos** (com
  fonte) e **Mencionado em** (onde aquela pessoa/instituição aparece).
- Os `[[wikilinks]]` ligam tudo — use o **Graph View** para visualizar a rede.
- O `log/` registra automaticamente o que o sistema fez.

---

## 8. Estrutura do projeto

```
config/            # fontes (sources.yaml) e perfis (profiles.yaml)
src/
  crew*.py         # definição dos agentes (conteudo, pesquisador, investigador)
  main.py          # todos os comandos (CLI)
  vault/           # grafo: notas, fila, log, render, dedupe, migração
  tools/           # busca web, scraping, RSS e ferramentas do vault
data/
  output/          # textos gerados e fila de postagem (não versionado)
  vault/           # grafo de conhecimento / Obsidian (não versionado)
scripts/
  loop-noite.ps1   # atalho do loop autônomo
AGENTS.md          # guia técnico para quem for mexer no código
```

---

## 9. Limitações conhecidas

- **UOL devolve 403** ao scraping por `requests` (proteção anti-bot). Use RSS ou outro portal.
- A busca web usa `ddgs` no modo `auto`; backends individuais costumam ser bloqueados.
- Modelos pequenos (9B) às vezes "suavizam" o tom — os prompts e o revisor existem para
  conter isso, mas **sempre revise**.
- **Qualidade da checagem**: o revisor é o próprio modelo local. Ele é um bom filtro, mas
  **não é auditoria independente**.

---

## 10. Roadmap

- [x] F0–F1: pesquisa + pipeline de 4 agentes.
- [x] F2: grafo de conhecimento (vault/Obsidian) + investigador + integração ao `run`.
- [x] F3: export por plataforma (Facebook/TikTok) + fila de postagem.
- [x] Dedupe de entidades + corpos renderizados.
- [ ] Futuro: auto-post via APIs oficiais, agendador (`.ics`/Task Scheduler), busca
  semântica opcional (embeddings) se o volume crescer.

---

## 11. Contribuição e licença

- Alterações no código: veja `AGENTS.md` (convenções, regras editoriais que **não** podem
  ser removidas, e como rodar).
- **Não** commite a pasta `data/` (conteúdo e grafo são locais).
- Licença: _a definir pelo autor._

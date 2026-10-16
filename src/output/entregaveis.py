import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import get_settings

DISCLOSURE = "Conteúdo gerado por IA - verificar antes de publicar."


def _entregaveis_dir() -> Path:
    return Path(get_settings().output_dir) / "entregaveis"


class CenaVideo(BaseModel):
    tempo: str = Field(description="Faixa de tempo da cena, ex: 0:00-0:12")
    bloco: str = Field(
        default="",
        description="Papel da cena: gancho | polemica | comparacao | humor | impacto | cta",
    )
    narracao: str = Field(description="O que e falado/narrado na cena")
    texto_tela: str = Field(description="Texto que aparece na tela")


class RoteiroVideo(BaseModel):
    tema: str
    perfil_alvo: str = Field(default="", description="Perfil demografico alvo")
    titulo: str = Field(description="Titulo do video")
    duracao: str = Field(default="1m45s", description="Duracao estimada (1m30s a 2min)")
    duracao_s: int = Field(default=0, description="Duracao total estimada em segundos")
    gancho: str = Field(description="Frase de abertura (primeiros segundos)")
    cenas: list[CenaVideo] = Field(default_factory=list)
    cta: str = Field(default="", description="Chamada para acao final")
    source_urls: list[str] = Field(default_factory=list)


class PacoteVideos(BaseModel):
    tema: str
    videos: list[RoteiroVideo] = Field(default_factory=list)


class PostFacebook(BaseModel):
    texto: str = Field(description="Texto da publicacao no Facebook (mais longo, com gancho e CTA)")
    hashtags: list[str] = Field(default_factory=list)


class ThreadBluesky(BaseModel):
    posts: list[str] = Field(
        description=(
            "Fio do Bluesky: de 1 a 4 posts, em ordem. Cada post com no maximo ~300 "
            "caracteres e, quando houver link/fonte, incluir o link no proprio post."
        )
    )


class TextoImagem(BaseModel):
    titulo: str = Field(description="Titulo curto (ate ~6 palavras) para a imagem no Canva")
    subtitulo: str = Field(description="Subtitulo curto que contextualiza a imagem")


class PacoteRedes(BaseModel):
    perfil_alvo: str = Field(default="", description="Perfil demografico alvo")
    facebook: PostFacebook
    bluesky: ThreadBluesky
    imagem: TextoImagem


class PacoteRedesMulti(BaseModel):
    tema: str
    itens: list[PacoteRedes] = Field(default_factory=list)


class Marco(BaseModel):
    data: str = Field(description="Data do fato (ex.: 07/07/2026 ou 'julho de 2026')")
    fato: str = Field(description="O que aconteceu, em uma linha, com numero/valor quando houver")
    fonte: str = Field(default="", description="URL ou veiculo da fonte")


class Reportagem(BaseModel):
    tema: str
    titulo: str = Field(description="Titulo da reportagem")
    linha_fina: str = Field(description="Subtitulo/linha fina")
    lead: str = Field(description="Paragrafo de abertura (lide)")
    corpo: str = Field(description="Corpo da materia em markdown, com secoes (## ...)")
    cronologia: list[Marco] = Field(
        default_factory=list, description="Linha do tempo dos fatos, com data e fonte"
    )
    dados_chave: list[str] = Field(
        default_factory=list, description="Numeros/dados essenciais da materia"
    )
    fontes: list[str] = Field(default_factory=list)


class Pauta(BaseModel):
    manchete: str = Field(description="Manchete da pauta (ate 12 palavras)")
    angulo: str = Field(description="A contradicao/consequencia concreta a explorar")
    entidades: list[str] = Field(default_factory=list, description="Entidades do grafo ligadas")
    alvos_pesquisa: list[str] = Field(
        default_factory=list,
        description="Nomes/temas relevantes ainda SEM nota no vault, a pesquisar",
    )
    source_url: str = Field(default="", description="URL da materia")


class PacotePautas(BaseModel):
    itens: list[Pauta] = Field(default_factory=list)


def _pautas_dir() -> Path:
    return Path(get_settings().output_dir) / "pautas"


def salvar_pautas_json(pacote: PacotePautas) -> Path:
    out = _pautas_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "pautas.json"
    path.write_text(json.dumps(pacote.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def carregar_pautas() -> list[dict]:
    path = _pautas_dir() / "pautas.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("itens", [])
    except json.JSONDecodeError:
        return []


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "saida"


def _path(prefixo: str, tema: str, sufixo: str = "") -> Path:
    out = _entregaveis_dir()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    nome = _slug(tema)[:40]
    if sufixo:
        nome = f"{nome}-{_slug(sufixo)[:24]}"
    return out / f"{stamp}-{prefixo}-{nome}.md"


def salvar_roteiro_video(rv: RoteiroVideo, tema: str) -> Path:
    linhas = [
        f"# Roteiro de video — {rv.titulo}",
        "",
        f"**Tema:** {tema}  |  **Perfil-alvo:** {rv.perfil_alvo}  |  **Duracao:** {rv.duracao}",
        "",
        f"**Gancho:** {rv.gancho}",
        "",
        "## Cenas",
    ]
    for i, cena in enumerate(rv.cenas, 1):
        bloco = f" [{cena.bloco.upper()}]" if cena.bloco else ""
        linhas.append(f"### Cena {i} ({cena.tempo}){bloco}")
        linhas.append(f"- Narracao: {cena.narracao}")
        linhas.append(f"- Texto na tela: {cena.texto_tela}")
    if rv.cta:
        linhas += ["", f"**CTA:** {rv.cta}"]
    if rv.source_urls:
        linhas += ["", "## Fontes"] + [f"- {u}" for u in rv.source_urls]
    linhas += ["", "---", DISCLOSURE]
    path = _path("roteiro-video", tema, rv.perfil_alvo)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path


def salvar_reportagem(rep: Reportagem, tema: str) -> Path:
    linhas = [
        f"# {rep.titulo}",
        "",
        f"*{rep.linha_fina}*",
        "",
        rep.lead,
        "",
        rep.corpo,
    ]
    if rep.cronologia:
        linhas += ["", "## Cronologia"]
        for m in rep.cronologia:
            linha = f"- **{m.data}** — {m.fato}"
            if m.fonte:
                linha += f" ({m.fonte})"
            linhas.append(linha)
    if rep.dados_chave:
        linhas += ["", "## Dados-chave"] + [f"- {d}" for d in rep.dados_chave]
    if rep.fontes:
        linhas += ["", "## Fontes"] + [f"- {u}" for u in rep.fontes]
    linhas += ["", "---", DISCLOSURE]
    path = _path("reportagem", tema)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path


def salvar_pacote_redes(pacote: PacoteRedes, tema: str) -> Path:
    n = len(pacote.bluesky.posts)
    linhas = [
        f"# Redes — {tema} ({pacote.perfil_alvo})",
        "",
        "## Imagem (para criar no Canva)",
        f"- **Título:** {pacote.imagem.titulo}",
        f"- **Subtítulo:** {pacote.imagem.subtitulo}",
        "",
        "## Facebook",
        pacote.facebook.texto,
    ]
    if pacote.facebook.hashtags:
        linhas.append("Hashtags: " + " ".join(pacote.facebook.hashtags))
    linhas += ["", f"## Bluesky (fio de {n} post{'s' if n != 1 else ''})"]
    for i, post in enumerate(pacote.bluesky.posts, 1):
        linhas += [f"### Post {i}/{n}", post]
    linhas += ["", "---", DISCLOSURE]
    path = _path("redes", tema, pacote.perfil_alvo)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

DISCLOSURE = "Conteúdo gerado por IA - verificar antes de publicar."
ENTREGAVEIS_DIR = Path("data/output/entregaveis")


class CenaVideo(BaseModel):
    tempo: str = Field(description="Faixa de tempo da cena, ex: 0:00-0:12")
    narracao: str = Field(description="O que e falado/narrado na cena")
    texto_tela: str = Field(description="Texto que aparece na tela")


class RoteiroVideo(BaseModel):
    tema: str
    perfil_alvo: str = Field(default="", description="Perfil demografico alvo")
    titulo: str = Field(description="Titulo do video")
    duracao: str = Field(default="1m30s", description="Duracao estimada")
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


class Reportagem(BaseModel):
    tema: str
    titulo: str = Field(description="Titulo da reportagem")
    linha_fina: str = Field(description="Subtitulo/linha fina")
    lead: str = Field(description="Paragrafo de abertura (lide)")
    corpo: str = Field(description="Corpo da materia em markdown, com secoes (## ...)")
    fontes: list[str] = Field(default_factory=list)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "saida"


def _path(prefixo: str, tema: str) -> Path:
    ENTREGAVEIS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ENTREGAVEIS_DIR / f"{stamp}-{prefixo}-{_slug(tema)[:40]}.md"


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
        linhas.append(f"### Cena {i} ({cena.tempo})")
        linhas.append(f"- Narracao: {cena.narracao}")
        linhas.append(f"- Texto na tela: {cena.texto_tela}")
    if rv.cta:
        linhas += ["", f"**CTA:** {rv.cta}"]
    if rv.source_urls:
        linhas += ["", "## Fontes"] + [f"- {u}" for u in rv.source_urls]
    linhas += ["", "---", DISCLOSURE]
    path = _path("roteiro-video", f"{tema}-{rv.perfil_alvo}")
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
    path = _path("redes", f"{tema}-{pacote.perfil_alvo}")
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path

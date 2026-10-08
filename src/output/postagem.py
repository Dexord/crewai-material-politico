import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

DISCLOSURE = "Conteúdo gerado por IA - verificar antes de publicar."
FILA_PATH = Path("data/output/fila-postagem.json")
POSTAGENS_DIR = Path("data/output/postagens")


class Roteiro(BaseModel):
    hook: str = Field(description="Gancho dos primeiros 2 segundos")
    problema: str = Field(description="O problema concreto")
    evidencia: str = Field(description="A evidencia/fato com base na fonte")
    cta: str = Field(description="Chamada para acao")


class Peca(BaseModel):
    plataforma: str = Field(description="facebook ou tiktok")
    perfil_alvo: str = Field(description="Perfil demografico alvo")
    manchete: str = Field(description="Manchete/titulo principal")
    texto_publicacao: str = Field(description="Legenda/descricao da publicacao")
    hashtags: list[str] = Field(default_factory=list)
    roteiro: Roteiro
    titulo: str | None = Field(default=None, description="TikTok: titulo exibido")
    imagem_titulo: str | None = Field(default=None, description="TikTok: titulo do texto da imagem")
    imagem_subtitulo: str | None = Field(default=None, description="TikTok: subtitulo do texto da imagem")
    texto_tela: list[str] = Field(default_factory=list, description="TikTok: texto por cena")
    source_url: str = ""
    disclosure: str = DISCLOSURE


class Pacote(BaseModel):
    tema: str
    pecas: list[Peca] = Field(default_factory=list)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "peca"


def _load() -> list[dict]:
    if not FILA_PATH.exists():
        return []
    try:
        return json.loads(FILA_PATH.read_text(encoding="utf-8")).get("pecas", [])
    except json.JSONDecodeError:
        return []


def _save(pecas: list[dict]) -> None:
    FILA_PATH.parent.mkdir(parents=True, exist_ok=True)
    FILA_PATH.write_text(
        json.dumps({"pecas": pecas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _unique_id(existentes: list[dict], base: str) -> str:
    ids = {p["id"] for p in existentes}
    if base not in ids:
        return base
    i = 2
    while f"{base}-{i}" in ids:
        i += 1
    return f"{base}-{i}"


def add_pacote(pacote: Pacote, tema: str | None = None) -> list[str]:
    pecas = _load()
    novos_ids: list[str] = []
    for peca in pacote.pecas:
        base = f"peca-{datetime.now():%Y%m%d}-{_slug(peca.plataforma)}-{_slug(peca.manchete)[:40]}"
        peca_id = _unique_id(pecas, base)
        registro = peca.model_dump()
        registro.update(
            {
                "id": peca_id,
                "tema": tema or pacote.tema,
                "status": "rascunho",
                "criado_em": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            }
        )
        pecas.append(registro)
        novos_ids.append(peca_id)
        _write_txt(registro)
    _save(pecas)
    return novos_ids


def list_pecas(status: str | None = None) -> list[dict]:
    pecas = _load()
    if status:
        pecas = [p for p in pecas if p.get("status") == status]
    return pecas


def set_status(peca_id: str, status: str) -> bool:
    pecas = _load()
    for p in pecas:
        if p["id"] == peca_id:
            p["status"] = status
            _save(pecas)
            return True
    return False


def _write_txt(peca: dict) -> Path:
    POSTAGENS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTAGENS_DIR / f"{peca['id']}.txt"
    path.write_text(_render(peca), encoding="utf-8")
    return path


def _render(peca: dict) -> str:
    r = peca.get("roteiro", {})
    linha = [f"### {peca.get('plataforma', '').upper()} — {peca.get('perfil_alvo', '')}"]
    linha.append(f"Manchete: {peca.get('manchete', '')}")

    if peca.get("plataforma") == "tiktok":
        linha.append(f"Título: {peca.get('titulo') or peca.get('manchete', '')}")
        linha.append("")
        linha.append("IMAGEM (texto da arte):")
        linha.append(f"  Título: {peca.get('imagem_titulo') or peca.get('manchete', '')}")
        linha.append(f"  Subtítulo: {peca.get('imagem_subtitulo') or ''}")
        if peca.get("texto_tela"):
            linha.append("")
            linha.append("Texto na tela (por cena):")
            for cena in peca["texto_tela"]:
                linha.append(f"  - {cena}")

    linha.append("")
    linha.append("Roteiro:")
    linha.append(f"  - Hook (0-2s): {r.get('hook', '')}")
    linha.append(f"  - Problema: {r.get('problema', '')}")
    linha.append(f"  - Evidência: {r.get('evidencia', '')}")
    linha.append(f"  - CTA: {r.get('cta', '')}")
    linha.append("")
    linha.append(f"Texto da publicação: {peca.get('texto_publicacao', '')}")
    if peca.get("hashtags"):
        linha.append("Hashtags: " + " ".join(peca["hashtags"]))
    linha.append(f"Fonte: {peca.get('source_url', '')}")
    linha.append("")
    linha.append(peca.get("disclosure") or DISCLOSURE)
    return "\n".join(linha) + "\n"


def render_all() -> list[Path]:
    paths = []
    for peca in _load():
        paths.append(_write_txt(peca))
    return paths

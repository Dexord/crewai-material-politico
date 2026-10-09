import re

from .vault import all_notes, normalize, note_path, read_note, save_note

PADROES_FORTES = [
    r"\bdelegacia\b", r"\bpolicia\b", r"\bministerio\b", r"\bsecretaria\b",
    r"\bprefeitura\b", r"\bgoverno\b", r"\bcamara dos deputados\b", r"\bcamara municipal\b",
    r"\bcamara legislativa\b", r"\bsenado\b", r"\bassembleia legislativa\b",
    r"\btribunal\b", r"\bstf\b", r"\bstj\b", r"\btse\b", r"\btre\b", r"\btce\b",
    r"\btcu\b", r"\bcgu\b", r"\bcoaf\b", r"\bbanco\b", r"\bpartido\b", r"\bassociacao\b",
    r"\binstituto\b", r"\bfundacao\b", r"\bconsorcio\b", r"\bholding\b",
    r"\bcomando vermelho\b", r"\bpcc\b", r"\bamigos dos amigos\b",
    r"\bfaccao\b", r"\bmilicia\b", r"\bong\b", r"\bsindicato\b", r"\buniversidade\b",
    r"\buerj\b", r"\bufrj\b", r"\busp\b", r"\bhospital\b", r"\breceita federal\b",
    r"\bcvm\b", r"\bpolícia federal\b", r"\bcongresso nacional\b", r"\bplanalto\b",
]

PADROES_DUVIDOSOS = [
    r"\bdp\b", r"\bpf\b", r"\bpm\b", r"\bmp\b", r"\bpl\b", r"\bpt\b", r"\bpsl\b",
    r"\bprf\b", r"\bada\b", r"\bcsn\b", r"\bempresa\b", r"\bcompanhia\b",
]


def _match(texto: str, padroes: list[str]) -> str | None:
    for pat in padroes:
        if re.search(pat, texto):
            return pat.replace("\\b", "")
    return None


def classificar() -> dict:
    fortes: list[dict] = []
    duvidosos: list[dict] = []
    for fm, _, _ in all_notes("pessoa"):
        if fm.get("tipo") != "pessoa":
            continue
        nome = fm.get("nome") or ""
        nome_n = normalize(nome)

        motivo = _match(nome_n, PADROES_FORTES)
        if motivo:
            fortes.append({"id": fm["id"], "nome": nome, "motivo": f"nome~{motivo}"})
            continue

        motivo = _match(nome_n, PADROES_DUVIDOSOS)
        if motivo:
            duvidosos.append({"id": fm["id"], "nome": nome, "motivo": f"nome~{motivo}"})
    return {"fortes": fortes, "duvidosos": duvidosos}


def _migrar_uma(note_id: str) -> None:
    found = read_note(note_id)
    if not found:
        raise ValueError("nota nao encontrada")
    fm, body = found
    if fm.get("tipo") == "organizacao":
        return
    fm["tipo"] = "organizacao"
    fm.setdefault("tipo_org", fm.get("cargos") or [])
    old_path = note_path("pessoa", note_id)
    save_note(fm, body)
    new_path = note_path("organizacao", note_id)
    if old_path.exists() and old_path.resolve() != new_path.resolve():
        old_path.unlink()


def migrar(aplicar: bool = False, incluir_duvidosos: bool = False) -> dict:
    cls = classificar()
    alvos = list(cls["fortes"]) + (list(cls["duvidosos"]) if incluir_duvidosos else [])
    migrados: list[str] = []
    erros: list[tuple[str, str]] = []
    if aplicar:
        for item in alvos:
            try:
                _migrar_uma(item["id"])
                migrados.append(item["id"])
            except Exception as exc:  # noqa: BLE001
                erros.append((item["id"], str(exc)))
    return {
        "aplicado": aplicar,
        "fortes": cls["fortes"],
        "duvidosos": cls["duvidosos"],
        "alvos": len(alvos),
        "migrados": migrados,
        "erros": erros,
    }

from pathlib import Path

import yaml

PROFILES_PATH = Path("config/profiles.yaml")


def load_profiles() -> list[dict]:
    if not PROFILES_PATH.exists():
        return []
    with PROFILES_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("perfis", [])


def profiles_as_markdown() -> str:
    perfis = load_profiles()
    if not perfis:
        return "Nenhum perfil configurado."
    lines = ["## Perfis demograficos"]
    for p in perfis:
        objecoes = p.get("objeções") or p.get("objecoes") or []
        lines.append(f"\n### {p.get('nome')} (id: {p.get('id')})")
        lines.append(f"- Dores: {', '.join(p.get('dores', []))}")
        lines.append(f"- Valores: {', '.join(p.get('valores', []))}")
        lines.append(f"- Canais: {', '.join(p.get('canais', []))}")
        lines.append(f"- Gatilhos: {', '.join(p.get('gatilhos', []))}")
        lines.append(f"- Objecoes: {', '.join(objecoes)}")
    return "\n".join(lines)

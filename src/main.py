import argparse
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from .config import get_settings
from .crew import build_crew
from .crew_investigador import build_investigador_crew
from .crew_pesquisador import build_pesquisador_crew
from .output import postagem
from .output.render import save_output
from .vault import queue as fila
from .vault.log import log_event
from .vault.vault import ensure_vault


def run(tema: str, plataformas: str = "") -> int:
    settings = get_settings()
    plats = [p.strip().lower() for p in plataformas.split(",") if p.strip()] or None
    crew = build_crew(settings, plats)
    result = crew.kickoff(inputs={"tema": tema})
    text = getattr(result, "raw", str(result))
    print(text)
    path = save_output(text, settings.output_dir, tema)
    print(f"\nSaída salva em: {path}")

    if plats:
        pacote = getattr(result, "pydantic", None)
        if pacote is not None:
            ids = postagem.add_pacote(pacote, tema)
            print(f"\n{len(ids)} peças enfileiradas (rascunho): {', '.join(ids)}")
            print("Arquivos de copiar-e-colar em: data/output/postagens/")
        else:
            print("\nAviso: saída estruturada de peças indisponível.")
    return 0


def investigar() -> int:
    settings = get_settings()
    ensure_vault()
    crew = build_investigador_crew(settings)
    result = crew.kickoff()
    text = getattr(result, "raw", str(result))
    print(text)
    path = save_output(text, settings.output_dir, "investigacao")
    print(f"\nResumo salvo em: {path}")
    return 0


def pesquisar(limite: int) -> int:
    settings = get_settings()
    ensure_vault()

    processados = 0
    while limite == 0 or processados < limite:
        item = fila.next_item()
        if not item:
            print("Fila vazia.")
            break
        if int(item.get("profundidade", 0)) > settings.max_depth:
            fila.mark_status(item["id"], "ignorado")
            continue

        alvo = item.get("alvo")
        print(f"\n=== Pesquisando: {alvo} ({item['id']}) ===")
        fila.mark_status(item["id"], "em_andamento")
        log_event(f"pesquisar iniciado: {alvo}", "fila")

        try:
            crew = build_pesquisador_crew(settings)
            result = crew.kickoff(
                inputs={
                    "alvo": alvo,
                    "motivo": item.get("motivo", ""),
                    "profundidade": item.get("profundidade", 0),
                    "max_depth": settings.max_depth,
                }
            )
            text = getattr(result, "raw", str(result))
            save_output(text, settings.output_dir, f"pesquisa-{item['id']}")
            fila.mark_status(item["id"], "concluido")
            log_event(f"pesquisar concluido: {alvo}", "fila")
        except Exception as exc:  # noqa: BLE001
            print(f"Erro ao pesquisar {alvo}: {exc}")
            log_event(f"pesquisar erro em {alvo}: {exc}", "fila")
            fila.mark_status(item["id"], "pendente")

        processados += 1

    print(f"\nItens processados: {processados}. Pendentes na fila: {fila.pending_count()}.")
    return 0


def agenda(status: str = "") -> int:
    pecas = postagem.list_pecas(status or None)
    if not pecas:
        print("Fila de postagem vazia.")
        return 0
    for p in pecas:
        print(
            f"[{p.get('status')}] {p['id']} | {p.get('plataforma')} | "
            f"{p.get('perfil_alvo', '')} | {str(p.get('manchete', ''))[:60]}"
        )
    print(f"\nTotal: {len(pecas)} peça(s).")
    return 0


def marcar_status(peca_id: str, status: str) -> int:
    if postagem.set_status(peca_id, status):
        print(f"{peca_id} -> {status}")
        return 0
    print(f"Peça não encontrada: {peca_id}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="material-politico")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_run = sub.add_parser("run", help="Executa o pipeline de conteudo")
    p_run.add_argument("--tema", required=True, help="Tema da pesquisa")
    p_run.add_argument(
        "--plataformas", default="", help="Gera pecas por plataforma (ex: facebook,tiktok)"
    )

    sub.add_parser("investigar", help="Estrutura o vault e mantem a fila de pesquisa")

    p_pesq = sub.add_parser("pesquisar", help="Consome a fila de pesquisa (overnight)")
    p_pesq.add_argument("--limite", type=int, default=0, help="Itens a processar (0 = esvaziar)")

    p_ag = sub.add_parser("agenda", help="Lista a fila de postagem")
    p_ag.add_argument("--status", default="", help="rascunho | aprovado | publicado")

    p_ap = sub.add_parser("aprovar", help="Marca peca como aprovada")
    p_ap.add_argument("id", help="Id da peca")

    p_pub = sub.add_parser("publicar", help="Marca peca como publicada")
    p_pub.add_argument("id", help="Id da peca")

    args = parser.parse_args()
    if args.comando == "run":
        return run(args.tema, args.plataformas)
    if args.comando == "investigar":
        return investigar()
    if args.comando == "pesquisar":
        return pesquisar(args.limite)
    if args.comando == "agenda":
        return agenda(args.status)
    if args.comando == "aprovar":
        return marcar_status(args.id, "aprovado")
    if args.comando == "publicar":
        return marcar_status(args.id, "publicado")
    return 1


if __name__ == "__main__":
    sys.exit(main())

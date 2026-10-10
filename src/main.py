import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

from .config import get_settings
from .crew import build_crew
from .crew_investigador import build_investigador_crew
from .crew_pesquisador import build_pesquisador_crew
from .output import postagem
from .output.render import save_output
from .vault import queue as fila
from .vault.entidades import deduplicar, fundir
from .vault.log import log_event
from .vault.migrar import migrar
from .vault.render import atualizar_entidades
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

    _render_entidades()
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
    _render_entidades()
    return 0


def _render_entidades() -> None:
    res = atualizar_entidades()
    print(
        f"[bibliotecario] {res['entidades']} entidades renderizadas; "
        f"{res['mencionado_atualizado']} com 'mencionado_em' atualizado."
    )


def render_entidades() -> int:
    _render_entidades()
    return 0


def enfileirar(alvo: str, motivo: str = "", prioridade: int = 3) -> int:
    ensure_vault()
    note_id = fila.add_item(alvo, motivo, prioridade, 0, "cli", forcar=True)
    if note_id:
        print(f"Enfileirado: {alvo} ({note_id})")
        return 0
    print(f"Ignorado (ja existe na fila): {alvo}")
    return 0


def _processar_item(item: dict, settings) -> bool:
    alvo = item.get("alvo")
    print(f"\n=== Pesquisando: {alvo} ({item['id']}) ===", flush=True)
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
        _render_entidades()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Erro ao pesquisar {alvo}: {exc}", flush=True)
        log_event(f"pesquisar erro em {alvo}: {exc}", "fila")
        fila.mark_status(item["id"], "pendente")
        return False


def pesquisar(limite: int = 0, horas: float = 0.0, lote: int = 10) -> int:
    settings = get_settings()
    ensure_vault()

    orfaos = fila.reset_em_andamento()
    if orfaos:
        print(f"Retomando {orfaos} item(ns) orfao(s) (em_andamento -> pendente).")

    if horas and horas > 0:
        return _daemon(settings, horas, lote)

    processados = 0
    while limite == 0 or processados < limite:
        item = fila.next_item()
        if not item:
            print("Fila vazia.")
            break
        if int(item.get("profundidade", 0)) > settings.max_depth:
            fila.mark_status(item["id"], "ignorado")
            continue
        _processar_item(item, settings)
        processados += 1

    print(f"\nItens processados: {processados}. Pendentes na fila: {fila.pending_count()}.")
    return 0


def _daemon(settings, horas: float, lote: int) -> int:
    deadline = datetime.now() + timedelta(hours=horas)
    log_path = Path(settings.output_dir) / f"loop-{datetime.now():%Y%m%d-%H%M%S}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"daemon iniciado por {horas}h (lote={lote}). Fim previsto: {deadline:%H:%M}.")
    log(f"log em: {log_path}")
    dry = 0
    total = 0

    while datetime.now() < deadline:
        if fila.pending_count() == 0:
            dry += 1
            log(f"fila vazia -> rodando investigador (dry={dry})")
            try:
                build_investigador_crew(settings).kickoff()
            except Exception as exc:  # noqa: BLE001
                log(f"erro no investigador: {exc}")
            if fila.pending_count() == 0:
                if dry >= 3:
                    log("saturado (3 ciclos sem novidades). Encerrando.")
                    break
                log("ainda vazio; aguardando 300s.")
                time.sleep(300)
                continue

        dry = 0
        processados_lote = 0
        while processados_lote < lote and datetime.now() < deadline:
            item = fila.next_item()
            if not item:
                break
            if int(item.get("profundidade", 0)) > settings.max_depth:
                fila.mark_status(item["id"], "ignorado")
                continue
            _processar_item(item, settings)
            processados_lote += 1
            total += 1
        log(f"lote concluido ({processados_lote} itens; total {total})")

    log(f"daemon encerrado. Itens processados: {total}. Pendentes: {fila.pending_count()}.")
    print(f"\nLog do loop: {log_path}")
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


def fila_limpar(aplicar: bool = False) -> int:
    res = fila.limpar(aplicar=aplicar)
    plano = res["plano"]
    print(f"Pendentes: {res['pendentes']} | a ignorar: {len(plano)}")
    for p in plano:
        print(f"  {p['alvo']}  ({p['id']})  [{'; '.join(p['motivos'])}]")
    if aplicar:
        print(f"\nMarcados como ignorado: {len(plano)}")
    else:
        print("\n(dry-run) Nada alterado. Use --aplicar para marcar como ignorado.")
    return 0


def deduplicar_cmd(aplicar: bool = False) -> int:
    res = deduplicar(aplicar=aplicar)
    plano = res["plano"]
    print(f"Clusters encontrados: {len(plano)} (pares: {len(res['pares'])})")
    for item in plano:
        tag = "AUTO" if item["auto"] else "revisar"
        print(f"\n[{tag}] canonico sugerido: {item['canonico']}")
        for membro in item["membros"]:
            print(f"    - {membro}")
    if aplicar:
        print(f"\nMerges aplicados (auto): {len(res['migrados'])}")
        for m in res["migrados"]:
            print(f"    - {m}")
    else:
        print("\n(dry-run) Nada alterado. Use --aplicar para fundir os clusters AUTO.")
    return 0


def fundir_cmd(id_a: str, id_b: str) -> int:
    print(fundir(id_a, id_b))
    return 0


def migrar_organizacoes(aplicar: bool = False, duvidosos: bool = False) -> int:
    res = migrar(aplicar=aplicar, incluir_duvidosos=duvidosos)
    fortes = res["fortes"]
    duv = res["duvidosos"]
    print(f"Fortes: {len(fortes)} | Duvidosos: {len(duv)}")
    print("\n-- FORTES (migram com --aplicar) --")
    for it in fortes:
        print(f"  {it['nome']}  ({it['id']})  [{it['motivo']}]")
    print("\n-- DUVIDOSOS (inclua com --duvidosos) --")
    for it in duv:
        print(f"  {it['nome']}  ({it['id']})  [{it['motivo']}]")
    if res["aplicado"]:
        print(f"\nMigrados: {len(res['migrados'])}")
        for e in res["erros"]:
            print(f"  ERRO {e[0]}: {e[1]}")
    else:
        print("\n(dry-run) Nada foi alterado. Use --aplicar para migrar.")
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

    p_pesq = sub.add_parser("pesquisar", help="Consome a fila de pesquisa")
    p_pesq.add_argument("--limite", type=int, default=0, help="Itens a processar (0 = esvaziar)")
    p_pesq.add_argument("--horas", type=float, default=0.0, help="Roda como daemon por N horas")
    p_pesq.add_argument("--lote", type=int, default=10, help="Itens por lote no modo --horas")

    p_enq = sub.add_parser("enfileirar", help="Adiciona um alvo a fila de pesquisa")
    p_enq.add_argument("alvo", help="Pessoa, instituicao ou tema")
    p_enq.add_argument("--motivo", default="", help="Por que pesquisar")
    p_enq.add_argument("--prioridade", type=int, default=3, help="1 a 5")

    p_ag = sub.add_parser("agenda", help="Lista a fila de postagem")
    p_ag.add_argument("--status", default="", help="rascunho | aprovado | publicado")

    p_ap = sub.add_parser("aprovar", help="Marca peca como aprovada")
    p_ap.add_argument("id", help="Id da peca")

    p_pub = sub.add_parser("publicar", help="Marca peca como publicada")
    p_pub.add_argument("id", help="Id da peca")

    p_mig = sub.add_parser(
        "migrar-organizacoes", help="Reclassifica pessoas->organizacoes (dry-run por padrao)"
    )
    p_mig.add_argument("--aplicar", action="store_true", help="Aplica de fato a migracao")
    p_mig.add_argument("--duvidosos", action="store_true", help="Inclui correspondencias ambiguas")

    sub.add_parser(
        "render-entidades", help="Renderiza o corpo das entidades (bibliotecario deterministico)"
    )

    p_ded = sub.add_parser("deduplicar", help="Encontra/funde entidades duplicadas")
    p_ded.add_argument("--aplicar", action="store_true", help="Funde os clusters de alta confianca")

    p_fund = sub.add_parser("fundir", help="Funde duas entidades (b -> a), reescrevendo links")
    p_fund.add_argument("a", help="Id canonico (destino)")
    p_fund.add_argument("b", help="Id a fundir (origem)")

    p_flim = sub.add_parser(
        "fila-limpar", help="Lista/marca itens de fila ja pesquisados ou duplicados"
    )
    p_flim.add_argument("--aplicar", action="store_true", help="Marca como ignorado")

    args = parser.parse_args()
    if args.comando == "run":
        return run(args.tema, args.plataformas)
    if args.comando == "investigar":
        return investigar()
    if args.comando == "pesquisar":
        return pesquisar(args.limite, args.horas, args.lote)
    if args.comando == "enfileirar":
        return enfileirar(args.alvo, args.motivo, args.prioridade)
    if args.comando == "agenda":
        return agenda(args.status)
    if args.comando == "aprovar":
        return marcar_status(args.id, "aprovado")
    if args.comando == "publicar":
        return marcar_status(args.id, "publicado")
    if args.comando == "migrar-organizacoes":
        return migrar_organizacoes(args.aplicar, args.duvidosos)
    if args.comando == "render-entidades":
        return render_entidades()
    if args.comando == "deduplicar":
        return deduplicar_cmd(args.aplicar)
    if args.comando == "fundir":
        return fundir_cmd(args.a, args.b)
    if args.comando == "fila-limpar":
        return fila_limpar(args.aplicar)
    return 1


if __name__ == "__main__":
    sys.exit(main())

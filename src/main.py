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
from .crew_pautas import build_pautas_crew
from .crew_pesquisador import build_pesquisador_crew
from .output import entregaveis, postagem
from .output.render import save_output
from .vault import queue as fila
from .vault.entidades import deduplicar, fundir
from .vault.log import log_event
from .vault.migrar import migrar
from .vault.render import atualizar_entidades
from .vault.vault import ensure_vault


def run(tema: str, saidas: str = "") -> int:
    settings = get_settings()
    tokens = [s.strip().lower() for s in saidas.split(",") if s.strip()]
    if any(t in ("todas", "tudo", "all") for t in tokens):
        tokens = ["video", "redes", "reportagem"]
    tokens = [t for t in tokens if t in ("video", "redes", "reportagem")]

    print(f"[{_ts()}] run: tema={tema!r} saidas={tokens or 'nenhuma'}", flush=True)
    crew = build_crew(settings, tokens or None, step_callback=_step_cb)
    result = crew.kickoff(inputs={"tema": tema})
    print(f"[{_ts()}] kickoff concluido; processando saidas", flush=True)
    outs = getattr(result, "tasks_output", []) or []

    revisao = outs[3] if len(outs) > 3 else None
    texto_final = getattr(revisao, "raw", None) or getattr(result, "raw", str(result))
    print(texto_final)
    path = save_output(texto_final, settings.output_dir, tema, "runs")
    print(f"\nSaída salva em: {path}")

    idx = 4
    if "reportagem" in tokens:
        idx += 1  # pula o rascunho; a versao validada pelo revisor vem na task seguinte
        if idx < len(outs):
            rep = getattr(outs[idx], "pydantic", None)
            if rep is not None:
                print(f"Reportagem salva em: {entregaveis.salvar_reportagem(rep, tema)}")
        idx += 1
    if "video" in tokens and idx < len(outs):
        pacote = getattr(outs[idx], "pydantic", None)
        if pacote is not None:
            for rv in pacote.videos:
                print(f"Roteiro de vídeo [{rv.perfil_alvo}] em: {entregaveis.salvar_roteiro_video(rv, tema)}")
        idx += 1
    if "redes" in tokens and idx < len(outs):
        multi = getattr(outs[idx], "pydantic", None)
        if multi is not None:
            for item in multi.itens:
                posts = [
                    {
                        "plataforma": "facebook",
                        "texto": item.facebook.texto,
                        "hashtags": item.facebook.hashtags,
                        "nota": item.perfil_alvo,
                    }
                ]
                thread = item.bluesky.posts
                for i, texto_bs in enumerate(thread, 1):
                    posts.append(
                        {
                            "plataforma": "bluesky",
                            "texto": texto_bs,
                            "hashtags": [],
                            "nota": f"{item.perfil_alvo} | fio {i}/{len(thread)}",
                        }
                    )
                ids = postagem.add_posts(posts, tema)
                print(
                    f"[{item.perfil_alvo}] {len(ids)} posts enfileirados | imagem: "
                    f"'{item.imagem.titulo}' / '{item.imagem.subtitulo}'"
                )
                print(f"  pacote de redes: {entregaveis.salvar_pacote_redes(item, tema)}")
        idx += 1

    _render_entidades()
    return 0


def investigar() -> int:
    settings = get_settings()
    ensure_vault()
    crew = build_investigador_crew(settings)
    result = crew.kickoff()
    text = getattr(result, "raw", str(result))
    print(text)
    path = save_output(text, settings.output_dir, "investigacao", "investigacoes")
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


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _step_cb(step) -> None:
    try:
        agente = getattr(step, "agent", "") or getattr(step, "role", "")
        saida = getattr(step, "output", step)
        saida = " ".join(str(saida).split())[:160]
        print(f"[{_ts()}] [passo] {agente}: {saida}", flush=True)
    except Exception:  # noqa: BLE001
        pass


def _processar_item(item: dict, settings) -> bool:
    alvo = item.get("alvo")
    print(f"\n[{_ts()}] >>> agente pesquisador (inicio): {alvo} ({item['id']})", flush=True)
    fila.mark_status(item["id"], "em_andamento")
    log_event(f"pesquisar iniciado: {alvo}", "fila")
    try:
        crew = build_pesquisador_crew(settings, step_callback=_step_cb)
        result = crew.kickoff(
            inputs={
                "alvo": alvo,
                "motivo": item.get("motivo", ""),
                "profundidade": item.get("profundidade", 0),
                "max_depth": settings.max_depth,
                "desde": item.get("desde", ""),
            }
        )
        text = getattr(result, "raw", str(result))
        save_output(text, settings.output_dir, f"pesquisa-{item['id']}", "pesquisas")
        fila.mark_status(item["id"], "concluido")
        log_event(f"pesquisar concluido: {alvo}", "fila")
        _render_entidades()
        print(f"[{_ts()}] <<< agente pesquisador (fim): {alvo}", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[{_ts()}] !!! erro no pesquisador ({alvo}): {exc}", flush=True)
        log_event(f"pesquisar erro em {alvo}: {exc}", "fila")
        fila.mark_status(item["id"], "pendente")
        return False


def pesquisar(
    limite: int = 0,
    horas: float = 0.0,
    lote: int = 10,
    pautas_cada: int = 1,
    revisitar: bool = False,
    dias: int | None = None,
    top: int | None = None,
    aleatorio: int | None = None,
) -> int:
    settings = get_settings()
    ensure_vault()

    orfaos = fila.reset_em_andamento()
    if orfaos:
        print(f"Retomando {orfaos} item(ns) orfao(s) (em_andamento -> pendente).")

    if revisitar:
        criados = fila.revisitar(dias, top, aleatorio)
        print(f"Revisita: {len(criados)} alvo(s) enfileirado(s).")
        for c in criados:
            print(f"  - {c['alvo']} (ultima coleta: {c['desde'] or 'nunca'})")
        if not horas and not limite:
            return 0

    if horas and horas > 0:
        return _daemon(settings, horas, lote, pautas_cada)

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


def _daemon(settings, horas: float, lote: int, pautas_cada: int = 1) -> int:
    deadline = datetime.now() + timedelta(hours=horas)
    log_path = Path(settings.output_dir) / f"loop-{datetime.now():%Y%m%d-%H%M%S}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{_ts()}] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"daemon iniciado por {horas}h (lote={lote}). Fim previsto: {deadline:%H:%M}.")
    if pautas_cada > 0:
        log(f"pautas: geracao automatica a cada {pautas_cada} lote(s).")
    log(f"log em: {log_path}")
    dry = 0
    total = 0
    ciclos = 0
    vistas: set[str] = set()
    for p in entregaveis.carregar_pautas(max_itens=0):
        if p.get("source_url"):
            vistas.add(p["source_url"])

    while datetime.now() < deadline:
        if fila.pending_count() == 0:
            try:
                revisitas = fila.revisitar()
            except Exception as exc:  # noqa: BLE001
                revisitas = []
                log(f"!!! erro na revisita: {exc}")
            if revisitas:
                log(f"fila vazia -> revisita enfileirou {len(revisitas)} alvo(s)")
            else:
                dry += 1
                log(f"fila vazia -> rodando investigador (dry={dry})")
                try:
                    log(">>> agente investigador (inicio)")
                    build_investigador_crew(settings, step_callback=_step_cb).kickoff()
                    log("<<< agente investigador (fim)")
                except Exception as exc:  # noqa: BLE001
                    log(f"!!! erro no investigador: {exc}")
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

        ciclos += 1
        if pautas_cada > 0 and ciclos % pautas_cada == 0:
            try:
                log(">>> gerador de pautas (inicio)")
                geradas = _gerar_pautas(settings, vistas)
                log(f"<<< gerador de pautas (fim; {geradas} manchete(s) nova(s))")
            except Exception as exc:  # noqa: BLE001
                log(f"!!! erro no gerador de pautas: {exc}")

    log(f"daemon encerrado. Itens processados: {total}. Pendentes: {fila.pending_count()}.")
    print(f"\nLog do loop: {log_path}")
    return 0


def _render_noticias(itens: list[dict]) -> str:
    linhas = []
    for i, item in enumerate(itens, 1):
        linhas.append(f"{i}. [{item.get('fonte', '')}] {item.get('titulo', '')}")
        linhas.append(f"   link: {item.get('link', '')}")
        if item.get("entidades"):
            linhas.append(f"   entidades do grafo: {', '.join(item['entidades'])}")
        if item.get("resumo"):
            linhas.append(f"   resumo: {item['resumo'][:250]}")
    return "\n".join(linhas)


def _gerar_pautas(settings, vistas: set[str] | None = None, enfileirar: bool = True) -> int:
    from .tools.sources import carregar_itens_rss, filtrar_relevantes
    from .vault import queue as fila
    from .vault.entidades import nomes_entidades

    if vistas is None:
        vistas = set()

    itens = carregar_itens_rss()
    relevantes = filtrar_relevantes(itens, nomes_entidades())

    novos: list[dict] = []
    usados: set[str] = set()
    for item in relevantes:
        link = item.get("link", "")
        if not link or link in vistas or link in usados:
            continue
        usados.add(link)
        novos.append(item)

    if not novos:
        print(f"[{_ts()}] pautas: nenhuma manchete nova relevante.", flush=True)
        return 0

    print(f"[{_ts()}] {len(novos)} manchete(s) nova(s); gerando pautas...", flush=True)
    crew = build_pautas_crew(settings, step_callback=_step_cb)
    result = crew.kickoff(inputs={"noticias": _render_noticias(novos)})
    text = getattr(result, "raw", str(result))
    pacote = getattr(result, "pydantic", None)
    tem_pacote = pacote is not None and bool(getattr(pacote, "itens", None))
    if tem_pacote:
        text = _render_pautas_md(pacote)
    print(text)
    path = save_output(text, settings.output_dir, "pautas", "pautas")
    print(f"\nPautas salvas em: {path}")
    vistas.update(usados)

    if tem_pacote:
        n_novas = entregaveis.acrescentar_pautas(pacote)
        print(f"Pautas na fila: +{n_novas} (limite {entregaveis.PAUTAS_MAX}).")
        if enfileirar:
            print(f"Alvos enfileirados a partir das pautas: {_enfileirar_pautas(pacote, fila)}")
    else:
        print("(o modelo nao devolveu pautas estruturadas; json/enfileiramento pulados)")

    return len(novos)


def _render_pautas_md(pacote) -> str:
    linhas: list[str] = []
    for i, p in enumerate(pacote.itens, 1):
        linhas.append(f"## Pauta {i}: {getattr(p, 'manchete', '')}")
        linhas.append(f"- **Angulo:** {getattr(p, 'angulo', '')}")
        if getattr(p, "entidades", None):
            linhas.append(f"- **Entidades do grafo:** {', '.join(p.entidades)}")
        if getattr(p, "alvos_pesquisa", None):
            linhas.append(f"- **Alvos a pesquisar:** {', '.join(p.alvos_pesquisa)}")
        if getattr(p, "source_url", ""):
            linhas.append(f"- **Fonte:** {p.source_url}")
        linhas.append("")
    return "\n".join(linhas).strip()


def _enfileirar_pautas(pacote, fila) -> int:
    total = 0
    for pauta in getattr(pacote, "itens", []) or []:
        motivo = f"pauta: {getattr(pauta, 'manchete', '')}"[:120]
        alvos = list(getattr(pauta, "alvos_pesquisa", None) or [])
        for alvo in alvos:
            nome = str(alvo).strip().strip("[]").strip()
            if not nome:
                continue
            if fila.add_item(nome, motivo, 3, 0, "pautas"):
                total += 1
    return total


def _listar_pautas() -> int:
    itens = entregaveis.carregar_pautas(max_itens=0)
    if not itens:
        print("Fila de pautas vazia. Rode 'pautas' antes.")
        return 0
    print(f"Fila de pautas ({len(itens)}; mais recente primeiro):")
    for i, p in enumerate(itens, 1):
        print(f"{i:>2}. [{p.get('criado_em', '')}] {p.get('manchete', '')}")
        if p.get("angulo"):
            print(f"      angulo: {p['angulo']}")
        if p.get("source_url"):
            print(f"      fonte:  {p['source_url']}")
    return 0


def _selecionar_pautas(spec: str) -> list[dict]:
    itens = entregaveis.carregar_pautas(max_itens=0)
    if not itens:
        return []
    s = spec.strip().lower().replace(" ", "-")
    if s in ("ultima", "ultimas", "ultimas-1"):
        return itens[:1]
    if s.startswith("ultimas-"):
        try:
            k = int(s.split("-", 1)[1])
        except ValueError:
            return []
        return itens[: max(0, k)]
    if s in ("todas", "tudo", "all", "*"):
        return list(itens)
    if "-" in s:
        try:
            a, b = (int(x) for x in s.split("-", 1))
        except ValueError:
            return []
        lo, hi = min(a, b), max(a, b)
        return [itens[i - 1] for i in range(lo, hi + 1) if 1 <= i <= len(itens)]
    try:
        n = int(s)
    except ValueError:
        return []
    return [itens[n - 1]] if 1 <= n <= len(itens) else []


def pautas() -> int:
    ensure_vault()
    _gerar_pautas(get_settings(), set())
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


def migrar_filas(aplicar: bool = False) -> int:
    import json as _json

    from .vault.vault import all_notes

    settings = get_settings()
    estado = Path(settings.estado_dir)

    def _ler(caminho: Path, chave: str) -> list[dict]:
        if not caminho.exists():
            return []
        try:
            return _json.loads(caminho.read_text(encoding="utf-8")).get(chave, [])
        except Exception:  # noqa: BLE001
            return []

    notas = []
    for fm, _, _ in all_notes("fila"):
        status = fm.get("status", "pendente")
        criado = fm.get("criado_em", "")
        notas.append(
            {
                "id": fm.get("id", ""),
                "tipo": "fila",
                "status": status,
                "prioridade": fm.get("prioridade", 3),
                "profundidade": fm.get("profundidade", 0),
                "alvo": fm.get("alvo", ""),
                "motivo": fm.get("motivo", ""),
                "origem": fm.get("origem", ""),
                "criado_em": criado,
                "concluido_em": criado if status == "concluido" else "",
                "tentativas": int(fm.get("tentativas", 0) or 0),
                "desde": "",
            }
        )

    destino_pesquisa = estado / "pesquisa.json"
    if destino_pesquisa.exists():
        existentes = _ler(destino_pesquisa, "itens")
        ids = {i.get("id") for i in existentes}
        pesquisa = existentes + [n for n in notas if n.get("id") not in ids]
    else:
        pesquisa = notas

    pautas_old = Path(settings.output_dir) / "pautas" / "pautas.json"
    destino_pautas = estado / "pautas.json"
    pautas = _ler(destino_pautas, "itens") or _ler(pautas_old, "itens")

    post_old = Path(settings.output_dir) / "fila-postagem.json"
    destino_post = estado / "postagem.json"
    postagem = _ler(destino_post, "pecas") or _ler(post_old, "pecas")

    print(f"pesquisa: {len(pesquisa)} item(ns) -> {destino_pesquisa}")
    print(f"pautas:   {len(pautas)} item(ns) -> {destino_pautas}")
    print(f"postagem: {len(postagem)} peca(s) -> {destino_post}")

    if not aplicar:
        print("\n(dry-run) Nada foi alterado. Use --aplicar.")
        return 0

    estado.mkdir(parents=True, exist_ok=True)
    destino_pesquisa.write_text(
        _json.dumps({"itens": pesquisa}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    destino_pautas.write_text(
        _json.dumps({"itens": pautas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    destino_post.write_text(
        _json.dumps({"pecas": postagem}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nMigrado para: {estado}")
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
    p_run.add_argument("--tema", default="", help="Tema da pesquisa")
    p_run.add_argument(
        "--pautas",
        default="",
        help="Selecao de pautas: listar | N | A-B | ultimas-K | todas (1 = mais recente)",
    )
    p_run.add_argument(
        "--saidas",
        default="",
        help="Gera entregaveis extras: video, redes, reportagem (ou todas)",
    )

    sub.add_parser("investigar", help="Estrutura o vault e mantem a fila de pesquisa")

    sub.add_parser("pautas", help="Gera pautas a partir das manchetes atuais dos RSS")

    p_pesq = sub.add_parser("pesquisar", help="Consome a fila de pesquisa")
    p_pesq.add_argument("--limite", type=int, default=0, help="Itens a processar (0 = esvaziar)")
    p_pesq.add_argument("--horas", type=float, default=0.0, help="Roda como daemon por N horas")
    p_pesq.add_argument("--lote", type=int, default=10, help="Itens por lote no modo --horas")
    p_pesq.add_argument(
        "--pautas-cada",
        type=int,
        default=1,
        help="Gera pautas a cada N lotes no daemon (0 = desliga)",
    )
    p_pesq.add_argument(
        "--revisitar",
        action="store_true",
        help="Enfileira revisitas de alvos velhos (top-N por centralidade + aleatorios)",
    )
    p_pesq.add_argument("--dias", type=int, default=None, help="Idade minima (dias) p/ revisitar")
    p_pesq.add_argument("--top", type=int, default=None, help="Quantos alvos por centralidade")
    p_pesq.add_argument("--aleatorio", type=int, default=None, help="Quantos alvos aleatorios")

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

    p_mf = sub.add_parser(
        "migrar-filas", help="Migra as filas antigas para data/estado/*.json"
    )
    p_mf.add_argument("--aplicar", action="store_true", help="Aplica a migracao")

    args = parser.parse_args()
    if args.comando == "run":
        spec = (args.pautas or "").strip()
        if spec:
            if spec.lower() in ("listar", "list", "ls"):
                return _listar_pautas()
            selecionadas = _selecionar_pautas(spec)
            if not selecionadas:
                print(f"Nenhuma pauta para '{spec}'. Use 'run --pautas listar'.")
                return 1
            saidas = args.saidas or "todas"
            print(f"run --pautas {spec}: {len(selecionadas)} pauta(s); saidas={saidas}")
            rc = 0
            for i, pauta in enumerate(selecionadas, 1):
                tema = f"{pauta.get('manchete', '')} — {pauta.get('angulo', '')}".strip(" —")
                print(f"\n=== [{i}/{len(selecionadas)}] pauta {pauta.get('id', '')}: {tema!r} ===")
                try:
                    code = run(tema, saidas)
                except Exception as exc:  # noqa: BLE001
                    print(f"!!! erro na pauta {pauta.get('id', '')}: {exc}")
                    code = 1
                if code == 0:
                    chave = pauta.get("id") or pauta.get("manchete", "")
                    entregaveis.remover_pauta(chave)
                    print(f"Pauta consumida e removida da fila: {chave}")
                else:
                    rc = code
            return rc
        tema = args.tema
        if not tema.strip():
            print('Informe --tema "..." ou --pautas <selecao>.')
            return 1
        return run(tema, args.saidas)
    if args.comando == "investigar":
        return investigar()
    if args.comando == "pautas":
        return pautas()
    if args.comando == "pesquisar":
        return pesquisar(
            args.limite,
            args.horas,
            args.lote,
            args.pautas_cada,
            args.revisitar,
            args.dias,
            args.top,
            args.aleatorio,
        )
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
    if args.comando == "migrar-filas":
        return migrar_filas(args.aplicar)
    return 1


if __name__ == "__main__":
    sys.exit(main())

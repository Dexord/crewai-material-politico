import argparse
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from .config import get_settings
from .crew import build_crew
from .output.render import save_output


def run(tema: str) -> int:
    settings = get_settings()
    crew = build_crew(settings)
    result = crew.kickoff(inputs={"tema": tema})
    text = getattr(result, "raw", str(result))
    print(text)
    path = save_output(text, settings.output_dir, tema)
    print(f"\nSaída salva em: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="material-politico")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_run = sub.add_parser("run", help="Executa o pipeline completo")
    p_run.add_argument("--tema", required=True, help="Tema da pesquisa")

    args = parser.parse_args()
    if args.comando == "run":
        return run(args.tema)
    return 1


if __name__ == "__main__":
    sys.exit(main())

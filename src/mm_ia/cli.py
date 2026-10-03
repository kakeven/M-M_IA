"""Interface de linha de comando para analisar um pedido."""

import argparse
import json

from mm_ia.pipeline import analyze_request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pedido", help="descrição em linguagem natural do poder")
    args = parser.parse_args()
    result = analyze_request(args.pedido)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

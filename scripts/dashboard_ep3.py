"""Exporta un dashboard autocontenido a partir del banco de pruebas o de las trazas locales."""

import argparse
import json
from pathlib import Path

from rag.observabilidad import leer

PLANTILLA = Path(__file__).resolve().parents[1] / "app" / "monitor.html"


def render_html(filas):
    # JSON embebido en script no ejecutable: escapar también el cierre de la etiqueta.
    datos = json.dumps(filas, ensure_ascii=True, allow_nan=False).replace(
        "<", "\\u003c"
    )
    return PLANTILLA.read_text(encoding="utf8").replace("__TRAZAS_EP3__", datos)


def exportar(filas, destino):
    html = render_html(filas)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--banco", type=Path, help="JSON de evaluación. Sin este argumento lee SQLite."
    )
    p.add_argument("--salida", type=Path, default=Path(".observabilidad/monitor.html"))
    args = p.parse_args()
    filas = json.loads(args.banco.read_text(encoding="utf8")) if args.banco else leer()
    exportar(filas, args.salida)
    print(f"{len(filas)} trazas · {args.salida}")


if __name__ == "__main__":
    main()

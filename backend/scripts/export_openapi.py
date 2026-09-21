"""Exporta o contrato OpenAPI para `docs/openapi.json` (base para gerar o cliente do front React).

    python -m scripts.export_openapi          # grava o arquivo
    python -m scripts.export_openapi --check  # falha (exit 1) se o arquivo estiver desatualizado
"""

import json
import sys
from pathlib import Path

from app.main import gerar_openapi

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def gerar_texto() -> str:
    return json.dumps(gerar_openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    texto = gerar_texto()
    if "--check" in sys.argv:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != texto:
            print("docs/openapi.json está desatualizado. Rode: python -m scripts.export_openapi", file=sys.stderr)
            sys.exit(1)
        print("docs/openapi.json está em dia.")
    else:
        DESTINO.parent.mkdir(exist_ok=True)
        DESTINO.write_text(texto, encoding="utf-8")
        print(f"Gravado {DESTINO}")

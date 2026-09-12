"""
Compila os catalogos .po em .mo sem depender do GNU gettext.

O `manage.py compilemessages` do Django precisa do binario `msgfmt`, que nao
existe numa instalacao padrao do Windows. Este script faz o mesmo usando a
biblioteca polib (ja em requirements/dev.txt).

Uso:
    python scripts/compile_messages.py

Observacao: a extracao de strings (`manage.py makemessages`) ainda exige o
GNU gettext instalado. Ver README.
"""

import sys
from pathlib import Path

import polib

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale"


def main() -> int:
    arquivos = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/*.po"))

    if not arquivos:
        print(f"Nenhum arquivo .po encontrado em {LOCALE_DIR}.")
        return 0

    for po_path in arquivos:
        mo_path = po_path.with_suffix(".mo")
        polib.pofile(str(po_path)).save_as_mofile(str(mo_path))
        print(f"{po_path.relative_to(BASE_DIR)} -> {mo_path.relative_to(BASE_DIR)}")

    print(f"\n{len(arquivos)} catalogo(s) compilado(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

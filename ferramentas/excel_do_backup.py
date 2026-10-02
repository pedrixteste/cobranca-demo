"""
Refaz o Excel (com as abas de leitura) a partir de um arquivo .json de backup.

O cofre do GitHub guarda só o .json; este programa devolve o Excel quando alguém precisar abrir.

  py ferramentas\\excel_do_backup.py "CAMINHO\\AAAA-MM-DD HHhMM backup cobrancas.json"

Grava o .xlsx ao lado do .json (não escreve por cima se já existir).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backup  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 1
    origem = Path(argv[0])
    copia = json.loads(origem.read_text(encoding="utf-8"))
    if backup.impressao_digital(copia["abas"]) != copia.get("impressao"):
        print("ERRO: o arquivo de backup está corrompido (a impressão digital não confere)", file=sys.stderr)
        return 1
    destino = origem.with_suffix(".xlsx")
    if destino.exists():
        print(f"Já existe: {destino} (não escrevi por cima)")
        return 1
    destino.write_bytes(backup.gerar_xlsx(copia))
    print(f"Excel refeito: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

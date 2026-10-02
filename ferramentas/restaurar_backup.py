"""
Reconstrói a planilha de cobranças a partir de um arquivo .json de backup.

Passo a passo (quando a planilha original foi perdida ou estragada):
  1. No Google Planilhas, crie uma planilha em branco.
  2. Compartilhe com o robô do app, como EDITOR (o e-mail está em client_email, no secrets).
  3. Rode:  py ferramentas\\restaurar_backup.py "CAMINHO\\AAAA-MM-DD HHhMM backup cobrancas.json" ID_DA_PLANILHA_NOVA
     (o ID é o trecho do endereço entre /d/ e /edit)
  4. Troque o spreadsheet_id nos Secrets do app (Streamlit) e do aviso diário (GitHub).

Trava de segurança: se a planilha de destino já tiver cobranças, o programa para sem
escrever nada. Só escreve por cima com --por-cima (apaga o que estiver nas abas do backup).

No fim, lê a planilha de volta e confere célula por célula com o backup.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import backup  # noqa: E402
from dados import SCOPES, _letra  # noqa: E402


def restaurar(sh, copia: dict, por_cima: bool = False) -> list[str]:
    """Escreve as abas do backup na planilha `sh` (gspread). Devolve as diferenças achadas na conferência."""
    abas = backup.normalizar(copia["abas"])
    if backup.impressao_digital(abas) != copia.get("impressao"):
        raise ValueError("o arquivo de backup está corrompido (a impressão digital não confere)")
    existentes = {ws.title: ws for ws in sh.worksheets()}
    if not por_cima:
        ocupadas = [n for n in backup.ABAS_OBRIGATORIAS
                    if n in existentes and len(existentes[n].get_all_values()) > 1]
        if ocupadas:
            raise RuntimeError("a planilha de destino já tem dados em " + ", ".join(ocupadas)
                               + "; nada foi escrito (use --por-cima se for isso mesmo)")
    for nome, linhas in abas.items():
        largura = max([len(l) for l in linhas] + [1])
        ws = existentes.get(nome)
        if ws is None:
            ws = sh.add_worksheet(title=nome, rows=max(len(linhas) + 200, 1000), cols=max(largura, 2))
        else:
            ws.clear()
            if ws.row_count < len(linhas) or ws.col_count < largura:
                ws.resize(rows=max(ws.row_count, len(linhas) + 200), cols=max(ws.col_count, largura))
        if not linhas:
            continue
        ws.update(range_name="A1", values=[l + [""] * (largura - len(l)) for l in linhas],
                  value_input_option="RAW")
        if nome.startswith("_"):   # mesmo cabeçalho que o app cria
            ws.format(f"A1:{_letra(largura)}1", {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.122, "green": 0.227, "blue": 0.373},
            })
            ws.freeze(rows=1)
    return comparar(sh, abas)


def comparar(sh, abas: dict) -> list[str]:
    """Lê a planilha de volta e compara com o backup, aba por aba."""
    faixas = ["'" + n.replace("'", "''") + "'" for n in abas]
    blocos = sh.values_batch_get(faixas).get("valueRanges", [])
    lido = backup.normalizar({n: b.get("values", []) for n, b in zip(abas, blocos)})
    return [f"a aba {n} não ficou igual ao backup" for n in abas if lido.get(n) != abas[n]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reconstrói a planilha a partir de um backup .json")
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("planilha_destino")
    ap.add_argument("--por-cima", action="store_true")
    args = ap.parse_args(argv)

    import gspread
    copia = json.loads(args.arquivo.read_text(encoding="utf-8"))
    with open(RAIZ / ".streamlit" / "secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    gc = gspread.service_account_from_dict(dict(secrets["gcp_service_account"]), scopes=SCOPES)
    sh = gc.open_by_key(args.planilha_destino)
    print(f"Backup de {copia['feito_em']}: " + ", ".join(f"{n} em {a}" for a, n in backup.contagem(copia).items()))
    print(f"Destino: \"{sh.title}\"")
    diferencas = restaurar(sh, copia, args.por_cima)
    for d in diferencas:
        print("ERRO: " + d, file=sys.stderr)
    if not diferencas:
        print("Planilha reconstruída e conferida: igual ao backup, célula por célula.")
    return 1 if diferencas else 0


if __name__ == "__main__":
    sys.exit(main())

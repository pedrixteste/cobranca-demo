#!/usr/bin/env python3
"""
Cópia de segurança dos COMPROVANTES (fotos e PDFs que o app guarda no Drive).

Cada comprovante é copiado UMA vez só: o Drive dá a cada arquivo um número de identidade,
e o índice (COMPROVANTES/indice.json) lembra quais já foram copiados. A rodada baixa só os
que faltam; nada é baixado duas vezes e nada é apagado, mesmo que suma do Drive.

  COMPROVANTES/AAAA/NN - Mês/AAAA-MM-DD Cliente - Turma - Parcela.jpg   (data do pagamento)
  COMPROVANTES/LISTA DE COMPROVANTES.xlsx   de quem é cada arquivo, para achar sem abrir um por um
  COMPROVANTES/indice.json                  o que já foi copiado (não mexer)

Só LÊ o Drive. Quem roda é o notebook (ferramentas/backup_no_servidor.py), que depois leva
a pasta para o servidor junto com as cópias da planilha.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path

import backup

PASTA = "COMPROVANTES"
INDICE = "indice.json"
LISTA = "LISTA DE COMPROVANTES.xlsx"

# O app grava "<Cliente - Turma - Parcela> - DD-MM-AAAA.ext": a data do pagamento vem no fim
_RE_DATA_NO_FIM = re.compile(r"^(?P<desc>.*?)\s*-\s*(?P<d>\d{2})-(?P<m>\d{2})-(?P<a>\d{4})(?P<ext>\.\w+)$")
_RE_PROIBIDO = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RE_ID_NO_LINK = re.compile(r"/d/([A-Za-z0-9_-]+)")


def listar_drive(service, raiz: str, caminho: str = "") -> list[dict]:
    """Todos os arquivos (não pastas) debaixo da pasta de comprovantes, com a pasta onde estão."""
    achados, pagina = [], None
    while True:
        r = service.files().list(
            q=f"'{raiz}' in parents and trashed = false", pageSize=200, pageToken=pagina,
            fields="nextPageToken, files(id,name,mimeType,size,md5Checksum,createdTime,webViewLink)").execute()
        for f in r.get("files", []):
            if f["mimeType"] == backup._MIME_PASTA:
                achados += listar_drive(service, f["id"], f"{caminho}/{f['name']}".strip("/"))
            else:
                achados.append({**f, "pasta": caminho})
        pagina = r.get("nextPageToken")
        if not pagina:
            return achados


def nome_no_backup(nome_drive: str, criado_em: str) -> tuple[date, str]:
    """(data do pagamento, nome com a data na frente). Sem data no nome, vale o dia em que subiu ao Drive."""
    m = _RE_DATA_NO_FIM.match(nome_drive)
    try:
        dia = date(int(m["a"]), int(m["m"]), int(m["d"])) if m else None
    except ValueError:
        dia = None
    if dia:
        descricao, ext = m["desc"], m["ext"]
    else:
        dia = datetime.fromisoformat(criado_em.replace("Z", "+00:00")).astimezone(backup.TIMEZONE).date()
        descricao, _, ext = nome_drive.rpartition(".")
        descricao, ext = (descricao, "." + ext) if descricao else (nome_drive, "")
    descricao = _RE_PROIBIDO.sub("-", descricao).strip(" .")[:140] or "Comprovante"
    return dia, f"{dia.isoformat()} {descricao}{ext.lower()}"


def caminho_no_backup(nome_drive: str, criado_em: str, ocupados) -> str:
    """Caminho relativo à pasta de backup; se o nome já existe (outro arquivo igual no nome), ganha (2), (3)..."""
    dia, nome = nome_no_backup(nome_drive, criado_em)
    pasta = f"{PASTA}/{dia.year}/{backup.MESES_PASTA[dia.month - 1]}"
    base, ponto, ext = nome.rpartition(".")
    candidato, n = f"{pasta}/{nome}", 1
    while candidato in ocupados:
        n += 1
        candidato = f"{pasta}/{base} ({n}){ponto}{ext}"
    return candidato


def ler_indice(pasta_base: Path) -> dict:
    """{"arquivos": {id do Drive: dados da cópia}, "planilha": impressão da planilha usada na última lista}"""
    try:
        indice = json.loads((Path(pasta_base) / PASTA / INDICE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        indice = {}
    indice.setdefault("arquivos", {})
    indice.setdefault("planilha", "")
    return indice


def _gravar_indice(pasta_base: Path, indice: dict):
    backup._gravar(Path(pasta_base) / PASTA / INDICE,
                   json.dumps(indice, ensure_ascii=False, indent=1).encode("utf-8"))


def copiar_novos(arquivos: list[dict], baixar, pasta_base: Path) -> tuple[int, list[str]]:
    """
    Baixa só o que ainda não está no índice. `baixar(id)` devolve os bytes do arquivo.
    Devolve (quantos copiou agora, erros). Um arquivo que falha não impede os outros.
    """
    pasta_base = Path(pasta_base)
    indice = ler_indice(pasta_base)
    copiados = indice["arquivos"]
    ocupados = {v["arquivo"] for v in copiados.values()}
    novos, erros = 0, []
    for f in sorted(arquivos, key=lambda x: x.get("createdTime", "")):
        if f["id"] in copiados:
            continue
        try:
            conteudo = baixar(f["id"])
            if f.get("md5Checksum") and hashlib.md5(conteudo).hexdigest() != f["md5Checksum"]:
                raise OSError("o arquivo baixado não bate com o do Drive")
            relativo = caminho_no_backup(f["name"], f.get("createdTime", ""), ocupados)
            destino = pasta_base / relativo
            if destino.exists():   # sobra de uma rodada interrompida antes de gravar o índice
                raise OSError(f"já existe um arquivo em {relativo} fora do índice")
            backup._gravar(destino, conteudo)
            copiados[f["id"]] = {"arquivo": relativo, "nome_drive": f["name"], "pasta_drive": f.get("pasta", ""),
                               "enviado_em": f.get("createdTime", ""), "tamanho": len(conteudo),
                               "link": f.get("webViewLink", "")}
            ocupados.add(relativo)
            _gravar_indice(pasta_base, indice)   # a cada arquivo: rodada interrompida não perde o que já fez
            novos += 1
        except Exception as e:
            erros.append(f"{f.get('name', f['id'])}: {type(e).__name__}: {e}")
    return novos, erros


def _parcelas_por_comprovante(copia: dict | None) -> dict:
    """Id do arquivo no Drive -> (cobrança, parcela), pelo link gravado na planilha."""
    if not copia:
        return {}
    import nucleo
    abas = copia["abas"]
    cobs = nucleo.montar_cobrancas(nucleo.linhas_de_valores(abas.get("_Cobrancas", [])),
                                   nucleo.linhas_de_valores(abas.get("_Parcelas", [])),
                                   datetime.fromisoformat(copia["feito_em"]).date(), incluir_excluidas=True)
    ligadas = {}
    for c in cobs:
        for p in c["parcelas"]:
            m = _RE_ID_NO_LINK.search(p.get("comprovante") or "")
            if m:
                ligadas[m.group(1)] = (c, p)
    return ligadas


def gerar_lista(indice: dict, copia: dict | None = None) -> bytes:
    """Planilha para gente: de quem é cada comprovante e onde está o arquivo."""
    from openpyxl import Workbook

    ligadas = _parcelas_por_comprovante(copia)
    colunas = [("Data do pagamento", 14, backup._DATA), ("Cliente", 34, None), ("Turma", 9, None),
               ("Parcela", 18, None), ("Valor", 14, backup._REAIS), ("Quem recebeu", 16, None),
               ("Arquivo (dentro de COMPROVANTES)", 70, None), ("Link no Drive", 50, None)]
    linhas = []
    for fid, item in indice["arquivos"].items():
        dia, nome = nome_no_backup(item["nome_drive"], item.get("enviado_em", ""))
        arquivo = item["arquivo"][len(PASTA) + 1:].replace("/", "\\")
        if fid in ligadas:
            c, p = ligadas[fid]
            linhas.append([p["pago_em"] or dia, c["cliente"], c["turma"], p["rotulo"], p["valor"],
                           p["marcado_por"], arquivo, item.get("link", "")])
        else:   # comprovante que nenhuma parcela aponta (parcela desfeita, envio repetido...)
            descricao = nome[11:].rsplit(".", 1)[0]
            linhas.append([dia, descricao + " (sem parcela ligada na planilha)", "", "", None, "",
                           arquivo, item.get("link", "")])
    linhas.sort(key=lambda l: (l[0], l[1]), reverse=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Comprovantes"
    backup._tabela(ws, 1, colunas, linhas)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def executar(service, raiz_drive: str, pasta_base: Path, copia: dict | None = None) -> tuple[int, int, list[str]]:
    """Uma rodada: lista o Drive, copia o que falta e refaz a lista. Devolve (novos, total guardado, erros)."""
    pasta_base = Path(pasta_base)
    arquivos = listar_drive(service, raiz_drive)
    novos, erros = copiar_novos(arquivos, lambda fid: service.files().get_media(fileId=fid).execute(), pasta_base)
    indice = ler_indice(pasta_base)
    lista = pasta_base / PASTA / LISTA
    planilha = copia["impressao"] if copia else indice["planilha"]
    # A lista só é refeita quando entrou comprovante ou a planilha mudou (pode ter ligado parcela a arquivo)
    if indice["arquivos"] and (novos or not lista.exists() or planilha != indice["planilha"]):
        backup._gravar(lista, gerar_lista(indice, copia))
        indice["planilha"] = planilha
        _gravar_indice(pasta_base, indice)
    return novos, len(indice["arquivos"]), erros

"""
Onde os dados moram: planilha Google (produção) ou um arquivo JSON local
(só para testar as telas no PC, ligado com COBRANCA_LOCAL=caminho.json).

Regras de gravação herdadas do boleto-tracker:
  - tudo gravado como RAW (texto começando com '=' nunca vira fórmula);
  - a linha a alterar é achada pelo ID NA HORA de gravar, nunca por um número
    de linha lido antes (outra pessoa pode ter mexido na planilha no meio);
  - excluir cobrança não apaga: marca Situação = Excluída (dá para restaurar).
"""
from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import date

from nucleo import (COBRANCAS_HEADERS, PARCELAS_HEADERS, SITUACAO_ATIVA, SITUACAO_EXCLUIDA,
                    data_br, linhas_de_valores, valor_planilha)

ABA_COBRANCAS = "_Cobrancas"
ABA_PARCELAS  = "_Parcelas"
ABA_CONFIG    = "_Config"
CONFIG_HEADERS = ["Chave", "Valor"]

# Só planilhas: a conta de serviço não precisa do Drive (quem sobe comprovante
# é a conta do dono, via OAuth drive.file).
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_MIME_PASTA = "application/vnd.google-apps.folder"
_MESES_PASTA = ["01 - Janeiro", "02 - Fevereiro", "03 - Março", "04 - Abril", "05 - Maio",
                "06 - Junho", "07 - Julho", "08 - Agosto", "09 - Setembro", "10 - Outubro",
                "11 - Novembro", "12 - Dezembro"]


def _celula(v) -> str:
    """Valor de campo → texto da planilha (datas dd/mm/aaaa, valores 1500,00)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Sim" if v else ""
    if isinstance(v, date):
        return data_br(v)
    if isinstance(v, float):
        return valor_planilha(v)
    return str(v)


def _linha(cabecalho: list, campos: dict) -> list:
    return [_celula(campos.get(h)) for h in cabecalho]


def _letra(col: int) -> str:
    s = ""
    while col:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def novo_id() -> str:
    return uuid.uuid4().hex[:8]


# ── Planilha Google ───────────────────────────────────────────────────────────

class Planilha:
    def __init__(self, spreadsheet_id: str, credenciais: dict):
        import gspread
        self._gc = gspread.service_account_from_dict(credenciais, scopes=SCOPES)
        self._id = spreadsheet_id
        self._sh = None

    def _planilha(self):
        if self._sh is None:
            self._sh = self._gc.open_by_key(self._id)
        return self._sh

    def _aba(self, nome: str, headers: list):
        """Abre a aba; cria com cabeçalho se não existir; só ACRESCENTA coluna que falte no fim."""
        import gspread
        sh = self._planilha()
        try:
            ws = sh.worksheet(nome)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=nome, rows=1000, cols=len(headers))
            ws.update(range_name="A1", values=[headers], value_input_option="RAW")
            ws.format(f"A1:{_letra(len(headers))}1", {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.122, "green": 0.227, "blue": 0.373},
            })
            ws.freeze(rows=1)
            return ws
        cab = ws.row_values(1)
        faltam = [h for h in headers if h not in cab]
        if faltam:
            if ws.col_count < len(cab) + len(faltam):
                ws.add_cols(len(cab) + len(faltam) - ws.col_count)
            ws.update(range_name=f"{_letra(len(cab) + 1)}1", values=[faltam],
                      value_input_option="RAW")
        return ws

    # Leitura -----------------------------------------------------------------

    def carregar(self) -> dict:
        sh = self._planilha()
        existentes = {ws.title for ws in sh.worksheets()}
        for nome, headers in ((ABA_COBRANCAS, COBRANCAS_HEADERS), (ABA_PARCELAS, PARCELAS_HEADERS)):
            if nome not in existentes:
                self._aba(nome, headers)
        blocos = sh.values_batch_get([f"'{ABA_COBRANCAS}'", f"'{ABA_PARCELAS}'"]).get("valueRanges", [])
        return {
            "cobrancas": linhas_de_valores(blocos[0].get("values", [])) if blocos else [],
            "parcelas": linhas_de_valores(blocos[1].get("values", [])) if len(blocos) > 1 else [],
        }

    def get_config(self) -> dict:
        import gspread
        try:
            valores = self._planilha().worksheet(ABA_CONFIG).get_all_values()
        except gspread.WorksheetNotFound:
            return {}
        return {l[0].strip(): l[1].strip() for l in valores[1:] if len(l) >= 2 and l[0].strip()}

    # Escrita -----------------------------------------------------------------

    def save_config(self, chave: str, valor: str):
        ws = self._aba(ABA_CONFIG, CONFIG_HEADERS)
        chaves = ws.col_values(1)
        if chave in chaves[1:]:
            linha = chaves.index(chave) + 1
            ws.update(range_name=f"B{linha}", values=[[valor]], value_input_option="RAW")
        else:
            ws.append_row([chave, valor], value_input_option="RAW", table_range="A1")

    def criar_cobranca(self, campos: dict, parcelas: list[dict]) -> str:
        cid = novo_id()
        campos = {**campos, "ID": cid, "Situação": SITUACAO_ATIVA,
                  "Criada em": campos.get("Criada em") or date.today()}
        ws_c = self._aba(ABA_COBRANCAS, COBRANCAS_HEADERS)
        ws_p = self._aba(ABA_PARCELAS, PARCELAS_HEADERS)
        cab_p = ws_p.row_values(1)
        hoje = date.today()
        linhas_p = [_linha(cab_p, {**p, "ID Cobrança": cid, "Registrado em": hoje}) for p in parcelas]
        # Parcelas primeiro: se a gravação da cobrança falhar, sobram linhas
        # órfãs (invisíveis no app), e não uma cobrança sem parcelas.
        if linhas_p:
            ws_p.append_rows(linhas_p, value_input_option="RAW", table_range="A1")
        ws_c.append_row(_linha(ws_c.row_values(1), campos), value_input_option="RAW",
                        table_range="A1")
        return cid

    def _atualizar(self, ws, linha: int, cabecalho: list, campos: dict):
        updates = [{"range": f"{_letra(cabecalho.index(k) + 1)}{linha}", "values": [[_celula(v)]]}
                   for k, v in campos.items() if k in cabecalho]
        if updates:
            ws.batch_update(updates, value_input_option="RAW")

    def atualizar_cobranca(self, cid: str, campos: dict) -> bool:
        ws = self._aba(ABA_COBRANCAS, COBRANCAS_HEADERS)
        cab = ws.row_values(1)
        ids = ws.col_values(cab.index("ID") + 1)
        if cid not in ids[1:]:
            return False
        self._atualizar(ws, ids.index(cid) + 1, cab, campos)
        return True

    def _linha_parcela(self, ws, cab: list, cid: str, n: int):
        valores = ws.get_all_values()
        c_id, c_n = cab.index("ID Cobrança"), cab.index("Nº")
        for i, row in enumerate(valores[1:], start=2):
            if len(row) > max(c_id, c_n) and row[c_id].strip() == cid and row[c_n].strip() == str(n):
                return i
        return None

    def atualizar_parcela(self, cid: str, n: int, campos: dict) -> bool:
        ws = self._aba(ABA_PARCELAS, PARCELAS_HEADERS)
        cab = ws.row_values(1)
        linha = self._linha_parcela(ws, cab, cid, n)
        if linha is None:
            return False
        self._atualizar(ws, linha, cab, campos)
        return True

    def adicionar_parcela(self, cid: str, campos: dict):
        ws = self._aba(ABA_PARCELAS, PARCELAS_HEADERS)
        ws.append_row(_linha(ws.row_values(1), {**campos, "ID Cobrança": cid,
                                                "Registrado em": date.today()}),
                      value_input_option="RAW", table_range="A1")

    def remover_parcela(self, cid: str, n: int) -> bool:
        ws = self._aba(ABA_PARCELAS, PARCELAS_HEADERS)
        cab = ws.row_values(1)
        linha = self._linha_parcela(ws, cab, cid, n)
        if linha is None:
            return False
        ws.delete_rows(linha)
        return True


# ── Arquivo local (só para testar no PC) ──────────────────────────────────────

class Local:
    """Mesma interface da Planilha, gravando num JSON. Nunca usado em produção."""

    def __init__(self, caminho: str):
        self._caminho = caminho
        if not os.path.exists(caminho):
            self._gravar({"cobrancas": [], "parcelas": [], "config": {}})

    def _ler(self) -> dict:
        # O arquivo pode sumir com o app ligado (pasta temporária limpa): recomeça vazio
        if not os.path.exists(self._caminho):
            self._gravar({"cobrancas": [], "parcelas": [], "config": {}})
        with open(self._caminho, encoding="utf-8") as f:
            return json.load(f)

    def _gravar(self, dados: dict):
        with open(self._caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)

    @staticmethod
    def _como_planilha(linhas: list, headers: list) -> list:
        return linhas_de_valores([headers] + [[l.get(h, "") for h in headers] for l in linhas])

    def carregar(self) -> dict:
        d = self._ler()
        return {"cobrancas": self._como_planilha(d["cobrancas"], COBRANCAS_HEADERS),
                "parcelas": self._como_planilha(d["parcelas"], PARCELAS_HEADERS)}

    def get_config(self) -> dict:
        return dict(self._ler().get("config", {}))

    def save_config(self, chave: str, valor: str):
        d = self._ler()
        d.setdefault("config", {})[chave] = valor
        self._gravar(d)

    def criar_cobranca(self, campos: dict, parcelas: list[dict]) -> str:
        d = self._ler()
        cid = novo_id()
        campos = {**campos, "ID": cid, "Situação": SITUACAO_ATIVA,
                  "Criada em": campos.get("Criada em") or date.today()}
        d["cobrancas"].append({h: _celula(campos.get(h)) for h in COBRANCAS_HEADERS})
        for p in parcelas:
            p = {**p, "ID Cobrança": cid, "Registrado em": date.today()}
            d["parcelas"].append({h: _celula(p.get(h)) for h in PARCELAS_HEADERS})
        self._gravar(d)
        return cid

    def atualizar_cobranca(self, cid: str, campos: dict) -> bool:
        d = self._ler()
        for c in d["cobrancas"]:
            if c.get("ID") == cid:
                c.update({k: _celula(v) for k, v in campos.items() if k in COBRANCAS_HEADERS})
                self._gravar(d)
                return True
        return False

    def atualizar_parcela(self, cid: str, n: int, campos: dict) -> bool:
        d = self._ler()
        for p in d["parcelas"]:
            if p.get("ID Cobrança") == cid and p.get("Nº") == str(n):
                p.update({k: _celula(v) for k, v in campos.items() if k in PARCELAS_HEADERS})
                self._gravar(d)
                return True
        return False

    def adicionar_parcela(self, cid: str, campos: dict):
        d = self._ler()
        p = {**campos, "ID Cobrança": cid, "Registrado em": date.today()}
        d["parcelas"].append({h: _celula(p.get(h)) for h in PARCELAS_HEADERS})
        self._gravar(d)

    def remover_parcela(self, cid: str, n: int) -> bool:
        d = self._ler()
        antes = len(d["parcelas"])
        d["parcelas"] = [p for p in d["parcelas"]
                         if not (p.get("ID Cobrança") == cid and p.get("Nº") == str(n))]
        self._gravar(d)
        return len(d["parcelas"]) < antes


def excluir_cobranca(banco, cid: str, hoje: date) -> bool:
    return banco.atualizar_cobranca(cid, {"Situação": SITUACAO_EXCLUIDA, "Excluída em": hoje})


def restaurar_cobranca(banco, cid: str) -> bool:
    return banco.atualizar_cobranca(cid, {"Situação": SITUACAO_ATIVA, "Excluída em": ""})


def receber_em_duas_formas(banco, cid: str, n: int, campos_parcela: dict, nova: dict) -> bool:
    """
    Pagamento híbrido de UMA parcela (as duas partes vêm de nucleo.dividir_recebimento):
    grava a linha nova e depois a parcela. São duas gravações; se a segunda falhar, a
    primeira é desfeita, para a cobrança não ficar com dinheiro a mais.
    """
    banco.adicionar_parcela(cid, nova)
    try:
        ok = banco.atualizar_parcela(cid, n, campos_parcela)
    except Exception:
        try:
            banco.remover_parcela(cid, nova["Nº"])
        except Exception:
            pass
        raise
    if not ok:
        banco.remover_parcela(cid, nova["Nº"])
    return ok


# ── Comprovantes no Drive (opcional) ──────────────────────────────────────────

def drive_configurado(secrets) -> bool:
    try:
        return all(secrets.get(k) for k in ("drive_folder_id", "drive_oauth_client_id",
                                            "drive_oauth_client_secret", "drive_oauth_refresh_token"))
    except Exception:
        return False


def _drive(secrets):
    """API do Drive como o DONO da conta (a conta de serviço não tem cota para arquivos)."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=secrets["drive_oauth_refresh_token"],
        client_id=secrets["drive_oauth_client_id"],
        client_secret=secrets["drive_oauth_client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _subpasta(service, nome: str, pai: str) -> str:
    seguro = nome.replace("\\", "\\\\").replace("'", "\\'")
    achados = service.files().list(
        q=f"name = '{seguro}' and '{pai}' in parents and mimeType = '{_MIME_PASTA}' and trashed = false",
        fields="files(id)", pageSize=1,
    ).execute().get("files", [])
    if achados:
        return achados[0]["id"]
    return service.files().create(body={"name": nome, "mimeType": _MIME_PASTA, "parents": [pai]},
                                  fields="id").execute()["id"]


def enviar_comprovante(secrets, conteudo: bytes, nome_original: str, treinamento: str,
                       descricao: str, quando: date) -> str:
    """
    Sobe o comprovante para <raiz>/TREINAMENTO/ANO/MÊS/ e devolve o link.
    PDF vai como está; foto é reduzida para 1200 px (JPEG 75).
    """
    from googleapiclient.http import MediaIoBaseUpload

    limpo = re.sub(r"[\\/:*?\"<>|]", "-", (descricao or "Comprovante").strip())[:90]
    if (nome_original or "").lower().endswith(".pdf"):
        corpo, mime, ext = io.BytesIO(conteudo), "application/pdf", "pdf"
    else:
        from PIL import Image
        img = Image.open(io.BytesIO(conteudo))
        if img.width > 1200:
            img = img.resize((1200, int(img.height * 1200 / img.width)), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        corpo = io.BytesIO()
        img.save(corpo, format="JPEG", quality=75)
        corpo.seek(0)
        mime, ext = "image/jpeg", "jpg"

    service = _drive(secrets)
    pasta = _subpasta(service, treinamento or "Sem treinamento", secrets["drive_folder_id"])
    pasta = _subpasta(service, str(quando.year), pasta)
    pasta = _subpasta(service, _MESES_PASTA[quando.month - 1], pasta)
    arq = service.files().create(
        body={"name": f"{limpo} - {quando.strftime('%d-%m-%Y')}.{ext}", "parents": [pasta]},
        media_body=MediaIoBaseUpload(corpo, mimetype=mime, resumable=False),
        fields="id, webViewLink",
    ).execute()
    return arq.get("webViewLink", "")

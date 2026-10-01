#!/usr/bin/env python3
"""
Avisos de cobrança no Telegram. Roda pelo GitHub Actions todo dia às 07:30 BRT.

  - Diário: UMA mensagem com 🔴 Atrasadas, 🚨 Cobrar hoje e ⚠️ Cobrar amanhã.
    Sem nada a avisar, não envia.
  - Segunda-feira: resumo da semana (o diário + o que vence até domingo +
    totais recebido / a receber / atrasado).
  - Vai para quem se conectou na tela Notificações do app (aba _Config,
    chaves telegram:<nome>) e não pausou os avisos. TELEGRAM_CHAT_IDS, se
    existir, é somado (jeito antigo, por secret).
  - O que entra na mensagem segue as chaves avisar_* / resumo_semanal do _Config.

Variáveis de ambiente:
  SPREADSHEET_ID       planilha
  GCP_SERVICE_ACCOUNT  JSON da conta de serviço (senão lê credentials.json)
  TELEGRAM_BOT_TOKEN   token do bot de COBRANÇAS (não é o bot do boleto)
  TELEGRAM_CHAT_IDS    opcional, ex.: "123456789,987654321"
  MODO                 auto (padrão) | diario | semanal
  DRY_RUN=1            imprime em vez de enviar

Sai com código 1 se a leitura falhar ou se algum envio falhar: "Success" verde
no Actions precisa querer dizer que a mensagem saiu mesmo.
"""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import nucleo

TIMEZONE = ZoneInfo("America/Sao_Paulo")
LIMITE_MENSAGEM = 4000
# Só leitura: o notificador nunca escreve na planilha
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _limpo(valor: str) -> str:
    """Tira espaços e o BOM (marca invisível que o PowerShell põe no começo ao gravar um secret)."""
    return (valor or "").replace("\ufeff", "").strip()


def hoje_sp() -> date:
    return datetime.now(tz=TIMEZONE).date()


def ler_planilha(spreadsheet_id: str) -> dict:
    import gspread
    from google.oauth2.service_account import Credentials

    raw = _limpo(os.environ.get("GCP_SERVICE_ACCOUNT", ""))
    if not raw:
        with open("credentials.json", encoding="utf-8") as f:
            raw = f.read()
    gc = gspread.authorize(Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES))
    abas = {ws.title: ws for ws in gc.open_by_key(spreadsheet_id).worksheets()}
    ler = lambda nome: nucleo.linhas_de_valores(abas[nome].get_all_values()) if nome in abas else []
    config = {}
    if "_Config" in abas:
        for linha in abas["_Config"].get_all_values()[1:]:
            if len(linha) >= 2 and linha[0].strip():
                config[linha[0].strip()] = linha[1].strip()
    return {"cobrancas": ler("_Cobrancas"), "parcelas": ler("_Parcelas"), "config": config}


# ── Texto ─────────────────────────────────────────────────────────────────────

def _esc(t) -> str:
    return html.escape(str(t), quote=False)


def _linha(p: dict, c: dict, hoje: date) -> str:
    d = p["vencimento"]
    quando = d.strftime("%d/%m") if d.year == hoje.year else d.strftime("%d/%m/%Y")
    atraso = (hoje - d).days
    if atraso > 0:
        quando += f" ({atraso} dia{'s' if atraso > 1 else ''} de atraso)"
    forma = "Pix"
    if c["tipo"] == nucleo.TIPO_CARTAO:
        forma = "💳 passar cartão" + (f" em {p['vezes']}x" if p.get("vezes", 1) > 1 else "")
    return (f"• <b>{_esc(c['cliente'])}</b> ({_esc(c['turma'])}) · {nucleo.formatar_brl(p['valor'])}"
            f" · {_esc(p['rotulo'].lower())} · {forma} · {quando}")


def _secao(titulo: str, itens: list, hoje: date) -> list:
    if not itens:
        return []
    soma = sum(p["valor"] for p, _ in itens)
    return ["", f"{titulo} ({len(itens)} · {nucleo.formatar_brl(soma)})"] + \
           [_linha(p, c, hoje) for p, c in itens]


def _filtrar(a: dict, opcoes: dict | None) -> dict:
    """Esvazia as seções desligadas na tela Notificações."""
    o = opcoes or {}
    return {"atrasadas": a["atrasadas"] if o.get("avisar_atrasadas", True) else [],
            "hoje": a["hoje"] if o.get("avisar_hoje", True) else [],
            "amanha": a["amanha"] if o.get("avisar_amanha", True) else [],
            "semana": a["semana"]}


def montar_diario(cobs: list, hoje: date, opcoes: dict | None = None) -> str | None:
    a = _filtrar(nucleo.avisos(cobs, hoje), opcoes)
    if not (a["atrasadas"] or a["hoje"] or a["amanha"]):
        return None
    linhas = [f"📋 <b>Cobranças · {DIAS_SEMANA[hoje.weekday()]}, {hoje.strftime('%d/%m/%Y')}</b>"]
    linhas += _secao("🔴 <b>Atrasadas</b>", a["atrasadas"], hoje)
    linhas += _secao("🚨 <b>Cobrar hoje</b>", a["hoje"], hoje)
    linhas += _secao("⚠️ <b>Cobrar amanhã</b>", a["amanha"], hoje)
    return "\n".join(linhas)


def montar_semanal(cobs: list, hoje: date, opcoes: dict | None = None) -> str:
    a = _filtrar(nucleo.avisos(cobs, hoje), opcoes)
    domingo = nucleo.inicio_semana(hoje) + timedelta(days=6)
    linhas = [f"🗓️ <b>Cobranças da semana · {hoje.strftime('%d/%m')} a {domingo.strftime('%d/%m/%Y')}</b>"]
    linhas += _secao("🔴 <b>Atrasadas</b>", a["atrasadas"], hoje)
    linhas += _secao("🚨 <b>Cobrar hoje</b>", a["hoje"], hoje)
    linhas += _secao("⚠️ <b>Cobrar amanhã</b>", a["amanha"], hoje)
    linhas += _secao("📅 <b>Resto da semana</b>", a["semana"], hoje)
    if len(linhas) == 1:
        linhas += ["", "Nada para cobrar esta semana."]
    r = nucleo.resumo(cobs)
    linhas += ["", "📊 <b>Geral</b>",
               f"Recebido: {nucleo.formatar_brl(r['recebido'])}",
               f"A receber: {nucleo.formatar_brl(r['a_receber'])}",
               f"Atrasado: {nucleo.formatar_brl(r['atrasado'])} ({r['n_atrasados']} cliente"
               f"{'s' if r['n_atrasados'] != 1 else ''})"]
    return "\n".join(linhas)


def dividir_mensagem(texto: str, limite: int = LIMITE_MENSAGEM) -> list:
    """Quebra em partes de até `limite` caracteres, sem cortar linha no meio."""
    partes, atual = [], ""
    for linha in texto.split("\n"):
        while len(linha) > limite:
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(linha[:limite])
            linha = linha[limite:]
        candidato = f"{atual}\n{linha}" if atual else linha
        if len(candidato) > limite:
            partes.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual.strip():
        partes.append(atual)
    return partes


# ── Envio ─────────────────────────────────────────────────────────────────────

def enviar(bot_token: str, chat_id: str, texto: str) -> bool:
    import requests
    partes = dividir_mensagem(texto)
    for n, parte in enumerate(partes, start=1):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                 json={"chat_id": chat_id, "text": parte, "parse_mode": "HTML",
                                       "disable_web_page_preview": True}, timeout=15)
            corpo = resp.json() if resp.content else {}
            if resp.status_code != 200 or not corpo.get("ok"):
                # Não loga a URL: ela carrega o token
                print(f"  ❌ Parte {n}/{len(partes)} recusada: HTTP {resp.status_code} "
                      f"{corpo.get('description', '')}")
                return False
            print(f"  ✅ Parte {n}/{len(partes)} enviada")
        except Exception as e:
            print(f"  ❌ Falha ao enviar parte {n}/{len(partes)}: {type(e).__name__}")
            return False
    return True


def main() -> int:
    sid = _limpo(os.environ.get("SPREADSHEET_ID", ""))
    if not sid:
        print("SPREADSHEET_ID não configurado.")
        return 1
    modo = (os.environ.get("MODO", "auto").strip().lower() or "auto")
    dry = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "sim")
    if modo not in ("auto", "diario", "semanal"):
        print(f"MODO inválido: {modo!r}")
        return 1
    hoje = hoje_sp()
    if modo == "auto":
        modo = "semanal" if hoje.weekday() == 0 else "diario"
    print(f"Rodando em {datetime.now(tz=TIMEZONE):%d/%m/%Y %H:%M} BRT | modo {modo}"
          f"{' (dry-run)' if dry else ''}")

    try:
        dados = ler_planilha(sid)
    except Exception as e:
        print(f"Erro ao ler a planilha: {type(e).__name__}: {e}")
        return 1
    cobs = nucleo.montar_cobrancas(dados["cobrancas"], dados["parcelas"], hoje)
    a = nucleo.avisos(cobs, hoje)
    print(f"Cobranças {len(cobs)} | atrasadas {len(a['atrasadas'])} | hoje {len(a['hoje'])} | "
          f"amanhã {len(a['amanha'])} | resto da semana {len(a['semana'])}")

    opcoes = nucleo.opcoes_avisos(dados["config"])
    if modo == "semanal" and not opcoes["resumo_semanal"]:
        print("Resumo semanal desligado na tela Notificações: vai o aviso diário.")
        modo = "diario"
    texto = montar_semanal(cobs, hoje, opcoes) if modo == "semanal" else montar_diario(cobs, hoje, opcoes)
    if not texto:
        print("Nada atrasado, nada para hoje nem amanhã. Nenhuma mensagem enviada.")
        return 0
    if dry:
        for n, parte in enumerate(dividir_mensagem(texto), start=1):
            print(f"\n──── parte {n} ({len(parte)} caracteres) ────\n{parte}")
        return 0

    token = _limpo(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    chats = [chat for _, chat in nucleo.destinatarios(dados["config"])]
    chats += [c.strip() for c in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    chats = list(dict.fromkeys(chats))   # sem repetir, mantendo a ordem
    if not token:
        print("Telegram não configurado: falta TELEGRAM_BOT_TOKEN nos secrets.")
        return 1
    if not chats:
        print("Ninguém conectou o Telegram ainda (tela Notificações do app). Nenhuma mensagem enviada.")
        return 0
    ok = True
    for i, chat in enumerate(chats, start=1):
        print(f"Enviando para a pessoa {i} de {len(chats)}")
        ok = enviar(token, chat, texto) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

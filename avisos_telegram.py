"""
Conversa com o bot do Telegram (usado pela tela Notificações do app).

O token do bot NUNCA vai para a planilha: fica nos Secrets (Streamlit e GitHub).
Na planilha fica só o número do chat de cada pessoa, que sozinho não serve
para nada.

Como uma pessoa se conecta: o app abre o bot com um código (t.me/<bot>?start=<código>),
ela toca em COMEÇAR, o Telegram manda "/start <código>" para o bot e o app
acha essa mensagem para descobrir o chat dela.
"""
from __future__ import annotations

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
TEMPO = 15


def _chamar(token: str, metodo: str, **dados) -> dict:
    """Devolve o 'result' da API; erro vira RuntimeError SEM o token no texto."""
    try:
        resp = requests.post(API.format(token=token, metodo=metodo), json=dados, timeout=TEMPO)
        corpo = resp.json()
    except Exception as e:
        raise RuntimeError(f"sem resposta do Telegram ({type(e).__name__})") from None
    if not corpo.get("ok"):
        raise RuntimeError(corpo.get("description") or f"erro {resp.status_code}")
    return corpo["result"]


def nome_do_bot(token: str) -> str:
    """@usuario do bot (para montar o link de abrir no Telegram)."""
    return _chamar(token, "getMe").get("username", "")


def link_para_conectar(usuario_bot: str, codigo: str) -> str:
    return f"https://t.me/{usuario_bot}?start={codigo}"


def achar_chat(token: str, codigo: str) -> str | None:
    """Chat de quem tocou em COMEÇAR com este código; None se a mensagem ainda não chegou."""
    for u in reversed(_chamar(token, "getUpdates", limit=100, timeout=0)):
        msg = u.get("message") or {}
        if (msg.get("text") or "").strip() == f"/start {codigo}":
            return str(msg["chat"]["id"])
    return None


def enviar(token: str, chat_id: str, texto: str):
    _chamar(token, "sendMessage", chat_id=chat_id, text=texto, parse_mode="HTML",
            disable_web_page_preview=True)

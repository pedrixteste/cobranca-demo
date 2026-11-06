import hashlib
import html as _html
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components


def _recarregar_modulos_alterados():
    """
    No Streamlit Cloud, um `git push` troca os arquivos com o app LIGADO. O app.py é relido a
    cada rodada, mas os outros arquivos (nucleo, dados...) ficam na memória na versão antiga,
    e o app novo quebra com ImportError ao pedir uma função que a versão antiga não tem
    (aconteceu em 01/10/2026). Aqui, a cada rodada, o que mudou no disco é recarregado.
    Ordem: quem é importado pelos outros vem primeiro.
    """
    import importlib
    import sys
    pasta = Path(__file__).parent
    vistos = sys.__dict__.setdefault("_cobranca_mtimes", {})
    recarregou = False
    for nome in ("nucleo", "dados", "demo", "feriados", "avisos_telegram", "notifier"):
        try:
            mtime = (pasta / f"{nome}.py").stat().st_mtime
        except OSError:
            continue
        # recarrega também depois que uma dependência foi recarregada (dados usa nomes do nucleo)
        if nome in sys.modules and (vistos.get(nome) != mtime or recarregou):
            importlib.reload(sys.modules[nome])
            recarregou = True
        vistos[nome] = mtime
    if recarregou:
        # objetos guardados em cache foram criados pelas classes antigas
        st.cache_resource.clear()
        st.cache_data.clear()


_recarregar_modulos_alterados()

from dados import (ABA_JUDICIAL, ABA_PROTESTOS, Local, Planilha, drive_configurado, enviar_comprovante,
                   excluir_cobranca, novo_id, receber_em_duas_formas, restaurar_cobranca)
from demo import banco_demo
import avisos_telegram
import feriados
import notifier
from nucleo import (CLI_ATRASADO, CLI_EM_BREVE, CLI_EM_DIA, CLI_QUITADO, OPCOES_AVISO, ROTULO_CLI, chave_busca,
                    administrador, aparelhos_por_pessoa, destinatarios, destinatarios_juridico, nome_do_aparelho, nomes_livres,
                    cidade_da_turma, local_da_cobranca, opcoes_avisos, pessoas_da_config,
                    formatar_telefone, link_ligar, link_whatsapp, telefone_do_cliente, telefone_valido,
                    dono_do_email, email_valido, emails_por_pessoa, login_google_ligado, normalizar_email,
                    pessoa_do_email,
                    texto_vezes,
                    FORMAS, TIPO_HIBRIDO, centavos, dividir_recebimento, parcelas_hibrido,
                    TIPO_PERMUTA, TIPO_CREDITO, parcelas_permuta, permutas_do_cliente, FORMAS_HIBRIDO,
                    SEP_TURMAS_PLANILHA, normalizar_turmas, treinamentos_das_turmas,
                    SIT_ATRASADA, SIT_EM_BREVE, SIT_PAGA, STATUS_PAGA, TIPO_CARTAO, TIPO_PIX,
                    TREINAMENTOS, agenda, conferir_total, datas_continuas, data_br, filtrar,
                    formatar_brl, inicio_semana, mes_mais, montar_cobrancas, nome_mes,
                    normalizar_turma, ordenar_para_cobrar, parcelas_cartao, parcelas_pix,
                    proximo_numero, resolver_valores, resumo, valor_para_float,
                    # Jurídico (pedido 03/11)
                    JUD_SEM_ACORDO, NEG_A_VISTA, NEG_PARCELADO, NEG_SEM, OBJETOS, ROTULO_JUD, SITUACAO_ATIVA,
                    SITUACAO_EXCLUIDA, acordo_para_texto, advogados_usados, casa_busca_juridico,
                    marcar_parcela_acordo, montar_judiciais, montar_protestos, ordenar_judiciais,
                    ordenar_protestos, parcelas_do_acordo, resumo_juridico,
                    # Acesso só ao Jurídico (pedido 04/11)
                    ACESSO_JURIDICO, MAX_PARCELAS_ACORDO, codigo_aparelho, liberacao_por_codigo,
                    pessoas_restritas, so_juridico, texto_limpo)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_ABREV = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
DIAS_SEMANA_LONGO = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                     "sexta-feira", "sábado", "domingo"]

SVG_MAIS = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
            'stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>')
SVG_LISTA = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" '
             'height="17" rx="2.5"/><path d="M16 2.5v3M8 2.5v3M3 9.5h18M8 14h8M8 17.5h5"/></svg>')
SVG_PIX = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linejoin="round"><rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1"/>'
           '<rect x="14" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="3.5" y="14" width="6.5" '
           'height="6.5" rx="1"/><path d="M14 14h2.5v2.5H14zM18 18h2.5v2.5H18zM14 18.5h1.5M18.5 14h2"/></svg>')
SVG_CARTAO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="5" width="19" '
              'height="14" rx="2.5"/><path d="M2.5 10h19M6.5 15h4"/></svg>')
# Híbrido = os dois juntos: os quadradinhos do Pix em cima e o cartão embaixo
SVG_HIBRIDO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="2.5" width="4.5" '
               'height="4.5" rx=".8"/><rect x="10" y="2.5" width="4.5" height="4.5" rx=".8"/>'
               '<rect x="2.5" y="10" width="4.5" height="4.5" rx=".8"/><rect x="9.5" y="11.5" '
               'width="12" height="9.5" rx="2"/><path d="M9.5 15.2h12"/></svg>')
# Permuta = troca: duas setas indo e voltando
SVG_PERMUTA = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h14M14 4l4 4-4 4"/>'
               '<path d="M20 16H6M10 12l-4 4 4 4"/></svg>')
SVG_SETA = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>')
# Jurídico = balança; cobrança judicial = martelo; protesto = papel com selo
SVG_BALANCA = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5v17M8 20.5h8M4 7h16"/>'
               '<path d="M4 7l-2.5 6M4 7l2.5 6M20 7l-2.5 6M20 7l2.5 6"/>'
               '<path d="M1.5 13a2.5 2.5 0 0 0 5 0zM17.5 13a2.5 2.5 0 0 0 5 0z"/></svg>')
SVG_MARTELO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5l6 6-3 3-6-6z"/>'
               '<path d="M13 8l-8.5 8.5a1.5 1.5 0 0 0 2.1 2.1L15 10"/><path d="M12.5 21h8"/></svg>')
SVG_PROTESTO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round"><path d="M6 2.5h8l4 4v15H6z"/>'
                '<path d="M14 2.5v4h4"/><circle cx="12" cy="13.5" r="3"/>'
                '<path d="M10.7 16.2l-.7 3.3 2-1 2 1-.7-3.3"/></svg>')


ICONE_TIPO = {TIPO_PIX: ":material/qr_code_2:", TIPO_CARTAO: ":material/credit_card:"}
# Classe de cor de cada situação (mesma paleta na parcela e na cobrança)
COR_CLI = {CLI_ATRASADO: "c-atraso", CLI_EM_BREVE: "c-breve", CLI_EM_DIA: "c-ok",
           CLI_QUITADO: "c-ok"}
COR_PARC = {SIT_PAGA: "c-ok", SIT_ATRASADA: "c-atraso", SIT_EM_BREVE: "c-breve", "aberta": "c-neutro"}

_FUSO = ZoneInfo("America/Sao_Paulo")


def _hoje() -> date:
    """Hoje no horário de Brasília (o servidor do Streamlit roda em UTC)."""
    return datetime.now(_FUSO).date()


st.set_page_config(page_title="Cobranças", page_icon="💳", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(f"<style>{Path(__file__).with_name('estilo.css').read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True)


# ── Onde os dados moram ───────────────────────────────────────────────────────

def _segredo(chave: str):
    try:
        return st.secrets[chave]
    except Exception:
        return None


def _modo_demo() -> bool:
    """Demonstração com clientes de exemplo (secret modo_demo = true); não toca em planilha."""
    valor = os.environ.get("COBRANCA_DEMO") or _segredo("modo_demo")
    return str(valor).lower() in ("true", "1", "sim")


@st.cache_resource(show_spinner=False)
def _banco():
    """
    Planilha Google em produção. COBRANCA_LOCAL=arquivo.json liga o modo de
    teste no PC; ele NUNCA é usado por falta de configuração (sem planilha
    configurada o app mostra erro, para ninguém lançar cobrança num arquivo
    que some).
    """
    local = os.environ.get("COBRANCA_LOCAL", "").strip()
    if local:
        return Local(local)
    if _modo_demo():
        return banco_demo(_hoje())
    sid = _segredo("spreadsheet_id")
    cred = _segredo("gcp_service_account")
    if not sid or not cred:
        return None
    info = json.loads(cred) if isinstance(cred, str) else json.loads(json.dumps(dict(cred)))
    return Planilha(sid, info)


def _secrets_drive():
    try:
        return st.secrets if drive_configurado(st.secrets) else None
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def _carregar() -> dict:
    # Erro aqui NÃO fica guardado (o Streamlit só guarda o que deu certo): a próxima tela tenta de novo
    return _banco().carregar()


def _invalidar():
    """Depois de qualquer gravação: a próxima tela lê a planilha de novo."""
    _carregar.clear()


class PlanilhaFora(Exception):
    """A planilha do Google não respondeu e não há uma leitura boa guardada para usar no lugar."""


# Depois que a planilha falha, o app passa este tempo sem tentar ler de novo SOZINHO (só com o
# "Tentar de novo"): sem isso, numa queda do Google, cada pedaço de cada tela de cada pessoa
# esperaria o prazo inteiro da leitura, e o app ficaria lento justo quando a planilha está fora.
ESPERA_DEPOIS_DE_FALHA = 20   # segundos


@st.cache_resource(show_spinner=False)
def _estado_planilha() -> dict:
    """
    Memória comum a todo mundo que usa o app (some quando o app reinicia):
      "cfg"            última configuração lida COM SUCESSO
      "config_falhou"  / "dados_falhou"   quando a leitura falhou por último (relógio do servidor)
      "erro"           o motivo da última falha (aparece pequeno embaixo do aviso)
    """
    return {}


def _falhou_ha_pouco(chave: str) -> bool:
    quando = _estado_planilha().get(chave)
    return quando is not None and time.monotonic() - quando < ESPERA_DEPOIS_DE_FALHA


def _pode_limpar_cache() -> bool:
    """No máximo uma releitura forçada a cada 20 s para o APP INTEIRO (abrir abas novas não fura)."""
    est = _estado_planilha()
    if time.monotonic() - est.get("limpou_em", -1e9) < ESPERA_DEPOIS_DE_FALHA:
        return False
    est["limpou_em"] = time.monotonic()
    return True


def _anotar_falha(chave: str, erro: Exception):
    est = _estado_planilha()
    est[chave] = time.monotonic()
    est["erro"] = str(erro)


def _aviso_planilha_fora():
    """
    Aviso com "Tentar de novo" quando a planilha não responde (uma vez só por tela, mesmo que
    várias partes da tela tenham tentado ler). Antes deste aviso o app ficava parado no
    "Carregando..." sem prazo, e quem atualizava a página caía na mesma espera (pedido 03/11).
    """
    if st.session_state.get("_avisou_fora"):
        return
    st.session_state["_avisou_fora"] = True
    _info("<b>A planilha do Google não respondeu agora.</b> Costuma passar em poucos segundos: "
          "toque em <b>Tentar de novo</b>.", "cx-perigo")
    if st.button("Tentar de novo", key="btn_tentar_de_novo", icon=":material/refresh:", type="primary",
                 use_container_width=True):
        if (_usuario() and _so_juridico()) or not _pode_limpar_cache():
            st.rerun()   # só força a releitura uma vez a cada 20 s para o app inteiro
        est = _estado_planilha()
        est.pop("config_falhou", None)
        est.pop("dados_falhou", None)
        _invalidar()
        _ler_config.clear()
        st.rerun()
    detalhe = _estado_planilha().get("erro", "")
    if detalhe and _sou_admin_sem_ler():
        st.markdown(f"<div class='cx-dica'>Detalhe: {_e(detalhe[:180])}</div>", unsafe_allow_html=True)


def _dados():
    """As abas do app, lidas da planilha (guardadas por 1 minuto). None se não deu para ler (o aviso
    com "Tentar de novo" já aparece)."""
    if _banco() is None:
        st.error("A planilha ainda não foi configurada nos Secrets do app.")
        return None
    if _falhou_ha_pouco("dados_falhou"):
        _aviso_planilha_fora()
        return None
    try:
        with st.spinner("Carregando..."):
            return _carregar()
    except Exception as e:
        _anotar_falha("dados_falhou", e)
        _aviso_planilha_fora()
        return None


def _cobrancas(incluir_excluidas: bool = False):
    """Cobranças já calculadas. None se a planilha não pôde ser lida (aviso já mostrado).
    Quem só tem acesso ao Jurídico nunca recebe cobrança nenhuma, venha o pedido de onde vier
    (segunda trava, além do roteador)."""
    if _so_juridico() or (_usuario() and not _sessao_ok()):
        return None
    d = _dados()
    if d is None:
        return None
    return montar_cobrancas(d["cobrancas"], d["parcelas"], _hoje(), incluir_excluidas)


def _cobranca(cid: str):
    for c in _cobrancas(incluir_excluidas=True) or []:
        if c["id"] == cid:
            return c
    return None


def _juridico(incluir_excluidos: bool = False):
    """(cobranças judiciais, protestos) já calculados. None se a planilha não pôde ser lida."""
    d = _dados()
    if d is None:
        return None
    return (montar_judiciais(d.get("judiciais", []), _hoje(), incluir_excluidos),
            montar_protestos(d.get("protestos", []), incluir_excluidos))


def _judicial(jid: str):
    return next((j for j in (_juridico(True) or ([], []))[0] if j["id"] == jid), None)


def _protesto(pid: str):
    return next((p for p in (_juridico(True) or ([], []))[1] if p["id"] == pid), None)


def _usuario() -> str:
    """Nome de quem está usando agora (escolhido na tela "Quem está usando?")."""
    return st.session_state.get("_quem", "")


def _email_login() -> str:
    """E-mail do login do Streamlit Cloud, quando ele informa (nem sempre informa)."""
    for atributo in ("user", "experimental_user"):
        try:
            u = getattr(st, atributo)
            email = u.get("email") if hasattr(u, "get") else getattr(u, "email", None)
            if email:
                return str(email).strip().lower()
        except Exception:
            pass
    return ""


# ── Tamanho do texto ──────────────────────────────────────────────────────────

TAMANHOS = {"Pequeno": 0.8, "Médio": 0.9, "Grande": 1.0}
TAMANHO_PADRAO = "Médio"


@st.cache_data(ttl=600, show_spinner=False)
def _ler_config() -> dict:
    # Erro aqui NÃO fica guardado: a próxima tela tenta ler de novo
    return _banco().get_config()


def _config() -> dict:
    """
    Configuração do app (_Config). Até 03/11, uma leitura que falhava virava "configuração vazia" e
    ficava GUARDADA por 10 minutos: nesse tempo o app não sabia quem era quem (sumia a entrada com
    Gmail, o botão Configurações e a lista de nomes). Agora, se a leitura falhar, vale a última que
    deu certo; se ainda não teve nenhuma, a tela mostra o aviso com "Tentar de novo".
    """
    if not _banco():
        return {}
    est = _estado_planilha()
    if not _falhou_ha_pouco("config_falhou"):
        try:
            cfg = _ler_config()
        except Exception as e:
            _anotar_falha("config_falhou", e)
        else:
            if est.get("cfg") != cfg:
                est["cfg"] = dict(cfg)   # troca a referência inteira: quem está lendo nunca vê pela metade
            return cfg
    guardada = est.get("cfg")
    if guardada is not None:
        return dict(guardada)
    raise PlanilhaFora(est.get("erro", ""))


def _tamanho_atual() -> str:
    if "_tamanho" not in st.session_state:
        try:
            salvo = _config().get("tamanho_texto")
        except PlanilhaFora:
            return TAMANHO_PADRAO   # tenta de novo na próxima tela
        st.session_state["_tamanho"] = salvo if salvo in TAMANHOS else TAMANHO_PADRAO
    return st.session_state["_tamanho"]


def _mudar_tamanho():
    if _so_juridico() or not _sessao_ok():
        return   # roda antes do roteador: quem é Só Jurídico não muda nada que vale para todos
    novo = st.session_state.get("_seg_tamanho")
    if novo not in TAMANHOS:
        # Tocar de novo na opção marcada desmarca: volta para a que estava
        st.session_state["_seg_tamanho"] = st.session_state.get("_tamanho", TAMANHO_PADRAO)
        return
    if novo != st.session_state.get("_tamanho"):
        st.session_state["_tamanho"] = novo
        try:
            _banco().save_config("tamanho_texto", novo)
            _ler_config.clear()
        except Exception:
            pass


st.markdown(
    # A janela é div[role=dialog] até o 1.60 e section[role=dialog] no 1.63 (Cloud)
    f"<style>.block-container, [data-testid='stDialog'] [role='dialog'] "
    f"{{ zoom: {TAMANHOS[_tamanho_atual()]}; }}</style>",
    unsafe_allow_html=True,
)


# ── Utilidades de tela ────────────────────────────────────────────────────────

def _e(texto) -> str:
    """Escapa texto que vai para HTML. Tudo que vem da planilha passa por aqui."""
    # Quebra de linha vira <br>: uma linha em branco dentro do st.markdown fechava o bloco HTML e o
    # resto virava Markdown (imagem/link de fora na tela de quem abrisse; auditoria de 04/11)
    return _html.escape(str(texto if texto is not None else "")).replace("\r", "").replace("\n", "<br>")


_RE_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|:~<>$])")


def _rotulo(texto) -> str:
    """Texto que vira RÓTULO de botão, pílula ou aviso (o Streamlit lê Markdown ali): uma linha só e
    com os sinais do Markdown neutralizados, para um nome digitado nunca virar imagem ou link."""
    return _RE_MARKDOWN.sub(r"\\\1", " ".join(str(texto or "").split()))


def _sou_admin_sem_ler() -> bool:
    try:
        return _sou_admin()
    except Exception:
        return False


def _erro_curto(e: Exception) -> str:
    """Motivo do erro para a tela: completo só para o administrador (pode trazer o código da planilha);
    para os outros, só o tipo. O completo vai sempre para o registro (Manage app → logs)."""
    print(f"[erro] {e!r}", flush=True)
    try:
        return str(e) if _sou_admin() else type(e).__name__
    except Exception:
        return type(e).__name__


def _pct(pago: float, total: float) -> int:
    """Porcentagem da barrinha, sempre entre 0 e 100 (valor absurdo não derruba a tela)."""
    try:
        r = 100 * (pago / total) if total else 0
        return int(round(min(100, max(0, r)))) if math.isfinite(r) else 0
    except (ZeroDivisionError, OverflowError, ValueError, TypeError):
        return 0


def _url_segura(url) -> str:
    u = str(url or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def _ir(tela: str):
    st.session_state.tela = tela
    st.rerun()


def _flash(msg: str, icone: str = "✅"):
    """Aviso que aparece DEPOIS do rerun (st.success antes de st.rerun some)."""
    st.session_state.setdefault("_flash", []).append((msg, icone))


def _mostrar_flash():
    for msg, icone in st.session_state.pop("_flash", []):
        st.toast(_rotulo(msg), icon=icone)


def _cabecalho(titulo: str, voltar_para: str, subtitulo: str = ""):
    if st.button("Voltar", key="voltar_topo", icon=":material/arrow_back:", type="tertiary"):
        _ir(voltar_para)
    sub = f"<div class='cx-sub'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(f"<div class='cx-titulo'>{_e(titulo)}</div>{sub}", unsafe_allow_html=True)


def _titulo_secao(numero: int, texto: str):
    st.markdown(f"<div class='sec-tit'><span>{numero}</span>{_e(texto)}</div>", unsafe_allow_html=True)


def _info(html_txt: str, classe: str = "cx-info"):
    st.markdown(f"<div class='{classe}'>{html_txt}</div>", unsafe_allow_html=True)


def _erro_campo(texto: str):
    """Aviso de erro embaixo de um campo. Não usa st.caption(":red[...]"): a legenda do
    Streamlit é meio transparente e, no modo noturno, o vermelho ficava apagado."""
    st.markdown(f"<div class='cx-erro'>{_e(texto)}</div>", unsafe_allow_html=True)


def _num_br(x: float) -> str:
    """1500 → '1.500,00' (o valor sem o 'R$', como aparece dentro dos campos)."""
    return formatar_brl(x).replace("R$ ", "")


VALOR_MAXIMO_CAMPO = 100_000_000   # R$ 100 milhões: acima disso é engano (ou tentativa de travar a tela)
MARCA_VALOR = "__rs"   # fim da chave de todo campo de valor: o script _JS_CAMPOS põe ponto do milhar e ",00"


def _valor(rotulo: str, key: str, placeholder: str = "0,00", help: str = None):
    """
    Campo de valor em reais. Devolve (valor, ok): valor None = em branco;
    ok False = digitou algo que não é valor (o aviso já aparece embaixo).
    Enquanto a pessoa digita, o navegador já mostra '1.500,00' (ver _JS_CAMPOS).
    """
    txt = st.text_input(rotulo, key=key + MARCA_VALOR, placeholder=placeholder, help=help, max_chars=20)
    if not txt.strip():
        return None, True
    v = valor_para_float(txt)
    if v is None or v < 0 or v > VALOR_MAXIMO_CAMPO:
        _erro_campo("Valor inválido. Ex.: 1500 ou 1.500,50")
        return None, False
    return v, True


def _valores_automaticos(chaves: list, restante: float):
    """
    Campos de valor de cada parcela (pedido 17/10): já vêm PREENCHIDOS com a parte de cada uma
    (10x de R$ 1.000 = R$ 100,00 em cada). Quem a pessoa mudou fica como ela escreveu; os outros
    dividem o que sobrou, então o total continua fechando. Apagar um campo devolve ele à conta.
    Roda ANTES de desenhar os campos (o Streamlit só deixa mudar o campo antes de ele aparecer).
    """
    ss = st.session_state
    mexidos, digitados = [], []
    for chave in chaves:
        k = chave + MARCA_VALOR
        atual = str(ss.get(k, "") or "")
        mexeu = bool(atual.strip()) and atual != ss.get(f"_auto_{k}")
        mexidos.append(mexeu)
        digitados.append(valor_para_float(atual) if mexeu else None)
    for chave, mexeu, parte in zip(chaves, mexidos, resolver_valores(restante, digitados)):
        if not mexeu:
            k = chave + MARCA_VALOR
            ss[k] = ss[f"_auto_{k}"] = _num_br(parte) if restante > 0 and parte > 0 else ""


def _limpar_campos(prefixo: str):
    for k in [k for k in st.session_state if str(k).startswith(prefixo)]:
        del st.session_state[k]


def _cartao_toque(chave_container: str, chave_botao: str, rotulo: str, html_cartao: str) -> bool:
    """Cartão inteiro tocável: o botão fica invisível por cima dele."""
    with st.container(key=chave_container):
        st.markdown(html_cartao, unsafe_allow_html=True)
        return st.button(_rotulo(rotulo), key=chave_botao)


def _cartao_inicio(chave_container, chave_botao, rotulo, classe, icone, titulo, descricao, chips=""):
    return _cartao_toque(
        chave_container, chave_botao, rotulo,
        f"<div class='hm-card {classe}'><div class='hm-ico'>{icone}</div>"
        f"<div class='hm-txt'><div class='hm-tit'>{titulo}</div>"
        f"<div class='hm-desc'>{descricao}</div>{chips}</div>"
        f"<div class='hm-seta'>{SVG_SETA}</div></div>",
    )


# ── Tela inicial ──────────────────────────────────────────────────────────────

def tela_inicio():
    hoje = _hoje()
    st.markdown(
        f"<div class='hm-data'>{DIAS_SEMANA_LONGO[hoje.weekday()]}, {hoje.day} de "
        f"{MESES[hoje.month - 1].lower()}</div><div class='hm-marca'>Cobranças</div>",
        unsafe_allow_html=True,
    )

    if _cartao_inicio("hm_nova", "tq_nova", "Cadastrar nova cobrança", "claro", SVG_MAIS,
                      "Nova cobrança", "Pix, cartão, híbrido ou permuta"):
        _ir("nova")

    chips = ""
    cobs = _cobrancas()
    if cobs:
        domingo = inicio_semana(hoje) + timedelta(days=6)
        n_atr = sum(1 for c in cobs if c["situacao"] == CLI_ATRASADO)
        n_sem = len(agenda(cobs, hoje, domingo, com_atrasadas=False))
        partes = []
        if n_atr:
            partes.append(f"<span class='hm-chip atraso'>{n_atr} atrasado{'s' if n_atr > 1 else ''}</span>")
        partes.append(f"<span class='hm-chip'>{n_sem} cobrança{'s' if n_sem != 1 else ''} esta semana</span>"
                      if n_sem else "<span class='hm-chip'>Nada para cobrar esta semana</span>")
        chips = f"<div class='hm-chips'>{''.join(partes)}</div>"

    if _cartao_inicio("hm_rel", "tq_rel", "Abrir relatório de cobranças", "escuro", SVG_LISTA,
                      "Relatório de cobranças", "Quem pagou, quem falta, quem atrasou", chips):
        _ir("relatorio")

    # Jurídico (pedido 03/11): cobranças judiciais e protestos
    if _cartao_inicio("hm_jur", "tq_jur", "Abrir jurídico", "claro", SVG_BALANCA,
                      "Jurídico", "Cobranças judiciais e protestos", _chips_juridico()):
        _ir("juridico")

    st.session_state.setdefault("_seg_tamanho", _tamanho_atual())
    st.segmented_control("Tamanho do texto", list(TAMANHOS), key="_seg_tamanho",
                         on_change=_mudar_tamanho)

    if st.button("Cobranças excluídas", key="btn_excluidas", icon=":material/restore_from_trash:",
                 type="tertiary"):
        _ir("excluidas")

    # Acessos discretos, lado a lado
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Notificações", key="btn_notificacoes", icon=":material/notifications:", type="tertiary"):
            _ir("notificacoes")
    with c2:
        if st.button("Feriados", key="btn_feriados", icon=":material/beach_access:", type="tertiary"):
            _ir("feriados")

    if _sou_admin() and st.button("Configurações", key="btn_config", icon=":material/settings:",
                                  type="tertiary"):
        _ir("config")

    if _usuario() and _login_ligado():
        if st.button(f"Usando como {_usuario()} · sair", key="btn_sair_google", icon=":material/logout:",
                     type="tertiary", help="Sai do Gmail neste aparelho. Para entrar de novo, é só tocar em "
                                           "Entrar com Google."):
            _sair_google()
    elif _usuario() and _travado():
        st.markdown(f"<div class='hm-quem'>Usando como <b>{_e(_usuario())}</b></div>", unsafe_allow_html=True)
    elif _usuario() and st.button(f"Usando como {_usuario()} · trocar", key="btn_trocar_pessoa",
                                  icon=":material/person:", type="tertiary"):
        st.session_state.pop("_quem", None)
        st.session_state["_trocando"] = True
        st.rerun()

    if _modo_demo() and st.button("Recomeçar o exemplo do zero", key="btn_demo_reset",
                                  icon=":material/refresh:", type="tertiary"):
        banco_demo(_hoje(), recomecar=True)
        _invalidar()
        _ler_config.clear()
        _flash("Exemplo recomeçado")
        st.rerun()


# ── Quem está usando ──────────────────────────────────────────────────────────
# O app é uma conta só para todo mundo, mas cada cobrança guarda QUEM cadastrou
# e cada pagamento guarda QUEM marcou.
#
# O Streamlit Cloud não informa o e-mail de quem está logado, então a trava é
# por APARELHO: na primeira vez a pessoa escolhe o nome e aquele aparelho fica
# preso nele (regras em nucleo.py, seção "Pessoas e aparelhos"). Para trocar,
# só pelo administrador, na tela Configurações.
#
# O aparelho é reconhecido por um código guardado em DOIS lugares:
#   - cookie `cob_dev`  (vale para o atalho que a pessoa já tem na tela do celular)
#   - `?a=<código>` no endereço (o iPhone apaga cookie de site depois de 7 dias
#     sem uso; com o código no endereço o atalho continua funcionando)
# Na demonstração não há trava: qualquer um digita um nome e pode trocar.

MAX_NOME = 30
COOKIE_APARELHO = "cob_dev"


def _travado() -> bool:
    return not _modo_demo()


def _pessoas() -> list:
    return pessoas_da_config(_config())


def _sou_admin() -> bool:
    return bool(_usuario()) and _usuario() == administrador(_config())


def _so_juridico() -> bool:
    """Quem está usando só pode ver o Jurídico (Configurações → Acesso: Só Jurídico). Na demonstração,
    "Recomeçar o exemplo" apaga a lista de pessoas: lá, estar fora da lista não restringe."""
    return bool(_usuario()) and so_juridico(_config(), _usuario(), fora_da_lista_restringe=not _modo_demo())


def _sessao_ok(cfg: dict | None = None) -> bool:
    """Quem está usando ainda é quem diz ser (Gmail ou aparelho ainda ligados ao nome, e o nome ainda na
    lista). Usa a configuração guardada (barato); o roteador já confere a cada tela, e isto cobre o que
    roda FORA dele: callbacks e janelinhas (auditoria de 04/11)."""
    quem = _usuario()
    if not quem:
        return False
    if _modo_demo():
        return True
    cfg = _config() if cfg is None else cfg
    if quem not in pessoas_da_config(cfg):
        return False
    if _login_ligado():
        return pessoa_do_email(cfg, _email_google()) == quem
    return nome_do_aparelho(cfg, _aparelho()) == quem


def _codigo_limpo(v) -> str:
    v = re.sub(r"[^a-f0-9]", "", str(v or "").lower())
    return v if 16 <= len(v) <= 64 else ""


def _aparelho() -> str:
    """Código deste aparelho: o do endereço (`?a=`), que o navegador coloca sozinho a partir do
    que tem guardado; o cookie só é lido direto onde a hospedagem o repassa (no PC, sim; no
    Streamlit Cloud, não). '' se ainda não tem nenhum."""
    do_endereco = _codigo_limpo(st.query_params.get("a", ""))
    try:
        do_cookie = _codigo_limpo(st.context.cookies.get(COOKIE_APARELHO, ""))
    except Exception:
        do_cookie = ""
    if os.environ.get("COBRANCA_SEM_COOKIE"):   # só para teste: imita o Streamlit Cloud no PC
        do_cookie = ""
    return do_endereco or do_cookie


def _script_aparelho(codigo: str = ""):
    """
    O código do aparelho mora no NAVEGADOR (cookie + localStorage), mas o Streamlit Cloud não
    repassa cookies para o app (testado em 01/10/2026: o cookie é gravado e o Python não o vê).
    Então é o navegador que entrega o código, colocando `?a=<código>` no endereço:
      - sem `codigo` (o Python ainda não sabe): lê ou cria o código, grava e recarrega a página
        já com `?a=`; se depois de 3 tentativas não der, troca o texto de espera por um aviso;
      - com `codigo`: só regrava (renova a validade; o iPhone apaga depois de 7 dias sem uso).
    """
    _iframe_invisivel("""
<script>
const P = window.parent, FIXO = "%s", CHAVE = "cob_dev", CONTA = "cob_dev_recarga";
const ler = () => { const m = P.document.cookie.match(/(?:^|; )cob_dev=([a-f0-9]+)/);
                    let v = m ? m[1] : ""; try { v = v || P.localStorage.getItem(CHAVE) || ""; } catch (e) {} return v; };
const gravar = id => { P.document.cookie = CHAVE + "=" + id + "; path=/; max-age=34560000; SameSite=Lax" +
                                           (P.location.protocol === "https:" ? "; Secure" : "");
                       try { P.localStorage.setItem(CHAVE, id); } catch (e) {} };
let id = FIXO || ler();
if (!id) { const a = new Uint8Array(12); crypto.getRandomValues(a);
           id = Array.from(a, b => b.toString(16).padStart(2, "0")).join(""); }
gravar(id);
if (FIXO) { try { P.sessionStorage.removeItem(CONTA); } catch (e) {} }
else {
  let n = 0; try { n = parseInt(P.sessionStorage.getItem(CONTA) || "0"); } catch (e) {}
  if (n < 3) {
    try { P.sessionStorage.setItem(CONTA, n + 1); } catch (e) {}
    const u = new URL(P.location.href); u.searchParams.set("a", id);
    // Este iframe é "sandbox" e não pode trocar o endereço da página de fora. Mas pode injetar
    // um script NELA (como a seta de voltar faz), e esse script, sim, pode.
    const s = P.document.createElement("script");
    s.textContent = "location.replace(" + JSON.stringify(u.toString()) + ");";
    P.document.head.appendChild(s);
  } else {
    const e = P.document.querySelector(".dev-espera");
    if (e) e.textContent = "Não consegui preparar este aparelho. Feche e abra o app de novo; se continuar, avise o Pedro.";
  }
}
</script>
""" % codigo)


def _renovar_cookie_do_aparelho():
    """
    Uma vez por sessão: deixa o cookie igual ao código do endereço e renova a validade.
    Fica no FIM da página de propósito: um elemento que só existe na 1ª rodada, se ficar
    no topo, desloca todos os outros e o Streamlit deixa pedaços apagados da tela anterior
    (ferramentas/auditoria_contraste.py acusa como FANTASMAS).
    """
    aparelho = _aparelho()
    if aparelho and not st.session_state.get("_aparelho_ok"):
        st.session_state["_aparelho_ok"] = True
        _script_aparelho(aparelho)


def _prender(aparelho: str, nome: str, pessoas: list):
    """Prende este aparelho no nome (criando a pessoa, se for nova) e entra."""
    nome = " ".join(nome.replace(",", " ").replace(":", " ").split())[:MAX_NOME]
    existente = next((p for p in pessoas if chave_busca(p) == chave_busca(nome)), None)
    final = existente or nome
    try:
        b = _banco()
        if not existente:
            b.save_config("pessoas", ", ".join(pessoas + [final]))
        b.save_config(f"aparelho:{aparelho}", final)
        if str(_config().get(f"liberado:{final}", "")).strip():
            b.save_config(f"liberado:{final}", "")   # a liberação vale para UM aparelho
        _ler_config.clear()
    except Exception as e:
        st.error(f"Não consegui guardar: {_erro_curto(e)}")
        return
    st.session_state["_quem"] = final
    st.session_state.pop("_trocando", None)
    if "quem" in st.query_params:
        del st.query_params["quem"]
    st.query_params["a"] = aparelho
    st.rerun()


# ── Entrada com Google (pedido 26/10) ─────────────────────────────────────────
# Cada pessoa ligada a UM Gmail (Configurações); quem entra com aquele Gmail, em qualquer
# aparelho, é aquela pessoa. Só vale quando as TRÊS coisas acontecem:
#   1. a chave do Google está nos Secrets ([auth] + [auth.google], ver _login_configurado);
#   2. o administrador testou com o próprio Gmail e tocou em "Ligar" (_Config login_google = sim);
#   3. não é a demonstração.
# Até lá, tudo continua pela trava por aparelho. Se um dia o Google der problema: tirar o [auth]
# dos Secrets volta o app para a trava por aparelho na hora (ninguém fica trancado do lado de fora).
# Teste no PC sem Google: COBRANCA_LOGIN_TESTE=1 troca o Google por um campo de e-mail.

def _login_teste() -> bool:
    return bool(os.environ.get("COBRANCA_LOGIN_TESTE"))


def _auth_secrets():
    try:
        return st.secrets.get("auth")
    except Exception:
        return None


def _provedor():
    """'google' quando a chave está em [auth.google]; None quando está direto em [auth]."""
    auth = _auth_secrets()
    try:
        return "google" if auth and auth.get("google") else None
    except Exception:
        return None


def _login_configurado() -> bool:
    if _modo_demo():
        return False
    if _login_teste():
        return True
    auth = _auth_secrets()
    try:
        return bool(auth and (auth.get("client_id") or (auth.get("google") or {}).get("client_id")))
    except Exception:
        return False


def _login_ligado() -> bool:
    return _login_configurado() and login_google_ligado(_config())


def _email_google() -> str:
    """Gmail com que a pessoa entrou ('' se não entrou)."""
    if _login_teste():
        return st.session_state.get("_email_teste", "")
    try:
        return normalizar_email(st.user.email) if st.user.is_logged_in else ""
    except Exception:
        return ""


def _botao_google(rotulo: str, chave: str):
    """Botão que leva para a tela do Google. No teste do PC, um campo de e-mail faz o papel do Google."""
    if _login_teste():
        email = st.text_input("E-mail do Google (teste)", key=f"{chave}_email")
        if st.button(rotulo, key=chave, type="primary", icon=":material/login:", use_container_width=True):
            st.session_state["_email_teste"] = normalizar_email(email)
            st.rerun()
        return
    if st.button(rotulo, key=chave, type="primary", icon=":material/login:", use_container_width=True):
        st.login(_provedor())


def _sair_google():
    st.session_state.pop("_quem", None)
    if _login_teste():
        st.session_state.pop("_email_teste", None)
        st.rerun()
    st.logout()


def _identificado_google() -> bool:
    """Com a entrada com Google ligada: quem é sai do Gmail (conferido a cada tela, então tirar o
    Gmail de alguém em Configurações vale na hora)."""
    email = _email_google()
    if email:
        nome = pessoa_do_email(_config(), email)
        if nome:
            st.session_state["_quem"] = nome
            return True
    st.session_state.pop("_quem", None)
    st.markdown("<div class='hm-marca' style='margin-top:.8rem'>Cobranças</div>", unsafe_allow_html=True)
    if email:
        adm = _e(administrador(_config()))
        _info(f"O Gmail <b>{_e(email)}</b> não tem acesso a este app. Peça para <b>{adm}</b> colocar o "
              "seu Gmail em <b>Configurações</b>.", "cx-perigo")
        if st.button("Entrar com outro Gmail", key="gg_outro", icon=":material/switch_account:",
                     use_container_width=True):
            _sair_google()
        return False
    st.markdown("<div class='cx-sub'>Entre com o seu Gmail. Vale em qualquer celular ou computador.</div>",
                unsafe_allow_html=True)
    _botao_google("Entrar com Google", "gg_entrar")
    return False


def _identificado() -> bool:
    """True se já se sabe quem está usando; senão mostra a tela certa e devolve False."""
    if _banco() is not None and _login_ligado():
        return _identificado_google()
    if _banco() is None:
        return True   # sem planilha configurada: a tela inicial mostra o erro
    travado = _travado()
    quem = st.session_state.get("_quem")
    if quem and not travado:
        return True   # demonstração: sem trava

    aparelho = _aparelho()
    if not aparelho:
        st.markdown("<div class='dev-espera cx-sub' style='margin-top:1.2rem'>Preparando este aparelho…</div>",
                    unsafe_allow_html=True)
        _script_aparelho()
        return False
    if st.query_params.get("a") != aparelho:
        st.query_params["a"] = aparelho     # o atalho salvo depois disso já leva o código

    cfg = _config()
    trocando = st.session_state.get("_trocando")
    nome = nome_do_aparelho(cfg, aparelho)
    if quem:
        # Conferido a cada toque (auditoria de 04/11), como já é com o Google: pessoa removida ou
        # aparelho desligado em Configurações sai na hora, mesmo com a página aberta
        if nome == quem and not trocando:
            return True
        st.session_state.pop("_quem", None)
    if nome and not trocando:
        st.session_state["_quem"] = nome
        return True

    pessoas = pessoas_da_config(cfg)
    if travado and not pessoas and isinstance(_banco(), Planilha) and not _segredo("primeiro_acesso"):
        # Planilha de verdade sem a lista de pessoas = _Config sumiu ou foi apagada. Não abre o
        # "primeiro cadastro" (quem abrisse viraria administrador; auditoria de 04/11). Planilha NOVA
        # de propósito (ex.: cópia para franqueado): pôr primeiro_acesso = true nos Secrets e tirar depois.
        st.markdown("<div class='hm-marca' style='margin-top:.8rem'>Cobranças</div>", unsafe_allow_html=True)
        _info("Não achei a lista de pessoas do app na planilha (aba <b>_Config</b>). Avise o Pedro.", "cx-perigo")
        return False
    por_codigo = travado and liberacao_por_codigo(cfg)
    livres = nomes_livres(cfg, aparelho) if travado else pessoas
    # Atalho antigo, de antes da trava (?quem=Nome): entra direto e já prende o aparelho
    pedido = chave_busca(st.query_params.get("quem", ""))
    do_atalho = next((p for p in livres if pedido and chave_busca(p) == pedido), None)
    if do_atalho and not trocando:
        _prender(aparelho, do_atalho, pessoas)
        return False

    st.markdown("<div class='hm-marca' style='margin-top:.8rem'>Quem está usando?</div>", unsafe_allow_html=True)
    if travado and pessoas:
        st.markdown("<div class='cx-sub'>Escolha o seu nome. Este aparelho fica ligado a ele e não dá "
                    "para trocar depois.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='cx-sub'>Fica registrado quem cadastrou cada cobrança e quem marcou "
                    "cada pagamento.</div>", unsafe_allow_html=True)
    for i, p in enumerate(livres):
        if st.button(p, key=f"quem_{i}", icon=":material/person:", use_container_width=True):
            _prender(aparelho, p, pessoas)

    if not travado or not pessoas:
        # Demonstração, ou a primeiríssima pessoa do app (que vira a administradora)
        # Sem st.container(key=...) em volta: com a moldura, o Streamlit deixava uma cópia apagada
        # do campo e do botão por cima da tela inicial depois do st.rerun() (ferramentas/teste_fantasma.py).
        novo = st.text_input("Seu nome" if not pessoas else "Outra pessoa", key="quem_novo",
                             max_chars=MAX_NOME, placeholder="Ex.: Pedro")
        if st.button("Entrar", key="quem_entrar", type="primary", use_container_width=True,
                     icon=":material/login:"):
            if len(novo.strip()) < 2:
                _erro_campo("Digite o seu nome.")
            else:
                _prender(aparelho, novo, pessoas)
    else:
        adm = _e(administrador(cfg))
        if livres:
            _info(f"Seu nome não está na lista? Peça para <b>{adm}</b> liberar o seu acesso.", "cx-nota")
        else:
            if por_codigo:
                curto = _anotar_codigo(aparelho)
                _info(f"Este aparelho ainda não tem acesso. Mostre para <b>{adm}</b> o código "
                      f"<b class='cf-codigo'>{_e(curto)}</b>: em <b>Configurações</b>, no "
                      "seu nome, ele toca em <b>Liberar novo aparelho</b> e digita esse código.", "cx-perigo")
                if not aparelhos_por_pessoa(cfg).get(administrador(cfg)):
                    # Saída só para quando o próprio administrador está sem nenhum aparelho
                    st.markdown(f"<div class='cx-dica'>Administrador sem aparelho: na planilha, aba _Config, "
                                f"acrescente a linha <b>liberado:{adm}</b> com o valor <b>{_e(aparelho)}</b>."
                                "</div>", unsafe_allow_html=True)
            else:
                _info(f"Este aparelho ainda não tem acesso. Peça para <b>{adm}</b> liberar o seu nome "
                      "em <b>Configurações</b> e abra o app de novo.", "cx-perigo")
            if st.button("Já liberaram, tentar de novo", key="quem_denovo", icon=":material/refresh:",
                         use_container_width=True):
                # Relê a configuração no máximo a cada 20 s por aparelho (tocar sem parar não gasta a
                # cota de leitura do Google de todo mundo)
                if _pode_limpar_cache():
                    _ler_config.clear()
                st.rerun()
    return False


# ── Configurações (só o administrador) ────────────────────────────────────────

ACESSOS_TELA = ["Tudo", "Só Jurídico"]   # opções de acesso de cada pessoa (Configurações)


def _config_varias(pares: dict) -> bool:
    try:
        for chave, valor in pares.items():
            _banco().save_config(chave, valor)
        _ler_config.clear()
        return True
    except Exception as e:
        _ler_config.clear()
        st.error(f"Não consegui salvar: {_erro_curto(e)}")
        return False


def _salvar_email(pessoa: str, email: str, chave_erro: str) -> bool:
    """Liga o Gmail à pessoa (vazio = tira). Confere se é e-mail e se ninguém mais usa."""
    email = normalizar_email(email)
    cfg = _config()
    if email and not email_valido(email):
        st.session_state[chave_erro] = "Esse e-mail não parece certo. Ex.: nome@gmail.com"
        return False
    outro = dono_do_email(cfg, email, menos=pessoa) if email else ""
    if outro:
        st.session_state[chave_erro] = f"Esse Gmail já é de {outro}."
        return False
    st.session_state.pop(chave_erro, None)
    return _config_varias({f"email:{pessoa}": email})


def _secao_google(cfg: dict, adm: str):
    """O teste e o botão de ligar a entrada com Google (só aparece com a chave nos Secrets)."""
    ligado = login_google_ligado(cfg)
    emails = emails_por_pessoa(cfg)
    meu = emails.get(adm, "")
    logado = _email_google()
    with st.container(key="sec_cf_google"):
        _titulo_secao("G", "Entrada com Google")
        if ligado:
            _info("<b>Ligada.</b> Cada pessoa entra com o próprio Gmail, em qualquer celular ou computador. "
                  "Para tirar o acesso de alguém, apague o Gmail dela abaixo.", "cx-ok")
            sem = [p for p, e in emails.items() if not e]
            if sem:
                _info(f"Sem Gmail (não conseguem entrar): <b>{_e(', '.join(sem))}</b>.", "cx-falta")
            if pessoas_restritas(cfg):
                _info("Com alguém em <b>Só Jurídico</b>, a entrada com Google não pode ser desligada: "
                      "só ela garante quem é quem.", "cx-nota")
            elif st.button("Desligar e voltar para a trava por aparelho", key="cf_gg_desligar",
                           icon=":material/phonelink_lock:", type="tertiary"):
                if _config_varias({"login_google": ""}):
                    _flash("Entrada com Google desligada: o app volta a reconhecer cada aparelho")
                    st.rerun()
            return
        _info("<b>Desligada.</b> Hoje o app reconhece cada aparelho. Com a entrada com Google, cada pessoa "
              "entra com o próprio Gmail, em qualquer aparelho.", "cx-nota")
        if not meu:
            _info("1. Coloque abaixo o Gmail de cada pessoa, começando pelo seu.", "cx-info")
            return
        if not logado:
            _info(f"Teste com o seu Gmail (<b>{_e(meu)}</b>). Depois de entrar no Google, volte a esta tela.",
                  "cx-info")
            _botao_google("Testar com o Google", "cf_gg_testar")
            return
        if logado != meu:
            _info(f"O Google confirmou o Gmail <b>{_e(logado)}</b>, mas o seu aqui é <b>{_e(meu)}</b>. "
                  "Entre com o Gmail certo.", "cx-perigo")
            if st.button("Entrar com outro Gmail", key="cf_gg_outro", icon=":material/switch_account:",
                         use_container_width=True):
                _sair_google()
            return
        _info(f"<b>Deu certo:</b> o Google confirmou que você é <b>{_e(logado)}</b>.", "cx-ok")
        sem = [p for p, e in emails.items() if not e]
        if sem:
            _info(f"Ainda sem Gmail: <b>{_e(', '.join(sem))}</b>. Quem ficar sem não consegue entrar depois "
                  "de ligar.", "cx-falta")
        if st.button("Ligar entrada com Google para todos", key="cf_gg_ligar", type="primary",
                     icon=":material/verified_user:", use_container_width=True):
            if _config_varias({"login_google": "sim"}):
                _flash("Entrada com Google ligada")
                st.rerun()


def tela_config():
    _cabecalho("Configurações", voltar_para="inicio", subtitulo="Quem usa o app e como entra")
    if not _sou_admin():
        st.info("Só o administrador do app abre esta tela.")
        return
    cfg = _config()
    pessoas = pessoas_da_config(cfg)
    presos = aparelhos_por_pessoa(cfg)
    adm = administrador(cfg)
    com_google = _login_configurado()
    ligado = com_google and login_google_ligado(cfg)
    emails = emails_por_pessoa(cfg)
    por_codigo = liberacao_por_codigo(cfg)

    if com_google:
        _secao_google(cfg, adm)
    if por_codigo and not ligado:
        _info("Celular novo: a pessoa abre o app e vê um <b>código de 6 letras</b>. Toque em <b>Liberar novo "
              "aparelho</b> no nome dela e digite esse código. Só aquele aparelho entra.", "cx-falta")

    for i, p in enumerate(pessoas):
        n = len(presos[p])
        liberado = bool(str(cfg.get(f"liberado:{p}", "")).strip())
        if ligado:
            estado = ("<span class='sit c-ok'>Com Gmail</span>" if emails[p]
                      else "<span class='sit c-atraso'>Sem Gmail</span>")
        elif liberado:
            cod = str(cfg.get(f"liberado:{p}", "")).strip()
            estado = ("<span class='sit c-breve'>Liberado para 1 aparelho novo"
                      + (f" ({_e(codigo_aparelho(cod))})" if cod.lower() != "sim" else "") + "</span>")
        elif n:
            estado = f"<span class='sit c-ok'>{n} aparelho{'s' if n > 1 else ''}</span>"
        else:
            estado = "<span class='sit c-neutro'>Ainda não entrou</span>"
        restrita = so_juridico(cfg, p)
        telegram = ("Telegram conectado" + (" (só avisos do Jurídico)" if restrita else "")
                    if cfg.get(f"telegram:{p}") else "Sem Telegram")
        with st.container(key=f"sec_cf_{i}"):
            st.markdown(f"<div class='nt-pessoa'><span>{_e(p)}{' · administrador' if p == adm else ''}</span>{estado}</div>"
                        f"<div class='cf-meta'>{telegram}</div>", unsafe_allow_html=True)
            # Acesso (pedido 04/11): tudo, ou só o Jurídico. O administrador sempre tem tudo.
            if p != adm:
                atual = ACESSOS_TELA[1] if restrita else ACESSOS_TELA[0]
                escolha = st.segmented_control(f"Acesso de {p}", ACESSOS_TELA, default=atual,
                                               key=f"cf_acesso_{i}_{atual}")
                if escolha and escolha != atual:
                    pares = {f"acesso:{p}": ACESSO_JURIDICO if escolha == ACESSOS_TELA[1] else ""}
                    if escolha == ACESSOS_TELA[1]:
                        pares["liberacao_por_codigo"] = "sim"
                    if _config_varias(pares):
                        _flash(f"{p}: " + ("agora só vê o Jurídico" if escolha == ACESSOS_TELA[1]
                                           else "agora vê tudo"))
                        st.rerun()
                # Pessoa de confiança (pedido 04/11): sem o limite de gravações seguidas
                if restrita:
                    sem_lim = chave_busca(cfg.get(f"sem_limite:{p}", "")) == "sim"
                    marcado = st.checkbox("Sem limite de gravações (pessoa de confiança)", value=sem_lim,
                                          key=f"cf_semlim_{i}_{sem_lim}",
                                          help="Desmarcado: no máximo 3 gravações por minuto, 20 a cada 10 minutos "
                                               "e 60 por dia.")
                    if marcado != sem_lim and _config_varias({f"sem_limite:{p}": "sim" if marcado else ""}):
                        _flash(f"{p}: " + ("sem limite de gravações" if marcado else "com limite de gravações"))
                        st.rerun()
            if com_google:
                erro = f"_cf_email_erro_{i}"
                if ligado and p == adm:
                    # Com a entrada ligada, o administrador não troca o próprio Gmail (ficaria do lado de fora)
                    st.markdown(f"<div class='cf-meta'>Gmail: <b>{_e(emails[p])}</b> (para trocar, desligue a "
                                "entrada com Google antes)</div>", unsafe_allow_html=True)
                else:
                    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
                    with c1:
                        novo = st.text_input(f"Gmail de {p}", value=emails[p], key=f"cf_email_{i}_{emails[p]}",
                                             placeholder="nome@gmail.com", max_chars=80)
                    with c2:
                        if st.button("Salvar", key=f"cf_email_ok_{i}", use_container_width=True):
                            if normalizar_email(novo) != emails[p] and _salvar_email(p, novo, erro):
                                _flash(f"Gmail de {p} salvo" if novo.strip() else f"Gmail de {p} apagado")
                                st.rerun()
                    if st.session_state.get(erro):
                        _erro_campo(st.session_state[erro])
            if not ligado:
                c1, c2 = st.columns(2)
                with c1:
                    # Com liberação por código (existe ou existiu alguém Só Jurídico): libera SÓ o aparelho
                    # que mostrar esse código (ver nucleo.nomes_livres)
                    if por_codigo and not liberado:
                        cod = st.text_input(f"Código do aparelho de {p}", key=f"cf_cod_{i}", max_chars=6,
                                            placeholder="Ex.: A1B2C3",
                                            help="O código de 6 letras que aparece no aparelho novo.")
                        if st.button("Liberar novo aparelho", key=f"cf_lib_{i}", icon=":material/add_to_home_screen:",
                                     use_container_width=True):
                            cod = "".join(ch for ch in cod.upper() if ch in "0123456789ABCDEF")
                            completo = _codigos_pendentes().get(cod, (None, 0))[0] if len(cod) == 6 else None
                            if not completo:
                                _erro_campo("Código não encontrado. Peça para a pessoa abrir o app no aparelho "
                                            "novo e ler o código que aparece agora.")
                            elif _config_varias({f"liberado:{p}": completo}):
                                _codigos_pendentes().pop(cod, None)
                                _flash(f"{p} pode entrar no aparelho {cod}")
                                st.rerun()
                    elif n and not liberado and st.button("Liberar novo aparelho", key=f"cf_lib_{i}",
                                                          icon=":material/add_to_home_screen:", use_container_width=True):
                        if _config_varias({f"liberado:{p}": "sim"}):
                            _flash(f"{p} pode escolher o nome em mais um aparelho")
                            st.rerun()
                    if liberado and st.button("Cancelar liberação", key=f"cf_canc_{i}", icon=":material/block:",
                                              use_container_width=True):
                        if _config_varias({f"liberado:{p}": ""}):
                            st.rerun()
                with c2:
                    # O administrador não desliga o próprio aparelho (ficaria sem a tela de Configurações)
                    if n and p != adm and st.button("Desligar aparelhos", key=f"cf_des_{i}",
                                                    icon=":material/phonelink_erase:", use_container_width=True,
                                                    help="Os aparelhos dessa pessoa perdem o acesso; o nome fica livre para ela escolher de novo."):
                        if _config_varias({f"aparelho:{a}": "" for a in presos[p]}):
                            _flash(f"Aparelhos de {p} desligados")
                            st.rerun()
            if p != adm and st.button(f"Remover {p}", key=f"cf_rem_{i}", type="tertiary", icon=":material/person_remove:"):
                st.session_state["_cf_remover"] = p
                st.rerun()

    alvo = st.session_state.get("_cf_remover")
    if alvo in pessoas and alvo != adm:
        _info(f"Remover <b>{_e(alvo)}</b>? Os aparelhos, o Gmail e o Telegram dessa pessoa são desligados. "
              "O que ela já registrou continua com o nome dela.", "cx-perigo")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Não", key="cf_rem_nao", use_container_width=True):
                st.session_state.pop("_cf_remover", None)
                st.rerun()
        with c2:
            if st.button("Sim, remover", key="cf_rem_sim", use_container_width=True):
                pares = {"pessoas": ", ".join(x for x in pessoas if x != alvo), f"telegram:{alvo}": "",
                         f"liberado:{alvo}": ""}
                if cfg.get(f"acesso:{alvo}"):
                    pares[f"acesso:{alvo}"] = ""
                if cfg.get(f"sem_limite:{alvo}"):
                    pares[f"sem_limite:{alvo}"] = ""
                if cfg.get(f"email:{alvo}"):
                    pares[f"email:{alvo}"] = ""
                pares.update({f"aparelho:{a}": "" for a in presos[alvo]})
                st.session_state.pop("_cf_remover", None)
                if _config_varias(pares):
                    _flash(f"{alvo} removida do app")
                    st.rerun()

    with st.container(key="sec_cf_nova"):
        _titulo_secao(len(pessoas) + 1, "Adicionar pessoa")
        novo = st.text_input("Nome", key="cf_novo", max_chars=MAX_NOME, placeholder="Ex.: Gabi")
        gmail = (st.text_input("Gmail", key="cf_novo_email", max_chars=80, placeholder="nome@gmail.com",
                               help="O Gmail com que ela vai entrar no app.")
                 if com_google else "")
        acesso_novo = st.segmented_control("Acesso", ACESSOS_TELA, default=None, key="cf_novo_acesso",
                                           help="Só Jurídico: a pessoa vê só as cobranças judiciais e os "
                                                "protestos. Nada de cobranças, relatório, avisos ou configurações.")
        if st.button("Adicionar", key="cf_add", type="primary", icon=":material/person_add:",
                     use_container_width=True):
            nome = " ".join(novo.replace(",", " ").replace(":", " ").split())
            gmail = normalizar_email(gmail)
            if len(nome) < 2:
                _erro_campo("Digite o nome.")
            elif any(chave_busca(x) == chave_busca(nome) for x in pessoas):
                _erro_campo("Já existe uma pessoa com esse nome.")
            elif ligado and not gmail:
                _erro_campo("Com a entrada com Google ligada, a pessoa precisa de um Gmail para entrar.")
            elif gmail and not email_valido(gmail):
                _erro_campo("Esse e-mail não parece certo. Ex.: nome@gmail.com")
            elif gmail and dono_do_email(cfg, gmail):
                _erro_campo(f"Esse Gmail já é de {dono_do_email(cfg, gmail)}.")
            elif acesso_novo not in ACESSOS_TELA:
                _erro_campo("Escolha o acesso: Tudo ou Só Jurídico.")
            else:
                pares = {}
                # Acesso gravado ANTES do nome entrar na lista: a pessoa nunca existe, nem por um instante,
                # com acesso a tudo
                if acesso_novo == ACESSOS_TELA[1]:
                    pares[f"acesso:{nome}"] = ACESSO_JURIDICO
                    pares["liberacao_por_codigo"] = "sim"
                elif cfg.get(f"acesso:{nome}"):
                    pares[f"acesso:{nome}"] = ""   # sobra de alguém removido com o mesmo nome
                if gmail:
                    pares[f"email:{nome}"] = gmail
                pares["pessoas"] = ", ".join(pessoas + [nome])
                if _config_varias(pares):
                    for k in ("cf_novo", "cf_novo_email", "cf_novo_acesso"):
                        st.session_state.pop(k, None)
                    _flash(f"{nome} adicionada com acesso {acesso_novo}. "
                           + ("Peça para ela entrar com esse Gmail." if ligado
                                                     else "Peça para ela abrir o app e escolher o nome."))
                    st.rerun()
    if ligado:
        _info("Cada pessoa entra com o próprio Gmail, em qualquer aparelho. Para tirar o acesso de alguém, "
              "apague o Gmail dela ou remova a pessoa.", "cx-nota")
    else:
        _info("Quando a pessoa abre o app pela primeira vez, ela escolhe o nome e aquele aparelho fica preso "
              "nele. Se trocar de celular, toque em <b>Liberar novo aparelho</b>.", "cx-nota")


# ── Nova cobrança: escolher o tipo ────────────────────────────────────────────

def tela_nova():
    _cabecalho("Nova cobrança", voltar_para="inicio", subtitulo="Como o cliente vai pagar?")
    if _cartao_inicio("hm_pix", "tq_pix", "Cobrança Pix", "claro", SVG_PIX,
                      "Cobrança Pix", "Entrada + parcelas por mês"):
        _limpar_campos("px_")
        _ir("pix")
    if _cartao_inicio("hm_cartao", "tq_cartao", "Cobrança cartão", "claro", SVG_CARTAO,
                      "Cobrança cartão", "Uma ou mais datas para passar o cartão"):
        _limpar_campos("ct_")
        _ir("cartao")
    if _cartao_inicio("hm_hibrido", "tq_hibrido", "Cobrança híbrida", "claro", SVG_HIBRIDO,
                      "Cobrança híbrida", "Juntar Pix, cartão e permuta"):
        _limpar_campos("hb_")
        _ir("hibrido")
    if _cartao_inicio("hm_permuta", "tq_permuta", "Permuta", "claro", SVG_PERMUTA,
                      "Permuta", "Treinamento em troca de produtos ou serviços"):
        _limpar_campos("pm_")
        _ir("permuta")


MAX_TURMAS = 6


def _mais_uma_turma(prefixo: str):
    st.session_state[f"{prefixo}n_turmas"] = min(st.session_state.get(f"{prefixo}n_turmas", 1) + 1, MAX_TURMAS)


def _tirar_turma(prefixo: str, i: int):
    """Tira a i-ésima turma extra e sobe as de baixo (roda antes da tela, por isso pode mexer nos campos)."""
    n = st.session_state.get(f"{prefixo}n_turmas", 1)
    for j in range(i, n - 1):
        st.session_state[f"{prefixo}turma_{j}"] = st.session_state.get(f"{prefixo}turma_{j + 1}", "")
    st.session_state.pop(f"{prefixo}turma_{n - 1}", None)
    st.session_state[f"{prefixo}n_turmas"] = max(n - 1, 1)


CHAVE_TEL = "telefone__tel"   # o fim "__tel" faz o script _JS_CAMPOS abrir o teclado de telefone


def _usar_telefone(prefixo: str, tel: str):
    st.session_state[f"{prefixo}{CHAVE_TEL}"] = tel


def _bloco_cliente(prefixo: str, numero: int = 1):
    """
    Cliente + turma(s): o treinamento sai da letra de cada turma. A cobrança pode valer para mais
    de uma turma (pedido 16/10): o botão "Adicionar outra turma" abre mais um campo embaixo.
    Devolve (cliente, turma, treino, erros), com turma e treino já como vão para a planilha
    ("L345" e "LORAP", ou "L345, V12" e "LORAP, Vendas").
    """
    _titulo_secao(numero, "Cliente")
    cliente = st.text_input("Nome do cliente", key=f"{prefixo}cliente").strip()
    turmas, erros = [], []
    # Telefone opcional (pedido 26/10), para facilitar falar com a pessoa. Vai junto no
    # _salvar, lido de st.session_state[f"{prefixo}{CHAVE_TEL}"].
    tel = st.text_input("Telefone (opcional)", key=f"{prefixo}{CHAVE_TEL}", max_chars=25,
                        placeholder="Ex.: (51) 99999-8888", help="Para ligar ou chamar no WhatsApp pela ficha.")
    if not telefone_valido(tel):
        _erro_campo("Telefone incompleto. Ex.: (51) 99999-8888, ou deixe em branco.")
        erros.append("Telefone incompleto (ou deixe em branco).")
    elif not tel.strip():
        de_outra = telefone_do_cliente(_cobrancas() or [], cliente)
        if de_outra:
            st.markdown(f"<div class='cx-dica'>Outra cobrança de {_e(cliente.upper())} tem o telefone "
                        f"<b>{_e(de_outra)}</b>.</div>", unsafe_allow_html=True)
            st.button("Usar esse telefone", key=f"{prefixo}usar_tel", icon=":material/call:", type="tertiary",
                      on_click=_usar_telefone, args=(prefixo, de_outra))
    for i in range(st.session_state.get(f"{prefixo}n_turmas", 1)):
        if i == 0:
            txt = st.text_input("Turma", key=f"{prefixo}turma", placeholder="Ex.: L345",
                                help="Letra do treinamento + número. L = LORAP, V = Vendas, "
                                     "I = Impacto, P = Perfil. L00345 e l345 dão no mesmo.")
        else:
            c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
            with c1:
                txt = st.text_input(f"{i + 1}ª turma", key=f"{prefixo}turma_{i}", placeholder="Ex.: V12")
            with c2:
                st.button("Tirar", key=f"{prefixo}tirar_{i}", icon=":material/close:", help="Tirar esta turma",
                          on_click=_tirar_turma, args=(prefixo, i), use_container_width=True)
        achadas = normalizar_turmas(txt)
        if achadas:
            _info(" &nbsp;·&nbsp; ".join(f"Turma <b>{t}</b> · {TREINAMENTOS[t[0]]}" for t in achadas))
            turmas += [t for t in achadas if t not in turmas]
        elif achadas is None:
            _erro_campo("Comece pela letra do treinamento (L, V, I ou P) e depois o número. Ex.: L345")
            erros.append("Tem turma escrita errado (ex.: L345).")
    if st.session_state.get(f"{prefixo}n_turmas", 1) < MAX_TURMAS:
        st.button("Adicionar outra turma", key=f"{prefixo}mais_turma", icon=":material/add:", type="tertiary",
                  on_click=_mais_uma_turma, args=(prefixo,))
    # Cidade: texto livre e opcional (vai junto no _salvar, lida de st.session_state[f"{prefixo}cidade"])
    st.text_input("Cidade da turma", key=f"{prefixo}cidade", max_chars=40, placeholder="Ex.: Lajeado, SCS…",
                  help="Opcional. Escreva do jeito que quiser.")
    ja_usada = cidade_da_turma(_cobrancas() or [], turmas[0]) if turmas else ""
    if ja_usada and not st.session_state.get(f"{prefixo}cidade", "").strip():
        st.markdown(f"<div class='cx-dica'>Outras cobranças da turma {_e(turmas[0])} estão como "
                    f"<b>{_e(ja_usada)}</b>.</div>", unsafe_allow_html=True)
    if not turmas and not erros:   # (turma escrita errado já tem o seu aviso)
        erros.append("Falta a turma (ex.: L345).")
    if not cliente:
        erros.insert(0, "Falta o nome do cliente.")
    return (cliente, SEP_TURMAS_PLANILHA.join(turmas),
            SEP_TURMAS_PLANILHA.join(treinamentos_das_turmas(turmas)), erros)


def _bloco_conferencia(total, partes, prefixo: str) -> bool:
    """Mostra se as partes fecham com o total. Devolve False se não fecha e não foi confirmado."""
    if total is None:
        return True
    dif = conferir_total(total, partes)
    brl = lambda v: formatar_brl(v).replace(" ", "&nbsp;")   # "R$" nunca sozinho no fim da linha
    if abs(dif) < 0.005:
        _info(f"<b>Fecha certinho</b> com o total de {brl(total)}.", "cx-ok")
        return True
    # Cada caso com a sua cor (pedido 21/10): faltando = laranja forte, passando = vermelho forte
    if dif > 0:
        _info(f"Faltam <b>{brl(dif)}</b> para chegar no total de {brl(total)}.", "cx-falta")
    else:
        _info(f"Passa <b>{brl(-dif)}</b> do total de {brl(total)}.", "cx-passa")
    return st.checkbox("Está certo assim, salvar mesmo com a diferença", key=f"{prefixo}aceito_dif")


# ── Gravação que não se perde nem duplica (problema de 05/11/2026) ────────────
# O que acontecia: gravar uma cobrança leva alguns segundos (vários pedidos ao Google) e a tela não
# mostrava nada. Se a pessoa tocasse em qualquer coisa nesse meio tempo (de novo em Salvar, Voltar...),
# o Streamlit começa NA HORA uma rodada nova, e a antiga, que estava gravando, é derrubada assim que
# encosta no session_state. A gravação terminava (a cobrança ENTRAVA na planilha), mas a tela não ia para
# a ficha, a leitura guardada não era limpa (o relatório não mostrava) e a trava "_salvando" ficava ligada
# para sempre: todo Salvar seguinte não fazia NADA, sem aviso, até fechar o app. A pessoa redigitava e a
# cobrança ficava repetida. Agora:
#   1. a gravação roda sem st.* e sem session_state; o desfecho fica num "pedido" guardado ANTES, e a
#      rodada que estiver valendo (a mesma ou uma nova) espera a gravação terminar e mostra o desfecho;
#   2. o mesmo conteúdo tem sempre o mesmo ID (_id_da_gravacao): nova tentativa nunca duplica;
#   3. erro na gravação → confere na planilha, pelo ID, se entrou mesmo assim;
#   4. a leitura guardada é limpa sempre, com ou sem erro; 5. aviso "Salvando..." enquanto grava.

ESPERA_PELA_GRAVACAO = 150   # segundos que uma rodada nova espera a gravação em andamento terminar
ID_NOVO_VALE_POR = 30 * 60   # segundos em que o mesmo conteúdo digitado de novo reaproveita o ID


class _NaoAchei(Exception):
    """A gravação não achou o registro (alteração de algo que sumiu da planilha): nada foi gravado."""


@st.cache_resource(show_spinner=False)
def _memoria_gravacoes() -> dict:
    """Comum a todas as sessões: {"trava", "ids": {assinatura: (id, quando)}, "travas": {id: trava}}."""
    return {"trava": threading.Lock(), "ids": {}, "travas": {}}


def _trava_do_id(rid: str):
    """O mesmo registro nunca é gravado por duas rodadas (ou duas pessoas) ao mesmo tempo."""
    mem = _memoria_gravacoes()
    with mem["trava"]:
        return mem["travas"].setdefault(rid, threading.Lock())


def _id_da_gravacao(*conteudo):
    """
    O MESMO conteúdo (mesmos campos, mesmas parcelas, mesma pessoa, mesmo dia) ganha sempre o mesmo ID
    por 30 minutos, em qualquer sessão: tocar em Salvar de novo, ou redigitar igual depois de o celular
    recarregar a página, cai na mesma cobrança, que já está gravada, em vez de criar outra.
    Devolve (id, trava do id).
    """
    texto = json.dumps(conteudo, sort_keys=True, default=str, ensure_ascii=False)
    chave = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    mem = _memoria_gravacoes()
    agora = time.monotonic()
    with mem["trava"]:
        for k, (rid, quando) in list(mem["ids"].items()):
            if agora - quando > ID_NOVO_VALE_POR:
                del mem["ids"][k]
                trava = mem["travas"].get(rid)
                if trava is not None and not trava.locked():
                    del mem["travas"][rid]
        if chave not in mem["ids"]:
            mem["ids"][chave] = (novo_id(), agora)
        rid = mem["ids"][chave][0]
        return rid, mem["travas"].setdefault(rid, threading.Lock())


def _esquecer_id(rid: str):
    """Excluiu: o mesmo conteúdo cadastrado de novo vira um registro novo (não reaproveita o excluído)."""
    mem = _memoria_gravacoes()
    with mem["trava"]:
        for k in [k for k, (r, _) in mem["ids"].items() if r == rid]:
            del mem["ids"][k]


def _aviso_salvando(texto: str):
    """Aviso fixo no pé da tela enquanto grava (antes a tela não mostrava nada e a pessoa tocava de novo)."""
    lugar = st.empty()
    lugar.markdown(f"<div class='cx-salvando'><span class='cx-salvando-roda'></span>{_e(texto)}</div>",
                   unsafe_allow_html=True)
    return lugar


def _conferir_se_entrou(conferir):
    """Depois de um erro: a gravação entrou na planilha mesmo assim? True/False; None = não deu para saber."""
    if conferir is None:
        return None
    resposta = None
    for espera in (0, 2, 4):
        time.sleep(espera)
        try:
            if conferir():
                return True
            resposta = False
        except Exception as e:
            print(f"[erro] conferindo a gravação: {e!r}", flush=True)
    return resposta


def _executar_gravacao(pedido: dict, trava, gravar, conferir):
    """
    A gravação em si. NADA de st.* nem de session_state aqui dentro: se a pessoa tocou em algo no meio,
    esta rodada já foi derrubada e qualquer toque no session_state pararia tudo no meio do caminho.
    """
    try:
        with trava:
            try:
                pedido["id"] = gravar() or pedido["id"]
                pedido["deu_certo"] = True
            except _NaoAchei as e:
                pedido["erro"], pedido["deu_certo"] = e, False
            except Exception as e:
                print(f"[erro] gravação {pedido['id']}: {e!r}", flush=True)
                pedido["erro"] = e
                pedido["deu_certo"] = _conferir_se_entrou(conferir)
    finally:
        _invalidar()   # a leitura guardada é limpa SEMPRE (antes, erro aqui deixava o relatório velho)
        pedido["pronto"].set()


def _texto_nao_salvou(pedido: dict) -> str:
    erro = pedido.get("erro")
    if isinstance(erro, _NaoAchei):
        return str(erro)
    if pedido.get("deu_certo") is False:
        texto = "Não salvou: nada foi gravado. Confira a internet e toque em Salvar de novo."
    else:
        texto = ("Não deu para confirmar se salvou (a planilha do Google não respondeu). Toque em Salvar "
                 "de novo: se já tinha salvo, não fica repetido.")
    if erro is not None and _sou_admin_sem_ler():
        texto += f" Detalhe: {str(erro)[:180]}"
    return texto


def _aplicar_gravacao(pedido: dict) -> bool:
    """Mostra o desfecho de uma gravação UMA vez, na rodada que estiver valendo. True = trocou de tela."""
    with pedido["trava"]:
        if pedido["aplicado"] or not pedido["pronto"].is_set():
            return False
        ss = st.session_state
        if ss.get("_gravacao") is pedido:
            del ss["_gravacao"]
        if pedido["deu_certo"]:
            _limpar_campos(pedido["prefixo"])
            for chave, valor in pedido["ok"].get("estado", {}).items():
                ss[chave] = pedido["id"] if valor == "{id}" else valor
            _flash(pedido["ok"]["flash"])
            ss.tela = pedido["ok"]["tela"]
        elif ss.get("tela") == pedido["tela_form"]:
            ss["_erro_salvar"] = (pedido["prefixo"], _texto_nao_salvou(pedido))   # embaixo do Salvar
        else:
            _flash(_texto_nao_salvou(pedido), "⚠️")   # a pessoa já saiu do formulário
        pedido["aplicado"] = True
        return bool(pedido["deu_certo"])


def _gravar_sem_perder(prefixo: str, rid: str, trava, gravar, conferir, ok: dict, aviso: str):
    """
    Grava e mostra o desfecho, mesmo que a pessoa toque em outra coisa no meio.
      gravar()   grava (sem st.* e sem session_state) e devolve o ID gravado
      conferir() depois de um erro, diz se a gravação entrou mesmo assim; None = não dá para conferir
      ok         {"tela", "flash", "estado": {chave: valor}} quando deu certo ("{id}" vira o ID gravado)
    """
    lugar = _aviso_salvando(aviso)
    st.session_state.pop("_erro_salvar", None)
    pedido = {"prefixo": prefixo, "tela_form": st.session_state.get("tela"), "ok": ok, "id": rid,
              "deu_certo": None, "erro": None, "pronto": threading.Event(), "trava": threading.Lock(),
              "aplicado": False}
    # Último toque no session_state ANTES de gravar: daqui até o fim da gravação esta rodada não para
    st.session_state["_gravacao"] = pedido
    _executar_gravacao(pedido, trava, gravar, conferir)
    lugar.empty()   # se a pessoa tocou em algo no meio, esta rodada para aqui e a nova mostra o desfecho
    if _aplicar_gravacao(pedido):
        st.rerun()


def _esperar_gravacao_em_andamento():
    """
    No começo de toda rodada: se uma gravação começou numa rodada que foi interrompida (a pessoa tocou em
    algo no meio), espera ela terminar e mostra o desfecho (a ficha do que foi salvo, ou o aviso de que
    não salvou). Antes, esse desfecho se perdia.
    """
    pedido = st.session_state.get("_gravacao")
    if not pedido or pedido["aplicado"]:
        return
    if not pedido["pronto"].is_set():
        lugar = _aviso_salvando("Salvando…")
        pedido["pronto"].wait(ESPERA_PELA_GRAVACAO)
        lugar.empty()
        if not pedido["pronto"].is_set():
            _info("A planilha do Google está demorando para confirmar a gravação. Espere um pouco antes de "
                  "tentar de novo.", "cx-perigo")
            return
    if _aplicar_gravacao(pedido):
        st.rerun()


def _aviso_do_salvar(prefixo: str):
    """Embaixo do botão Salvar: o aviso de que a gravação NÃO deu certo (mesmo quando quem descobriu foi
    uma rodada nova, porque a pessoa tocou em algo no meio da gravação)."""
    erro = st.session_state.get("_erro_salvar")
    if erro and erro[0] == prefixo:
        del st.session_state["_erro_salvar"]
        st.error(erro[1])


def _salvar(tipo: str, cliente: str, turma: str, treino: str, total: float, parcelas: list, prefixo: str,
            observacoes: str = ""):
    campos = {
        # Tudo que se digita vai em MAIÚSCULA (pedido 16/10)
        "Tipo": tipo, "Cliente": cliente.upper(), "Turma": turma, "Treinamento": treino,
        "Valor Total": total, "Criada em": _hoje(), "Criada por": _usuario(),
        "Observações": observacoes.strip().upper(),
        "Cidade": " ".join(str(st.session_state.get(f"{prefixo}cidade", "")).split()).upper(),
        "Telefone": formatar_telefone(st.session_state.get(f"{prefixo}{CHAVE_TEL}", "")),
    }
    cid, trava = _id_da_gravacao("cobranca", campos, parcelas)
    banco = _banco()
    _gravar_sem_perder(
        prefixo, cid, trava,
        gravar=lambda: banco.criar_cobranca(campos, parcelas, cid=cid),
        conferir=lambda: banco.cobranca_existe(cid),
        ok={"tela": "cobranca", "flash": f"Cobrança de {cliente.upper()} salva",
            "estado": {"cob_id": "{id}", "cob_volta": "inicio"}},
        aviso="Salvando a cobrança…")


# ── Blocos do Pix e do cartão (as telas Pix, Cartão e Híbrida usam os mesmos) ──
# O `prefixo` separa as chaves dos campos: "px_" e "ct_" nas telas de uma forma só,
# "hb_px_" e "hb_ct_" na híbrida.

def _bloco_parcelas_pix(prefixo: str, restante: float, total, primeira_padrao: date, erros: list):
    """Quantas parcelas, o valor e o vencimento de cada uma (Contínuo ou Parcial).
    Devolve (valores, datas) e acrescenta em `erros` o que estiver faltando."""
    valores, datas = [], []
    n = st.number_input("Número de parcelas", min_value=1, value=None, step=1,
                        key=f"{prefixo}n", placeholder="Ex.: 10")
    modo_valor = st.radio("Valor das parcelas", ["Contínuo", "Parcial"], horizontal=True,
                          key=f"{prefixo}mv", captions=["igual todo mês", "muda por mês"])
    modo_data = st.radio("Vencimento", ["Contínuo", "Parcial"], horizontal=True,
                         key=f"{prefixo}md", captions=["mesmo dia todo mês", "escolher cada data"])
    primeira = st.date_input("1º vencimento", value=primeira_padrao,
                             format="DD/MM/YYYY", key=f"{prefixo}primeira")
    if not n:
        erros.append("Falta o número de parcelas.")
        return valores, datas

    n = int(n)
    if modo_valor == "Contínuo":
        sugestao = restante / n if restante else 0
        vp, ok_v = _valor("Valor de cada parcela", f"{prefixo}vparc",
                          placeholder=_num_br(sugestao) if sugestao else "0,00",
                          help="Em branco = divide o que falta igual entre as parcelas.")
        if not ok_v:
            erros.append("Tem valor digitado errado.")
        valores = [vp] * n if vp is not None else resolver_valores(restante, [None] * n)
    base = datas_continuas(primeira, n) if primeira else [None] * n

    if modo_valor == "Parcial" or modo_data == "Parcial":
        st.markdown("<div class='px-lista'>Parcela por parcela</div>", unsafe_allow_html=True)
        if modo_valor == "Parcial":
            _valores_automaticos([f"{prefixo}v{k}_{n}" for k in range(n)], restante)
        digitados = []
        for k in range(n):
            with st.container(key=f"{prefixo}linha_{k}"):
                cols = st.columns(2) if modo_valor == "Parcial" and modo_data == "Parcial" else [st.container()]
                if modo_valor == "Parcial":
                    with cols[0]:
                        v, ok_v = _valor(f"Valor da {k + 1}ª", f"{prefixo}v{k}_{n}",
                                         placeholder="em branco = divide")
                        if not ok_v:
                            erros.append("Tem valor digitado errado.")
                        digitados.append(v)
                if modo_data == "Parcial":
                    with cols[-1]:
                        # A chave leva o 1º vencimento: trocar ele recalcula as datas sugeridas
                        datas.append(st.date_input(
                            f"Vencimento da {k + 1}ª", value=base[k], format="DD/MM/YYYY",
                            key=f"{prefixo}d{k}_{n}_{primeira}"))
        if modo_valor == "Parcial":
            valores = resolver_valores(restante, digitados)
    if modo_data == "Contínuo":
        datas = base

    if any(d is None for d in datas):
        erros.append("Falta alguma data de vencimento.")
    if total and any(v <= 0 for v in valores):
        erros.append("Tem parcela com valor zero ou negativo.")
    return valores, datas


def _caixas_ja_pagas(prefixo: str, valores: list, datas: list, hoje: date) -> list:
    """
    Cobrança antiga cadastrada agora (pedido 16/10): cada parcela com data que já passou ganha
    a caixa "já paga", que vem marcada, senão ela entraria como atrasada (e o Telegram avisaria
    todo dia). Devolve um sim/não por parcela.
    """
    if not any(d and d < hoje for d in datas):
        return [False] * len(valores)
    st.markdown("<div class='px-lista'>Datas que já passaram</div>", unsafe_allow_html=True)
    pagas = []
    for k, (d, v) in enumerate(zip(datas, valores)):
        pagas.append(bool(d and d < hoje and st.checkbox(
            f"{k + 1}ª parcela · {data_br(d)} · {formatar_brl(v)} · já paga", value=True,
            key=f"{prefixo}pg{k}_{d}", help="Marcada = entra como já recebida. Desmarque se ainda não pagou.")))
    return pagas


def _resumo_pix(entrada: float, data_entrada, valores: list, datas: list, hoje: date,
                com_fim: bool = True, pagas: list | None = None) -> list:
    """Linhas do resumo do Pix: a entrada, as parcelas e (com `com_fim`) até quando vai."""
    linhas = []
    if entrada > 0 and data_entrada:
        paga = "paga" if data_entrada <= hoje else "a receber"
        linhas.append(f"Entrada de <b>{formatar_brl(entrada)}</b> em {data_br(data_entrada)} ({paga})")
    if valores and datas and all(datas):
        iguais = len(set(round(v, 2) for v in valores)) == 1
        parc = (f"<b>{len(valores)}x de {formatar_brl(valores[0])}</b>" if iguais
                else f"<b>{len(valores)} parcelas</b> somando {formatar_brl(sum(valores))}")
        linhas.append(f"{parc}, de {data_br(min(datas))} a {data_br(max(datas))}")
        n_pagas = sum(1 for x in pagas or [] if x)
        if n_pagas:
            linhas.append(f"<b>{n_pagas} parcela{'s' if n_pagas > 1 else ''} já paga{'s' if n_pagas > 1 else ''}</b>"
                          " (data que já passou)")
        if com_fim:
            linhas.append(f"A cobrança vai até <b>{nome_mes(max(datas))}</b>")
        if sorted(datas) != datas:
            linhas.append(":warning: As datas não estão em ordem")
    return linhas


def _resumo_cartao(ja_pago: float, valores: list, datas: list, vezes: list, passou: list,
                   com_fim: bool = True, cabecalho: bool = True) -> list:
    """
    Linhas do resumo do cartão, no mesmo jeito do Pix (pedido 21/10): o já pago, cada passada
    (data, valor, em quantas vezes) e até quando vai. Aparece desde que se diz quantas vezes
    passa: a passada ainda sem data vai para o fim com "falta escolher", para dar para
    conferir enquanto preenche. `cabecalho` = linha com quantas passadas e quanto somam.
    """
    linhas = []
    if ja_pago > 0:
        linhas.append(f"Já pago: <b>{formatar_brl(ja_pago)}</b>")
    if not valores:
        return linhas
    if cabecalho and len(valores) > 1:
        linhas.append(f"Cartão em <b>{len(valores)} passadas</b>, somando {formatar_brl(sum(valores))}")
    for d, v, x, ok in sorted((d, v, x, ok) for d, v, x, ok in zip(datas, valores, vezes, passou) if d):
        linhas.append(f"<b>{data_br(d)}</b> · {formatar_brl(v)} · {texto_vezes(v, x)}"
                      + (" · <b>já passou</b>" if ok else ""))
    for k, (d, v, x) in enumerate(zip(datas, valores, vezes)):
        if d is None:
            linhas.append(f"<b>Data {k + 1}: falta escolher</b> · {formatar_brl(v)} · {texto_vezes(v, x)}")
    if com_fim and all(datas):
        linhas.append(f"A cobrança vai até <b>{nome_mes(max(datas))}</b>")
    return linhas


def _bloco_passadas_cartao(prefixo: str, a_cobrar: float, total, erros: list, hoje: date | None = None):
    """
    Quantas vezes o cartão passa e, em cada uma, a data, o valor e em quantas parcelas.
    Devolve (valores, datas, vezes, ja_passou). Com `hoje`, a passada com data de hoje ou
    anterior ganha a caixa "Já passou", que vem marcada. O valor de cada passada já vem
    preenchido com a sua parte do que falta (ver _valores_automaticos).
    """
    valores, datas, vezes, ja_passou = [], [], [], []
    n = st.number_input("Quantas vezes você vai passar o cartão?", min_value=1,
                        value=None, step=1, key=f"{prefixo}n", placeholder="Ex.: 3",
                        help="Cada vez é um dia em que você passa o cartão do cliente. "
                             "Em cada uma você diz o valor e em quantas parcelas ela foi dividida.")
    if not n:
        erros.append("Falta dizer quantas vezes vai passar o cartão.")
        return valores, datas, vezes, ja_passou

    n = int(n)
    _valores_automaticos([f"{prefixo}v{k}" for k in range(n)], a_cobrar)
    digitados = []
    for k in range(n):
        with st.container(key=f"{prefixo}linha_{k}"):
            c1, c2 = st.columns(2)
            with c1:
                datas.append(st.date_input(f"Data {k + 1}", value=None, format="DD/MM/YYYY",
                                           key=f"{prefixo}d{k}"))
            with c2:
                v, ok_v = _valor(f"Valor {k + 1}", f"{prefixo}v{k}", placeholder="em branco = divide")
                if not ok_v:
                    erros.append("Tem valor digitado errado.")
                digitados.append(v)
            vezes.append(int(st.number_input(
                f"Parcelado em quantas vezes ({k + 1}ª passada)", min_value=1,
                value=1, step=1, key=f"{prefixo}x{k}",
                help="Em quantas parcelas essa passada é dividida no cartão. 1 = à vista.")))
            ja_passou.append(bool(
                hoje and datas[-1] and datas[-1] <= hoje
                and st.checkbox(f"Já passou o cartão ({k + 1}ª passada)", value=True, key=f"{prefixo}ok{k}",
                                help="Marcado = entra como já recebido. Desmarque se ainda vai passar.")))
    valores = resolver_valores(a_cobrar, digitados)
    if any(d is None for d in datas):
        erros.append("Falta escolher alguma data.")
    if total and any(v <= 0 for v in valores):
        erros.append("Tem data com valor zero ou negativo.")
    return valores, datas, vezes, ja_passou


# ── Cobrança Pix ──────────────────────────────────────────────────────────────

def tela_pix():
    hoje = _hoje()
    _cabecalho("Cobrança Pix", voltar_para="nova")
    with st.container(key="sec_px1"):
        cliente, turma, treino, erros = _bloco_cliente("px_")

    with st.container(key="sec_px2"):
        _titulo_secao(2, "Valores")
        total, ok_t = _valor("Valor total", "px_total")
        entrada, ok_e = _valor("Valor de entrada", "px_entrada", placeholder="0,00 se não teve entrada")
        entrada = entrada or 0.0
        data_entrada = None
        if entrada > 0:
            data_entrada = st.date_input("Data da entrada", value=hoje, format="DD/MM/YYYY",
                                         key="px_dt_entrada",
                                         help="O dia em que a pessoa pagou a entrada.")
        if not ok_t or not ok_e:
            erros.append("Tem valor digitado errado.")
        if total is None or total <= 0:
            erros.append("Falta o valor total.")
        elif entrada > total:
            erros.append("A entrada é maior que o valor total.")

    restante = max((total or 0) - entrada, 0)
    with st.container(key="sec_px3"):
        _titulo_secao(3, "Parcelas")
        valores, datas = _bloco_parcelas_pix("px_", restante, total, mes_mais(data_entrada or hoje, 1), erros)
        pagas = _caixas_ja_pagas("px_", valores, datas, hoje)

    # ── Resumo calculado ──
    confirmado = True
    with st.container(key="sec_px4"):
        _titulo_secao(4, "Resumo")
        linhas = _resumo_pix(entrada, data_entrada, valores, datas, hoje, pagas=pagas)
        if linhas:
            _info("<br>".join(linhas))
            if valores:
                confirmado = _bloco_conferencia(total, [entrada] + valores, "px_")
            _info("O Telegram avisa vocês 1 dia antes de cada vencimento, no dia, "
                  "e todo dia enquanto estiver atrasado.", "cx-nota")
        else:
            st.caption("Preencha os valores e as parcelas para ver o resumo.")

    obs_px = st.text_input("Observação (opcional)", key="px_obs", max_chars=300,
                           placeholder="Ex.: parte em permuta")
    if st.button("Salvar cobrança", type="primary", key="px_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            _salvar(TIPO_PIX, cliente, turma, treino, total,
                    parcelas_pix(entrada, data_entrada, valores, datas, hoje, pagas), "px_", obs_px)
    _aviso_do_salvar("px_")


# ── Cobrança cartão ───────────────────────────────────────────────────────────

def tela_cartao():
    hoje = _hoje()
    _cabecalho("Cobrança cartão", voltar_para="nova")
    with st.container(key="sec_ct1"):
        cliente, turma, treino, erros = _bloco_cliente("ct_")

    with st.container(key="sec_ct2"):
        _titulo_secao(2, "Valores")
        total, ok_t = _valor("Valor total", "ct_total")
        ja_pago, ok_p = _valor("Valor que já foi pago", "ct_pago", placeholder="0,00 se ainda não pagou nada")
        ja_pago = ja_pago or 0.0
        if not ok_t or not ok_p:
            erros.append("Tem valor digitado errado.")
        if total is None or total <= 0:
            erros.append("Falta o valor total.")
        elif ja_pago > total:
            erros.append("O valor já pago é maior que o total.")
        a_cobrar = max((total or 0) - ja_pago, 0)
        if total:
            _info(f"Valor a cobrar: <b>{formatar_brl(a_cobrar)}</b>")

    with st.container(key="sec_ct3"):
        _titulo_secao(3, "Datas para passar o cartão")
        st.caption("Para quando o cliente não tem limite para passar tudo de uma vez.")
        # data que já passou ganha a caixa "Já passou" (cobrança antiga cadastrada agora, pedido 16/10)
        valores, datas, vezes, passou = _bloco_passadas_cartao("ct_", a_cobrar, total, erros, hoje=hoje)

    confirmado = True
    with st.container(key="sec_ct4"):
        _titulo_secao(4, "Resumo")
        if valores:
            _info("<br>".join(_resumo_cartao(ja_pago, valores, datas, vezes, passou)))
            confirmado = _bloco_conferencia(total, [ja_pago] + valores, "ct_")
            _info("O Telegram avisa vocês 1 dia antes de cada data, no dia, "
                  "e todo dia enquanto não passar.", "cx-nota")
        else:
            st.caption("Diga quantas vezes vai passar o cartão para ver o resumo.")

    obs_ct = st.text_input("Observação (opcional)", key="ct_obs", max_chars=300,
                           placeholder="Ex.: cartão do marido")
    if st.button("Salvar cobrança", type="primary", key="ct_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ordem = sorted(zip(datas, valores, vezes, passou))
            _salvar(TIPO_CARTAO, cliente, turma, treino, total,
                    parcelas_cartao(ja_pago, hoje, [v for _, v, _, _ in ordem], [d for d, _, _, _ in ordem],
                                    [x for _, _, x, _ in ordem], [ok for _, _, _, ok in ordem]), "ct_", obs_ct)
    _aviso_do_salvar("ct_")


# ── Cobrança híbrida (duas ou três formas: Pix, cartão e permuta) ─────────────
# Pedido 06/11: no topo a pessoa marca QUAIS formas o cliente usa (pelo menos duas; vem marcado
# Pix + cartão, como sempre foi) e só aparecem os blocos delas. A parte da permuta tem os mesmos
# campos da tela Permuta (valores com data e retiradas) e vira as mesmas linhas de uma permuta,
# dentro da mesma cobrança.

ROTULO_FORMA = {TIPO_PIX: "Pix", TIPO_CARTAO: "Cartão de crédito", TIPO_PERMUTA: "Permuta"}
_NA_FORMA = {TIPO_PIX: "no Pix", TIPO_CARTAO: "no cartão", TIPO_PERMUTA: "na permuta"}
_ARTIGO_FORMA = {TIPO_PIX: "o Pix", TIPO_CARTAO: "o cartão", TIPO_PERMUTA: "a permuta"}
_CHAVE_PARTE = {TIPO_PIX: "hb_v_pix", TIPO_CARTAO: "hb_v_cartao", TIPO_PERMUTA: "hb_v_perm"}


def _lista_e(itens: list, conectivo: str = "e") -> str:
    """['o Pix', 'o cartão', 'a permuta'] → 'o Pix, o cartão e a permuta'."""
    return itens[0] if len(itens) == 1 else f"{', '.join(itens[:-1])} {conectivo} {itens[-1]}"


def _resumo_parte_permuta(creditos: list, retiradas: list) -> list:
    """Linhas do resumo da parte na permuta: cada valor com a data, as retiradas e o saldo."""
    if not creditos:
        return []
    total = sum(v for _, v in creditos)
    if len(creditos) > 1:
        linhas = [f"{data_br(d)} · valor de {formatar_brl(v)}" for d, v in sorted(creditos)]
    else:
        linhas = [f"Valor de {formatar_brl(total)} em {data_br(creditos[0][0])}"]
    for produto, d, v in sorted(retiradas, key=lambda r: r[1]):
        linhas.append(f"{data_br(d)} · retirada · {_e(produto)} · {formatar_brl(v)}")
    if not retiradas:
        linhas.append("Nenhuma retirada ainda")
    saldo = (centavos(total) - centavos(sum(v for _, _, v in retiradas))) / 100
    linhas.append(f"Saldo para retirar: <b>{formatar_brl(saldo)}</b>" if saldo >= 0
                  else f":warning: As retiradas passam do total da permuta em <b>{formatar_brl(-saldo)}</b>")
    return linhas


def tela_hibrido():
    hoje = _hoje()
    _cabecalho("Cobrança híbrida", voltar_para="nova", subtitulo="Marque as formas que o cliente vai usar")
    num = iter(range(1, 20))   # os blocos são numerados na ordem em que aparecem
    with st.container(key="sec_hb0"):
        _titulo_secao(next(num), "Formas de pagamento")
        escolhidas = st.pills("Formas de pagamento", FORMAS_HIBRIDO, selection_mode="multi",
                              default=[TIPO_PIX, TIPO_CARTAO], key="hb_formas", format_func=ROTULO_FORMA.get,
                              label_visibility="collapsed")
        formas = [f for f in FORMAS_HIBRIDO if f in (escolhidas or [])]   # sempre na mesma ordem
        if len(formas) < 2:
            _erro_campo("Marque pelo menos duas formas. Se é tudo de um jeito só, use a cobrança Pix, "
                        "a cobrança cartão ou a permuta.")
        else:
            st.caption("Toque para marcar ou desmarcar. Só aparecem os blocos das formas marcadas.")
    with st.container(key="sec_hb1"):
        cliente, turma, treino, erros = _bloco_cliente("hb_", numero=next(num))
    if len(formas) < 2:
        erros.append("Marque pelo menos duas formas de pagamento (ex.: Pix e permuta).")

    partes = {f: 0.0 for f in FORMAS_HIBRIDO}   # quanto vai em cada forma (0 = ainda não dá para saber)
    total = None
    if len(formas) >= 2:
        with st.container(key="sec_hb2"):
            _titulo_secao(next(num), "Valores")
            total, ok_t = _valor("Valor total", "hb_total")
            ajuda = ("Preencha um dos dois: o outro é o que sobra do total." if len(formas) == 2
                     else "Deixe uma em branco: ela fica com o que sobra do total.")
            digitado, tudo_ok = {}, ok_t
            for f in formas:
                digitado[f], ok = _valor(f"Quanto vai {_NA_FORMA[f]}", _CHAVE_PARTE[f],
                                         placeholder="em branco = o resto", help=ajuda)
                tudo_ok = tudo_ok and ok
            if not tudo_ok:
                erros.append("Tem valor digitado errado.")
            vazias = [f for f in formas if digitado[f] is None]
            if total is None or total <= 0:
                erros.append("Falta o valor total.")
            elif len(vazias) > 1:
                if len(formas) == 2:   # (o texto de sempre do Pix + cartão)
                    erros.append(f"Falta dizer quanto vai {_NA_FORMA[formas[0]]} ou quanto vai {_NA_FORMA[formas[1]]}.")
                else:
                    erros.append(f"Falta dizer quanto vai {_lista_e([_NA_FORMA[f] for f in vazias], 'ou')} "
                                 "(só uma pode ficar em branco: ela fica com o resto).")
            else:
                if vazias:
                    outras = sum(centavos(digitado[f]) for f in formas if f != vazias[0])
                    digitado[vazias[0]] = (centavos(total) - outras) / 100
                if any(digitado[f] <= 0 for f in formas):
                    quais = _lista_e([_ARTIGO_FORMA[f] for f in formas])
                    curto = f"{quais[0].upper()}{quais[1:]} precisam ter valor, e nenhuma parte pode passar do total."
                    erros.append(f"{curto} Se é tudo de um jeito só, use a cobrança Pix, a cobrança cartão ou a permuta.")
                    _erro_campo(curto)
                else:
                    partes.update(digitado)
                    # cada etiqueta fica junto do seu valor ("R$" nunca sozinho no fim da linha)
                    _info(" &nbsp;+&nbsp; ".join(f"<span style='white-space:nowrap'>{_chip_tipo(f)} "
                                                 f"<b>{formatar_brl(partes[f])}</b></span>" for f in formas))

    data_entrada, entrada, valores_px, datas_px, pix_pagas = None, 0.0, [], [], []
    if TIPO_PIX in formas and len(formas) >= 2:
        parte_pix = partes[TIPO_PIX]
        with st.container(key="sec_hb3"):
            _titulo_secao(next(num), "Parte no Pix")
            entrada, ok_e = _valor("Valor de entrada", "hb_entrada", placeholder="0,00 se não teve entrada",
                                   help="O que entra primeiro no Pix. Se o Pix foi pago de uma vez só, "
                                        "coloque aqui a parte inteira do Pix.")
            entrada = entrada or 0.0
            if entrada > 0:
                data_entrada = st.date_input("Data da entrada", value=hoje, format="DD/MM/YYYY",
                                             key="hb_dt_entrada",
                                             help="O dia em que a pessoa pagou a entrada.")
            if not ok_e:
                erros.append("Tem valor digitado errado.")
            if parte_pix and centavos(entrada) > centavos(parte_pix):
                erros.append("A entrada é maior que a parte do Pix.")
            if parte_pix and centavos(entrada) == centavos(parte_pix):
                _info("O Pix fica todo na entrada, sem parcelas.")
            else:
                valores_px, datas_px = _bloco_parcelas_pix("hb_px_", max(parte_pix - entrada, 0), total,
                                                           mes_mais(data_entrada or hoje, 1), erros)
                pix_pagas = _caixas_ja_pagas("hb_px_", valores_px, datas_px, hoje)

    valores_ct, datas_ct, vezes, passou = [], [], [], []
    if TIPO_CARTAO in formas and len(formas) >= 2:
        with st.container(key="sec_hb4"):
            _titulo_secao(next(num), "Parte no cartão")
            st.caption("Uma data para cada vez que o cartão passa. Se já passou, coloque o dia em que passou.")
            valores_ct, datas_ct, vezes, passou = _bloco_passadas_cartao("hb_ct_", partes[TIPO_CARTAO], total,
                                                                        erros, hoje=hoje)

    creditos, retiradas = [], []
    if TIPO_PERMUTA in formas and len(formas) >= 2:
        # os mesmos campos da tela Permuta: valores (com data) e retiradas (opcionais)
        with st.container(key="sec_hb_pm"):
            _titulo_secao(next(num), "Parte na permuta")
            st.markdown("<div class='px-lista'>Valores da permuta</div>", unsafe_allow_html=True)
            creditos = _bloco_valores_permuta("hb_pm_", hoje, erros, a_dividir=partes[TIPO_PERMUTA])
            st.markdown("<div class='px-lista'>Retiradas</div>", unsafe_allow_html=True)
            st.caption("O que vocês já pegaram da empresa. Se ainda não pegaram nada, deixe em branco: "
                       "dá para anotar depois, na ficha da cobrança.")
            retiradas = _bloco_retiradas("hb_pm_", hoje, erros)
            if creditos:
                st.markdown(_html_saldo(sum(v for _, v in creditos), sum(v for _, _, v in retiradas)),
                            unsafe_allow_html=True)
    total_pm = sum(v for _, v in creditos)
    retirado = sum(v for _, _, v in retiradas)

    confirmado = True
    with st.container(key="sec_hb5"):
        _titulo_secao(next(num), "Resumo")
        # Aparece assim que o total está dividido (pedido 21/10): a parte ainda não preenchida
        # fica com "falta preencher", para dar para conferir enquanto preenche.
        if len(formas) < 2:
            st.caption("Marque pelo menos duas formas de pagamento para ver o resumo.")
        elif not any(partes[f] for f in formas):
            st.caption(f"Preencha o valor total e quanto vai {_lista_e([_NA_FORMA[f] for f in formas], 'ou')} "
                       "para ver o resumo.")
        else:
            linhas, prontas = [], True
            linhas_px, linhas_ct = [], []
            if TIPO_PIX in formas:
                linhas_px = _resumo_pix(entrada, data_entrada, valores_px, datas_px, hoje, com_fim=False,
                                        pagas=pix_pagas)
                soma_px = entrada + sum(valores_px) if linhas_px else partes[TIPO_PIX]
                linhas.append(f"{_chip_tipo(TIPO_PIX)} <b>{formatar_brl(soma_px)}</b>")
                linhas += linhas_px or ["<b>Falta preencher</b> a parte do Pix"]
                prontas = prontas and bool(linhas_px)
            if TIPO_CARTAO in formas:
                linhas_ct = _resumo_cartao(0, valores_ct, datas_ct, vezes, passou, com_fim=False, cabecalho=False)
                soma_ct = sum(valores_ct) if valores_ct else partes[TIPO_CARTAO]
                linhas.append(f"{_chip_tipo(TIPO_CARTAO)} <b>{formatar_brl(soma_ct)}</b>")
                linhas += linhas_ct or ["<b>Falta preencher</b> a parte do cartão"]
                prontas = prontas and bool(valores_ct)
            if TIPO_PERMUTA in formas:
                linhas_pm = _resumo_parte_permuta(creditos, retiradas)
                linhas.append(f"{_chip_tipo(TIPO_PERMUTA)} <b>{formatar_brl(total_pm or partes[TIPO_PERMUTA])}</b>")
                linhas += linhas_pm or ["<b>Falta preencher</b> a parte da permuta"]
                prontas = prontas and bool(creditos)
            # até quando vai = a última data do DINHEIRO (a permuta não tem data para cobrar)
            if prontas and all(datas_ct) and (TIPO_PIX not in formas or linhas_px):
                datas_din = [d for d in datas_px if d] + list(datas_ct) + ([data_entrada] if data_entrada else [])
                if datas_din:
                    linhas.append(f"A cobrança vai até <b>{nome_mes(max(datas_din))}</b>")
            _info("<br>".join(linhas))
            if prontas:
                confirmado = _bloco_conferencia(total, [entrada] + valores_px + valores_ct + [v for _, v in creditos],
                                                "hb_")
            nota = "O Telegram avisa vocês 1 dia antes de cada data, no dia, e todo dia enquanto estiver atrasado."
            if TIPO_PERMUTA in formas:
                nota += (" A parte da permuta não entra no Recebido nem no A receber, e o Telegram não avisa: "
                         "ela tem o próprio saldo.")
            _info(nota, "cx-nota")

    obs_hb = st.text_input("Observação (opcional)", key="hb_obs", max_chars=300,
                           placeholder="Ex.: cartão do marido")
    if st.button("Salvar cobrança", type="primary", key="hb_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if total_pm and centavos(retirado) > centavos(total_pm):
            erros.append("As retiradas passam do total da permuta.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ordem = sorted(zip(datas_ct, valores_ct, vezes, passou))
            _salvar(TIPO_HIBRIDO, cliente, turma, treino, total,
                    parcelas_hibrido(entrada, data_entrada, valores_px, datas_px,
                                     [v for _, v, _, _ in ordem], [d for d, _, _, _ in ordem],
                                     [x for _, _, x, _ in ordem], [ok for _, _, _, ok in ordem], hoje, pix_pagas,
                                     creditos=creditos, retiradas=retiradas, quem=_usuario()),
                    "hb_", obs_hb)
    _aviso_do_salvar("hb_")


# ── Permuta (treinamento em troca de produtos ou serviços) ────────────────────
# A Vithall ganha um SALDO com a empresa do cliente e vai pegando produtos até zerar.
# Cada VALOR que entra tem a sua data (a pessoa pode fechar outra permuta meses depois: é
# só tocar no "+" dos valores) e cada RETIRADA = produto + data + quanto desconta do saldo.

_CAMPOS_VALOR = ("cdata_", "cval_")            # cada valor da permuta: data e valor
_CAMPOS_RETIRADA = ("prod_", "rdata_", "rval_")  # cada retirada: produto, data e valor


def _mais_uma_linha(prefixo: str, contador: str):
    st.session_state[f"{prefixo}{contador}"] = st.session_state.get(f"{prefixo}{contador}", 1) + 1


def _tirar_linha(prefixo: str, contador: str, campos: tuple, i: int):
    """Tira a i-ésima linha e sobe as de baixo (roda antes da tela, por isso pode mexer nos campos)."""
    ss = st.session_state
    n = ss.get(f"{prefixo}{contador}", 1)
    chave = lambda campo, j: f"{prefixo}{campo}{j}" + (MARCA_VALOR if campo.endswith("val_") else "")
    for j in range(i, n - 1):
        for campo in campos:
            if chave(campo, j + 1) in ss:
                ss[chave(campo, j)] = ss[chave(campo, j + 1)]
            else:
                ss.pop(chave(campo, j), None)
    for campo in campos:
        ss.pop(chave(campo, n - 1), None)
    ss[f"{prefixo}{contador}"] = max(n - 1, 1)


def _bloco_valores_permuta(prefixo: str, hoje: date, erros: list, a_dividir: float | None = None) -> list:
    """
    Cada valor de permuta que entrou, com a data dele, e o "+" para mais um (a mesma pessoa pode
    fechar outra permuta depois). Devolve [(data, valor)].
    `a_dividir` (cobrança híbrida): a parte da permuta já dita em "Valores"; os campos vêm
    preenchidos com ela, como as parcelas do Pix e as passadas do cartão (_valores_automaticos).
    """
    valores = []
    n = st.session_state.get(f"{prefixo}n_cred", 1)
    if a_dividir is not None:
        _valores_automaticos([f"{prefixo}cval_{i}" for i in range(n)], a_dividir)
    for i in range(n):
        with st.container(key=f"{prefixo}cred_{i}"):
            if n > 1:
                c0, cx = st.columns([6, 1], vertical_alignment="center")
                with c0:
                    st.markdown(f"<div class='px-lista'>{i + 1}º valor</div>", unsafe_allow_html=True)
                with cx:
                    st.button("Tirar", key=f"{prefixo}tirar_cred_{i}", icon=":material/close:",
                              help="Tirar este valor", on_click=_tirar_linha,
                              args=(prefixo, "n_cred", _CAMPOS_VALOR, i), use_container_width=True)
            c1, c2 = st.columns(2)
            with c1:
                valor, ok = _valor("Valor da permuta", f"{prefixo}cval_{i}",
                                   help="Quanto essa permuta vale em produtos ou serviços da empresa do cliente.")
            with c2:
                data = st.date_input("Data da permuta", value=hoje, format="DD/MM/YYYY", key=f"{prefixo}cdata_{i}",
                                     help="O dia em que vocês fecharam essa permuta.")
        if not ok:
            erros.append("Tem valor digitado errado.")
        elif valor and data:
            valores.append((data, valor))
        elif valor:
            erros.append(f"Falta a data do {i + 1}º valor.")
    st.button("Adicionar outro valor", key=f"{prefixo}mais_cred", icon=":material/add:", type="tertiary",
              on_click=_mais_uma_linha, args=(prefixo, "n_cred"),
              help="Fechou mais uma permuta com essa pessoa? Põe o valor novo com a data dele.")
    if not valores:
        erros.append("Falta o valor da permuta.")
    return valores


def _bloco_retiradas(prefixo: str, hoje: date, erros: list) -> list:
    """
    As retiradas já feitas: produto, data e quanto desconta do saldo, com "+" para mais uma.
    Linha toda em branco é ignorada (dá para cadastrar a permuta sem retirada nenhuma).
    Devolve [(produto, data, valor)].
    """
    retiradas = []
    n = st.session_state.get(f"{prefixo}n_ret", 1)
    for i in range(n):
        with st.container(key=f"{prefixo}ret_{i}"):
            st.markdown(f"<div class='px-lista'>{i + 1}ª retirada</div>", unsafe_allow_html=True)
            c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
            with c1:
                produto = st.text_input("Produto", key=f"{prefixo}prod_{i}", max_chars=120,
                                        placeholder="Ex.: 10 camisetas, 2 jantares…")
            with c2:
                st.button("Tirar", key=f"{prefixo}tirar_ret_{i}", icon=":material/close:", help="Tirar esta retirada",
                          on_click=_tirar_linha, args=(prefixo, "n_ret", _CAMPOS_RETIRADA, i),
                          use_container_width=True)
            c3, c4 = st.columns(2)
            with c3:
                data = st.date_input("Data", value=hoje, format="DD/MM/YYYY", key=f"{prefixo}rdata_{i}")
            with c4:
                valor, ok = _valor("Quanto desconta", f"{prefixo}rval_{i}",
                                   help="Quanto essa retirada desconta do saldo da permuta.")
        if not ok:
            erros.append("Tem valor digitado errado.")
        if produto.strip() or valor:
            if not produto.strip():
                erros.append(f"Falta o produto da {i + 1}ª retirada.")
            if not valor:
                erros.append(f"Falta quanto desconta a {i + 1}ª retirada.")
            if not data:
                erros.append(f"Falta a data da {i + 1}ª retirada.")
            if produto.strip() and valor and data:
                retiradas.append((" ".join(produto.split()).upper(), data, valor))
    st.button("Adicionar retirada", key=f"{prefixo}mais_ret", icon=":material/add:", type="tertiary",
              on_click=_mais_uma_linha, args=(prefixo, "n_ret"))
    return retiradas


def _html_saldo(total, retirado: float) -> str:
    saldo = (centavos(total or 0) - centavos(retirado)) / 100
    if saldo < 0:
        return (f"<div class='cx-passa'>As retiradas passam do total da permuta em "
                f"<b>{formatar_brl(-saldo)}</b>.</div>")
    return f"<div class='cx-ok'>Saldo para retirar: <b>{formatar_brl(saldo)}</b></div>"


def tela_permuta():
    hoje = _hoje()
    _cabecalho("Permuta", voltar_para="nova", subtitulo="Treinamento em troca de produtos ou serviços da empresa")
    with st.container(key="sec_pm1"):
        cliente, turma, treino, erros = _bloco_cliente("pm_")
        outras = permutas_do_cliente(_cobrancas() or [], cliente)
        if outras:
            ja = outras[0]
            st.markdown(f"<div class='cx-dica'>{_e(cliente.upper())} já tem uma permuta (saldo de "
                        f"{formatar_brl(max(ja['saldo'], 0))}). Para somar uma permuta nova a ela, abra a dela e "
                        f"toque em <b>Adicionar valor</b>.</div>", unsafe_allow_html=True)
            if st.button(f"Abrir a permuta de {ja['cliente']}", key="pm_abrir_existente",
                         icon=":material/open_in_new:", type="tertiary"):
                _abrir_cobranca(ja["id"], "nova")

    with st.container(key="sec_pm2"):
        _titulo_secao(2, "Valores")
        creditos = _bloco_valores_permuta("pm_", hoje, erros)
        total = sum(v for _, v in creditos)
        if len(creditos) > 1:
            _info(f"Total da permuta: <b>{formatar_brl(total)}</b>")

    with st.container(key="sec_pm3"):
        _titulo_secao(3, "Retiradas")
        st.caption("O que vocês já pegaram da empresa. Se ainda não pegaram nada, deixe em branco: "
                   "dá para anotar depois, na ficha da permuta.")
        retiradas = _bloco_retiradas("pm_", hoje, erros)
        retirado = sum(v for _, _, v in retiradas)
        if total:
            st.markdown(_html_saldo(total, retirado), unsafe_allow_html=True)

    with st.container(key="sec_pm4"):
        _titulo_secao(4, "Resumo")
        if total:
            linhas = [f"Permuta de <b>{formatar_brl(total)}</b>"]
            if len(creditos) > 1:
                linhas += [f"{data_br(d)} · valor de {formatar_brl(v)}" for d, v in sorted(creditos)]
            else:
                linhas[0] += f" em {data_br(creditos[0][0])}"
            for produto, d, v in sorted(retiradas, key=lambda r: r[1]):
                linhas.append(f"{data_br(d)} · retirada · {_e(produto)} · {formatar_brl(v)}")
            if not retiradas:
                linhas.append("Nenhuma retirada ainda")
            _info("<br>".join(linhas))
            st.markdown(_html_saldo(total, retirado), unsafe_allow_html=True)   # o "fecha certinho" da permuta
            _info("Permuta não entra no Recebido nem no A receber, e o Telegram não avisa: ela tem o "
                  "próprio saldo.", "cx-nota")
        else:
            st.caption("Preencha o valor da permuta para ver o resumo.")

    obs_pm = st.text_input("Observação (opcional)", key="pm_obs", max_chars=300,
                           placeholder="Ex.: troca por produtos da loja")
    if st.button("Salvar permuta", type="primary", key="pm_salvar", use_container_width=True,
                 icon=":material/check:"):
        if total and centavos(retirado) > centavos(total):
            erros.append("As retiradas passam do total da permuta.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            _salvar(TIPO_PERMUTA, cliente, turma, treino, total,
                    parcelas_permuta(retiradas, _usuario(), creditos), "pm_", obs_pm)
    _aviso_do_salvar("pm_")


# ── Relatório ─────────────────────────────────────────────────────────────────

def _chip_sit(sit: str) -> str:
    return f"<span class='sit {COR_CLI[sit]}'>{ROTULO_CLI[sit]}</span>"


def _chip_situacao(c: dict) -> str:
    """Situação da cobrança; a permuta tem a dela: com saldo ou saldo zerado. A híbrida com parte
    na permuta segue o dinheiro (Pix e cartão); o saldo da permuta aparece à parte."""
    if c.get("permuta"):
        return _chip_saldo(c)
    return _chip_sit(c["situacao"])


_CLASSE_TIPO = {TIPO_PIX: "tp-pix", TIPO_CARTAO: "tp-cartao", TIPO_HIBRIDO: "tp-hib", TIPO_PERMUTA: "tp-perm"}


def _chip_tipo(tipo: str) -> str:
    """Etiqueta da forma de pagamento: Pix azul, Cartão rosa (para bater o olho e diferenciar);
    Híbrido é metade de cada cor."""
    return f"<span class='tp {_CLASSE_TIPO.get(tipo, 'tp-pix')}'>{_e(tipo)}</span>"


# Híbrida: uma faixa da cor de cada forma que ela tem (Pix azul, Cartão rosa, Permuta verde-água)
_CLASSE_HIBRIDA = {(TIPO_PIX, TIPO_CARTAO): "tp-hib", (TIPO_PIX, TIPO_PERMUTA): "tp-hib hb-px-pm",
                   (TIPO_CARTAO, TIPO_PERMUTA): "tp-hib hb-ct-pm",
                   (TIPO_PIX, TIPO_CARTAO, TIPO_PERMUTA): "tp-hib hb-tres"}


def _chip_cobranca(c: dict) -> str:
    """Etiqueta da cobrança inteira: na híbrida, as cores das formas que ela tem (2 ou 3 faixas)."""
    if c["tipo"] != TIPO_HIBRIDO:
        return _chip_tipo(c["tipo"])
    classe = _CLASSE_HIBRIDA.get(tuple(c.get("formas") or ()), "tp-hib")
    return f"<span class='tp {classe}'>{_e(TIPO_HIBRIDO)}</span>"


def _nome_tipo(c: dict) -> str:
    """'Híbrido (Pix + permuta)' na híbrida; 'Pix', 'Cartão' ou 'Permuta' nas outras."""
    if not c["hibrida"]:
        return c["tipo"]
    nomes = {TIPO_PIX: "Pix", TIPO_CARTAO: "cartão", TIPO_PERMUTA: "permuta"}
    return f"{TIPO_HIBRIDO} ({' + '.join(nomes[f] for f in c['formas'])})"


def _saldo_permuta_curto(c: dict) -> str:
    """O saldo da parte na permuta de uma híbrida, curtinho, para o cartão do relatório."""
    if c["saldo"] > 0.005:
        return f"<span class='cc-sp'>saldo <b>{formatar_brl(c['saldo'])}</b></span>"
    return "<span class='cc-sp'>saldo zerado</span>"


def _linha_estado(c: dict, hoje: date) -> str:
    """A data vai SEMPRE por extenso e com o ano (tem parcela que cai no ano seguinte)."""
    if c["situacao"] == CLI_QUITADO:
        return "Tudo pago"
    if c["situacao"] == CLI_ATRASADO:
        d = c["dias_atraso"]
        desde = data_br(hoje - timedelta(days=d))
        return f"<b>{formatar_brl(c['atrasado'])}</b> atrasado desde <b>{desde}</b> ({d} dia{'s' if d > 1 else ''})"
    p = c["proxima"]
    if p:
        apelido = (" (hoje)" if p["vencimento"] == hoje
                   else " (amanhã)" if p["vencimento"] == hoje + timedelta(days=1) else "")
        # na híbrida com Pix E cartão, diz de que forma é a próxima (umas são Pix, outras cartão)
        dinheiro = [f for f in c.get("formas", []) if f in FORMAS]
        forma = f" · no {'cartão' if p['tipo'] == TIPO_CARTAO else 'Pix'}" if len(dinheiro) > 1 else ""
        return f"Próxima: <b>{data_br(p['vencimento'])}</b>{apelido} · {formatar_brl(p['valor'])}{forma}"
    return ""


def _html_cliente(c: dict, hoje: date) -> str:
    """Cartão compacto (3 linhas finas) para caber mais gente na tela; a barrinha de quanto já
    foi pago fica na borda de baixo."""
    total = c["pago"] + c["falta"]
    pct = _pct(c["pago"], total)
    quitado = c["situacao"] == CLI_QUITADO
    nota = "<span class='cc-nota'>obs</span>" if c["tem_obs"] else ""
    if c.get("permuta"):
        # permuta: o que importa é o saldo que ainda dá para retirar
        valor = (f"saldo <b>{formatar_brl(c['saldo'])}</b>" if not quitado
                 else f"retirado <b>{formatar_brl(c['pago'])}</b>")
        estado = ("" if quitado else
                  f"<div class='cc-est'>Retirado {formatar_brl(c['pago'])} de {formatar_brl(c['total_permuta'])}</div>")
    else:
        valor = (f"pago <b>{formatar_brl(c['pago'])}</b>" if quitado
                 else f"falta <b>{formatar_brl(c['falta'])}</b>")
        if c.get("com_permuta"):   # híbrida com parte na permuta: o saldo dela ao lado (pedido 06/11)
            valor += f" · {_saldo_permuta_curto(c)}"
        estado = "" if quitado else f"<div class='cc-est'>{_linha_estado(c, hoje)}</div>"
    return (
        f"<div class='cc {COR_CLI[c['situacao']]}'>"
        f"<div class='cc-l1'><span class='cc-nome'>{_e(c['cliente'])}</span>{nota}"
        f"{_chip_cobranca(c)}{_chip_situacao(c)}</div>"
        f"<div class='cc-l2'><span class='cc-turma'>{_e(local_da_cobranca(c))}</span>"
        f"<span class='cc-val'>{valor}</span></div>{estado}"
        f"<i class='cc-pg' style='width:{pct}%'></i></div>"
    )


def _abrir_cobranca(cid: str, volta: str):
    st.session_state.cob_id = cid
    st.session_state.cob_volta = volta
    _ir("cobranca")


def _brl_curto(x: float) -> str:
    """'R$' pequeno na frente: três valores grandes lado a lado cabem no celular."""
    return f"<small>R$</small>{formatar_brl(x).replace('R$ ', '')}"


def _html_resumo(r: dict) -> str:
    n = r["n_atrasados"]
    quem = f"{n} cliente{'s' if n > 1 else ''}" if n else "ninguém"
    return (
        "<div class='rs'>"
        f"<div class='rs-it c-ok'><b>{_brl_curto(r['recebido'])}</b><span>Recebido</span></div>"
        f"<div class='rs-it c-neutro'><b>{_brl_curto(r['a_receber'])}</b><span>A receber</span></div>"
        f"<div class='rs-it c-atraso'><b>{_brl_curto(r['atrasado'])}</b><span>Atrasado</span>"
        f"<em>{quem}</em></div></div>"
        # permuta não é dinheiro: conta à parte, logo embaixo
        + (f"<div class='rs-perm'><span class='tp tp-perm'>Permuta</span>Saldo para retirar: "
           f"<b>{formatar_brl(r['saldo_permuta'])}</b> em {r['n_permutas']} permuta"
           f"{'s' if r['n_permutas'] > 1 else ''}</div>" if r.get("n_permutas") else "")
    )


PERIODOS = ["Hoje", "Esta semana", "Próxima semana", "Este mês", "Escolher datas"]
SITUACOES_FILTRO = {"Atrasado": CLI_ATRASADO, "Vence em breve": CLI_EM_BREVE,
                    "Em dia": CLI_EM_DIA, "Quitado": CLI_QUITADO}


def _periodo(escolha: str, hoje: date):
    seg = inicio_semana(hoje)
    if escolha == "Hoje":
        return hoje, hoje
    if escolha == "Próxima semana":
        return seg + timedelta(days=7), seg + timedelta(days=13)
    if escolha == "Este mês":
        return hoje.replace(day=1), mes_mais(hoje.replace(day=1), 1) - timedelta(days=1)
    if escolha == "Escolher datas":
        c1, c2 = st.columns(2)
        with c1:
            de = st.date_input("De", value=hoje, format="DD/MM/YYYY", key="rf_de")
        with c2:
            ate = st.date_input("Até", value=hoje + timedelta(days=7), format="DD/MM/YYYY", key="rf_ate")
        return de, max(de, ate)
    return seg, seg + timedelta(days=6)


def tela_relatorio():
    hoje = _hoje()
    _cabecalho("Relatório de cobranças", voltar_para="inicio")
    cobs = _cobrancas()
    if cobs is None:
        return

    termo = st.text_input("Buscar", key="rf_busca", placeholder="Nome, turma ou palavra da observação",
                          label_visibility="collapsed", icon=":material/search:")

    with st.expander("Filtros", icon=":material/tune:"):
        sits = st.pills("Situação", list(SITUACOES_FILTRO), selection_mode="multi", key="rf_sit")
        tipos = st.pills("Forma", [TIPO_PIX, TIPO_CARTAO, TIPO_HIBRIDO, TIPO_PERMUTA], selection_mode="multi",
                         key="rf_tipo")
        treinos = st.pills("Treinamento", list(TREINAMENTOS.values()), selection_mode="multi", key="rf_trein")
        turma = st.text_input("Turma", key="rf_turma", placeholder="Ex.: L345")
        if turma.strip() and not normalizar_turma(turma):
            _erro_campo("Turma não reconhecida. Ex.: L345")
        com_obs = st.pills("Observações", ["Com observação", "Sem observação"], key="rf_obs")

    filtradas = filtrar(cobs, termo, [SITUACOES_FILTRO[s] for s in sits or []], tipos or None,
                        treinos or None, turma,
                        obs={"Com observação": "com", "Sem observação": "sem"}.get(com_obs, ""))
    st.markdown(_html_resumo(resumo(filtradas)), unsafe_allow_html=True)

    visao = st.segmented_control("Ver", ["Clientes", "Agenda"], key="rf_visao", default="Clientes",
                                 label_visibility="collapsed")
    if visao == "Agenda":
        _visao_agenda(filtradas, hoje)
    else:
        _visao_clientes(filtradas, hoje, bool(termo or sits or tipos or treinos or turma or com_obs))

    if st.button("Atualizar", key="rf_atualizar", icon=":material/refresh:", type="tertiary"):
        _invalidar()
        st.rerun()


def _visao_clientes(cobs: list, hoje: date, filtrando: bool):
    if not cobs:
        st.markdown("<div class='cx-vazio'>" + ("Nada encontrado com essa busca." if filtrando
                    else "Nenhuma cobrança cadastrada ainda.") + "</div>", unsafe_allow_html=True)
        return
    n = len(cobs)
    st.markdown(f"<div class='rl-cont'>{n} cobrança{'s' if n > 1 else ''}</div>", unsafe_allow_html=True)
    for c in ordenar_para_cobrar(cobs):
        if _cartao_toque(f"cc_{c['id']}", f"tq_{c['id']}", f"Abrir {c['cliente']}", _html_cliente(c, hoje)):
            _abrir_cobranca(c["id"], "relatorio")


def _rotulo_dia(d: date, hoje: date) -> str:
    if d < hoje:
        return "Atrasadas"
    if d == hoje:
        return f"Hoje · {DIAS_SEMANA[d.weekday()]} {data_br(d)}"
    if d == hoje + timedelta(days=1):
        return f"Amanhã · {DIAS_SEMANA[d.weekday()]} {data_br(d)}"
    return f"{DIAS_SEMANA[d.weekday()]} {data_br(d)}"


def _visao_agenda(cobs: list, hoje: date):
    escolha = st.pills("Período", PERIODOS, key="rf_periodo", default="Esta semana")
    de, ate = _periodo(escolha or "Esta semana", hoje)
    com_atr = st.toggle("Incluir as atrasadas", value=True, key="rf_com_atr")
    itens = agenda(cobs, de, ate, com_atr)
    if not itens:
        st.markdown("<div class='cx-vazio'>Nenhuma cobrança nesse período.</div>", unsafe_allow_html=True)
        return
    soma = sum(p["valor"] for p, _ in itens)
    n = len(itens)
    st.markdown(f"<div class='rl-cont'>{n} cobrança{'s' if n > 1 else ''} · {formatar_brl(soma)}</div>",
                unsafe_allow_html=True)
    grupo_atual = None
    for p, c in itens:
        grupo = _rotulo_dia(p["vencimento"], hoje)
        if grupo != grupo_atual:
            grupo_atual = grupo
            classe = " atraso" if grupo == "Atrasadas" else ""
            st.markdown(f"<div class='ag-dia{classe}'>{_e(grupo)}</div>", unsafe_allow_html=True)
        _parcela_ui(p, c, hoje, contexto="ag", mostrar_cliente=True)


# ── Parcela (usada na agenda e na ficha do cliente) ───────────────────────────

def _html_parcela(p: dict, c: dict, hoje: date, mostrar_cliente: bool) -> str:
    d = p["vencimento"]
    cor = COR_PARC[p["situacao"]]
    cartao = p["tipo"] == TIPO_CARTAO   # a forma é a DESTA parcela (na híbrida elas se misturam)
    if d:
        bloco = (f"<div class='pc-data'><span class='pc-mes'>{MESES_ABREV[d.month - 1]} {d.year}</span>"
                 f"<span class='pc-dia'>{d.day}</span><span class='pc-sem'>{DIAS_SEMANA[d.weekday()]}</span></div>")
    else:
        bloco = "<div class='pc-data'><span class='pc-dia'>?</span></div>"
    if p["paga"]:
        sit = ""
        pago_em = f"<small>{p['pago_em'].strftime('%d/%m/%y')}</small>" if p["pago_em"] else ""
        carimbo = f"<div class='pc-carimbo'>{'PASSOU' if cartao else 'PAGO'}{pago_em}</div>"
    else:
        carimbo = ""
        if p["situacao"] == SIT_ATRASADA:
            dias = (hoje - d).days
            txt = f"{dias} dia{'s' if dias > 1 else ''} de atraso"
        elif p["situacao"] == SIT_EM_BREVE:
            txt = "Vence hoje" if d == hoje else "Amanhã" if d == hoje + timedelta(days=1) else "Em breve"
        else:
            txt = "Em aberto"
        sit = f"<span class='sit {cor}'>{txt}</span>"
    # Na ficha o cliente, a turma e a forma já estão no título: o topo fica vazio
    topo = _e(local_da_cobranca(c)) if mostrar_cliente else ""
    nome = f"<div class='pc-nome'>{_e(c['cliente'])}</div>" if mostrar_cliente else ""
    quem = ""
    if p["paga"] and p["marcado_por"]:
        verbo = "passou" if cartao else "recebeu"
        quem = f"<br><span class='pc-quem'>{_e(p['marcado_por'])} {verbo}</span>"
    obs = f"<div class='pc-obs'>{_e(p['observacao'])}</div>" if p["observacao"] else ""
    if cartao and p["n"] > 0:
        quem = f" · {texto_vezes(p['valor'], p['vezes'])}" + quem
    # Na agenda a etiqueta diz a forma; na ficha só precisa quando a cobrança é híbrida
    etiqueta = _chip_tipo(p["tipo"]) if mostrar_cliente or c["hibrida"] else ""
    return (
        f"<div class='pc {cor}{' pago' if p['paga'] else ''}'>{bloco}<div class='pc-corpo'>"
        f"<div class='pc-topo'><span class='pc-tag'>{topo}</span>"
        f"{etiqueta}{sit}</div>{nome}"
        f"<div class='pc-rot'>{_e(p['rotulo'])}{quem}</div>"
        f"<div class='pc-valor'>{formatar_brl(p['valor'])}</div>{obs}</div>{carimbo}</div>"
    )


def _parcela_ui(p: dict, c: dict, hoje: date, contexto: str, mostrar_cliente: bool = False):
    chave = f"{contexto}_{c['id']}_{p['n']}"
    with st.container(key=f"pc_{chave}"):
        st.markdown(_html_parcela(p, c, hoje, mostrar_cliente), unsafe_allow_html=True)
        if p["paga"]:
            if st.button("Ver pagamento", key=f"ver_{chave}", icon=":material/receipt:",
                         use_container_width=True):
                _dlg_ver(c["id"], p["n"])
            return
        botoes = st.columns(3 if mostrar_cliente else 2)
        rot_receber = "Passou" if p["tipo"] == TIPO_CARTAO else "Recebi"
        with botoes[0]:
            if st.button(rot_receber, key=f"rec_{chave}", icon=":material/check_circle:",
                         use_container_width=True):
                _dlg_receber(c["id"], p["n"])
        with botoes[1]:
            if st.button("Alterar", key=f"alt_{chave}", icon=":material/edit:", use_container_width=True):
                _dlg_alterar(c["id"], p["n"])
        if mostrar_cliente:
            with botoes[2]:
                if st.button("Cliente", key=f"cli_{chave}", icon=":material/person:",
                             use_container_width=True):
                    _abrir_cobranca(c["id"], "relatorio")


def _parcela_por_n(c: dict, n: int):
    return next((p for p in c["parcelas"] if p["n"] == n), None) if c else None


def _cab_dialogo(c: dict, p: dict):
    st.markdown(f"<div class='dl-cab'><b>{_e(c['cliente'])}</b><span>{_e(c['turma'])} · "
                f"{_e(p['rotulo'])} · {formatar_brl(p['valor'])}</span></div>", unsafe_allow_html=True)


@st.dialog("Confirmar recebimento")
def _dlg_receber(cid: str, n: int):
    c = _cobranca(cid)
    p = _parcela_por_n(c, n)
    if not p:
        st.error("Essa parcela não existe mais. Feche e atualize.")
        return
    _cab_dialogo(c, p)
    k = f"_rc_{cid}_{n}"   # chave com o ID: fechar no X não pode vazar campo para outra parcela
    cartao = p["tipo"] == TIPO_CARTAO   # a forma é a desta parcela
    quando = st.date_input("Passou em" if cartao else "Recebido em", value=_hoje(),
                           format="DD/MM/YYYY", key=f"{k}_data")
    vezes = p["vezes"]
    if cartao:
        vezes = int(st.number_input("Passou em quantas vezes", min_value=1,
                                    value=p["vezes"], step=1, key=f"{k}_vezes"))
        if not st.session_state.get(f"{k}_hib"):
            # HTML, não st.caption: dois "R$" na mesma linha viram fórmula ($...$) no markdown do Streamlit
            _info(f"{formatar_brl(p['valor'])} · <b>{texto_vezes(p['valor'], vezes)}</b>")

    # Pagamento híbrido desta parcela: uma parte veio na outra forma
    outra = "Pix" if cartao else "cartão"
    v_outra, divisao_ok = None, True
    dividir = st.toggle(f"Pagamento híbrido: uma parte foi no {outra}", key=f"{k}_hib")
    if dividir:
        v_outra, ok_o = _valor(f"Quanto foi no {outra}", f"{k}_outra")
        if not cartao:
            vezes = int(st.number_input("No cartão, em quantas vezes", min_value=1,
                                        value=1, step=1, key=f"{k}_hvezes"))
        divisao_ok = bool(ok_o and v_outra and 0 < centavos(v_outra) < centavos(p["valor"]))
        if divisao_ok:
            fica = p["valor"] - v_outra
            no_pix, no_cartao = (v_outra, fica) if cartao else (fica, v_outra)
            _info(f"{_chip_tipo(TIPO_PIX)} <b>{formatar_brl(no_pix)}</b> &nbsp;+&nbsp; {_chip_tipo(TIPO_CARTAO)} "
                  f"<b>{formatar_brl(no_cartao)}</b> ({texto_vezes(no_cartao, vezes)})")
        elif ok_o and v_outra is not None:
            _erro_campo(f"Tem que ser maior que zero e menor que {formatar_brl(p['valor'])}.")
    obs = st.text_input("Observação (opcional)", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: pago em permuta")
    arquivo = None
    sec = _secrets_drive()
    if sec:
        arquivo = st.file_uploader("Comprovante (opcional)", type=["pdf", "png", "jpg", "jpeg", "webp"],
                                   key=f"{k}_arq")
    if st.button("Confirmar", type="primary", key=f"{k}_ok", use_container_width=True,
                 icon=":material/check:"):
        if dividir and not divisao_ok:
            st.error(f"Diga quanto foi no {outra}: maior que zero e menor que {formatar_brl(p['valor'])}.")
            return
        link = ""
        if arquivo is not None:
            try:
                with st.spinner("Enviando comprovante..."):
                    link = enviar_comprovante(sec, arquivo.getvalue(), arquivo.name, (c["treinamentos"] or [""])[0],
                                              f"{c['cliente']} - {c['turma']} - {p['rotulo']}", quando)
            except Exception as e:
                st.error(f"O comprovante não subiu ({e}). Nada foi marcado; tente de novo "
                         "ou confirme sem o comprovante.")
                return
        pagamento = {"Pago em": quando, "Comprovante": link, "Marcado por": _usuario(),
                     "Observação": obs.strip().upper()}
        try:
            if dividir:
                da_parcela, nova = dividir_recebimento(p, v_outra, proximo_numero(c["parcelas"]), vezes,
                                                       pagamento)
                ok = receber_em_duas_formas(_banco(), cid, n, da_parcela, nova)
            else:
                ok = _banco().atualizar_parcela(cid, n, {"Status": STATUS_PAGA, **pagamento,
                                                        **({"Vezes no cartão": vezes} if cartao else {})})
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        if not ok:
            st.error("Essa parcela não foi encontrada na planilha. Atualize a tela.")
            return
        _invalidar()
        _flash(f"{p['rotulo']} de {c['cliente']} marcada como paga"
               + (": parte no Pix, parte no cartão" if dividir else ""))
        st.rerun()


@st.dialog("Pagamento")
def _dlg_ver(cid: str, n: int):
    c = _cobranca(cid)
    p = _parcela_por_n(c, n)
    if not p:
        st.error("Essa parcela não existe mais.")
        return
    _cab_dialogo(c, p)
    linhas = [f"Pago em <b>{data_br(p['pago_em'])}</b>" if p["pago_em"] else "Paga"]
    if p["marcado_por"]:
        linhas.append(f"Marcado por {_e(p['marcado_por'])}")
    _info("<br>".join(linhas), "cx-ok")
    link = _url_segura(p["comprovante"])
    if link:
        st.link_button("Abrir comprovante", link, icon=":material/open_in_new:", use_container_width=True)
    k = f"_vp_{cid}_{n}"
    obs = st.text_input("Observação", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: pago em permuta")
    if obs.strip().upper() != p["observacao"].upper() and st.button("Salvar observação", key=f"{k}_obs_ok", type="primary",
                                                    icon=":material/check:", use_container_width=True):
        try:
            _banco().atualizar_parcela(cid, n, {"Observação": obs.strip().upper()})
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Observação salva")
        st.rerun()
    if not st.session_state.get(f"{k}_conf"):
        if st.button("Desmarcar pagamento", key=f"{k}_des", type="tertiary", icon=":material/undo:"):
            st.session_state[f"{k}_conf"] = True
            st.rerun(scope="fragment")
    else:
        _info("Tem certeza? A parcela volta a ficar em aberto.", "cx-perigo")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Não", key=f"{k}_nao", use_container_width=True):
                st.session_state[f"{k}_conf"] = False
                st.rerun(scope="fragment")
        with c2:
            if st.button("Sim, desmarcar", key=f"{k}_sim", use_container_width=True):
                st.session_state[f"{k}_conf"] = False
                try:
                    _banco().atualizar_parcela(cid, n, {"Status": "", "Pago em": "", "Comprovante": "",
                                                        "Marcado por": ""})
                except Exception as e:
                    st.error(f"Não consegui salvar: {_erro_curto(e)}")
                    return
                _invalidar()
                _flash("Pagamento desmarcado")
                st.rerun()


@st.dialog("Alterar")
def _dlg_alterar(cid: str, n: int):
    c = _cobranca(cid)
    p = _parcela_por_n(c, n)
    if not p:
        st.error("Essa parcela não existe mais.")
        return
    _cab_dialogo(c, p)
    k = f"_al_{cid}_{n}"
    nova_data = st.date_input("Data", value=p["vencimento"], format="DD/MM/YYYY", key=f"{k}_data")
    novo_valor, ok_v = _valor("Valor", f"{k}_valor", placeholder=_num_br(p['valor']),
                              help="Em branco = continua o mesmo valor.")
    # Trocar a forma de UMA parcela é o que torna a cobrança híbrida (ex.: essa vai ser no cartão)
    forma = st.radio("Forma de pagamento", FORMAS, index=FORMAS.index(p["tipo"]), horizontal=True,
                     key=f"{k}_forma")
    vezes = p["vezes"]
    if forma == TIPO_CARTAO and p["n"] > 0:
        vezes = int(st.number_input("Parcelado em quantas vezes", min_value=1,
                                    value=p["vezes"], step=1, key=f"{k}_vezes"))
    obs = st.text_input("Observação (opcional)", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: combinou pagar em permuta")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not ok_v or not nova_data or (novo_valor is not None and novo_valor <= 0):
            st.error("Confira a data e o valor.")
            return
        campos = {"Vencimento": nova_data, "Observação": obs.strip().upper()}
        if forma != p["tipo"]:
            campos["Forma"] = forma
        if forma == TIPO_CARTAO and p["n"] > 0:
            campos["Vezes no cartão"] = vezes
        if novo_valor is not None:
            campos["Valor"] = novo_valor
        try:
            _banco().atualizar_parcela(cid, n, campos)
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Alterado")
        st.rerun()

    st.markdown("<div class='cx-divisa'></div>", unsafe_allow_html=True)
    if not st.session_state.get(f"{k}_rm"):
        if st.button("Remover esta parcela", key=f"{k}_remover", type="tertiary", icon=":material/delete:"):
            st.session_state[f"{k}_rm"] = True
            st.rerun(scope="fragment")
    else:
        _info(f"Remover <b>{_e(p['rotulo'])}</b> de {formatar_brl(p['valor'])}? "
              "O valor sai do que falta receber.", "cx-perigo")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Não", key=f"{k}_rm_nao", use_container_width=True):
                st.session_state[f"{k}_rm"] = False
                st.rerun(scope="fragment")
        with c2:
            if st.button("Sim, remover", key=f"{k}_rm_sim", use_container_width=True):
                st.session_state[f"{k}_rm"] = False
                try:
                    _banco().remover_parcela(cid, n)
                except Exception as e:
                    st.error(f"Não consegui remover: {_erro_curto(e)}")
                    return
                _invalidar()
                _flash("Parcela removida")
                st.rerun()


@st.dialog("Adicionar")
def _dlg_adicionar(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    k = f"_ad_{cid}"
    ultima = c["ultima"] or _hoje()
    # Vem na forma da cobrança (na híbrida com uma forma de dinheiro só, ex. cartão + permuta, vem
    # nela); escolher a outra é o que torna a cobrança híbrida
    dinheiro = [f for f in c.get("formas", []) if f in FORMAS]
    padrao = dinheiro[0] if len(dinheiro) == 1 else (c["tipo"] if c["tipo"] in FORMAS else TIPO_PIX)
    forma = st.radio("Forma de pagamento", FORMAS, index=FORMAS.index(padrao), horizontal=True,
                     key=f"{k}_forma")
    data = st.date_input("Data", value=mes_mais(ultima, 1) if forma == TIPO_PIX else None,
                         format="DD/MM/YYYY", key=f"{k}_data" if forma == padrao else f"{k}_data_{forma}")
    valor, ok_v = _valor("Valor", f"{k}_valor")
    vezes = 1
    if forma == TIPO_CARTAO:
        vezes = int(st.number_input("Parcelado em quantas vezes", min_value=1,
                                    value=1, step=1, key=f"{k}_vezes"))
    if st.button("Adicionar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/add:"):
        if not data or not ok_v or not valor:
            st.error("Preencha a data e o valor.")
            return
        try:
            _banco().adicionar_parcela(cid, {"Nº": proximo_numero(c["parcelas"]), "Vencimento": data,
                                             "Valor": valor, "Forma": forma,
                                             **({"Vezes no cartão": vezes} if forma == TIPO_CARTAO else {})})
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Adicionado")
        st.rerun()


@st.dialog("Observações")
def _dlg_obs(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    st.markdown(f"<div class='dl-cab'><b>{_e(c['cliente'])}</b><span>Anotação só para o registro de vocês "
                "(ex.: parte paga em permuta).</span></div>", unsafe_allow_html=True)
    k = f"_ob_{cid}"
    txt = st.text_area("Observações", value=c["observacoes"], key=f"{k}_txt", height=150, max_chars=1500,
                       label_visibility="collapsed", placeholder="Escreva aqui…")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        try:
            _banco().atualizar_cobranca(cid, {"Observações": txt.strip().upper()})
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Observação salva")
        st.rerun()


@st.dialog("Editar dados")
def _dlg_editar(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    k = f"_ed_{cid}"
    cliente = st.text_input("Nome do cliente", value=c["cliente"], key=f"{k}_cli").strip()
    tel = st.text_input("Telefone (opcional)", value=c["telefone"], key=f"{k}_{CHAVE_TEL}", max_chars=25,
                        placeholder="Ex.: (51) 99999-8888")
    if not telefone_valido(tel):
        _erro_campo("Telefone incompleto. Ex.: (51) 99999-8888, ou deixe em branco.")
    turma_txt = st.text_input("Turma", value=c["turma"], key=f"{k}_turma",
                              help="Mais de uma turma: separe com vírgula. Ex.: L345, V12")
    turmas = normalizar_turmas(turma_txt)
    if turmas:
        _info(" &nbsp;·&nbsp; ".join(f"Turma <b>{t}</b> · {TREINAMENTOS[t[0]]}" for t in turmas))
    else:
        _erro_campo("Turma não reconhecida. Ex.: L345 (ou L345, V12)")
    cidade = st.text_input("Cidade da turma", value=c["cidade"], key=f"{k}_cidade", max_chars=40,
                           placeholder="Ex.: Lajeado, SCS…")
    if c["permuta"]:   # o total da permuta é a soma dos valores, que mudam na ficha
        total, ok_t = None, True
        _info("O total da permuta é a soma dos valores: para mudar, use <b>Adicionar valor</b> ou "
              "<b>Alterar</b> na ficha.", "cx-nota")
    else:
        total, ok_t = _valor("Valor total", f"{k}_total", placeholder=_num_br(c["valor_total"] or 0),
                             help="Em branco = continua o mesmo.")
    obs = st.text_area("Observações", value=c["observacoes"], key=f"{k}_obs", height=80)
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not cliente or not turmas or not ok_t or not telefone_valido(tel):
            st.error("Confira o nome, o telefone, a turma e o valor.")
            return
        campos = {"Cliente": cliente.upper(), "Turma": SEP_TURMAS_PLANILHA.join(turmas),
                  "Treinamento": SEP_TURMAS_PLANILHA.join(treinamentos_das_turmas(turmas)),
                  "Observações": obs.strip().upper(), "Cidade": " ".join(cidade.split()).upper(),
                  "Telefone": formatar_telefone(tel)}
        if total:
            campos["Valor Total"] = total
        try:
            _banco().atualizar_cobranca(cid, campos)
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Dados salvos")
        st.rerun()


@st.dialog("Excluir cobrança")
def _dlg_excluir(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    _info(f"Excluir a cobrança de <b>{_e(c['cliente'])}</b> ({_e(c['turma'])} · {_e(_nome_tipo(c))})?<br>"
          "Ela some do relatório e dos avisos. Dá para restaurar em "
          "<b>Cobranças excluídas</b>, na tela inicial.", "cx-perigo")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Não, manter", key=f"_ex_{cid}_nao", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("Sim, excluir", key=f"_ex_{cid}_sim", use_container_width=True):
            try:
                excluir_cobranca(_banco(), cid, _hoje())
            except Exception as e:
                st.error(f"Não consegui excluir: {_erro_curto(e)}")
                return
            _invalidar()
            _esquecer_id(cid)
            _flash("Cobrança excluída")
            st.session_state.tela = st.session_state.get("cob_volta", "relatorio")
            st.rerun()


# ── Ficha da cobrança ─────────────────────────────────────────────────────────

def _contato(c: dict):
    """Telefone do cliente no topo da ficha, com Ligar e WhatsApp (pedido 26/10)."""
    tel = c.get("telefone", "")
    if not tel:
        return
    with st.container(key="fc_contato"):
        st.markdown(f"<div class='fc-tel'><span class='fc-tel-num'>{_e(tel)}</span></div>", unsafe_allow_html=True)
        ligar, whats = link_ligar(tel), link_whatsapp(tel)
        cols = st.columns(2) if ligar and whats else [st.container()]
        if ligar:
            with cols[0]:
                st.link_button("Ligar", ligar, icon=":material/call:", use_container_width=True)
        if whats:
            with cols[-1]:
                st.link_button("WhatsApp", whats, icon=":material/chat:", use_container_width=True)


def tela_cobranca():
    hoje = _hoje()
    cid = st.session_state.get("cob_id")
    volta = st.session_state.get("cob_volta", "relatorio")
    c = _cobranca(cid) if cid else None
    if not c or c["excluida"]:
        _cabecalho("Cobrança", voltar_para=volta)
        st.info("Essa cobrança não está mais disponível.")
        return
    _cabecalho(c["cliente"], voltar_para=volta,
               subtitulo=f"Turma {_e(local_da_cobranca(c))} · {_e(_nome_tipo(c))}")
    _contato(c)
    if c["permuta"]:
        _ficha_permuta(c)
        return

    dinheiro_total = c["pago"] + c["falta"]
    # Total = o combinado de tudo: o dinheiro (Pix e cartão) + a parte na permuta, se tiver (pedido 06/11)
    total = dinheiro_total + (c["total_permuta"] if c["com_permuta"] else 0.0)
    pct = _pct(c["pago"], dinheiro_total)
    selo = "<span class='sit c-ok'>Quitado</span>" if c["situacao"] == CLI_QUITADO else _chip_sit(c["situacao"])
    ate = f"Vai até <b>{nome_mes(c['ultima'])}</b>" if c["ultima"] else ""
    quem = ""
    if c["criada_por"] or c["criada_em"]:
        por = f" por <b>{_e(c['criada_por'])}</b>" if c["criada_por"] else ""
        em = f" em {data_br(c['criada_em'])}" if c["criada_em"] else ""
        quem = f"<div class='fc-quem'>Cadastrada{por}{em}</div>"
    aviso_total = ""
    if c["valor_total"] and abs(conferir_total(c["valor_total"], [total])) >= 0.005:
        aviso_total = (f"<div class='fc-aviso'>O total combinado é {formatar_brl(c['valor_total'])}, "
                       f"mas as {'partes' if c['com_permuta'] else 'parcelas'} somam {formatar_brl(total)}.</div>")
    # Híbrida: quanto é de cada forma e quanto de cada uma já entrou (a permuta: retirado e saldo)
    formas = ""
    if c["hibrida"]:
        itens = []
        for f in c["formas"]:
            pf = c["por_forma"][f]
            if f == TIPO_PERMUTA:
                brl = lambda v: formatar_brl(v).replace(" ", "&nbsp;")   # "R$" nunca sozinho no fim da linha
                itens.append(f"<div>{_chip_tipo(f)}<span>retirado <b>{brl(pf['pago'])}</b> de "
                             f"{brl(pf['total'])} · saldo <b>{brl(max(pf['saldo'], 0))}</b>"
                             "</span></div>")
            else:
                verbo = "passou" if f == TIPO_CARTAO else "pago"
                itens.append(f"<div>{_chip_tipo(f)}<span>{verbo} <b>{formatar_brl(pf['pago'])}</b> "
                             f"de {formatar_brl(pf['total'])}</span></div>")
        formas = "<div class='fc-formas'>" + "".join(itens) + "</div>"
    st.markdown(
        f"<div class='fc {COR_CLI[c['situacao']]}'><div class='fc-topo'>{selo}<span>{ate}</span></div>"
        # Total da cobrança (pedido 03/11): facilita para quem vai cobrar
        f"<div class='fc-total'><span>Total</span><b>{formatar_brl(total)}</b></div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='fc-nums'><div><b>{formatar_brl(c['pago'])}</b><span>Pago</span></div>"
        f"<div><b>{formatar_brl(c['falta'])}</b><span>Falta</span></div>"
        f"<div class='{'atr' if c['atrasado'] else ''}'><b>{formatar_brl(c['atrasado'])}</b><span>Atrasado</span></div>"
        f"</div>{formas}{aviso_total}{quem}</div>",
        unsafe_allow_html=True,
    )
    _bloco_obs_ficha(c)

    dinheiro = [f for f in c["formas"] if f in FORMAS]
    if c["hibrida"] or c["com_permuta"]:
        # Um bloco para cada forma: primeiro tudo que é Pix, depois tudo que é cartão; a permuta no fim
        for forma in dinheiro:
            st.markdown(f"<div class='fc-grupo'>{'No cartão' if forma == TIPO_CARTAO else 'No Pix'}</div>",
                        unsafe_allow_html=True)
            for p in c["parcelas"]:
                if p["tipo"] == forma:
                    _parcela_ui(p, c, hoje, contexto="fc")
    else:
        for p in c["parcelas"]:
            _parcela_ui(p, c, hoje, contexto="fc")

    if not dinheiro and c["tipo"] in FORMAS:
        dinheiro = [c["tipo"]]
    rot_add = ("Adicionar parcela ou data" if len(dinheiro) > 1 else
               "Adicionar data" if dinheiro == [TIPO_CARTAO] else "Adicionar parcela")
    if st.button(rot_add, key="fc_add", icon=":material/add:", use_container_width=True):
        _dlg_adicionar(c["id"])

    if c["com_permuta"]:
        # Parte na permuta da híbrida (pedido 06/11): o saldo dela, cada valor e cada retirada
        st.markdown("<div class='fc-grupo'>Na permuta</div>", unsafe_allow_html=True)
        st.markdown(_html_numeros_permuta(c), unsafe_allow_html=True)
        _listas_permuta(c, classe_titulo="px-lista")
    _botoes_editar_excluir(c)


def _bloco_obs_ficha(c: dict):
    with st.container(key="fc_obs"):
        if c["observacoes"]:
            st.markdown("<div class='ob'><span>Observações</span>"
                        + _e(c["observacoes"]).replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
        if st.button("Editar observação" if c["observacoes"] else "Anotar observação", key="fc_obs_btn",
                     icon=":material/edit_note:", use_container_width=True):
            _dlg_obs(c["id"])


def _botoes_editar_excluir(c: dict):
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Editar dados", key="fc_editar", icon=":material/edit:", use_container_width=True):
            _dlg_editar(c["id"])
    with c2:
        if st.button("Excluir", key="fc_excluir", icon=":material/delete:", use_container_width=True):
            _dlg_excluir(c["id"])


# ── Ficha da permuta ──────────────────────────────────────────────────────────

def _bloco_data(d) -> str:
    return (f"<div class='pc-data'><span class='pc-mes'>{MESES_ABREV[d.month - 1]} {d.year}</span>"
            f"<span class='pc-dia'>{d.day}</span><span class='pc-sem'>{DIAS_SEMANA[d.weekday()]}</span></div>"
            if d else "<div class='pc-data'><span class='pc-dia'>?</span></div>")


def _html_retirada(p: dict) -> str:
    quem = f"<br><span class='pc-quem'>{_e(p['marcado_por'])} registrou</span>" if p["marcado_por"] else ""
    obs = f"<div class='pc-obs'>{_e(p['observacao'])}</div>" if p["observacao"] else ""
    return (f"<div class='pc c-ret'>{_bloco_data(p['vencimento'])}<div class='pc-corpo'>"
            f"<div class='pc-nome'>{_e(p['produto'] or 'Retirada')}</div>"
            f"<div class='pc-rot'>Retirada{quem}</div>"
            f"<div class='pc-valor'>{formatar_brl(p['valor'])}</div>{obs}</div></div>")


def _html_valor_permuta(d, valor: float, quem: str = "") -> str:
    quem = f"<br><span class='pc-quem'>{_e(quem)} registrou</span>" if quem else ""
    return (f"<div class='pc c-cred'>{_bloco_data(d)}<div class='pc-corpo'>"
            f"<div class='pc-nome'>Valor da permuta</div>"
            f"<div class='pc-rot'>Entrou no saldo{quem}</div>"
            f"<div class='pc-valor'>+ {formatar_brl(valor)}</div></div></div>")


def _chip_saldo(c: dict) -> str:
    """Situação da permuta (inteira ou a parte de uma híbrida): com saldo ou saldo zerado."""
    return ("<span class='sit c-ok'>Com saldo</span>" if c["saldo"] > 0.005
            else "<span class='sit c-neutro'>Saldo zerado</span>")


def _html_numeros_permuta(c: dict, rodape: str = "") -> str:
    """Cartão com Total da permuta, Retirado e Saldo (na permuta inteira e na parte de uma híbrida)."""
    total, retirado, saldo = c["total_permuta"], c["retirado"], c["saldo"]
    aviso = (f"<div class='fc-aviso'>As retiradas passam do total da permuta em {formatar_brl(-saldo)}.</div>"
             if saldo < -0.005 else "")
    n_ret = len(c["retiradas"])
    return (
        f"<div class='fc {'c-ok' if saldo > 0.005 else 'c-neutro'}'><div class='fc-topo'>{_chip_saldo(c)}"
        f"<span>{n_ret} retirada{'s' if n_ret != 1 else ''}</span></div>"
        f"<div class='pg'><i style='width:{_pct(retirado, total)}%'></i></div>"
        f"<div class='fc-nums fc-perm'><div><b>{formatar_brl(total)}</b><span>Total da permuta</span></div>"
        f"<div><b>{formatar_brl(retirado)}</b><span>Retirado</span></div>"
        f"<div><b>{formatar_brl(max(saldo, 0))}</b><span>Saldo</span></div>"
        f"</div>{aviso}{rodape}</div>"
    )


def _ficha_permuta(c: dict):
    """Total (soma dos valores), retirado e saldo; cada valor com a data e cada retirada."""
    quem = ""
    if c["criada_por"] or c["criada_em"]:
        por = f" por <b>{_e(c['criada_por'])}</b>" if c["criada_por"] else ""
        em = f" em {data_br(c['criada_em'])}" if c["criada_em"] else ""
        quem = f"<div class='fc-quem'>Cadastrada{por}{em}</div>"
    st.markdown(_html_numeros_permuta(c, quem), unsafe_allow_html=True)
    _bloco_obs_ficha(c)
    _listas_permuta(c, classe_titulo="fc-grupo")

    # permuta do mesmo cliente cadastrada à parte (antes do "+" dos valores existir)
    saldo = c["saldo"]
    outras = permutas_do_cliente(_cobrancas() or [], c["cliente"], menos=c["id"])
    if outras:
        st.markdown(f"<div class='fc-grupo'>Outras permutas de {_e(c['cliente'])}</div>", unsafe_allow_html=True)
        soma = sum(max(x["saldo"], 0) for x in outras) + max(saldo, 0)
        _info(f"Somando as {len(outras) + 1} permutas: <b>{formatar_brl(soma)}</b> de saldo para retirar.")
        for x in sorted(outras, key=lambda x: x["criada_em"] or date.min):
            if _cartao_toque(f"cc_{x['id']}", f"tq_{x['id']}", f"Abrir permuta de {x['cliente']}",
                             _html_cliente(x, _hoje())):
                _abrir_cobranca(x["id"], st.session_state.get("cob_volta", "relatorio"))
    _botoes_editar_excluir(c)


def _listas_permuta(c: dict, classe_titulo: str):
    """
    Valores da permuta (cada um com a data, Alterar e "Adicionar valor") e Retiradas (Alterar e
    "Adicionar retirada"). Na ficha da permuta os títulos são grandes (fc-grupo); dentro do bloco
    "Na permuta" de uma híbrida, pequenos (px-lista).
    """
    total, saldo = c["total_permuta"], c["saldo"]
    # cada valor que entrou, com a data (a pessoa pode fechar outra permuta depois)
    st.markdown(f"<div class='{classe_titulo}'>Valores da permuta</div>", unsafe_allow_html=True)
    if c["creditos"]:
        for p in sorted(c["creditos"], key=lambda p: (p["vencimento"] or date.min, p["n"])):
            with st.container(key=f"pc_cr_{c['id']}_{p['n']}"):
                st.markdown(_html_valor_permuta(p["vencimento"], p["valor"], p["marcado_por"]),
                            unsafe_allow_html=True)
                if st.button("Alterar", key=f"cr_alt_{c['id']}_{p['n']}", icon=":material/edit:",
                             use_container_width=True):
                    _dlg_valor_permuta(c["id"], p["n"])
    elif c["permuta"]:   # permuta das primeiras versões: só o valor total, sem linha própria
        with st.container(key=f"pc_cr_{c['id']}_base"):
            st.markdown(_html_valor_permuta(c["criada_em"], total, c["criada_por"]), unsafe_allow_html=True)
    else:
        st.markdown("<div class='cx-vazio'>Nenhum valor de permuta.</div>", unsafe_allow_html=True)
    if st.button("Adicionar valor", key="fc_add_cred", icon=":material/add:", use_container_width=True,
                 help="Fechou mais uma permuta com essa pessoa? Põe o valor novo com a data dele."):
        _dlg_valor_permuta(c["id"])

    st.markdown(f"<div class='{classe_titulo}'>Retiradas</div>", unsafe_allow_html=True)
    if not c["retiradas"]:
        st.markdown("<div class='cx-vazio'>Nada retirado ainda.</div>", unsafe_allow_html=True)
    for p in sorted(c["retiradas"], key=lambda p: (p["vencimento"] or date.min, p["n"])):
        with st.container(key=f"pc_rt_{c['id']}_{p['n']}"):
            st.markdown(_html_retirada(p), unsafe_allow_html=True)
            if st.button("Alterar", key=f"rt_alt_{c['id']}_{p['n']}", icon=":material/edit:",
                         use_container_width=True):
                _dlg_retirada(c["id"], p["n"])
    if st.button("Adicionar retirada", key="fc_add_ret", icon=":material/add:", use_container_width=True,
                 type="primary" if saldo > 0.005 else "secondary"):
        _dlg_retirada(c["id"])


@st.dialog("Valor da permuta")
def _dlg_valor_permuta(cid: str, n: int | None = None):
    """Valor novo da permuta (n=None: a pessoa fechou outra permuta) ou alterar/remover um que existe."""
    c = _cobranca(cid)
    p = next((x for x in c["creditos"] if x["n"] == n), None) if (c and n is not None) else None
    if not c or (n is not None and not p):
        st.error("Esse valor não existe mais. Feche e atualize.")
        return
    total = c["total_permuta"]
    st.markdown(f"<div class='dl-cab'><b>{_e(c['cliente'])}</b><span>Total hoje: {formatar_brl(total)} · "
                f"saldo {formatar_brl(max(c['saldo'], 0))}</span></div>", unsafe_allow_html=True)
    k = f"_cr_{cid}_{n}"
    valor, ok_v = _valor("Valor da permuta", f"{k}_valor", placeholder=_num_br(p["valor"]) if p else "0,00",
                         help="Em branco = continua o mesmo." if p else "Quanto essa nova permuta vale.")
    data = st.date_input("Data da permuta", value=(p["vencimento"] if p else _hoje()), format="DD/MM/YYYY",
                         key=f"{k}_data", help="O dia em que vocês fecharam essa permuta.")
    # Só na permuta INTEIRA o "Valor Total" é a soma dos valores. Na híbrida ele é o combinado de tudo
    # (Pix, cartão e permuta) e não muda sozinho, igual quando se altera uma parcela (pedido 06/11).
    inteira = c["permuta"]
    if not inteira:
        _info("Isto muda só a parte da permuta. O total combinado da cobrança continua o mesmo: "
              "se ele mudou, ajuste em <b>Editar dados</b>.", "cx-nota")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not data or not ok_v or (p is None and not valor) or (valor is not None and valor <= 0):
            st.error("Preencha o valor e a data.")
            return
        b = _banco()
        try:
            if p:
                campos = {"Vencimento": data, "Pago em": data, **({"Valor": valor} if valor else {})}
                b.atualizar_parcela(cid, n, campos)
                novo_total = total - p["valor"] + (valor or p["valor"])
            else:
                proximo = proximo_numero(c["parcelas"])
                linha = {"Status": STATUS_PAGA, "Forma": TIPO_CREDITO, "Marcado por": _usuario()}
                if inteira and not c["creditos"] and total > 0:
                    # permuta antiga (só com o total): o total vira o 1º valor, na data do cadastro
                    base = c["criada_em"] or _hoje()
                    b.adicionar_parcela(cid, {**linha, "Nº": proximo, "Vencimento": base, "Pago em": base,
                                              "Valor": total, "Marcado por": c["criada_por"]})
                    proximo += 1
                b.adicionar_parcela(cid, {**linha, "Nº": proximo, "Vencimento": data, "Pago em": data,
                                          "Valor": valor})
                novo_total = total + valor
            if inteira:
                b.atualizar_cobranca(cid, {"Valor Total": novo_total})   # "Valor Total" acompanha a soma
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Valor da permuta salvo")
        st.rerun()
    if p:
        st.markdown("<div class='cx-divisa'></div>", unsafe_allow_html=True)
        if not st.session_state.get(f"{k}_rm"):
            if st.button("Remover este valor", key=f"{k}_remover", type="tertiary", icon=":material/delete:"):
                st.session_state[f"{k}_rm"] = True
                st.rerun(scope="fragment")
        else:
            _info(f"Remover o valor de {formatar_brl(p['valor'])} ({data_br(p['vencimento'])})? "
                  + ("Ele sai do total e do saldo." if inteira else "Ele sai do total e do saldo da permuta."),
                  "cx-perigo")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Não", key=f"{k}_rm_nao", use_container_width=True):
                    st.session_state[f"{k}_rm"] = False
                    st.rerun(scope="fragment")
            with c2:
                if st.button("Sim, remover", key=f"{k}_rm_sim", use_container_width=True):
                    st.session_state[f"{k}_rm"] = False
                    try:
                        _banco().remover_parcela(cid, n)
                        if inteira:
                            _banco().atualizar_cobranca(cid, {"Valor Total": total - p["valor"]})
                    except Exception as e:
                        st.error(f"Não consegui remover: {_erro_curto(e)}")
                        return
                    _invalidar()
                    _flash("Valor removido")
                    st.rerun()


@st.dialog("Retirada")
def _dlg_retirada(cid: str, n: int | None = None):
    """Anotar uma retirada nova (n=None) ou alterar/remover uma que já existe."""
    c = _cobranca(cid)
    p = _parcela_por_n(c, n) if (c and n is not None) else None
    if not c or (n is not None and not p):
        st.error("Essa retirada não existe mais. Feche e atualize.")
        return
    disponivel = c["saldo"] + (p["valor"] if p else 0)
    st.markdown(f"<div class='dl-cab'><b>{_e(c['cliente'])}</b><span>Saldo para retirar: "
                f"{formatar_brl(max(disponivel, 0))}</span></div>", unsafe_allow_html=True)
    k = f"_rt_{cid}_{n}"
    produto = st.text_input("Produto", value=p["produto"] if p else "", key=f"{k}_prod", max_chars=120,
                            placeholder="Ex.: 10 camisetas, 2 jantares…")
    data = st.date_input("Data da retirada", value=(p["vencimento"] if p else _hoje()), format="DD/MM/YYYY",
                         key=f"{k}_data")
    valor, ok_v = _valor("Quanto desconta do saldo", f"{k}_valor",
                         placeholder=_num_br(p["valor"]) if p else "0,00",
                         help="Em branco = continua o mesmo." if p else "Quanto essa retirada desconta do saldo.")
    usado = valor if valor is not None else (p["valor"] if p else 0)
    if usado and centavos(usado) > centavos(disponivel):
        _erro_campo(f"Passa do saldo ({formatar_brl(max(disponivel, 0))}). Dá para salvar assim mesmo.")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        falta_valor = p is None and not valor
        if not produto.strip() or not data or not ok_v or falta_valor or (valor is not None and valor <= 0):
            st.error("Preencha o produto, a data e quanto desconta.")
            return
        campos = {"Produto": " ".join(produto.split()).upper(), "Vencimento": data, "Pago em": data}
        if valor is not None:
            campos["Valor"] = valor
        try:
            if p:
                _banco().atualizar_parcela(cid, n, campos)
            else:
                _banco().adicionar_parcela(cid, {**campos, "Nº": proximo_numero(c["parcelas"]),
                                                 "Status": STATUS_PAGA, "Forma": TIPO_PERMUTA,
                                                 "Marcado por": _usuario()})
        except Exception as e:
            st.error(f"Não consegui salvar: {_erro_curto(e)}")
            return
        _invalidar()
        _flash("Retirada salva")
        st.rerun()
    if p:
        st.markdown("<div class='cx-divisa'></div>", unsafe_allow_html=True)
        if not st.session_state.get(f"{k}_rm"):
            if st.button("Remover esta retirada", key=f"{k}_remover", type="tertiary", icon=":material/delete:"):
                st.session_state[f"{k}_rm"] = True
                st.rerun(scope="fragment")
        else:
            _info(f"Remover <b>{_e(p['produto'] or 'a retirada')}</b> de {formatar_brl(p['valor'])}? "
                  "O valor volta para o saldo.", "cx-perigo")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Não", key=f"{k}_rm_nao", use_container_width=True):
                    st.session_state[f"{k}_rm"] = False
                    st.rerun(scope="fragment")
            with c2:
                if st.button("Sim, remover", key=f"{k}_rm_sim", use_container_width=True):
                    st.session_state[f"{k}_rm"] = False
                    try:
                        _banco().remover_parcela(cid, n)
                    except Exception as e:
                        st.error(f"Não consegui remover: {_erro_curto(e)}")
                        return
                    _invalidar()
                    _flash("Retirada removida")
                    st.rerun()


# ── Cobranças excluídas ───────────────────────────────────────────────────────

def tela_excluidas():
    _cabecalho("Cobranças excluídas", voltar_para="inicio")
    todas = _cobrancas(incluir_excluidas=True)
    if todas is None:
        return
    excl = sorted((c for c in todas if c["excluida"]),
                  key=lambda c: c["excluida_em"] or date.min, reverse=True)
    if not excl:
        st.markdown("<div class='cx-vazio'>Nenhuma cobrança excluída.</div>", unsafe_allow_html=True)
        return
    for c in excl:
        with st.container(key=f"lx_{c['id']}"):
            quando = f"Excluída em {data_br(c['excluida_em'])}" if c["excluida_em"] else "Excluída"
            st.markdown(
                f"<div class='lx-nome'>{_e(c['cliente'])}</div>"
                f"<div class='lx-meta'>{_e(c['turma'])} · {_e(_nome_tipo(c))} · pago {formatar_brl(c['pago'])}"
                f" · falta {formatar_brl(c['falta'])}"
                + (f" · saldo da permuta {formatar_brl(max(c['saldo'], 0))}" if c["com_permuta"] and not c["permuta"]
                   else "")
                + f"</div><div class='lx-prazo'>{quando}</div>",
                unsafe_allow_html=True)
            if st.button("Restaurar", key=f"lxr_{c['id']}", icon=":material/restore:"):
                try:
                    restaurar_cobranca(_banco(), c["id"])
                except Exception as e:
                    st.error(f"Não consegui restaurar: {_erro_curto(e)}")
                    return
                _invalidar()
                _flash(f"Cobrança de {c['cliente']} restaurada")
                st.rerun()


# ── Jurídico (pedido 03/11) ───────────────────────────────────────────────────
# Tela inicial → Jurídico → Cobranças judiciais | Protestos. Cada um na sua aba da planilha
# (_Judicial e _Protestos): nada daqui entra no relatório, na agenda nem nos avisos do Telegram.
# Decisões do Pedro (03/11): nome "Jurídico"; acordo parcelado com UMA DATA POR PARCELA; marcar
# parcela do acordo como paga só nessa tela; todo mundo do app vê e mexe.

COR_JUD = {**COR_CLI, JUD_SEM_ACORDO: "c-neutro"}
NEGOCIACOES = {"Ainda não": NEG_SEM, "Acordo à vista": NEG_A_VISTA, "Parcelado": NEG_PARCELADO}
_NEG_TELA = {v: k for k, v in NEGOCIACOES.items()}


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _chip(texto: str, atraso: bool = False) -> str:
    return f"<span class='hm-chip{' atraso' if atraso else ''}'>{texto}</span>"


def _chips_juridico() -> str:
    """Contagem do Jurídico no cartão da tela inicial (some quando não tem nada cadastrado)."""
    jur = _juridico()
    if not jur:
        return ""
    r = resumo_juridico(*jur)
    partes = []
    if r["n_atrasados"]:
        partes.append(_chip(_plural(r["n_atrasados"], "acordo atrasado", "acordos atrasados"), atraso=True))
    if r["n_judiciais"]:
        partes.append(_chip(f"{r['n_judiciais']} na justiça"))
    if r["n_protestos_abertos"]:
        partes.append(_chip(_plural(r["n_protestos_abertos"], "protesto em aberto", "protestos em aberto")))
    return f"<div class='hm-chips'>{''.join(partes)}</div>" if partes else ""


def _rodape_quem():
    """'Usando como X · sair' (ou só o nome, na trava por aparelho), igual ao da tela inicial."""
    if _usuario() and _login_ligado():
        if st.button(f"Usando como {_usuario()} · sair", key="btn_sair_google", icon=":material/logout:",
                     type="tertiary", help="Sai do Gmail neste aparelho. Para entrar de novo, é só tocar em "
                                           "Entrar com Google."):
            _sair_google()
    elif _usuario():
        st.markdown(f"<div class='hm-quem'>Usando como <b>{_e(_usuario())}</b></div>", unsafe_allow_html=True)


def tela_juridico():
    restrito = _so_juridico()
    if restrito:
        # Para quem só tem o Jurídico, esta é a tela inicial: sem "Voltar" (não há para onde voltar)
        hoje = _hoje()
        st.markdown(f"<div class='hm-data'>{DIAS_SEMANA_LONGO[hoje.weekday()]}, {hoje.day} de "
                    f"{MESES[hoje.month - 1].lower()}</div><div class='hm-marca'>Jurídico</div>",
                    unsafe_allow_html=True)
    else:
        _cabecalho("Jurídico", voltar_para="inicio", subtitulo="Clientes cobrados na justiça e títulos protestados")
    jur = _juridico()
    chips_jud = chips_prot = ""
    if jur:
        r = resumo_juridico(*jur)
        if r["n_judiciais"]:
            partes = [_chip(_plural(r["n_judiciais"], "cobrança", "cobranças"))]
            if r["n_atrasados"]:
                partes.insert(0, _chip(_plural(r["n_atrasados"], "acordo atrasado", "acordos atrasados"), True))
            if r["n_sem_acordo"]:
                partes.append(_chip(f"{r['n_sem_acordo']} sem acordo"))
            chips_jud = f"<div class='hm-chips'>{''.join(partes)}</div>"
        if r["n_protestos"]:
            pagos = r["n_protestos"] - r["n_protestos_abertos"]
            partes = [_chip(f"{r['n_protestos_abertos']} em aberto")]
            if pagos:
                partes.append(_chip(_plural(pagos, "pago", "pagos")))
            chips_prot = f"<div class='hm-chips'>{''.join(partes)}</div>"
    if _cartao_inicio("hm_jud", "tq_jud", "Abrir cobranças judiciais", "claro", SVG_MARTELO,
                      "Cobranças judiciais", "Clientes na justiça e os acordos", chips_jud):
        _ir("judicial")
    if _cartao_inicio("hm_prot", "tq_prot", "Abrir protestos", "claro", SVG_PROTESTO,
                      "Protestos", "Cheque, promissória ou ficha protestados", chips_prot):
        _ir("protestos")
    if restrito:
        if st.button("Notificações", key="btn_notificacoes", icon=":material/notifications:", type="tertiary"):
            _ir("notificacoes")
        _rodape_quem()


def _busca(chave: str, placeholder: str) -> str:
    return st.text_input("Buscar", key=chave, placeholder=placeholder, label_visibility="collapsed",
                         icon=":material/search:")


def _campos_cliente_turma(prefixo: str, erros: list):
    """Nome do cliente e turma(s) do Jurídico. Devolve (cliente, turmas) e põe em `erros` o que falta."""
    cliente = texto_limpo(st.text_input("Nome do cliente", key=f"{prefixo}cliente", max_chars=80))
    turma_txt = st.text_input("Turma", key=f"{prefixo}turma", placeholder="Ex.: L345", max_chars=40,
                              help="Letra do treinamento + número: L = LORAP, V = Vendas, I = Impacto, "
                                   "P = Perfil. Mais de uma turma: separe com vírgula. Ex.: L345, V12")
    turmas = normalizar_turmas(turma_txt)
    if turmas:
        _info(" &nbsp;·&nbsp; ".join(f"Turma <b>{t}</b> · {TREINAMENTOS[t[0]]}" for t in turmas))
    elif turmas is None:
        _erro_campo("Comece pela letra do treinamento (L, V, I ou P) e depois o número. Ex.: L345")
        erros.append("Tem turma escrita errado (ex.: L345).")
    else:
        erros.append("Falta a turma (ex.: L345).")
    if not cliente:
        erros.insert(0, "Falta o nome do cliente.")
    return cliente, turmas or []


def _objeto(prefixo: str, erros: list) -> str:
    objeto = st.pills("Objeto", OBJETOS, key=f"{prefixo}objeto")
    if not objeto:
        erros.append("Falta escolher o objeto: cheque, promissória ou ficha.")
    return objeto or ""


@st.dialog("Excluir")
def _dlg_excluir_juridico(aba: str, rid: str, o_que: str, volta: str):
    _info(f"Excluir {_e(o_que)}?<br>Sai da lista, mas continua guardado na planilha.", "cx-perigo")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Não, manter", key=f"_exj_{rid}_nao", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("Sim, excluir", key=f"_exj_{rid}_sim", use_container_width=True):
            if not _pode_gravar_juridico():
                return
            em, por = ("Excluída em", "Excluída por") if aba == ABA_JUDICIAL else ("Excluído em", "Excluído por")
            try:
                ok = _banco().atualizar_registro(aba, rid, {"Situação": SITUACAO_EXCLUIDA, em: _hoje(), por: _usuario()},
                                                 historico=_hist("exclusão"))
            except Exception as e:
                st.error(f"Não consegui excluir: {_erro_curto(e)}")
                return
            if not ok:
                st.error("Não achei esse registro na planilha. Feche e abra de novo.")
                return
            _invalidar()
            _esquecer_id(rid)
            _flash("Excluído")
            st.session_state.tela = volta
            st.rerun()


# ── Antes de gravar no Jurídico (auditoria de 04/11) ─────────────────────────

# Quem é "Só Jurídico": tentativas de gravar (deem certo ou não) por janela de tempo. Passou de
# qualquer uma, fica 15 min sem gravar. Contado ANTES de ler a planilha: assim nem tocar sem parar
# gasta a cota de leitura do Google, que é uma só para o app inteiro (2ª auditoria de 04/11).
LIMITES_TENTATIVAS = ((3, 60), (20, 10 * 60), (60, 24 * 3600))
BLOQUEIO_TENTATIVAS = 15 * 60
CONFIG_FRESCA_POR = 15   # segundos que a releitura da configuração vale, por sessão


@st.cache_resource(show_spinner=False)
def _tentativas() -> dict:
    """{nome: {"t": [horários], "ate": bloqueado até}}, comum a todas as sessões e abas."""
    return {}


def _dentro_do_limite() -> bool:
    if not _so_juridico() or chave_busca(_config().get(f"sem_limite:{_usuario()}", "")) == "sim":
        return True   # acesso a tudo, ou pessoa de confiança marcada em Configurações
    reg = _tentativas().setdefault(_usuario(), {"t": [], "ate": 0.0})
    agora = time.monotonic()
    if agora < reg["ate"]:
        return False
    reg["t"] = [t for t in reg["t"] if agora - t < LIMITES_TENTATIVAS[-1][1]] + [agora]
    if any(sum(1 for t in reg["t"] if agora - t < janela) > maximo for maximo, janela in LIMITES_TENTATIVAS):
        reg["ate"] = agora + BLOQUEIO_TENTATIVAS
        return False
    return True


def _config_fresca() -> dict:
    """A configuração lida AGORA da planilha (sem limpar a guardada de todo mundo), reaproveitada por
    alguns segundos dentro da mesma sessão."""
    memo = st.session_state.get("_cfg_fresca")
    if memo and time.monotonic() - memo[0] < CONFIG_FRESCA_POR:
        return memo[1]
    cfg = _banco().get_config()
    st.session_state["_cfg_fresca"] = (time.monotonic(), cfg)
    return cfg


def _sessao_ainda_vale():
    """Antes de gravar no Jurídico, inclusive de dentro das janelinhas (que não passam pelo roteador):
    relê a configuração e confere que a pessoa ainda é quem diz ser. Quem foi removida, perdeu o Gmail
    ou o aparelho com a janelinha aberta não grava mais nada. None = não deu para ler agora."""
    if _modo_demo():
        return bool(_usuario())
    try:
        cfg = _config_fresca()
    except Exception:
        return None
    return _sessao_ok(cfg)


def _pode_gravar_juridico() -> bool:
    if not _dentro_do_limite():
        st.error("Muitas tentativas seguidas. Espere 15 minutos e tente de novo.")
        return False
    vale = _sessao_ainda_vale()
    if vale is None:
        st.error("A planilha do Google não respondeu agora. Tente de novo em instantes.")
        return False
    if not vale:
        st.session_state.pop("_quem", None)
        st.error("O seu acesso mudou. Feche e abra o app de novo.")
        return False
    return True


def _excluidos_juridico(aba: str):
    """Só o administrador: o que foi excluído no Jurídico, com 'Restaurar' (auditoria de 04/11: quem é
    Só Jurídico pode excluir, então tem que dar para desfazer sem mexer na planilha)."""
    if not _sou_admin():
        return
    todos = _juridico(True)
    if not todos:
        return
    judicial = aba == ABA_JUDICIAL
    excl = [x for x in (todos[0] if judicial else todos[1]) if x.get("excluida" if judicial else "excluido")]
    if not excl:
        return
    with st.expander(f"Excluíd{'as' if judicial else 'os'} ({len(excl)})", icon=":material/restore_from_trash:"):
        for x in excl:
            with st.container(key=f"lx_jur_{x['id']}"):
                st.markdown(f"<div class='lx-nome'>{_e(x['cliente'])}</div>"
                            f"<div class='lx-meta'>{_e(' · '.join(v for v in (x['turma'], x['objeto']) if v))}</div>",
                            unsafe_allow_html=True)
                if st.button("Restaurar", key=f"lxj_{x['id']}", icon=":material/restore:"):
                    if not _pode_gravar_juridico():
                        return
                    em, por = ("Excluída em", "Excluída por") if judicial else ("Excluído em", "Excluído por")
                    try:
                        ok = _banco().atualizar_registro(aba, x["id"], {"Situação": SITUACAO_ATIVA, em: "", por: ""},
                                                         historico=_hist("restaurou"))
                    except Exception as e:
                        st.error(f"Não consegui restaurar: {_erro_curto(e)}")
                        return
                    if ok:
                        _invalidar()
                        _flash(f"{x['cliente']} restaurad{'a' if judicial else 'o'}")
                        st.rerun()


@st.cache_resource(show_spinner=False)
def _codigos_pendentes() -> dict:
    """{código curto: (código completo do aparelho, quando)} dos aparelhos novos que mostraram o código
    na tela. O administrador digita o curto e o app grava o COMPLETO na liberação."""
    return {}


def _anotar_codigo(aparelho: str) -> str:
    curto = codigo_aparelho(aparelho)
    pend = _codigos_pendentes()
    agora = time.monotonic()
    for k in [k for k, (_, t) in pend.items() if agora - t > 24 * 3600]:
        pend.pop(k, None)
    pend[curto] = (aparelho, agora)
    return curto


def _hist(acao: str) -> dict:
    """Quem, quando e o quê, para a aba _Historico_Juridico."""
    return {"Quando": datetime.now(_FUSO).strftime("%d/%m/%Y %H:%M:%S"), "Quem": _usuario(), "Ação": acao}


# ── Cobranças judiciais ───────────────────────────────────────────────────────

def _html_judicial(j: dict, hoje: date) -> str:
    """Cartão compacto da lista, no mesmo jeito do relatório de cobranças."""
    sit = j["situacao"]
    ps = j["parcelas"]
    if not ps:
        partes = []
        if j["desde"]:
            partes.append(f"No jurídico desde <b>{data_br(j['desde'])}</b>")
        if j["advogado"]:
            partes.append(_e(j["advogado"]))
        estado = " · ".join(partes)
    elif sit == CLI_QUITADO:
        estado = "Acordo todo pago"
    elif sit == CLI_ATRASADO:
        estado = (f"Acordo: <b>{formatar_brl(j['atrasado'])}</b> atrasado "
                  f"({_plural(j['dias_atraso'], 'dia', 'dias')})")
    else:
        p = j["proxima"]
        estado = (f"Acordo: próxima <b>{data_br(p['vencimento'])}</b> · {formatar_brl(p['valor'])}"
                  if p else "Acordo fechado")
    if len(ps) > 1 and sit != CLI_QUITADO:
        estado += f" · {sum(1 for p in ps if p['paga'])} de {len(ps)} pagas"
    total = j["pago"] + j["falta"]
    pct = _pct(j["pago"], total)
    local = " · ".join(x for x in (j["turma"], j["objeto"]) if x)
    return (
        f"<div class='cc {COR_JUD[sit]}'>"
        f"<div class='cc-l1'><span class='cc-nome'>{_e(j['cliente'])}</span>"
        f"<span class='sit {COR_JUD[sit]}'>{ROTULO_JUD[sit]}</span></div>"
        f"<div class='cc-l2'><span class='cc-turma'>{_e(local)}</span>"
        f"<span class='cc-val'>cobrado <b>{formatar_brl(j['valor'])}</b></span></div>"
        + (f"<div class='cc-est'>{estado}</div>" if estado else "")
        + f"<i class='cc-pg' style='width:{pct}%'></i></div>"
    )


def tela_judicial():
    hoje = _hoje()
    _cabecalho("Cobranças judiciais", voltar_para="juridico")
    if st.button("Nova cobrança judicial", key="jd_nova", type="primary", icon=":material/add:",
                 use_container_width=True):
        _abrir_form_judicial(None)
    jur = _juridico()
    if jur is None:
        return
    termo = _busca("jd_busca", "Nome, turma ou advogado")
    achados = [j for j in jur[0] if casa_busca_juridico(j, termo)]
    if not achados:
        msg = "Nada encontrado com essa busca." if termo.strip() else "Nenhuma cobrança judicial cadastrada ainda."
        st.markdown(f"<div class='cx-vazio'>{msg}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='rl-cont'>{_plural(len(achados), 'cobrança judicial', 'cobranças judiciais')} · "
                    f"{formatar_brl(sum(j['valor'] for j in achados))} cobrado</div>", unsafe_allow_html=True)
        for j in ordenar_judiciais(achados):
            if _cartao_toque(f"cc_j{j['id']}", f"tq_j{j['id']}", f"Abrir {j['cliente']}", _html_judicial(j, hoje)):
                st.session_state.jud_id = j["id"]
                _ir("jud_ficha")
    _excluidos_juridico(ABA_JUDICIAL)


def _abrir_form_judicial(j: dict | None):
    """Abre o cadastro (j = None) ou a edição, com os campos já preenchidos."""
    _limpar_campos("jf_")
    ss = st.session_state
    ss.jud_edit = j["id"] if j else None
    if j:
        ss["jf_cliente"] = j["cliente"]
        ss["jf_turma"] = SEP_TURMAS_PLANILHA.join(j["turmas"])
        if j["objeto"] in OBJETOS:
            ss["jf_objeto"] = j["objeto"]
        ss["jf_valor" + MARCA_VALOR] = _num_br(j["valor"]) if j["valor"] else ""
        if j["desde"]:
            ss["jf_desde"] = j["desde"]
        ss["jf_adv"] = j["advogado"]
        ss["jf_neg"] = _NEG_TELA[j["negociacao"]]
        ps = j["parcelas"]
        if ps:
            ss["jf_acordo" + MARCA_VALOR] = _num_br(j["valor_acordo"])
        if j["negociacao"] == NEG_A_VISTA:
            ss["jf_venc_av"] = ps[0]["vencimento"]
        elif j["negociacao"] == NEG_PARCELADO and ps[0]["vencimento"]:
            n, primeira = len(ps), ps[0]["vencimento"]
            ss["jf_n"] = n
            ss["jf_primeira"] = primeira
            for k, p in enumerate(ps):
                ss[f"jf_v{k}_{n}" + MARCA_VALOR] = _num_br(p["valor"])
                if p["vencimento"]:
                    ss[f"jf_d{k}_{n}_{primeira}"] = p["vencimento"]
    _ir("jud_form")


def _usar_advogado():
    escolha = st.session_state.get("jf_adv_sug")
    if escolha:
        st.session_state["jf_adv"] = escolha
    st.session_state["jf_adv_sug"] = None


def tela_jud_form():
    hoje = _hoje()
    ss = st.session_state
    jid = ss.get("jud_edit")
    atual = _judicial(jid) if jid else None
    if jid and (not atual or atual["excluida"]):
        _cabecalho("Cobrança judicial", voltar_para="judicial")
        st.info("Essa cobrança judicial não está mais disponível.")
        return
    _cabecalho("Editar cobrança judicial" if atual else "Nova cobrança judicial",
               voltar_para="jud_ficha" if atual else "judicial")
    erros = []
    with st.container(key="sec_jf1"):
        _titulo_secao(1, "Cliente")
        cliente, turmas = _campos_cliente_turma("jf_", erros)

    with st.container(key="sec_jf2"):
        _titulo_secao(2, "Cobrança na justiça")
        objeto = _objeto("jf_", erros)
        valor, ok_v = _valor("Valor que está sendo cobrado", "jf_valor")
        if not ok_v:
            erros.append("Tem valor digitado errado.")
        elif not valor:
            erros.append("Falta o valor que está sendo cobrado.")
        ss.setdefault("jf_desde", hoje)
        desde = st.date_input("Em cobrança no jurídico desde", format="DD/MM/YYYY", key="jf_desde")
        if not desde:
            erros.append("Falta a data em que foi para o jurídico.")
        advogado = texto_limpo(st.text_input("Advogado responsável", key="jf_adv", max_chars=60))
        if not advogado:
            usados = advogados_usados((_juridico() or ([], []))[0])
            if usados:
                st.pills("Já usados", usados[:6], key="jf_adv_sug", on_change=_usar_advogado, format_func=_rotulo)

    valor_acordo, valores, datas, conf_ok = None, [], [], True
    with st.container(key="sec_jf3"):
        _titulo_secao(3, "Negociação")
        st.markdown("<div class='cx-dica' style='margin:0 0 .3rem'>Pode preencher agora ou depois, "
                    "em <b>Editar</b>.</div>", unsafe_allow_html=True)
        neg = NEGOCIACOES[st.radio("Negociação", list(NEGOCIACOES), key="jf_neg", label_visibility="collapsed",
                                   captions=["sem acordo por enquanto", "paga tudo de uma vez",
                                             "dividido em parcelas"])]
        # Na edição, a parcela que já estava paga continua paga (se o tipo de acordo não mudou)
        anteriores = atual["parcelas"] if atual and atual["negociacao"] == neg else []
        if neg != NEG_SEM:
            acordo, ok_a = _valor("Valor do acordo", "jf_acordo", placeholder=_num_br(valor) if valor else "0,00",
                                  help="Em branco = o mesmo valor que está sendo cobrado.")
            if not ok_a:
                erros.append("Tem valor digitado errado.")
            valor_acordo = acordo if acordo is not None else valor
            if not valor_acordo:
                erros.append("Falta o valor do acordo.")
        if neg == NEG_A_VISTA:
            venc = st.date_input("Vencimento", value=None, format="DD/MM/YYYY", key="jf_venc_av")
            if not venc:
                erros.append("Falta o vencimento do acordo.")
            valores, datas = [valor_acordo or 0.0], [venc]
            if anteriores and anteriores[0]["paga"]:
                _info(f"Este acordo já está <b>pago</b> ({data_br(anteriores[0]['pago_em'])}).", "cx-ok")
        elif neg == NEG_PARCELADO:
            n = st.number_input("Em quantas parcelas?", min_value=2, max_value=MAX_PARCELAS_ACORDO, value=None,
                                step=1, key="jf_n", placeholder="Ex.: 5")
            primeira = st.date_input("1º vencimento", value=None, format="DD/MM/YYYY", key="jf_primeira",
                                     help="As outras vêm todo mês no mesmo dia. Dá para mudar cada uma embaixo.")
            if not n:
                erros.append("Falta dizer em quantas parcelas.")
            elif not 2 <= int(n) <= MAX_PARCELAS_ACORDO:   # conferido aqui também: o navegador pode mentir
                erros.append(f"O acordo pode ter de 2 a {MAX_PARCELAS_ACORDO} parcelas.")
            elif not primeira:
                erros.append("Falta o 1º vencimento.")
            else:
                n = int(n)
                base = datas_continuas(primeira, n)
                st.markdown("<div class='px-lista'>Parcela por parcela</div>", unsafe_allow_html=True)
                # Cada parcela já vem com a sua parte; a que for mudada fica e as outras dividem o resto
                _valores_automaticos([f"jf_v{k}_{n}" for k in range(n)], valor_acordo or 0.0)
                digitados = []
                for k in range(n):
                    with st.container(key=f"jf_linha_{k}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            v, ok = _valor(f"Valor da {k + 1}ª", f"jf_v{k}_{n}", placeholder="em branco = divide")
                            if not ok:
                                erros.append("Tem valor digitado errado.")
                            digitados.append(v)
                        with c2:
                            # A chave leva o 1º vencimento: trocar ele recalcula as datas sugeridas
                            chave_d = f"jf_d{k}_{n}_{primeira}"
                            ss.setdefault(chave_d, base[k])
                            datas.append(st.date_input(f"Vencimento da {k + 1}ª", format="DD/MM/YYYY",
                                                       key=chave_d))
                        if k < len(anteriores) and anteriores[k]["paga"]:
                            st.markdown(f"<div class='cx-dica'>Já paga em <b>{data_br(anteriores[k]['pago_em'])}"
                                        "</b></div>", unsafe_allow_html=True)
                valores = resolver_valores(valor_acordo or 0.0, digitados)
                if any(d is None for d in datas):
                    erros.append("Falta alguma data de vencimento.")
                if any(v <= 0 for v in valores):
                    erros.append("Tem parcela com valor zero ou negativo.")
                if valor_acordo:
                    conf_ok = _bloco_conferencia(valor_acordo, valores, "jf_")
                somem = sum(1 for p in anteriores[n:] if p["paga"])
                if somem:
                    _info(f"Atenção: {_plural(somem, 'parcela já paga sai', 'parcelas já pagas saem')} do "
                          "acordo com esse número de parcelas.", "cx-perigo")
        if atual and neg != atual["negociacao"] and any(p["paga"] for p in atual["parcelas"]):
            _info("Atenção: trocar o tipo de acordo apaga as marcas de pago do acordo de antes.", "cx-perigo")

    rotulo = "Salvar alterações" if atual else "Salvar cobrança judicial"
    if st.button(rotulo, type="primary", key="jf_salvar", use_container_width=True, icon=":material/check:"):
        if not conf_ok:
            erros.append("As parcelas não fecham com o valor do acordo: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            # Tudo que se digita vai em MAIÚSCULA (pedido 16/10)
            _salvar_judicial(atual, {
                "Cliente": cliente.upper(), "Turma": SEP_TURMAS_PLANILHA.join(turmas), "Objeto": objeto,
                "Valor cobrado": valor, "No jurídico desde": desde, "Advogado": advogado.upper(),
                "Negociação": neg, "Valor do acordo": valor_acordo if neg else "",
            }, neg, valores, datas)
    _aviso_do_salvar("jf_")


def _salvar_judicial(atual: dict | None, campos: dict, neg: str, valores: list, datas: list):
    # (a trava "_salvando" saiu em 05/11: se a pessoa tocasse em algo no meio da gravação, ela ficava ligada
    # e nenhum Salvar funcionava mais; agora quem segura é _gravar_sem_perder)
    if not _pode_gravar_juridico():
        return
    anteriores = []
    if atual:
        # Relê na hora de gravar: se alguém marcou uma parcela como paga com este formulário
        # aberto, a marca não se perde
        _invalidar()
        fresco = _judicial(atual["id"]) or atual
        anteriores = fresco["parcelas"] if fresco["negociacao"] == neg else []
    if len(valores) > MAX_PARCELAS_ACORDO:
        st.error(f"O acordo pode ter no máximo {MAX_PARCELAS_ACORDO} parcelas.")
        return
    campos["Acordo"] = acordo_para_texto(parcelas_do_acordo(valores, datas, anteriores)) if neg else ""
    banco = _banco()
    if atual:
        jid = atual["id"]
        mudou = {**campos, "Alterada por": _usuario(), "Alterada em": _hoje()}
        hist = _hist("edição")

        def gravar():
            if not banco.atualizar_registro(ABA_JUDICIAL, jid, mudou, historico=hist):
                raise _NaoAchei("Não achei essa cobrança judicial na planilha. Volte e abra de novo.")
            return jid
        trava, conferir = _trava_do_id(jid), None
    else:
        novo = {**campos, "Cadastrada por": _usuario(), "Criada em": _hoje(), "Situação": SITUACAO_ATIVA}
        hist = _hist("cadastro")
        jid, trava = _id_da_gravacao(ABA_JUDICIAL, novo)
        gravar = lambda: banco.criar_registro(ABA_JUDICIAL, novo, historico=hist, rid=jid)
        conferir = lambda: banco.registro_existe(ABA_JUDICIAL, jid)
    _gravar_sem_perder("jf_", jid, trava, gravar, conferir,
                       ok={"tela": "jud_ficha", "flash": f"Cobrança judicial de {campos['Cliente']} salva",
                           "estado": {"jud_id": "{id}", "jud_edit": None}},
                       aviso="Salvando…")


def _html_parcela_acordo(p: dict, hoje: date) -> str:
    """Parcela do acordo como folha de carnê, igual às das cobranças (carimbo PAGO quando paga)."""
    d = p["vencimento"]
    cor = COR_PARC[p["situacao"]]
    if p["paga"]:
        pago_em = f"<small>{p['pago_em'].strftime('%d/%m/%y')}</small>" if p["pago_em"] else ""
        carimbo, sit = f"<div class='pc-carimbo'>PAGO{pago_em}</div>", ""
    else:
        carimbo = ""
        if p["situacao"] == SIT_ATRASADA:
            txt = f"{_plural((hoje - d).days, 'dia', 'dias')} de atraso"
        elif p["situacao"] == SIT_EM_BREVE:
            txt = "Vence hoje" if d == hoje else "Amanhã" if d == hoje + timedelta(days=1) else "Em breve"
        else:
            txt = "Em aberto"
        sit = f"<span class='sit {cor}'>{txt}</span>"
    quem = f"<br><span class='pc-quem'>{_e(p['marcado_por'])} marcou</span>" if p["paga"] and p["marcado_por"] else ""
    return (f"<div class='pc {cor}{' pago' if p['paga'] else ''}'>{_bloco_data(d)}<div class='pc-corpo'>"
            f"<div class='pc-topo'><span class='pc-tag'></span>{sit}</div>"
            f"<div class='pc-rot'>{_e(p['rotulo'])}{quem}</div>"
            f"<div class='pc-valor'>{formatar_brl(p['valor'])}</div></div>{carimbo}</div>")


def _parcela_acordo_ui(j: dict, p: dict, hoje: date):
    chave = f"{j['id']}_{p['n']}"
    with st.container(key=f"pc_jd_{chave}"):
        st.markdown(_html_parcela_acordo(p, hoje), unsafe_allow_html=True)
        if p["paga"]:
            if st.button("Desfazer pagamento", key=f"jdp_des_{chave}", icon=":material/undo:",
                         use_container_width=True):
                _dlg_acordo_desfazer(j["id"], p["n"])
        elif st.button("Marcar como paga", key=f"jdp_pg_{chave}", icon=":material/check_circle:",
                       use_container_width=True):
            _dlg_acordo_pagar(j["id"], p["n"])


def _parcela_do_acordo(jid: str, n: int):
    j = _judicial(jid)
    if not j or not 1 <= n <= len(j["parcelas"]):
        return j, None
    return j, j["parcelas"][n - 1]


def _gravar_acordo(jid: str, n: int, paga: bool, quando: date | None = None) -> bool:
    """Marca ou desmarca UMA parcela do acordo. Relê a planilha na hora: se outra pessoa mexeu
    em outra parcela do mesmo acordo há pouco, a marca dela não se perde."""
    if not _pode_gravar_juridico():
        return False
    _invalidar()
    j, p = _parcela_do_acordo(jid, n)
    if not p:
        st.error("Não achei essa parcela. Feche e abra a ficha de novo.")
        return False
    novas = marcar_parcela_acordo(j["parcelas"], n, paga, quando, _usuario())
    try:
        ok = _banco().atualizar_registro(
            ABA_JUDICIAL, jid, {"Acordo": acordo_para_texto(novas), "Alterada por": _usuario(), "Alterada em": _hoje()},
            historico=_hist(f"{'marcou paga' if paga else 'desfez pagamento'}: {p['rotulo']}"))
    except Exception as e:
        st.error(f"Não consegui salvar: {_erro_curto(e)}")
        return False
    if not ok:
        st.error("Não achei essa cobrança judicial na planilha.")
        return False
    _invalidar()
    return True


@st.dialog("Marcar como paga")
def _dlg_acordo_pagar(jid: str, n: int):
    j, p = _parcela_do_acordo(jid, n)
    if not p:
        return
    st.markdown(f"<div class='dl-cab'><b>{_e(j['cliente'])}</b><span>{_e(p['rotulo'])} · "
                f"{formatar_brl(p['valor'])}</span></div>", unsafe_allow_html=True)
    quando = st.date_input("Pago em", value=_hoje(), format="DD/MM/YYYY", key=f"_jdp_{jid}_{n}_data")
    if st.button("Confirmar pagamento", type="primary", key=f"_jdp_{jid}_{n}_ok", use_container_width=True,
                 icon=":material/check:"):
        if not quando:
            _erro_campo("Escolha a data do pagamento.")
        elif _gravar_acordo(jid, n, True, quando):
            _flash("Pagamento marcado")
            st.rerun()


@st.dialog("Desfazer pagamento")
def _dlg_acordo_desfazer(jid: str, n: int):
    j, p = _parcela_do_acordo(jid, n)
    if not p:
        return
    _info(f"Tirar a marca de pago de <b>{_e(p['rotulo'])}</b> ({formatar_brl(p['valor'])}) de "
          f"<b>{_e(j['cliente'])}</b>? Ela volta a ficar em aberto.", "cx-perigo")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Não, manter", key=f"_jdd_{jid}_{n}_nao", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("Sim, desfazer", key=f"_jdd_{jid}_{n}_sim", use_container_width=True):
            if _gravar_acordo(jid, n, False):
                _flash("Pagamento desfeito")
                st.rerun()


def tela_jud_ficha():
    hoje = _hoje()
    j = _judicial(st.session_state.get("jud_id", ""))
    if not j or j["excluida"]:
        _cabecalho("Cobrança judicial", voltar_para="judicial")
        st.info("Essa cobrança judicial não está mais disponível.")
        return
    sub = " · ".join(x for x in (f"Turma {_e(j['turma'])}" if j["turma"] else "", _e(j["objeto"])) if x)
    _cabecalho(j["cliente"], voltar_para="judicial", subtitulo=sub)
    sit = j["situacao"]
    selo = f"<span class='sit {COR_JUD[sit]}'>{ROTULO_JUD[sit]}</span>"
    desde = f"No jurídico desde <b>{data_br(j['desde'])}</b>" if j["desde"] else ""
    adv = f"Advogado: <b>{_e(j['advogado'])}</b>" if j["advogado"] else "Advogado: não informado"
    ps = j["parcelas"]
    acordo = ""
    if ps:
        total = j["pago"] + j["falta"]
        pct = _pct(j["pago"], total)
        titulo = (f"Acordo à vista de <b>{formatar_brl(total)}</b>" if j["negociacao"] == NEG_A_VISTA
                  else f"Acordo em <b>{len(ps)} parcelas</b>, somando <b>{formatar_brl(total)}</b>")
        acordo = (f"<div class='fc-acordo'>{titulo}</div><div class='pg'><i style='width:{pct}%'></i></div>"
                  f"<div class='fc-nums'><div><b>{formatar_brl(j['pago'])}</b><span>Pago</span></div>"
                  f"<div><b>{formatar_brl(j['falta'])}</b><span>Falta</span></div>"
                  f"<div class='{'atr' if j['atrasado'] else ''}'><b>{formatar_brl(j['atrasado'])}</b>"
                  f"<span>Atrasado</span></div></div>")
    quem = ""
    if j["criada_por"] or j["criada_em"]:
        por = f" por <b>{_e(j['criada_por'])}</b>" if j["criada_por"] else ""
        em = f" em {data_br(j['criada_em'])}" if j["criada_em"] else ""
        quem = f"<div class='fc-quem'>Cadastrada{por}{em}</div>"
    st.markdown(
        f"<div class='fc {COR_JUD[sit]}'><div class='fc-topo'>{selo}<span>{desde}</span></div>"
        f"<div class='fc-total'><span>Valor cobrado</span><b>{formatar_brl(j['valor'])}</b></div>"
        f"<div class='fc-linha'>{adv}</div>{acordo}{quem}</div>",
        unsafe_allow_html=True,
    )
    if not ps:
        _info("Ainda sem acordo. Quando fechar, toque em <b>Editar</b> e preencha a negociação.", "cx-nota")
    else:
        st.markdown("<div class='fc-grupo'>Acordo</div>", unsafe_allow_html=True)
        for p in ps:
            _parcela_acordo_ui(j, p, hoje)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Editar", key="jd_editar", icon=":material/edit:", use_container_width=True):
            _abrir_form_judicial(j)
    with c2:
        if st.button("Excluir", key="jd_excluir", icon=":material/delete:", use_container_width=True):
            _dlg_excluir_juridico(ABA_JUDICIAL, j["id"], f"a cobrança judicial de {j['cliente']}", "judicial")


# ── Protestos ─────────────────────────────────────────────────────────────────

def _html_protesto(p: dict) -> str:
    cor = "c-ok" if p["pago"] else "c-neutro"
    chip = "<span class='sit c-ok'>Pago</span>" if p["pago"] else "<span class='sit c-neutro'>Em aberto</span>"
    local = " · ".join(x for x in (p["turma"], p["objeto"]) if x)
    quando = f"protestado <b>{data_br(p['protestado_em'])}</b>" if p["protestado_em"] else ""
    estado = ""
    if p["pago"]:
        por = f" · {_e(p['marcado_por'])} marcou" if p["marcado_por"] else ""
        em = f" em <b>{data_br(p['pago_em'])}</b>" if p["pago_em"] else ""
        estado = f"<div class='cc-est'>Pago{em}{por}</div>"
    return (f"<div class='cc {cor}'><div class='cc-l1'><span class='cc-nome'>{_e(p['cliente'])}</span>{chip}</div>"
            f"<div class='cc-l2'><span class='cc-turma'>{_e(local)}</span>"
            f"<span class='cc-val'>{quando}</span></div>{estado}</div>")


def tela_protestos():
    _cabecalho("Protestos", voltar_para="juridico")
    if st.button("Novo protesto", key="pt_novo", type="primary", icon=":material/add:", use_container_width=True):
        _abrir_form_protesto(None)
    jur = _juridico()
    if jur is None:
        return
    termo = _busca("pt_busca", "Nome, turma ou objeto")
    achados = [p for p in jur[1] if casa_busca_juridico(p, termo)]
    if not achados:
        msg = "Nada encontrado com essa busca." if termo.strip() else "Nenhum protesto cadastrado ainda."
        st.markdown(f"<div class='cx-vazio'>{msg}</div>", unsafe_allow_html=True)
    else:
        abertos = sum(1 for p in achados if not p["pago"])
        st.markdown(f"<div class='rl-cont'>{_plural(len(achados), 'protesto', 'protestos')} · {abertos} em aberto"
                    "</div>", unsafe_allow_html=True)
        for p in ordenar_protestos(achados):
            if _cartao_toque(f"cc_p{p['id']}", f"tq_p{p['id']}", f"Abrir {p['cliente']}", _html_protesto(p)):
                _abrir_form_protesto(p)
    _excluidos_juridico(ABA_PROTESTOS)


def _abrir_form_protesto(p: dict | None):
    _limpar_campos("pf_")
    ss = st.session_state
    ss.prot_edit = p["id"] if p else None
    if p:
        ss["pf_cliente"] = p["cliente"]
        ss["pf_turma"] = SEP_TURMAS_PLANILHA.join(p["turmas"])
        if p["objeto"] in OBJETOS:
            ss["pf_objeto"] = p["objeto"]
        if p["protestado_em"]:
            ss["pf_data"] = p["protestado_em"]
        ss["pf_pago"] = p["pago"]
        if p["pago_em"]:
            ss["pf_pago_em"] = p["pago_em"]
    _ir("prot_form")


def tela_prot_form():
    hoje = _hoje()
    ss = st.session_state
    pid = ss.get("prot_edit")
    atual = _protesto(pid) if pid else None
    if pid and (not atual or atual["excluido"]):
        _cabecalho("Protesto", voltar_para="protestos")
        st.info("Esse protesto não está mais disponível.")
        return
    _cabecalho("Protesto" if atual else "Novo protesto", voltar_para="protestos")
    erros = []
    with st.container(key="sec_pf1"):
        cliente, turmas = _campos_cliente_turma("pf_", erros)
        objeto = _objeto("pf_", erros)
        ss.setdefault("pf_data", hoje)
        data = st.date_input("Data de inclusão do protesto", format="DD/MM/YYYY", key="pf_data")
        if not data:
            erros.append("Falta a data de inclusão do protesto.")
        pago = st.checkbox("Já foi pago", key="pf_pago")
        pago_em = None
        if pago:
            ss.setdefault("pf_pago_em", hoje)
            pago_em = st.date_input("Pago em", format="DD/MM/YYYY", key="pf_pago_em")
            if not pago_em:
                erros.append("Falta a data do pagamento.")

    if atual and (atual["criado_por"] or atual["criado_em"]):
        por = f" por <b>{_e(atual['criado_por'])}</b>" if atual["criado_por"] else ""
        em = f" em {data_br(atual['criado_em'])}" if atual["criado_em"] else ""
        st.markdown(f"<div class='cf-meta'>Cadastrado{por}{em}</div>", unsafe_allow_html=True)
    rotulo = "Salvar alterações" if atual else "Salvar protesto"
    if st.button(rotulo, type="primary", key="pf_salvar", use_container_width=True, icon=":material/check:"):
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ja_marcado = atual["marcado_por"] if atual and atual["pago"] else ""
            _salvar_protesto(atual, {
                "Cliente": cliente.upper(), "Turma": SEP_TURMAS_PLANILHA.join(turmas), "Objeto": objeto,
                "Protestado em": data, "Pago": pago, "Pago em": pago_em if pago else "",
                "Marcado por": (ja_marcado or _usuario()) if pago else "",
            })
    _aviso_do_salvar("pf_")
    if atual and st.button("Excluir protesto", key="pt_excluir", icon=":material/delete:", use_container_width=True):
        _dlg_excluir_juridico(ABA_PROTESTOS, atual["id"], f"o protesto de {atual['cliente']}", "protestos")


def _salvar_protesto(atual: dict | None, campos: dict):
    # (sem a trava "_salvando" desde 05/11, como em _salvar_judicial)
    if not _pode_gravar_juridico():
        return
    banco = _banco()
    if atual:
        pid = atual["id"]
        mudou = {**campos, "Alterado por": _usuario(), "Alterado em": _hoje()}
        hist = _hist("edição")

        def gravar():
            if not banco.atualizar_registro(ABA_PROTESTOS, pid, mudou, historico=hist):
                raise _NaoAchei("Não achei esse protesto na planilha. Volte e abra de novo.")
            return pid
        trava, conferir = _trava_do_id(pid), None
    else:
        novo = {**campos, "Cadastrado por": _usuario(), "Criado em": _hoje(), "Situação": SITUACAO_ATIVA}
        hist = _hist("cadastro")
        pid, trava = _id_da_gravacao(ABA_PROTESTOS, novo)
        gravar = lambda: banco.criar_registro(ABA_PROTESTOS, novo, historico=hist, rid=pid)
        conferir = lambda: banco.registro_existe(ABA_PROTESTOS, pid)
    _gravar_sem_perder("pf_", pid, trava, gravar, conferir,
                       ok={"tela": "protestos", "flash": f"Protesto de {campos['Cliente']} salvo",
                           "estado": {"prot_edit": None}},
                       aviso="Salvando…")


# ── Notificações ──────────────────────────────────────────────────────────────

def _token_bot() -> str:
    return str(_segredo("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()


@st.cache_data(ttl=3600, show_spinner=False)
def _usuario_do_bot(_token: str) -> str:
    return avisos_telegram.nome_do_bot(_token)


def _salvar_config(chave: str, valor: str) -> bool:
    if not _sessao_ok():
        return False
    if _so_juridico() and chave not in (f"telegram:{_usuario()}", f"avisos:{_usuario()}"):
        return False   # quem é Só Jurídico só mexe no próprio Telegram (callbacks rodam antes do roteador)   # (callbacks das Notificações rodam antes do roteador)
    try:
        _banco().save_config(chave, valor)
        _ler_config.clear()
        return True
    except Exception as e:
        st.error(f"Não consegui salvar: {_erro_curto(e)}")
        return False


def _mudar_opcao_aviso(chave: str, widget: str):
    _salvar_config(chave, "sim" if st.session_state.get(widget) else "nao")


def _previa_juridico(semanal: bool = False) -> str | None:
    jur = _juridico()
    if not jur:
        return None
    return notifier.montar_juridico(jur[0], jur[1], _hoje(), semanal, opcoes_avisos(_config()))


def tela_notificacoes():
    restrito = _so_juridico()
    _cabecalho("Notificações", voltar_para="juridico" if restrito else "inicio",
               subtitulo=("Avisos do Jurídico no Telegram, todo dia às 7h30" if restrito
                          else "Avisos de cobrança e do Jurídico no Telegram, todo dia às 7h30"))
    eu = _usuario()
    cfg = _config()
    token = _token_bot()
    meu_chat = cfg.get(f"telegram:{eu}", "")

    with st.container(key="sec_nt1"):
        _titulo_secao(1, f"Celular de {eu}")
        if _modo_demo():
            _info("Na demonstração os avisos não são enviados. No app de verdade, aqui você liga "
                  "o seu Telegram em três toques.", "cx-nota")
        elif not token:
            _info("O bot do Telegram ainda não foi ligado ao app (falta o token nos Secrets).", "cx-perigo")
        elif meu_chat:
            _info("<b>Telegram conectado.</b> Os avisos chegam neste celular.", "cx-ok")
            st.toggle("Receber os avisos", key="nt_receber",
                      value=chave_busca(cfg.get(f"avisos:{eu}", "")) != "nao",
                      on_change=_mudar_opcao_aviso, args=(f"avisos:{eu}", "nt_receber"))
            if st.button("Mandar um aviso de teste agora", key="nt_teste", icon=":material/send:",
                         use_container_width=True):
                try:
                    partes = []
                    if not restrito:
                        partes.append(notifier.montar_diario(_cobrancas() or [], _hoje(), opcoes_avisos(cfg)))
                    partes.append(_previa_juridico())
                    previa = "\n\n".join(x for x in partes if x)
                    avisos_telegram.enviar(token, meu_chat,
                                           "✅ <b>Teste dos avisos</b>\nÉ assim que chega, todo dia às 7h30.\n\n"
                                           + (previa or "Hoje não há nada atrasado, nem para hoje ou amanhã."))
                    st.toast("Aviso de teste enviado. Olhe o Telegram.", icon="✅")
                except Exception as e:
                    st.error(f"O Telegram recusou: {e}")
            if st.button("Desconectar este celular", key="nt_desconectar", type="tertiary",
                         icon=":material/link_off:"):
                if _salvar_config(f"telegram:{eu}", ""):
                    _flash("Telegram desconectado")
                    st.rerun()
        else:
            try:
                bot = _usuario_do_bot(token)
            except Exception as e:
                bot = ""
                st.error(f"Não consegui falar com o bot: {_erro_curto(e)}")
            if bot:
                codigo = st.session_state.setdefault("_nt_codigo", os.urandom(4).hex())
                _info("Para receber os avisos neste celular:<br><b>1.</b> Abra o bot no Telegram"
                      "<br><b>2.</b> Toque em <b>COMEÇAR</b> lá embaixo<br><b>3.</b> Volte aqui e confirme")
                st.link_button("1. Abrir o bot no Telegram", avisos_telegram.link_para_conectar(bot, codigo),
                               icon=":material/open_in_new:", use_container_width=True)
                if st.button("3. Já toquei em Começar", key="nt_conectar", type="primary",
                             icon=":material/check:", use_container_width=True):
                    try:
                        chat = avisos_telegram.achar_chat(token, codigo)
                    except Exception as e:
                        chat = None
                        st.error(f"Não consegui falar com o Telegram: {_erro_curto(e)}")
                    if chat and _salvar_config(f"telegram:{eu}", chat):
                        _salvar_config(f"avisos:{eu}", "sim")
                        st.session_state.pop("_nt_codigo", None)
                        try:
                            o_que = "do Jurídico" if restrito else "de cobrança e do Jurídico"
                            avisos_telegram.enviar(token, chat, f"✅ Avisos {o_que} ligados para <b>{_e(eu)}</b>. "
                                                                "Eles chegam aqui todo dia às 7h30.")
                        except Exception:
                            pass
                        _flash("Telegram conectado")
                        st.rerun()
                    elif not chat:
                        _erro_campo("Ainda não vi o seu toque. Abra o bot pelo botão 1, toque em COMEÇAR "
                                    "e confirme aqui de novo.")

    if restrito:
        _info("Chegam no Telegram as parcelas dos acordos atrasadas, as que vencem hoje e as que vencem "
              "amanhã. Na segunda, o resumo da semana do Jurídico.", "cx-nota")
        return   # o resto da tela (o que avisar, quem recebe) é de quem tem acesso a tudo

    with st.container(key="sec_nt2"):
        _titulo_secao(2, "O que avisar")
        st.caption("Vale para todo mundo que recebe.")
        opcoes = opcoes_avisos(cfg)
        for chave, rotulo in OPCOES_AVISO.items():
            st.toggle(rotulo, key=f"nt_{chave}", value=opcoes[chave],
                      on_change=_mudar_opcao_aviso, args=(chave, f"nt_{chave}"))

    with st.container(key="sec_nt3"):
        _titulo_secao(3, "Quem recebe")
        recebem = dict(destinatarios(cfg))
        recebem_jur = dict(destinatarios_juridico(cfg))
        for p in _pessoas():
            if p in recebem:
                estado = "<span class='sit c-ok'>Recebe</span>"
            elif p in recebem_jur:
                estado = "<span class='sit c-ok'>Só Jurídico</span>"
            elif cfg.get(f"telegram:{p}"):
                estado = "<span class='sit c-neutro'>Pausado</span>"
            else:
                estado = "<span class='sit c-neutro'>Sem Telegram</span>"
            st.markdown(f"<div class='nt-pessoa'><span>{_e(p)}</span>{estado}</div>", unsafe_allow_html=True)
        _info("Cada pessoa liga o próprio celular: abre o app com o nome dela e segue os 3 passos acima.", "cx-nota")


# ── Feriados (piada interna; para tirar, apague esta tela, o botão e feriados.py) ──

def tela_feriados():
    hoje = _hoje()
    _cabecalho("Feriados", voltar_para="inicio", subtitulo="Os feriados nacionais do Brasil")
    prox = feriados.proximo(hoje)
    if prox:
        dias = (prox["data"] - hoje).days
        quando = "é hoje" if dias == 0 else "é amanhã" if dias == 1 else f"faltam {dias} dias"
        st.markdown(
            f"<div class='fr-prox'><span>Próximo feriado</span><b>{_e(prox['nome'])}</b>"
            f"<em>{prox['dia_semana']}, {data_br(prox['data'])} · {quando}</em></div>",
            unsafe_allow_html=True)
    ano = st.segmented_control("Ano", [hoje.year, hoje.year + 1], key="fr_ano", default=hoje.year,
                               label_visibility="collapsed") or hoje.year
    linhas = []
    for f in feriados.feriados(ano):
        classes = "fr" + ("" if f["nacional"] else " facultativo") + (" passou" if f["data"] < hoje else "")
        etiqueta = (f"<span class='sit c-neutro'>{_e(f['obs'])}</span>" if f["nacional"]
                    else "<span class='sit c-breve'>facultativo</span>")
        linhas.append(
            f"<div class='{classes}'><div class='fr-data'><b>{f['data'].day:02d}</b>"
            f"<span>{MESES_ABREV[f['data'].month - 1]}</span></div>"
            f"<div class='fr-corpo'><div class='fr-nome'>{_e(f['nome'])}</div>"
            f"<div class='fr-dia'>{f['dia_semana']}</div></div>{etiqueta}</div>")
    st.markdown("".join(linhas), unsafe_allow_html=True)
    _info("<b>Facultativo</b> não é feriado nacional: Carnaval e Corpus Christi só são folga "
          "onde a empresa libera ou onde há lei da cidade ou do estado.", "cx-nota")


# ── Voltar do celular ─────────────────────────────────────────────────────────

# Para onde cada tela volta com a setinha do aparelho ("inicio" sai do app).
_TELA_PAI = {"nova": "inicio", "pix": "nova", "cartao": "nova", "hibrido": "nova", "permuta": "nova",
             "relatorio": "inicio",
             "excluidas": "inicio", "notificacoes": "inicio", "feriados": "inicio", "config": "inicio",
             "cobranca": None,
             "juridico": "inicio", "judicial": "juridico", "protestos": "juridico",
             "jud_ficha": "judicial", "jud_form": "judicial", "prot_form": "protestos"}


def _voltar_do_celular():
    """
    A setinha de voltar do celular navega dentro do app em vez de fechá-lo:
    um botão invisível faz a volta em Python e um script no documento principal
    intercepta o "voltar" do navegador e clica nele (mesma solução do boleto).
    """
    tela = st.session_state.tela
    if tela not in _TELA_PAI or (tela == "juridico" and _so_juridico()):
        return   # tela de partida: a seta do celular sai do app
    pai = _TELA_PAI[tela] or st.session_state.get("cob_volta", "relatorio")
    if tela == "jud_form" and st.session_state.get("jud_edit"):
        pai = "jud_ficha"   # editando: volta para a ficha que estava aberta
    st.markdown("<style>.st-key-_btn_voltar_hw{display:none}</style>", unsafe_allow_html=True)
    if st.button("voltar", key="_btn_voltar_hw"):
        st.session_state.tela = pai
        st.rerun()
    _iframe_invisivel("""
<script>
const P = window.parent;
const SEL = ".st-key-_btn_voltar_hw button";
if (!P.__voltarHook) {
  P.__voltarHook = true;
  const s = P.document.createElement("script");
  s.textContent = `
    window.addEventListener("popstate", function () {
      var btn = document.querySelector("` + SEL + `");
      if (btn) { history.pushState({voltarApp: 1}, ""); btn.click(); return; }
      if (!window.__saindoDoApp) {
        window.__saindoDoApp = true;
        setTimeout(function () { window.__saindoDoApp = false; }, 1000);
        history.back();
      }
    });
  `;
  P.document.head.appendChild(s);
}
if (!(P.history.state && P.history.state.voltarApp)) { P.history.pushState({voltarApp: 1}, ""); }
</script>
""")


# Campos de texto no celular (pedidos de 16/10), feito no NAVEGADOR porque o Streamlit só
# recebe o que foi digitado depois do Enter:
#   - VALOR (chave terminada em MARCA_VALOR): enquanto digita já mostra "1.500,00". O ponto do
#     milhar entra sozinho e o ",00" fica sempre à vista; vírgula ou ponto pula para os centavos
#     (e marca eles, para trocar digitando por cima). Teclado de números.
#   - O resto dos campos de texto abre o teclado do celular em MAIÚSCULA (o estilo.css mostra em
#     maiúscula e o Python grava em maiúscula). O nome de quem usa o app fica de fora.
_JS_CAMPOS = r"""
<script>
const P = window.parent;
if (!P.__camposVithall) {
  P.__camposVithall = true;
  const s = P.document.createElement("script");
  s.textContent = "(" + instalar.toString() + ")();";   // roda na página de fora, onde estão os campos
  P.document.head.appendChild(s);
}
function instalar() {
  var MARCA = "__rs";
  var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  var mexendo = false;
  function milhar(d) { return d.replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function trocar(el, v, pos) {
    // o Streamlit (React) só fica sabendo do valor novo por um evento "input"
    mexendo = true;
    setter.call(el, v);
    el.dispatchEvent(new Event("input", {bubbles: true}));
    mexendo = false;
    try { el.setSelectionRange(pos, pos); } catch (e) {}
  }
  function formatar(el) {
    var v = el.value, cur = el.selectionStart == null ? v.length : el.selectionStart;
    if (v.indexOf(",") < 0 && /^\d+\.\d{1,2}$/.test(v)) v = v.replace(".", ",");   // colou "1500.50"
    var i = v.indexOf(",");
    var inteiro = (i < 0 ? v : v.slice(0, i)).replace(/\D/g, "").replace(/^0+(?=\d)/, "");
    var cent = (i < 0 ? "" : v.slice(i + 1)).replace(/\D/g, "");
    if (!inteiro && !/[1-9]/.test(cent)) { if (el.value !== "") trocar(el, "", 0); return; }
    var noCent = i >= 0 && cur > i;
    var antes = noCent ? v.slice(i + 1, cur).replace(/\D/g, "").length
                       : v.slice(0, i < 0 ? cur : Math.min(cur, i)).replace(/\D/g, "").length;
    if (cent.length > 2) cent = antes >= cent.length ? cent.slice(-2) : cent.slice(0, 2);
    var ifmt = milhar(inteiro || "0");
    var novo = ifmt + "," + (cent + "00").slice(0, 2);
    var pos = 0;
    if (noCent) pos = ifmt.length + 1 + Math.min(antes, 2);
    else if (inteiro) {
      // cursor logo depois do mesmo dígito em que estava (os pontos não contam)
      for (var k = 0, d = 0, n = Math.min(antes, inteiro.length); k < ifmt.length && d < n; k++) {
        if (/\d/.test(ifmt[k])) d++;
        pos = k + 1;
      }
    }
    if (novo !== el.value) trocar(el, novo, pos);
  }
  function antesDeDigitar(e) {
    var el = e.target, v = el.value, i = v.indexOf(","), a = el.selectionStart, b = el.selectionEnd;
    if (e.inputType === "insertText" && (e.data === "," || e.data === ".")) {
      e.preventDefault();                        // vírgula ou ponto = ir para os centavos
      if (i < 0) {
        var dig = v.replace(/\D/g, "");
        trocar(el, (dig ? milhar(dig.replace(/^0+(?=\d)/, "")) : "0") + ",00", 0);
        i = el.value.indexOf(",");
      }
      el.setSelectionRange(i + 1, i + 3);        // centavos marcados: digitar troca eles
    } else if (e.inputType === "deleteContentBackward" && a === b && i >= 0 && a === i + 1) {
      e.preventDefault(); el.setSelectionRange(i, i);   // apagar a vírgula = só pular para antes dela
    } else if (e.inputType === "deleteContentForward" && a === b && a === i) {
      e.preventDefault(); el.setSelectionRange(i + 1, i + 1);
    }
  }
  function cursorNoInteiro(el) {
    // tocou no campo e o cursor caiu no fim (depois do ",00"): volta para antes da vírgula,
    // senão o próximo número digitado iria para os centavos
    setTimeout(function () {
      var v = el.value, i = v.indexOf(",");
      if (i >= 0 && v.slice(i + 1) === "00" && el.selectionStart === el.selectionEnd && el.selectionStart > i)
        el.setSelectionRange(i, i);
    }, 0);
  }
  function preparar() {
    document.querySelectorAll('[class*="' + MARCA + '"] input:not([data-rs])').forEach(function (el) {
      el.setAttribute("data-rs", "1");
      el.setAttribute("inputmode", "decimal");
      el.setAttribute("autocomplete", "off");
      el.addEventListener("beforeinput", antesDeDigitar);
      el.addEventListener("input", function () { if (!mexendo) formatar(el); });
      el.addEventListener("focus", function () { cursorNoInteiro(el); });
      el.addEventListener("click", function () { cursorNoInteiro(el); });
    });
    // Telefone (chave termina em "__tel"): teclado de telefone no celular
    document.querySelectorAll('[class*="__tel"] input:not([data-tel])').forEach(function (el) {
      el.setAttribute("data-tel", "1");
      el.setAttribute("inputmode", "tel");
      el.setAttribute("autocomplete", "off");
    });
    document.querySelectorAll('.stTextInput input:not([data-cap]):not([data-rs]), .stTextArea textarea:not([data-cap])')
      .forEach(function (el) {
        el.setAttribute("data-cap", "1");
        if (el.closest('[class*="email"]')) {   // Gmail: teclado de e-mail, sem maiúscula
          el.setAttribute("autocapitalize", "none");
          el.setAttribute("inputmode", "email");
        } else if (!el.closest(".st-key-quem_novo, .st-key-cf_novo")) el.setAttribute("autocapitalize", "characters");
      });
  }
  var agendado = false;
  preparar();
  new MutationObserver(function () {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(function () { agendado = false; preparar(); });
  }).observe(document.body, {childList: true, subtree: true});
}
</script>
"""


def _campos_do_celular():
    _iframe_invisivel(_JS_CAMPOS)


def _iframe_invisivel(html_js: str):
    """
    Roda um script num iframe de altura zero. `st.components.v1.html` foi
    marcado para remoção (o aviso dava prazo até 01/06/2026): quando ele sumir,
    chamar ele derruba TODAS as telas menos a inicial. Por isso usa `st.iframe`
    (versões novas) e só cai no antigo em Streamlit velho.
    """
    if hasattr(st, "iframe"):
        st.iframe(html_js, height=1)
    else:
        components.html(html_js, height=0)


# ── Roteador ──────────────────────────────────────────────────────────────────

st.session_state.setdefault("tela", "inicio")
_esperar_gravacao_em_andamento()   # gravação que começou numa rodada interrompida: mostra o desfecho (05/11)
_mostrar_flash()
if _modo_demo():
    st.markdown("<div class='demo-faixa'><b>Demonstração</b> · clientes de exemplo, pode testar à "
                "vontade: nada aqui é real nem vai para a planilha.</div>", unsafe_allow_html=True)

telas = {
    "inicio": tela_inicio,
    "nova": tela_nova,
    "pix": tela_pix,
    "cartao": tela_cartao,
    "hibrido": tela_hibrido,
    "permuta": tela_permuta,
    "relatorio": tela_relatorio,
    "cobranca": tela_cobranca,
    "excluidas": tela_excluidas,
    "notificacoes": tela_notificacoes,
    "config": tela_config,
    "feriados": tela_feriados,
    "juridico": tela_juridico,
    "judicial": tela_judicial,
    "jud_form": tela_jud_form,
    "jud_ficha": tela_jud_ficha,
    "protestos": tela_protestos,
    "prot_form": tela_prot_form,
}
if st.session_state.tela not in telas:
    st.session_state.tela = "inicio"
# Telas que quem tem acesso SÓ AO JURÍDICO pode abrir (lista do que PODE: tela nova fica fechada
# para essa pessoa até alguém pôr aqui de propósito)
TELAS_SO_JURIDICO = {"juridico", "judicial", "jud_form", "jud_ficha", "protestos", "prot_form", "notificacoes"}

st.session_state["_avisou_fora"] = False   # o aviso "a planilha não respondeu" aparece uma vez por tela
try:
    if _identificado():
        if _so_juridico() and st.session_state.tela not in TELAS_SO_JURIDICO:
            st.session_state.tela = "juridico"
        telas[st.session_state.tela]()
        _voltar_do_celular()
        _campos_do_celular()
        _renovar_cookie_do_aparelho()
except PlanilhaFora:
    # A planilha não respondeu e ainda não há uma leitura boa guardada: em vez de uma tela errada
    # (ex.: "Quem está usando?" sem ninguém na lista), o aviso com "Tentar de novo"
    st.markdown("<div class='hm-marca' style='margin-top:.8rem'>Cobranças</div>", unsafe_allow_html=True)
    _aviso_planilha_fora()

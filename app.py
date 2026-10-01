import html as _html
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from dados import (Local, Planilha, drive_configurado, enviar_comprovante, excluir_cobranca,
                   restaurar_cobranca)
from demo import banco_demo
from nucleo import (CLI_ATRASADO, CLI_EM_BREVE, CLI_EM_DIA, CLI_QUITADO, ROTULO_CLI,
                    SIT_ATRASADA, SIT_EM_BREVE, SIT_PAGA, STATUS_PAGA, TIPO_CARTAO, TIPO_PIX,
                    TREINAMENTOS, agenda, conferir_total, datas_continuas, data_br, filtrar,
                    formatar_brl, inicio_semana, mes_mais, montar_cobrancas, nome_mes,
                    normalizar_turma, ordenar_para_cobrar, parcelas_cartao, parcelas_pix,
                    proximo_numero, resolver_valores, resumo, valor_para_float)

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
SVG_SETA = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>')

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
    return _banco().carregar()


def _invalidar():
    """Depois de qualquer gravação: a próxima tela lê a planilha de novo."""
    _carregar.clear()


def _cobrancas(incluir_excluidas: bool = False):
    """Cobranças já calculadas. None se a planilha não pôde ser lida (erro já mostrado)."""
    if _banco() is None:
        st.error("A planilha ainda não foi configurada nos Secrets do app.")
        return None
    try:
        with st.spinner("Carregando..."):
            d = _carregar()
    except Exception as e:
        st.error(f"Não consegui ler a planilha: {e}")
        return None
    return montar_cobrancas(d["cobrancas"], d["parcelas"], _hoje(), incluir_excluidas)


def _cobranca(cid: str):
    for c in _cobrancas(incluir_excluidas=True) or []:
        if c["id"] == cid:
            return c
    return None


def _usuario() -> str:
    """E-mail de quem está usando (o Streamlit Cloud informa em app fechado)."""
    try:
        u = st.user
        email = u.get("email") if hasattr(u, "get") else getattr(u, "email", None)
        return str(email or "")
    except Exception:
        return ""


# ── Tamanho do texto ──────────────────────────────────────────────────────────

TAMANHOS = {"Pequeno": 0.8, "Médio": 0.9, "Grande": 1.0}
TAMANHO_PADRAO = "Médio"


@st.cache_data(ttl=600, show_spinner=False)
def _config() -> dict:
    try:
        return _banco().get_config() if _banco() else {}
    except Exception:
        return {}


def _tamanho_atual() -> str:
    if "_tamanho" not in st.session_state:
        salvo = _config().get("tamanho_texto")
        st.session_state["_tamanho"] = salvo if salvo in TAMANHOS else TAMANHO_PADRAO
    return st.session_state["_tamanho"]


def _mudar_tamanho():
    novo = st.session_state.get("_seg_tamanho")
    if novo not in TAMANHOS:
        # Tocar de novo na opção marcada desmarca: volta para a que estava
        st.session_state["_seg_tamanho"] = st.session_state.get("_tamanho", TAMANHO_PADRAO)
        return
    if novo != st.session_state.get("_tamanho"):
        st.session_state["_tamanho"] = novo
        try:
            _banco().save_config("tamanho_texto", novo)
            _config.clear()
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
    return _html.escape(str(texto if texto is not None else ""))


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
        st.toast(msg, icon=icone)


def _cabecalho(titulo: str, voltar_para: str, subtitulo: str = ""):
    if st.button("Voltar", key="voltar_topo", icon=":material/arrow_back:", type="tertiary"):
        _ir(voltar_para)
    sub = f"<div class='cx-sub'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(f"<div class='cx-titulo'>{_e(titulo)}</div>{sub}", unsafe_allow_html=True)


def _titulo_secao(numero: int, texto: str):
    st.markdown(f"<div class='sec-tit'><span>{numero}</span>{_e(texto)}</div>", unsafe_allow_html=True)


def _info(html_txt: str, classe: str = "cx-info"):
    st.markdown(f"<div class='{classe}'>{html_txt}</div>", unsafe_allow_html=True)


def _valor(rotulo: str, key: str, placeholder: str = "0,00", help: str = None):
    """
    Campo de valor em reais. Devolve (valor, ok): valor None = em branco;
    ok False = digitou algo que não é valor (o aviso já aparece embaixo).
    """
    txt = st.text_input(rotulo, key=key, placeholder=placeholder, help=help)
    if not txt.strip():
        return None, True
    v = valor_para_float(txt)
    if v is None or v < 0:
        st.caption(":red[Valor inválido. Ex.: 1500 ou 1.500,50]")
        return None, False
    return v, True


def _data_curta(d: date, hoje: date) -> str:
    return d.strftime("%d/%m") if d.year == hoje.year else d.strftime("%d/%m/%Y")


def _limpar_campos(prefixo: str):
    for k in [k for k in st.session_state if str(k).startswith(prefixo)]:
        del st.session_state[k]


def _cartao_toque(chave_container: str, chave_botao: str, rotulo: str, html_cartao: str) -> bool:
    """Cartão inteiro tocável: o botão fica invisível por cima dele."""
    with st.container(key=chave_container):
        st.markdown(html_cartao, unsafe_allow_html=True)
        return st.button(rotulo, key=chave_botao)


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
                      "Nova cobrança", "Pix ou cartão"):
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

    st.session_state.setdefault("_seg_tamanho", _tamanho_atual())
    st.segmented_control("Tamanho do texto", list(TAMANHOS), key="_seg_tamanho",
                         on_change=_mudar_tamanho)

    if st.button("Cobranças excluídas", key="btn_excluidas", icon=":material/restore_from_trash:",
                 type="tertiary"):
        _ir("excluidas")

    if _modo_demo() and st.button("Recomeçar o exemplo do zero", key="btn_demo_reset",
                                  icon=":material/refresh:", type="tertiary"):
        banco_demo(_hoje(), recomecar=True)
        _invalidar()
        _flash("Exemplo recomeçado")
        st.rerun()


# ── Nova cobrança: escolher o tipo ────────────────────────────────────────────

def tela_nova():
    _cabecalho("Nova cobrança", voltar_para="inicio", subtitulo="Como o cliente vai pagar?")
    if _cartao_inicio("hm_pix", "tq_pix", "Cobrança Pix", "claro", SVG_PIX,
                      "Cobrança Pix", "Entrada + parcelas por mês"):
        _limpar_campos("px_")
        _ir("pix")
    if _cartao_inicio("hm_cartao", "tq_cartao", "Cobrança cartão", "claro", SVG_CARTAO,
                      "Cobrança cartão", "Até 10 datas para passar o cartão"):
        _limpar_campos("ct_")
        _ir("cartao")


def _bloco_cliente(prefixo: str):
    """Cliente + turma (o treinamento sai da letra da turma). Devolve (cliente, turma, treino, erros)."""
    _titulo_secao(1, "Cliente")
    cliente = st.text_input("Nome do cliente", key=f"{prefixo}cliente").strip()
    turma_txt = st.text_input("Turma", key=f"{prefixo}turma", placeholder="Ex.: L345",
                              help="Letra do treinamento + número. L = LORAP, V = Vendas, "
                                   "I = Impacto, P = Perfil. L00345 e l345 dão no mesmo.")
    turma = normalizar_turma(turma_txt)
    treino = TREINAMENTOS[turma[0]] if turma else ""
    if turma:
        _info(f"Turma <b>{turma}</b> · {treino}")
    elif turma_txt.strip():
        st.caption(":red[Comece pela letra do treinamento (L, V, I ou P) e depois o número. Ex.: L345]")
    erros = []
    if not cliente:
        erros.append("Falta o nome do cliente.")
    if not turma:
        erros.append("Falta a turma (ex.: L345).")
    return cliente, turma, treino, erros


def _bloco_conferencia(total, partes, prefixo: str) -> bool:
    """Mostra se as partes fecham com o total. Devolve False se não fecha e não foi confirmado."""
    if total is None:
        return True
    dif = conferir_total(total, partes)
    if abs(dif) < 0.005:
        _info(f"<b>Fecha certinho</b> com o total de {formatar_brl(total)}.", "cx-ok")
        return True
    txt = (f"Faltam <b>{formatar_brl(dif)}</b> para chegar no total" if dif > 0
           else f"Passa <b>{formatar_brl(-dif)}</b> do total")
    _info(f"{txt} de {formatar_brl(total)}.", "cx-perigo")
    return st.checkbox("Está certo assim, salvar mesmo com a diferença", key=f"{prefixo}aceito_dif")


def _salvar(tipo: str, cliente: str, turma: str, treino: str, total: float, parcelas: list, prefixo: str):
    if st.session_state.get("_salvando"):
        return
    st.session_state["_salvando"] = True
    try:
        cid = _banco().criar_cobranca(
            {"Tipo": tipo, "Cliente": cliente, "Turma": turma, "Treinamento": treino,
             "Valor Total": total, "Criada em": _hoje(), "Criada por": _usuario()},
            parcelas,
        )
    except Exception as e:
        st.error(f"Não consegui salvar: {e}")
        return
    finally:
        st.session_state["_salvando"] = False
    _invalidar()
    _limpar_campos(prefixo)
    st.session_state.cob_id = cid
    st.session_state.cob_volta = "inicio"
    _flash(f"Cobrança de {cliente} salva")
    _ir("cobranca")


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
    valores, datas = [], []
    with st.container(key="sec_px3"):
        _titulo_secao(3, "Parcelas")
        n = st.number_input("Número de parcelas", min_value=1, max_value=60, value=None, step=1,
                            key="px_n", placeholder="Ex.: 10")
        modo_valor = st.radio("Valor das parcelas", ["Contínuo", "Parcial"], horizontal=True,
                              key="px_mv", captions=["igual todo mês", "muda por mês"])
        modo_data = st.radio("Vencimento", ["Contínuo", "Parcial"], horizontal=True,
                             key="px_md", captions=["mesmo dia todo mês", "escolher cada data"])
        primeira = st.date_input("1º vencimento", value=mes_mais(data_entrada or hoje, 1),
                                 format="DD/MM/YYYY", key="px_primeira")

        if n:
            n = int(n)
            if modo_valor == "Contínuo":
                sugestao = restante / n if restante else 0
                vp, ok_v = _valor("Valor de cada parcela", "px_vparc",
                                  placeholder=f"{sugestao:.2f}".replace(".", ",") if sugestao else "0,00",
                                  help="Em branco = divide o que falta igual entre as parcelas.")
                if not ok_v:
                    erros.append("Tem valor digitado errado.")
                valores = [vp] * n if vp is not None else resolver_valores(restante, [None] * n)
            base = datas_continuas(primeira, n) if primeira else [None] * n

            if modo_valor == "Parcial" or modo_data == "Parcial":
                st.markdown("<div class='px-lista'>Parcela por parcela</div>", unsafe_allow_html=True)
                digitados = []
                for k in range(n):
                    with st.container(key=f"px_linha_{k}"):
                        cols = st.columns(2) if modo_valor == "Parcial" and modo_data == "Parcial" else [st.container()]
                        if modo_valor == "Parcial":
                            with cols[0]:
                                v, ok_v = _valor(f"Valor da {k + 1}ª", f"px_v{k}_{n}",
                                                 placeholder="em branco = divide")
                                if not ok_v:
                                    erros.append("Tem valor digitado errado.")
                                digitados.append(v)
                        if modo_data == "Parcial":
                            with cols[-1]:
                                # A chave leva o 1º vencimento: trocar ele recalcula as datas sugeridas
                                datas.append(st.date_input(
                                    f"Vencimento da {k + 1}ª", value=base[k], format="DD/MM/YYYY",
                                    key=f"px_d{k}_{n}_{primeira}"))
                if modo_valor == "Parcial":
                    valores = resolver_valores(restante, digitados)
            if modo_data == "Contínuo":
                datas = base

            if any(d is None for d in datas):
                erros.append("Falta alguma data de vencimento.")
            if total and any(v <= 0 for v in valores):
                erros.append("Tem parcela com valor zero ou negativo.")
        else:
            erros.append("Falta o número de parcelas.")

    # ── Resumo calculado ──
    confirmado = True
    with st.container(key="sec_px4"):
        _titulo_secao(4, "Resumo")
        linhas = []
        if entrada > 0 and data_entrada:
            paga = "paga" if data_entrada <= hoje else "a receber"
            linhas.append(f"Entrada de <b>{formatar_brl(entrada)}</b> em {data_br(data_entrada)} ({paga})")
        if valores and datas and all(datas):
            iguais = len(set(round(v, 2) for v in valores)) == 1
            parc = (f"<b>{len(valores)}x de {formatar_brl(valores[0])}</b>" if iguais
                    else f"<b>{len(valores)} parcelas</b> somando {formatar_brl(sum(valores))}")
            linhas.append(f"{parc}, de {data_br(min(datas))} a {data_br(max(datas))}")
            linhas.append(f"A cobrança vai até <b>{nome_mes(max(datas))}</b>")
            if sorted(datas) != datas:
                linhas.append(":warning: As datas não estão em ordem")
        if linhas:
            _info("<br>".join(linhas))
            if valores:
                confirmado = _bloco_conferencia(total, [entrada] + valores, "px_")
            _info("O Telegram avisa vocês 1 dia antes de cada vencimento, no dia, "
                  "e todo dia enquanto estiver atrasado.", "cx-nota")
        else:
            st.caption("Preencha os valores e as parcelas para ver o resumo.")

    if st.button("Salvar cobrança", type="primary", key="px_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            _salvar(TIPO_PIX, cliente, turma, treino, total,
                    parcelas_pix(entrada, data_entrada, valores, datas, hoje), "px_")


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

    valores, datas = [], []
    with st.container(key="sec_ct3"):
        _titulo_secao(3, "Datas para passar o cartão")
        st.caption("Para quando o cliente não tem limite para passar tudo de uma vez.")
        n = st.number_input("Em quantas vezes vai passar?", min_value=1, max_value=10, value=None,
                            step=1, key="ct_n", placeholder="De 1 a 10")
        if n:
            n = int(n)
            digitados = []
            for k in range(n):
                with st.container(key=f"ct_linha_{k}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        datas.append(st.date_input(f"Data {k + 1}", value=None, format="DD/MM/YYYY",
                                                   key=f"ct_d{k}"))
                    with c2:
                        v, ok_v = _valor(f"Valor {k + 1}", f"ct_v{k}", placeholder="em branco = divide")
                        if not ok_v:
                            erros.append("Tem valor digitado errado.")
                        digitados.append(v)
            valores = resolver_valores(a_cobrar, digitados)
            if any(d is None for d in datas):
                erros.append("Falta escolher alguma data.")
            if total and any(v <= 0 for v in valores):
                erros.append("Tem data com valor zero ou negativo.")
        else:
            erros.append("Falta dizer em quantas vezes vai passar.")

    confirmado = True
    with st.container(key="sec_ct4"):
        _titulo_secao(4, "Resumo")
        if valores and all(datas):
            linhas = [f"<b>{data_br(d)}</b> · {formatar_brl(v)}" for d, v in sorted(zip(datas, valores))]
            _info("<br>".join(linhas) + f"<br>A cobrança vai até <b>{nome_mes(max(datas))}</b>")
            confirmado = _bloco_conferencia(total, [ja_pago] + valores, "ct_")
            _info("O Telegram avisa vocês 1 dia antes de cada data, no dia, "
                  "e todo dia enquanto não passar.", "cx-nota")
        else:
            st.caption("Escolha as datas para ver o resumo.")

    if st.button("Salvar cobrança", type="primary", key="ct_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ordem = sorted(zip(datas, valores))
            _salvar(TIPO_CARTAO, cliente, turma, treino, total,
                    parcelas_cartao(ja_pago, hoje, [v for _, v in ordem], [d for d, _ in ordem]), "ct_")


# ── Relatório ─────────────────────────────────────────────────────────────────

def _chip_sit(sit: str) -> str:
    return f"<span class='sit {COR_CLI[sit]}'>{ROTULO_CLI[sit]}</span>"


def _linha_estado(c: dict, hoje: date) -> str:
    if c["situacao"] == CLI_QUITADO:
        return "Tudo pago"
    if c["situacao"] == CLI_ATRASADO:
        d = c["dias_atraso"]
        return (f"<b>{formatar_brl(c['atrasado'])}</b> atrasado · há {d} dia{'s' if d > 1 else ''}")
    p = c["proxima"]
    if p:
        quando = ("hoje" if p["vencimento"] == hoje else "amanhã" if p["vencimento"] == hoje + timedelta(days=1)
                  else _data_curta(p["vencimento"], hoje))
        return f"Próxima: <b>{quando}</b> · {formatar_brl(p['valor'])}"
    return ""


def _html_cliente(c: dict, hoje: date) -> str:
    total = c["pago"] + c["falta"]
    pct = int(round(100 * c["pago"] / total)) if total else 0
    selo = "<div class='cc-selo'>QUITADO</div>" if c["situacao"] == CLI_QUITADO else ""
    return (
        f"<div class='cc {COR_CLI[c['situacao']]}'>"
        f"<div class='cc-topo'><span class='cc-turma'>{_e(c['turma'])} · {_e(c['treinamento'])} · "
        f"{_e(c['tipo'])}</span>{'' if selo else _chip_sit(c['situacao'])}</div>"
        f"<div class='cc-nome'>{_e(c['cliente'])}</div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='cc-val'>Pago <b>{formatar_brl(c['pago'])}</b> · falta <b>{formatar_brl(c['falta'])}</b></div>"
        f"<div class='cc-est'>{_linha_estado(c, hoje)}</div>{selo}</div>"
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

    termo = st.text_input("Buscar", key="rf_busca", placeholder="Nome do cliente ou turma (ex.: L345)",
                          label_visibility="collapsed", icon=":material/search:")

    with st.expander("Filtros", icon=":material/tune:"):
        sits = st.pills("Situação", list(SITUACOES_FILTRO), selection_mode="multi", key="rf_sit")
        tipos = st.pills("Forma", [TIPO_PIX, TIPO_CARTAO], selection_mode="multi", key="rf_tipo")
        treinos = st.pills("Treinamento", list(TREINAMENTOS.values()), selection_mode="multi", key="rf_trein")
        turma = st.text_input("Turma", key="rf_turma", placeholder="Ex.: L345")
        if turma.strip() and not normalizar_turma(turma):
            st.caption(":red[Turma não reconhecida. Ex.: L345]")

    filtradas = filtrar(cobs, termo, [SITUACOES_FILTRO[s] for s in sits or []], tipos or None,
                        treinos or None, turma)
    st.markdown(_html_resumo(resumo(filtradas)), unsafe_allow_html=True)

    visao = st.segmented_control("Ver", ["Clientes", "Agenda"], key="rf_visao", default="Clientes",
                                 label_visibility="collapsed")
    if visao == "Agenda":
        _visao_agenda(filtradas, hoje)
    else:
        _visao_clientes(filtradas, hoje, bool(termo or sits or tipos or treinos or turma))

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
        return f"Hoje · {DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"
    if d == hoje + timedelta(days=1):
        return f"Amanhã · {DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"
    return f"{DIAS_SEMANA[d.weekday()]} {_data_curta(d, hoje)}"


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
    if d:
        bloco = (f"<div class='pc-data'><span class='pc-mes'>{MESES_ABREV[d.month - 1]}</span>"
                 f"<span class='pc-dia'>{d.day}</span><span class='pc-sem'>{DIAS_SEMANA[d.weekday()]}</span></div>")
    else:
        bloco = "<div class='pc-data'><span class='pc-dia'>?</span></div>"
    if p["paga"]:
        sit = ""
        pago_em = f"<small>{p['pago_em'].strftime('%d/%m/%y')}</small>" if p["pago_em"] else ""
        carimbo = f"<div class='pc-carimbo'>{'PASSOU' if c['tipo'] == TIPO_CARTAO else 'PAGO'}{pago_em}</div>"
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
    topo = f"{_e(c['turma'])} · {_e(c['treinamento'])}" if mostrar_cliente else ""
    nome = f"<div class='pc-nome'>{_e(c['cliente'])}</div>" if mostrar_cliente else ""
    return (
        f"<div class='pc {cor}{' pago' if p['paga'] else ''}'>{bloco}<div class='pc-corpo'>"
        f"<div class='pc-topo'><span class='pc-tag'>{topo}</span>{sit}</div>{nome}"
        f"<div class='pc-rot'>{_e(p['rotulo'])}</div>"
        f"<div class='pc-valor'>{formatar_brl(p['valor'])}</div></div>{carimbo}</div>"
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
        rot_receber = "Passou" if c["tipo"] == TIPO_CARTAO else "Recebi"
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
    quando = st.date_input("Recebido em" if c["tipo"] == TIPO_PIX else "Passou em", value=_hoje(),
                           format="DD/MM/YYYY", key=f"{k}_data")
    arquivo = None
    sec = _secrets_drive()
    if sec:
        arquivo = st.file_uploader("Comprovante (opcional)", type=["pdf", "png", "jpg", "jpeg", "webp"],
                                   key=f"{k}_arq")
    if st.button("Confirmar", type="primary", key=f"{k}_ok", use_container_width=True,
                 icon=":material/check:"):
        link = ""
        if arquivo is not None:
            try:
                with st.spinner("Enviando comprovante..."):
                    link = enviar_comprovante(sec, arquivo.getvalue(), arquivo.name, c["treinamento"],
                                              f"{c['cliente']} - {c['turma']} - {p['rotulo']}", quando)
            except Exception as e:
                st.error(f"O comprovante não subiu ({e}). Nada foi marcado; tente de novo "
                         "ou confirme sem o comprovante.")
                return
        try:
            ok = _banco().atualizar_parcela(cid, n, {"Status": STATUS_PAGA, "Pago em": quando,
                                                    "Comprovante": link, "Marcado por": _usuario()})
        except Exception as e:
            st.error(f"Não consegui salvar: {e}")
            return
        if not ok:
            st.error("Essa parcela não foi encontrada na planilha. Atualize a tela.")
            return
        _invalidar()
        _flash(f"{p['rotulo']} de {c['cliente']} marcada como paga")
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
                    st.error(f"Não consegui salvar: {e}")
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
    novo_valor, ok_v = _valor("Valor", f"{k}_valor", placeholder=f"{p['valor']:.2f}".replace(".", ","),
                              help="Em branco = continua o mesmo valor.")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not ok_v or not nova_data or (novo_valor is not None and novo_valor <= 0):
            st.error("Confira a data e o valor.")
            return
        campos = {"Vencimento": nova_data}
        if novo_valor is not None:
            campos["Valor"] = novo_valor
        try:
            _banco().atualizar_parcela(cid, n, campos)
        except Exception as e:
            st.error(f"Não consegui salvar: {e}")
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
                    st.error(f"Não consegui remover: {e}")
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
    data = st.date_input("Data", value=mes_mais(ultima, 1) if c["tipo"] == TIPO_PIX else None,
                         format="DD/MM/YYYY", key=f"{k}_data")
    valor, ok_v = _valor("Valor", f"{k}_valor")
    if st.button("Adicionar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/add:"):
        if not data or not ok_v or not valor:
            st.error("Preencha a data e o valor.")
            return
        try:
            _banco().adicionar_parcela(cid, {"Nº": proximo_numero(c["parcelas"]), "Vencimento": data,
                                             "Valor": valor})
        except Exception as e:
            st.error(f"Não consegui salvar: {e}")
            return
        _invalidar()
        _flash("Adicionado")
        st.rerun()


@st.dialog("Editar dados")
def _dlg_editar(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    k = f"_ed_{cid}"
    cliente = st.text_input("Nome do cliente", value=c["cliente"], key=f"{k}_cli").strip()
    turma_txt = st.text_input("Turma", value=c["turma"], key=f"{k}_turma")
    turma = normalizar_turma(turma_txt)
    if turma:
        _info(f"Turma <b>{turma}</b> · {TREINAMENTOS[turma[0]]}")
    else:
        st.caption(":red[Turma não reconhecida. Ex.: L345]")
    total, ok_t = _valor("Valor total", f"{k}_total",
                         placeholder=f"{(c['valor_total'] or 0):.2f}".replace(".", ","),
                         help="Em branco = continua o mesmo.")
    obs = st.text_area("Observações", value=c["observacoes"], key=f"{k}_obs", height=80)
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not cliente or not turma or not ok_t:
            st.error("Confira o nome, a turma e o valor.")
            return
        campos = {"Cliente": cliente, "Turma": turma, "Treinamento": TREINAMENTOS[turma[0]],
                  "Observações": obs.strip()}
        if total:
            campos["Valor Total"] = total
        try:
            _banco().atualizar_cobranca(cid, campos)
        except Exception as e:
            st.error(f"Não consegui salvar: {e}")
            return
        _invalidar()
        _flash("Dados salvos")
        st.rerun()


@st.dialog("Excluir cobrança")
def _dlg_excluir(cid: str):
    c = _cobranca(cid)
    if not c:
        return
    _info(f"Excluir a cobrança de <b>{_e(c['cliente'])}</b> ({_e(c['turma'])} · {_e(c['tipo'])})?<br>"
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
                st.error(f"Não consegui excluir: {e}")
                return
            _invalidar()
            _flash("Cobrança excluída")
            st.session_state.tela = st.session_state.get("cob_volta", "relatorio")
            st.rerun()


# ── Ficha da cobrança ─────────────────────────────────────────────────────────

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
               subtitulo=f"Turma {_e(c['turma'])} · {_e(c['treinamento'])} · {_e(c['tipo'])}")

    total = c["pago"] + c["falta"]
    pct = int(round(100 * c["pago"] / total)) if total else 0
    selo = "<span class='sit c-ok'>Quitado</span>" if c["situacao"] == CLI_QUITADO else _chip_sit(c["situacao"])
    ate = f"Vai até <b>{nome_mes(c['ultima'])}</b>" if c["ultima"] else ""
    aviso_total = ""
    if c["valor_total"] and abs(conferir_total(c["valor_total"], [total])) >= 0.005:
        aviso_total = (f"<div class='fc-aviso'>O total combinado é {formatar_brl(c['valor_total'])}, "
                       f"mas as parcelas somam {formatar_brl(total)}.</div>")
    st.markdown(
        f"<div class='fc {COR_CLI[c['situacao']]}'><div class='fc-topo'>{selo}<span>{ate}</span></div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='fc-nums'><div><b>{formatar_brl(c['pago'])}</b><span>Pago</span></div>"
        f"<div><b>{formatar_brl(c['falta'])}</b><span>Falta</span></div>"
        f"<div class='{'atr' if c['atrasado'] else ''}'><b>{formatar_brl(c['atrasado'])}</b><span>Atrasado</span></div>"
        f"</div>{aviso_total}</div>",
        unsafe_allow_html=True,
    )
    if c["observacoes"]:
        _info(_e(c["observacoes"]), "cx-nota")

    for p in c["parcelas"]:
        _parcela_ui(p, c, hoje, contexto="fc")

    rot_add = "Adicionar data" if c["tipo"] == TIPO_CARTAO else "Adicionar parcela"
    if st.button(rot_add, key="fc_add", icon=":material/add:", use_container_width=True):
        _dlg_adicionar(c["id"])
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Editar dados", key="fc_editar", icon=":material/edit:", use_container_width=True):
            _dlg_editar(c["id"])
    with c2:
        if st.button("Excluir", key="fc_excluir", icon=":material/delete:", use_container_width=True):
            _dlg_excluir(c["id"])


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
                f"<div class='lx-meta'>{_e(c['turma'])} · {_e(c['tipo'])} · pago {formatar_brl(c['pago'])}"
                f" · falta {formatar_brl(c['falta'])}</div><div class='lx-prazo'>{quando}</div>",
                unsafe_allow_html=True)
            if st.button("Restaurar", key=f"lxr_{c['id']}", icon=":material/restore:"):
                try:
                    restaurar_cobranca(_banco(), c["id"])
                except Exception as e:
                    st.error(f"Não consegui restaurar: {e}")
                    return
                _invalidar()
                _flash(f"Cobrança de {c['cliente']} restaurada")
                st.rerun()


# ── Voltar do celular ─────────────────────────────────────────────────────────

# Para onde cada tela volta com a setinha do aparelho ("inicio" sai do app).
_TELA_PAI = {"nova": "inicio", "pix": "nova", "cartao": "nova", "relatorio": "inicio",
             "excluidas": "inicio", "cobranca": None}


def _voltar_do_celular():
    """
    A setinha de voltar do celular navega dentro do app em vez de fechá-lo:
    um botão invisível faz a volta em Python e um script no documento principal
    intercepta o "voltar" do navegador e clica nele (mesma solução do boleto).
    """
    tela = st.session_state.tela
    if tela not in _TELA_PAI:
        return
    pai = _TELA_PAI[tela] or st.session_state.get("cob_volta", "relatorio")
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
_mostrar_flash()
if _modo_demo():
    st.markdown("<div class='demo-faixa'><b>Demonstração</b> · clientes de exemplo, pode testar à "
                "vontade: nada aqui é real nem vai para a planilha.</div>", unsafe_allow_html=True)

telas = {
    "inicio": tela_inicio,
    "nova": tela_nova,
    "pix": tela_pix,
    "cartao": tela_cartao,
    "relatorio": tela_relatorio,
    "cobranca": tela_cobranca,
    "excluidas": tela_excluidas,
}
if st.session_state.tela not in telas:
    st.session_state.tela = "inicio"
telas[st.session_state.tela]()
_voltar_do_celular()

import html as _html
import json
import os
import re
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

from dados import (Local, Planilha, drive_configurado, enviar_comprovante, excluir_cobranca,
                   receber_em_duas_formas, restaurar_cobranca)
from demo import banco_demo
import avisos_telegram
import feriados
import notifier
from nucleo import (CLI_ATRASADO, CLI_EM_BREVE, CLI_EM_DIA, CLI_QUITADO, OPCOES_AVISO, ROTULO_CLI, chave_busca,
                    administrador, aparelhos_por_pessoa, destinatarios, nome_do_aparelho, nomes_livres,
                    cidade_da_turma, local_da_cobranca, opcoes_avisos, pessoas_da_config,
                    formatar_telefone, link_ligar, link_whatsapp, telefone_do_cliente, telefone_valido,
                    dono_do_email, email_valido, emails_por_pessoa, login_google_ligado, normalizar_email,
                    pessoa_do_email,
                    texto_vezes,
                    FORMAS, TIPO_HIBRIDO, centavos, dividir_recebimento, parcelas_hibrido,
                    TIPO_PERMUTA, TIPO_CREDITO, parcelas_permuta, permutas_do_cliente,
                    SEP_TURMAS_PLANILHA, normalizar_turmas, treinamentos_das_turmas,
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


def _erro_campo(texto: str):
    """Aviso de erro embaixo de um campo. Não usa st.caption(":red[...]"): a legenda do
    Streamlit é meio transparente e, no modo noturno, o vermelho ficava apagado."""
    st.markdown(f"<div class='cx-erro'>{_e(texto)}</div>", unsafe_allow_html=True)


def _num_br(x: float) -> str:
    """1500 → '1.500,00' (o valor sem o 'R$', como aparece dentro dos campos)."""
    return formatar_brl(x).replace("R$ ", "")


MARCA_VALOR = "__rs"   # fim da chave de todo campo de valor: o script _JS_CAMPOS põe ponto do milhar e ",00"


def _valor(rotulo: str, key: str, placeholder: str = "0,00", help: str = None):
    """
    Campo de valor em reais. Devolve (valor, ok): valor None = em branco;
    ok False = digitou algo que não é valor (o aviso já aparece embaixo).
    Enquanto a pessoa digita, o navegador já mostra '1.500,00' (ver _JS_CAMPOS).
    """
    txt = st.text_input(rotulo, key=key + MARCA_VALOR, placeholder=placeholder, help=help)
    if not txt.strip():
        return None, True
    v = valor_para_float(txt)
    if v is None or v < 0:
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
        _config.clear()
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
        if chave_busca(_config().get(f"liberado:{final}", "")) == "sim":
            b.save_config(f"liberado:{final}", "")   # a liberação vale para UM aparelho
        _config.clear()
    except Exception as e:
        st.error(f"Não consegui guardar: {e}")
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
    if st.session_state.get("_quem"):
        return True
    if _banco() is None:
        return True   # sem planilha configurada: a tela inicial mostra o erro

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
    if nome and not trocando:
        st.session_state["_quem"] = nome
        return True

    travado = _travado()
    pessoas = pessoas_da_config(cfg)
    livres = nomes_livres(cfg) if travado else pessoas
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
            _info(f"Este aparelho ainda não tem acesso. Peça para <b>{adm}</b> liberar o seu nome "
                  "em <b>Configurações</b> e abra o app de novo.", "cx-perigo")
            if st.button("Já liberaram, tentar de novo", key="quem_denovo", icon=":material/refresh:",
                         use_container_width=True):
                _config.clear()
                st.rerun()
    return False


# ── Configurações (só o administrador) ────────────────────────────────────────

def _config_varias(pares: dict) -> bool:
    try:
        for chave, valor in pares.items():
            _banco().save_config(chave, valor)
        _config.clear()
        return True
    except Exception as e:
        _config.clear()
        st.error(f"Não consegui salvar: {e}")
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
            if st.button("Desligar e voltar para a trava por aparelho", key="cf_gg_desligar",
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

    if com_google:
        _secao_google(cfg, adm)

    for i, p in enumerate(pessoas):
        n = len(presos[p])
        liberado = chave_busca(cfg.get(f"liberado:{p}", "")) == "sim"
        if ligado:
            estado = ("<span class='sit c-ok'>Com Gmail</span>" if emails[p]
                      else "<span class='sit c-atraso'>Sem Gmail</span>")
        elif liberado:
            estado = "<span class='sit c-breve'>Liberado para 1 aparelho novo</span>"
        elif n:
            estado = f"<span class='sit c-ok'>{n} aparelho{'s' if n > 1 else ''}</span>"
        else:
            estado = "<span class='sit c-neutro'>Ainda não entrou</span>"
        telegram = "Telegram conectado" if cfg.get(f"telegram:{p}") else "Sem Telegram"
        with st.container(key=f"sec_cf_{i}"):
            st.markdown(f"<div class='nt-pessoa'><span>{_e(p)}{' · administrador' if p == adm else ''}</span>{estado}</div>"
                        f"<div class='cf-meta'>{telegram}</div>", unsafe_allow_html=True)
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
                    if n and not liberado and st.button("Liberar novo aparelho", key=f"cf_lib_{i}",
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
            else:
                pares = {"pessoas": ", ".join(pessoas + [nome])}
                if gmail:
                    pares[f"email:{nome}"] = gmail
                if _config_varias(pares):
                    _flash(f"{nome} adicionada. " + ("Peça para ela entrar com esse Gmail." if ligado
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
                      "Cobrança híbrida", "Uma parte no Pix, outra no cartão"):
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


def _bloco_cliente(prefixo: str):
    """
    Cliente + turma(s): o treinamento sai da letra de cada turma. A cobrança pode valer para mais
    de uma turma (pedido 16/10): o botão "Adicionar outra turma" abre mais um campo embaixo.
    Devolve (cliente, turma, treino, erros), com turma e treino já como vão para a planilha
    ("L345" e "LORAP", ou "L345, V12" e "LORAP, Vendas").
    """
    _titulo_secao(1, "Cliente")
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


def _salvar(tipo: str, cliente: str, turma: str, treino: str, total: float, parcelas: list, prefixo: str,
            observacoes: str = ""):
    if st.session_state.get("_salvando"):
        return
    st.session_state["_salvando"] = True
    try:
        cid = _banco().criar_cobranca(
            # Tudo que se digita vai em MAIÚSCULA (pedido 16/10)
            {"Tipo": tipo, "Cliente": cliente.upper(), "Turma": turma, "Treinamento": treino,
             "Valor Total": total, "Criada em": _hoje(), "Criada por": _usuario(),
             "Observações": observacoes.strip().upper(),
             "Cidade": " ".join(str(st.session_state.get(f"{prefixo}cidade", "")).split()).upper(),
             "Telefone": formatar_telefone(st.session_state.get(f"{prefixo}{CHAVE_TEL}", ""))},
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
    _flash(f"Cobrança de {cliente.upper()} salva")
    _ir("cobranca")


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


# ── Cobrança híbrida (uma parte no Pix, outra no cartão) ──────────────────────

def tela_hibrido():
    hoje = _hoje()
    _cabecalho("Cobrança híbrida", voltar_para="nova", subtitulo="Uma parte no Pix e outra no cartão")
    with st.container(key="sec_hb1"):
        cliente, turma, treino, erros = _bloco_cliente("hb_")

    parte_pix = parte_cartao = 0.0
    with st.container(key="sec_hb2"):
        _titulo_secao(2, "Valores")
        total, ok_t = _valor("Valor total", "hb_total")
        ajuda = "Preencha um dos dois: o outro é o que sobra do total."
        v_pix, ok_x = _valor("Quanto vai no Pix", "hb_v_pix", placeholder="em branco = o resto", help=ajuda)
        v_cartao, ok_c = _valor("Quanto vai no cartão", "hb_v_cartao", placeholder="em branco = o resto",
                                help=ajuda)
        if not (ok_t and ok_x and ok_c):
            erros.append("Tem valor digitado errado.")
        if total is None or total <= 0:
            erros.append("Falta o valor total.")
        elif v_pix is None and v_cartao is None:
            erros.append("Falta dizer quanto vai no Pix ou quanto vai no cartão.")
        else:
            if v_pix is None:
                v_pix = (centavos(total) - centavos(v_cartao)) / 100
            elif v_cartao is None:
                v_cartao = (centavos(total) - centavos(v_pix)) / 100
            if v_pix <= 0 or v_cartao <= 0:
                erros.append("O Pix e o cartão precisam ter valor, e nenhum pode passar do total. "
                             "Se é tudo de um jeito só, use a cobrança Pix ou a cobrança cartão.")
                _erro_campo("O Pix e o cartão precisam ter valor, e nenhum pode passar do total.")
            else:
                parte_pix, parte_cartao = v_pix, v_cartao
                _info(f"{_chip_tipo(TIPO_PIX)} <b>{formatar_brl(v_pix)}</b> &nbsp;+&nbsp; "
                      f"{_chip_tipo(TIPO_CARTAO)} <b>{formatar_brl(v_cartao)}</b>")

    data_entrada, valores_px, datas_px, pix_pagas = None, [], [], []
    with st.container(key="sec_hb3"):
        _titulo_secao(3, "Parte no Pix")
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

    with st.container(key="sec_hb4"):
        _titulo_secao(4, "Parte no cartão")
        st.caption("Uma data para cada vez que o cartão passa. Se já passou, coloque o dia em que passou.")
        valores_ct, datas_ct, vezes, passou = _bloco_passadas_cartao("hb_ct_", parte_cartao, total, erros,
                                                                    hoje=hoje)

    confirmado = True
    with st.container(key="sec_hb5"):
        _titulo_secao(5, "Resumo")
        # Aparece assim que o total está dividido (pedido 21/10): a parte ainda não preenchida
        # fica com "falta preencher", para dar para conferir enquanto preenche.
        linhas_px = _resumo_pix(entrada, data_entrada, valores_px, datas_px, hoje, com_fim=False, pagas=pix_pagas)
        linhas_ct = _resumo_cartao(0, valores_ct, datas_ct, vezes, passou, com_fim=False, cabecalho=False)
        if parte_pix:
            soma_px = entrada + sum(valores_px) if linhas_px else parte_pix
            soma_ct = sum(valores_ct) if valores_ct else parte_cartao
            linhas = [f"{_chip_tipo(TIPO_PIX)} <b>{formatar_brl(soma_px)}</b>"]
            linhas += linhas_px or ["<b>Falta preencher</b> a parte do Pix"]
            linhas.append(f"{_chip_tipo(TIPO_CARTAO)} <b>{formatar_brl(soma_ct)}</b>")
            linhas += linhas_ct or ["<b>Falta preencher</b> a parte do cartão"]
            if linhas_px and valores_ct and all(datas_ct):
                fim = max([d for d in datas_px if d] + datas_ct + ([data_entrada] if data_entrada else []))
                linhas.append(f"A cobrança vai até <b>{nome_mes(fim)}</b>")
            _info("<br>".join(linhas))
            if linhas_px and valores_ct:
                confirmado = _bloco_conferencia(total, [entrada] + valores_px + valores_ct, "hb_")
            _info("O Telegram avisa vocês 1 dia antes de cada data, no dia, "
                  "e todo dia enquanto estiver atrasado.", "cx-nota")
        else:
            st.caption("Preencha o valor total e quanto vai no Pix ou no cartão para ver o resumo.")

    obs_hb = st.text_input("Observação (opcional)", key="hb_obs", max_chars=300,
                           placeholder="Ex.: cartão do marido")
    if st.button("Salvar cobrança", type="primary", key="hb_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ordem = sorted(zip(datas_ct, valores_ct, vezes, passou))
            _salvar(TIPO_HIBRIDO, cliente, turma, treino, total,
                    parcelas_hibrido(entrada, data_entrada, valores_px, datas_px,
                                     [v for _, v, _, _ in ordem], [d for d, _, _, _ in ordem],
                                     [x for _, _, x, _ in ordem], [ok for _, _, _, ok in ordem], hoje, pix_pagas),
                    "hb_", obs_hb)


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


def _bloco_valores_permuta(prefixo: str, hoje: date, erros: list) -> list:
    """
    Cada valor de permuta que entrou, com a data dele, e o "+" para mais um (a mesma pessoa pode
    fechar outra permuta depois). Devolve [(data, valor)].
    """
    valores = []
    n = st.session_state.get(f"{prefixo}n_cred", 1)
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


# ── Relatório ─────────────────────────────────────────────────────────────────

def _chip_sit(sit: str) -> str:
    return f"<span class='sit {COR_CLI[sit]}'>{ROTULO_CLI[sit]}</span>"


def _chip_situacao(c: dict) -> str:
    """Situação da cobrança; a permuta tem a dela: com saldo ou saldo zerado."""
    if c.get("permuta"):
        return ("<span class='sit c-ok'>Com saldo</span>" if c["saldo"] > 0.005
                else "<span class='sit c-neutro'>Saldo zerado</span>")
    return _chip_sit(c["situacao"])


_CLASSE_TIPO = {TIPO_PIX: "tp-pix", TIPO_CARTAO: "tp-cartao", TIPO_HIBRIDO: "tp-hib", TIPO_PERMUTA: "tp-perm"}


def _chip_tipo(tipo: str) -> str:
    """Etiqueta da forma de pagamento: Pix azul, Cartão rosa (para bater o olho e diferenciar);
    Híbrido é metade de cada cor."""
    return f"<span class='tp {_CLASSE_TIPO.get(tipo, 'tp-pix')}'>{_e(tipo)}</span>"


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
        # na híbrida, diz de que forma é a próxima (umas são Pix, outras cartão)
        forma = f" · no {'cartão' if p['tipo'] == TIPO_CARTAO else 'Pix'}" if c["hibrida"] else ""
        return f"Próxima: <b>{data_br(p['vencimento'])}</b>{apelido} · {formatar_brl(p['valor'])}{forma}"
    return ""


def _html_cliente(c: dict, hoje: date) -> str:
    """Cartão compacto (3 linhas finas) para caber mais gente na tela; a barrinha de quanto já
    foi pago fica na borda de baixo."""
    total = c["pago"] + c["falta"]
    pct = int(round(100 * c["pago"] / total)) if total else 0
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
        estado = "" if quitado else f"<div class='cc-est'>{_linha_estado(c, hoje)}</div>"
    return (
        f"<div class='cc {COR_CLI[c['situacao']]}'>"
        f"<div class='cc-l1'><span class='cc-nome'>{_e(c['cliente'])}</span>{nota}"
        f"{_chip_tipo(c['tipo'])}{_chip_situacao(c)}</div>"
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
            st.error(f"Não consegui salvar: {e}")
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
            st.error(f"Não consegui salvar: {e}")
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
    # Vem na forma da cobrança; escolher a outra é o que torna a cobrança híbrida
    padrao = c["tipo"] if c["tipo"] in FORMAS else TIPO_PIX
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
            st.error(f"Não consegui salvar: {e}")
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
            st.error(f"Não consegui salvar: {e}")
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
               subtitulo=f"Turma {_e(local_da_cobranca(c))} · {_e(c['tipo'])}")
    _contato(c)
    if c["permuta"]:
        _ficha_permuta(c)
        return

    total = c["pago"] + c["falta"]
    pct = int(round(100 * c["pago"] / total)) if total else 0
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
                       f"mas as parcelas somam {formatar_brl(total)}.</div>")
    # Híbrida: quanto é de cada forma e quanto de cada uma já entrou
    formas = ""
    if c["hibrida"]:
        formas = "<div class='fc-formas'>" + "".join(
            f"<div>{_chip_tipo(f)}<span>{verbo} <b>{formatar_brl(c['por_forma'][f]['pago'])}</b> "
            f"de {formatar_brl(c['por_forma'][f]['total'])}</span></div>"
            for f, verbo in ((TIPO_PIX, "pago"), (TIPO_CARTAO, "passou"))) + "</div>"
    st.markdown(
        f"<div class='fc {COR_CLI[c['situacao']]}'><div class='fc-topo'>{selo}<span>{ate}</span></div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='fc-nums'><div><b>{formatar_brl(c['pago'])}</b><span>Pago</span></div>"
        f"<div><b>{formatar_brl(c['falta'])}</b><span>Falta</span></div>"
        f"<div class='{'atr' if c['atrasado'] else ''}'><b>{formatar_brl(c['atrasado'])}</b><span>Atrasado</span></div>"
        f"</div>{formas}{aviso_total}{quem}</div>",
        unsafe_allow_html=True,
    )
    _bloco_obs_ficha(c)

    if c["hibrida"]:
        # Um bloco para cada forma: primeiro tudo que é Pix, depois tudo que é cartão
        for forma, titulo in ((TIPO_PIX, "No Pix"), (TIPO_CARTAO, "No cartão")):
            st.markdown(f"<div class='fc-grupo'>{titulo}</div>", unsafe_allow_html=True)
            for p in c["parcelas"]:
                if p["tipo"] == forma:
                    _parcela_ui(p, c, hoje, contexto="fc")
    else:
        for p in c["parcelas"]:
            _parcela_ui(p, c, hoje, contexto="fc")

    rot_add = {TIPO_CARTAO: "Adicionar data", TIPO_HIBRIDO: "Adicionar parcela ou data"}.get(
        c["tipo"], "Adicionar parcela")
    if st.button(rot_add, key="fc_add", icon=":material/add:", use_container_width=True):
        _dlg_adicionar(c["id"])
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


def _ficha_permuta(c: dict):
    """Total (soma dos valores), retirado e saldo; cada valor com a data e cada retirada."""
    total = c["total_permuta"]
    retirado, saldo = c["pago"], c["saldo"]
    pct = min(int(round(100 * retirado / total)), 100) if total else 0
    quem = ""
    if c["criada_por"] or c["criada_em"]:
        por = f" por <b>{_e(c['criada_por'])}</b>" if c["criada_por"] else ""
        em = f" em {data_br(c['criada_em'])}" if c["criada_em"] else ""
        quem = f"<div class='fc-quem'>Cadastrada{por}{em}</div>"
    aviso = (f"<div class='fc-aviso'>As retiradas passam do total da permuta em {formatar_brl(-saldo)}.</div>"
             if saldo < -0.005 else "")
    n_ret = len(c["retiradas"])
    st.markdown(
        f"<div class='fc {'c-ok' if saldo > 0.005 else 'c-neutro'}'><div class='fc-topo'>{_chip_situacao(c)}"
        f"<span>{n_ret} retirada{'s' if n_ret != 1 else ''}</span></div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='fc-nums fc-perm'><div><b>{formatar_brl(total)}</b><span>Total da permuta</span></div>"
        f"<div><b>{formatar_brl(retirado)}</b><span>Retirado</span></div>"
        f"<div><b>{formatar_brl(max(saldo, 0))}</b><span>Saldo</span></div>"
        f"</div>{aviso}{quem}</div>",
        unsafe_allow_html=True,
    )
    _bloco_obs_ficha(c)

    # cada valor que entrou, com a data (a pessoa pode fechar outra permuta depois)
    st.markdown("<div class='fc-grupo'>Valores da permuta</div>", unsafe_allow_html=True)
    if c["creditos"]:
        for p in sorted(c["creditos"], key=lambda p: (p["vencimento"] or date.min, p["n"])):
            with st.container(key=f"pc_cr_{c['id']}_{p['n']}"):
                st.markdown(_html_valor_permuta(p["vencimento"], p["valor"], p["marcado_por"]),
                            unsafe_allow_html=True)
                if st.button("Alterar", key=f"cr_alt_{c['id']}_{p['n']}", icon=":material/edit:",
                             use_container_width=True):
                    _dlg_valor_permuta(c["id"], p["n"])
    else:   # permuta das primeiras versões: só o valor total, sem linha própria
        with st.container(key=f"pc_cr_{c['id']}_base"):
            st.markdown(_html_valor_permuta(c["criada_em"], total, c["criada_por"]), unsafe_allow_html=True)
    if st.button("Adicionar valor", key="fc_add_cred", icon=":material/add:", use_container_width=True,
                 help="Fechou mais uma permuta com essa pessoa? Põe o valor novo com a data dele."):
        _dlg_valor_permuta(c["id"])

    st.markdown("<div class='fc-grupo'>Retiradas</div>", unsafe_allow_html=True)
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

    # permuta do mesmo cliente cadastrada à parte (antes do "+" dos valores existir)
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
                if not c["creditos"] and total > 0:
                    # permuta antiga (só com o total): o total vira o 1º valor, na data do cadastro
                    base = c["criada_em"] or _hoje()
                    b.adicionar_parcela(cid, {**linha, "Nº": proximo, "Vencimento": base, "Pago em": base,
                                              "Valor": total, "Marcado por": c["criada_por"]})
                    proximo += 1
                b.adicionar_parcela(cid, {**linha, "Nº": proximo, "Vencimento": data, "Pago em": data,
                                          "Valor": valor})
                novo_total = total + valor
            b.atualizar_cobranca(cid, {"Valor Total": novo_total})   # "Valor Total" acompanha a soma
        except Exception as e:
            st.error(f"Não consegui salvar: {e}")
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
                  "Ele sai do total e do saldo.", "cx-perigo")
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
                        _banco().atualizar_cobranca(cid, {"Valor Total": total - p["valor"]})
                    except Exception as e:
                        st.error(f"Não consegui remover: {e}")
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
            st.error(f"Não consegui salvar: {e}")
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
                        st.error(f"Não consegui remover: {e}")
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


# ── Notificações ──────────────────────────────────────────────────────────────

def _token_bot() -> str:
    return str(_segredo("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()


@st.cache_data(ttl=3600, show_spinner=False)
def _usuario_do_bot(_token: str) -> str:
    return avisos_telegram.nome_do_bot(_token)


def _salvar_config(chave: str, valor: str) -> bool:
    try:
        _banco().save_config(chave, valor)
        _config.clear()
        return True
    except Exception as e:
        st.error(f"Não consegui salvar: {e}")
        return False


def _mudar_opcao_aviso(chave: str, widget: str):
    _salvar_config(chave, "sim" if st.session_state.get(widget) else "nao")


def tela_notificacoes():
    _cabecalho("Notificações", voltar_para="inicio",
               subtitulo="Avisos de cobrança no Telegram, todo dia às 7h30")
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
                    cobs = _cobrancas() or []
                    previa = notifier.montar_diario(cobs, _hoje(), opcoes_avisos(cfg))
                    avisos_telegram.enviar(token, meu_chat,
                                           "✅ <b>Teste dos avisos de cobrança</b>\nÉ assim que chega, todo dia às 7h30.\n\n"
                                           + (previa or "Hoje não há nada atrasado, nem para cobrar hoje ou amanhã."))
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
                st.error(f"Não consegui falar com o bot: {e}")
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
                        st.error(f"Não consegui falar com o Telegram: {e}")
                    if chat and _salvar_config(f"telegram:{eu}", chat):
                        _salvar_config(f"avisos:{eu}", "sim")
                        st.session_state.pop("_nt_codigo", None)
                        try:
                            avisos_telegram.enviar(token, chat, f"✅ Avisos de cobrança ligados para <b>{_e(eu)}</b>. "
                                                                "Eles chegam aqui todo dia às 7h30.")
                        except Exception:
                            pass
                        _flash("Telegram conectado")
                        st.rerun()
                    elif not chat:
                        _erro_campo("Ainda não vi o seu toque. Abra o bot pelo botão 1, toque em COMEÇAR "
                                    "e confirme aqui de novo.")

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
        for p in _pessoas():
            if p in recebem:
                estado = "<span class='sit c-ok'>Recebe</span>"
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
             "cobranca": None}


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
}
if st.session_state.tela not in telas:
    st.session_state.tela = "inicio"
if _identificado():
    telas[st.session_state.tela]()
    _voltar_do_celular()
    _campos_do_celular()
    _renovar_cookie_do_aparelho()

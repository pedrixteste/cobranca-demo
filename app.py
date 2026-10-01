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
                   restaurar_cobranca)
from demo import banco_demo
import avisos_telegram
import feriados
import notifier
from nucleo import (CLI_ATRASADO, CLI_EM_BREVE, CLI_EM_DIA, CLI_QUITADO, OPCOES_AVISO, ROTULO_CLI, chave_busca,
                    administrador, aparelhos_por_pessoa, destinatarios, nome_do_aparelho, nomes_livres,
                    MAX_VEZES_CARTAO, cidade_da_turma, local_da_cobranca, opcoes_avisos, pessoas_da_config,
                    texto_vezes,
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

MAX_DATAS_CARTAO = 20   # em quantas vezes dá para dividir a passada no cartão

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
        _erro_campo("Valor inválido. Ex.: 1500 ou 1.500,50")
        return None, False
    return v, True


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

    if _usuario() and _travado():
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


def _identificado() -> bool:
    """True se já se sabe quem está usando; senão mostra a tela certa e devolve False."""
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


def tela_config():
    _cabecalho("Configurações", voltar_para="inicio", subtitulo="Quem usa o app e em quais aparelhos")
    if not _sou_admin():
        st.info("Só o administrador do app abre esta tela.")
        return
    cfg = _config()
    pessoas = pessoas_da_config(cfg)
    presos = aparelhos_por_pessoa(cfg)
    adm = administrador(cfg)

    for i, p in enumerate(pessoas):
        n = len(presos[p])
        liberado = chave_busca(cfg.get(f"liberado:{p}", "")) == "sim"
        if liberado:
            estado = "<span class='sit c-breve'>Liberado para 1 aparelho novo</span>"
        elif n:
            estado = f"<span class='sit c-ok'>{n} aparelho{'s' if n > 1 else ''}</span>"
        else:
            estado = "<span class='sit c-neutro'>Ainda não entrou</span>"
        telegram = "Telegram conectado" if cfg.get(f"telegram:{p}") else "Sem Telegram"
        with st.container(key=f"sec_cf_{i}"):
            st.markdown(f"<div class='nt-pessoa'><span>{_e(p)}{' · administrador' if p == adm else ''}</span>{estado}</div>"
                        f"<div class='cf-meta'>{telegram}</div>", unsafe_allow_html=True)
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
        _info(f"Remover <b>{_e(alvo)}</b>? Os aparelhos e o Telegram dessa pessoa são desligados. "
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
                pares.update({f"aparelho:{a}": "" for a in presos[alvo]})
                st.session_state.pop("_cf_remover", None)
                if _config_varias(pares):
                    _flash(f"{alvo} removida do app")
                    st.rerun()

    with st.container(key="sec_cf_nova"):
        _titulo_secao(len(pessoas) + 1, "Adicionar pessoa")
        novo = st.text_input("Nome", key="cf_novo", max_chars=MAX_NOME, placeholder="Ex.: Gabi")
        if st.button("Adicionar", key="cf_add", type="primary", icon=":material/person_add:",
                     use_container_width=True):
            nome = " ".join(novo.replace(",", " ").replace(":", " ").split())
            if len(nome) < 2:
                _erro_campo("Digite o nome.")
            elif any(chave_busca(x) == chave_busca(nome) for x in pessoas):
                _erro_campo("Já existe uma pessoa com esse nome.")
            elif _config_varias({"pessoas": ", ".join(pessoas + [nome])}):
                _flash(f"{nome} adicionada. Peça para ela abrir o app e escolher o nome.")
                st.rerun()
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
                      "Cobrança cartão", f"Até {MAX_DATAS_CARTAO} datas para passar o cartão"):
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
        _erro_campo("Comece pela letra do treinamento (L, V, I ou P) e depois o número. Ex.: L345")
    # Cidade: texto livre e opcional (vai junto no _salvar, lida de st.session_state[f"{prefixo}cidade"])
    st.text_input("Cidade da turma", key=f"{prefixo}cidade", max_chars=40, placeholder="Ex.: Lajeado, SCS…",
                  help="Opcional. Escreva do jeito que quiser.")
    ja_usada = cidade_da_turma(_cobrancas() or [], turma) if turma else ""
    if ja_usada and not st.session_state.get(f"{prefixo}cidade", "").strip():
        st.markdown(f"<div class='cx-dica'>Outras cobranças da turma {_e(turma)} estão como "
                    f"<b>{_e(ja_usada)}</b>.</div>", unsafe_allow_html=True)
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


def _salvar(tipo: str, cliente: str, turma: str, treino: str, total: float, parcelas: list, prefixo: str,
            observacoes: str = ""):
    if st.session_state.get("_salvando"):
        return
    st.session_state["_salvando"] = True
    try:
        cid = _banco().criar_cobranca(
            {"Tipo": tipo, "Cliente": cliente, "Turma": turma, "Treinamento": treino,
             "Valor Total": total, "Criada em": _hoje(), "Criada por": _usuario(),
             "Observações": observacoes.strip(),
             "Cidade": " ".join(str(st.session_state.get(f"{prefixo}cidade", "")).split())},
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
                    parcelas_pix(entrada, data_entrada, valores, datas, hoje), "px_", obs_px)


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
        n = st.number_input("Quantas vezes você vai passar o cartão?", min_value=1, max_value=MAX_DATAS_CARTAO,
                            value=None, step=1, key="ct_n", placeholder=f"De 1 a {MAX_DATAS_CARTAO}",
                            help="Cada vez é um dia em que você passa o cartão do cliente. "
                                 "Em cada uma você diz o valor e em quantas parcelas ela foi dividida.")
        vezes = []
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
                    vezes.append(int(st.number_input(
                        f"Parcelado em quantas vezes ({k + 1}ª passada)", min_value=1, max_value=MAX_VEZES_CARTAO,
                        value=1, step=1, key=f"ct_x{k}",
                        help="Em quantas parcelas essa passada é dividida no cartão. 1 = à vista.")))
            valores = resolver_valores(a_cobrar, digitados)
            if any(d is None for d in datas):
                erros.append("Falta escolher alguma data.")
            if total and any(v <= 0 for v in valores):
                erros.append("Tem data com valor zero ou negativo.")
        else:
            erros.append("Falta dizer quantas vezes vai passar o cartão.")

    confirmado = True
    with st.container(key="sec_ct4"):
        _titulo_secao(4, "Resumo")
        if valores and all(datas):
            linhas = [f"<b>{data_br(d)}</b> · {formatar_brl(v)} · {texto_vezes(v, x)}"
                      for d, v, x in sorted(zip(datas, valores, vezes))]
            _info("<br>".join(linhas) + f"<br>A cobrança vai até <b>{nome_mes(max(datas))}</b>")
            confirmado = _bloco_conferencia(total, [ja_pago] + valores, "ct_")
            _info("O Telegram avisa vocês 1 dia antes de cada data, no dia, "
                  "e todo dia enquanto não passar.", "cx-nota")
        else:
            st.caption("Escolha as datas para ver o resumo.")

    obs_ct = st.text_input("Observação (opcional)", key="ct_obs", max_chars=300,
                           placeholder="Ex.: cartão do marido")
    if st.button("Salvar cobrança", type="primary", key="ct_salvar", use_container_width=True,
                 icon=":material/check:"):
        if not confirmado:
            erros.append("O valor não fecha com o total: confira ou marque a caixa acima.")
        if erros:
            st.error("\n".join(f"- {e}" for e in dict.fromkeys(erros)))
        else:
            ordem = sorted(zip(datas, valores, vezes))
            _salvar(TIPO_CARTAO, cliente, turma, treino, total,
                    parcelas_cartao(ja_pago, hoje, [v for _, v, _ in ordem], [d for d, _, _ in ordem],
                                    [x for _, _, x in ordem]), "ct_", obs_ct)


# ── Relatório ─────────────────────────────────────────────────────────────────

def _chip_sit(sit: str) -> str:
    return f"<span class='sit {COR_CLI[sit]}'>{ROTULO_CLI[sit]}</span>"


def _chip_tipo(tipo: str) -> str:
    """Etiqueta da forma de pagamento: Pix azul, Cartão rosa (para bater o olho e diferenciar)."""
    return f"<span class='tp {'tp-cartao' if tipo == TIPO_CARTAO else 'tp-pix'}'>{_e(tipo)}</span>"


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
        return f"Próxima: <b>{data_br(p['vencimento'])}</b>{apelido} · {formatar_brl(p['valor'])}"
    return ""


def _html_cliente(c: dict, hoje: date) -> str:
    """Cartão compacto (3 linhas finas) para caber mais gente na tela; a barrinha de quanto já
    foi pago fica na borda de baixo."""
    total = c["pago"] + c["falta"]
    pct = int(round(100 * c["pago"] / total)) if total else 0
    quitado = c["situacao"] == CLI_QUITADO
    nota = "<span class='cc-nota'>obs</span>" if c["tem_obs"] else ""
    valor = (f"pago <b>{formatar_brl(c['pago'])}</b>" if quitado
             else f"falta <b>{formatar_brl(c['falta'])}</b>")
    estado = "" if quitado else f"<div class='cc-est'>{_linha_estado(c, hoje)}</div>"
    return (
        f"<div class='cc {COR_CLI[c['situacao']]}'>"
        f"<div class='cc-l1'><span class='cc-nome'>{_e(c['cliente'])}</span>{nota}"
        f"{_chip_tipo(c['tipo'])}{_chip_sit(c['situacao'])}</div>"
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
        tipos = st.pills("Forma", [TIPO_PIX, TIPO_CARTAO], selection_mode="multi", key="rf_tipo")
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
    if d:
        bloco = (f"<div class='pc-data'><span class='pc-mes'>{MESES_ABREV[d.month - 1]} {d.year}</span>"
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
    topo = _e(local_da_cobranca(c)) if mostrar_cliente else ""
    nome = f"<div class='pc-nome'>{_e(c['cliente'])}</div>" if mostrar_cliente else ""
    quem = ""
    if p["paga"] and p["marcado_por"]:
        verbo = "passou" if c["tipo"] == TIPO_CARTAO else "recebeu"
        quem = f"<br><span class='pc-quem'>{_e(p['marcado_por'])} {verbo}</span>"
    obs = f"<div class='pc-obs'>{_e(p['observacao'])}</div>" if p["observacao"] else ""
    if c["tipo"] == TIPO_CARTAO and p["n"] > 0:
        quem = f" · {texto_vezes(p['valor'], p['vezes'])}" + quem
    return (
        f"<div class='pc {cor}{' pago' if p['paga'] else ''}'>{bloco}<div class='pc-corpo'>"
        f"<div class='pc-topo'><span class='pc-tag'>{topo}</span>"
        f"{_chip_tipo(c['tipo']) if mostrar_cliente else ''}{sit}</div>{nome}"
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
    vezes = p["vezes"]
    if c["tipo"] == TIPO_CARTAO:
        vezes = int(st.number_input("Passou em quantas vezes", min_value=1, max_value=MAX_VEZES_CARTAO,
                                    value=p["vezes"], step=1, key=f"{k}_vezes"))
        # HTML, não st.caption: dois "R$" na mesma linha viram fórmula ($...$) no markdown do Streamlit
        _info(f"{formatar_brl(p['valor'])} · <b>{texto_vezes(p['valor'], vezes)}</b>")
    obs = st.text_input("Observação (opcional)", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: pago em permuta")
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
                                                    "Comprovante": link, "Marcado por": _usuario(),
                                                    "Observação": obs.strip(),
                                                    **({"Vezes no cartão": vezes} if c["tipo"] == TIPO_CARTAO else {})})
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
    obs = st.text_input("Observação", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: pago em permuta")
    if obs.strip() != p["observacao"] and st.button("Salvar observação", key=f"{k}_obs_ok", type="primary",
                                                    icon=":material/check:", use_container_width=True):
        try:
            _banco().atualizar_parcela(cid, n, {"Observação": obs.strip()})
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
    novo_valor, ok_v = _valor("Valor", f"{k}_valor", placeholder=f"{p['valor']:.2f}".replace(".", ","),
                              help="Em branco = continua o mesmo valor.")
    vezes = p["vezes"]
    if c["tipo"] == TIPO_CARTAO and p["n"] > 0:
        vezes = int(st.number_input("Parcelado em quantas vezes", min_value=1, max_value=MAX_VEZES_CARTAO,
                                    value=p["vezes"], step=1, key=f"{k}_vezes"))
    obs = st.text_input("Observação (opcional)", value=p["observacao"], key=f"{k}_obs", max_chars=200,
                        placeholder="Ex.: combinou pagar em permuta")
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not ok_v or not nova_data or (novo_valor is not None and novo_valor <= 0):
            st.error("Confira a data e o valor.")
            return
        campos = {"Vencimento": nova_data, "Observação": obs.strip()}
        if c["tipo"] == TIPO_CARTAO and p["n"] > 0:
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
    data = st.date_input("Data", value=mes_mais(ultima, 1) if c["tipo"] == TIPO_PIX else None,
                         format="DD/MM/YYYY", key=f"{k}_data")
    valor, ok_v = _valor("Valor", f"{k}_valor")
    vezes = 1
    if c["tipo"] == TIPO_CARTAO:
        vezes = int(st.number_input("Parcelado em quantas vezes", min_value=1, max_value=MAX_VEZES_CARTAO,
                                    value=1, step=1, key=f"{k}_vezes"))
    if st.button("Adicionar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/add:"):
        if not data or not ok_v or not valor:
            st.error("Preencha a data e o valor.")
            return
        try:
            _banco().adicionar_parcela(cid, {"Nº": proximo_numero(c["parcelas"]), "Vencimento": data,
                                             "Valor": valor,
                                             **({"Vezes no cartão": vezes} if c["tipo"] == TIPO_CARTAO else {})})
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
            _banco().atualizar_cobranca(cid, {"Observações": txt.strip()})
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
    turma_txt = st.text_input("Turma", value=c["turma"], key=f"{k}_turma")
    turma = normalizar_turma(turma_txt)
    if turma:
        _info(f"Turma <b>{turma}</b> · {TREINAMENTOS[turma[0]]}")
    else:
        _erro_campo("Turma não reconhecida. Ex.: L345")
    cidade = st.text_input("Cidade da turma", value=c["cidade"], key=f"{k}_cidade", max_chars=40,
                           placeholder="Ex.: Lajeado, SCS…")
    total, ok_t = _valor("Valor total", f"{k}_total",
                         placeholder=f"{(c['valor_total'] or 0):.2f}".replace(".", ","),
                         help="Em branco = continua o mesmo.")
    obs = st.text_area("Observações", value=c["observacoes"], key=f"{k}_obs", height=80)
    if st.button("Salvar", type="primary", key=f"{k}_ok", use_container_width=True, icon=":material/check:"):
        if not cliente or not turma or not ok_t:
            st.error("Confira o nome, a turma e o valor.")
            return
        campos = {"Cliente": cliente, "Turma": turma, "Treinamento": TREINAMENTOS[turma[0]],
                  "Observações": obs.strip(), "Cidade": " ".join(cidade.split())}
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
               subtitulo=f"Turma {_e(local_da_cobranca(c))} · {_e(c['tipo'])}")

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
    st.markdown(
        f"<div class='fc {COR_CLI[c['situacao']]}'><div class='fc-topo'>{selo}<span>{ate}</span></div>"
        f"<div class='pg'><i style='width:{pct}%'></i></div>"
        f"<div class='fc-nums'><div><b>{formatar_brl(c['pago'])}</b><span>Pago</span></div>"
        f"<div><b>{formatar_brl(c['falta'])}</b><span>Falta</span></div>"
        f"<div class='{'atr' if c['atrasado'] else ''}'><b>{formatar_brl(c['atrasado'])}</b><span>Atrasado</span></div>"
        f"</div>{aviso_total}{quem}</div>",
        unsafe_allow_html=True,
    )
    with st.container(key="fc_obs"):
        if c["observacoes"]:
            st.markdown("<div class='ob'><span>Observações</span>"
                        + _e(c["observacoes"]).replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
        if st.button("Editar observação" if c["observacoes"] else "Anotar observação", key="fc_obs_btn",
                     icon=":material/edit_note:", use_container_width=True):
            _dlg_obs(c["id"])

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
_TELA_PAI = {"nova": "inicio", "pix": "nova", "cartao": "nova", "relatorio": "inicio",
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
    "notificacoes": tela_notificacoes,
    "config": tela_config,
    "feriados": tela_feriados,
}
if st.session_state.tela not in telas:
    st.session_state.tela = "inicio"
if _identificado():
    telas[st.session_state.tela]()
    _voltar_do_celular()
    _renovar_cookie_do_aparelho()

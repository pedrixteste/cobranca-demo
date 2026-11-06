"""
Regras do app de cobranças, sem Streamlit e sem Google: o app e o notificador
do Telegram usam as mesmas funções, então o que aparece na tela e o que chega
no celular nunca discordam.

Modelo (duas abas na planilha):
  _Cobrancas  uma linha por cobrança (cliente, turma, tipo Pix/Cartão, total)
  _Parcelas   uma linha por pagamento esperado da cobrança:
                Nº 0      = entrada (Pix) ou valor já pago antes (Cartão)
                Nº 1..N   = parcelas do Pix ou datas de passar o cartão
              Cada parcela tem a própria data e o próprio valor, por isso
              "contínua" e "parcial" dão no mesmo modelo: a contínua só gera
              as linhas com valor e dia iguais.

Permuta (pedido 20/10): o cliente paga o treinamento com produtos ou serviços da
empresa dele. A cobrança Permuta guarda em "Valor Total" o saldo que a Vithall
ganhou com essa empresa, e cada linha de _Parcelas é uma RETIRADA (o que já foi
pegado: Produto, data e quanto desconta do saldo). Saldo = total - retiradas.
Desde 20/10 (2º pedido) a mesma permuta pode receber VÁRIOS valores, cada um com a
sua data (a pessoa fechou outra permuta depois): são as linhas com Forma "Crédito
de permuta", e o total passa a ser a soma delas ("Valor Total" acompanha a soma).
Permuta sem nenhuma linha de crédito (as primeiras) usa o "Valor Total".
Permuta não é dinheiro: fica fora de Recebido / A receber / Atrasado, da agenda
e dos avisos do Telegram.

Pagamento híbrido (uma parte no Pix, outra no cartão): cada parcela tem a sua
FORMA (coluna Forma: Pix ou Cartão). Em branco = a forma da cobrança, que é
como estão todas as parcelas anteriores a essa coluna. A cobrança aparece como
"Híbrido" quando tem parcela das duas formas: isso é CALCULADO pelas parcelas,
então vale tanto para a cobrança que já nasce híbrida quanto para a que vira
híbrida depois (uma parcela trocou de forma, ou foi recebida metade em cada).
"""
from __future__ import annotations

import calendar
import math
import re
import unicodedata
from datetime import date, datetime, timedelta

# ── Constantes ────────────────────────────────────────────────────────────────

# A letra da turma define o treinamento (L345 = turma 345 do LORAP)
TREINAMENTOS = {"L": "LORAP", "V": "Vendas", "I": "Impacto", "P": "Perfil"}

TIPO_PIX     = "Pix"
TIPO_CARTAO  = "Cartão"
TIPO_HIBRIDO = "Híbrido"                  # parte no Pix, parte no cartão
TIPO_PERMUTA = "Permuta"                  # treinamento trocado por produtos/serviços (saldo a retirar)
TIPO_CREDITO = "Crédito de permuta"       # Forma da linha que SOMA saldo numa permuta (valor + data)
TIPOS        = [TIPO_PIX, TIPO_CARTAO, TIPO_HIBRIDO, TIPO_PERMUTA]
FORMAS       = [TIPO_PIX, TIPO_CARTAO]    # forma de UMA parcela em dinheiro (nunca "Híbrido")
# O que pode entrar numa cobrança híbrida (pedido 06/11: Pix + permuta, por exemplo). A parte da
# permuta são as mesmas linhas de uma permuta (valores que entram + retiradas), dentro da cobrança.
FORMAS_HIBRIDO = [TIPO_PIX, TIPO_CARTAO, TIPO_PERMUTA]
LINHAS_PERMUTA = (TIPO_CREDITO, TIPO_PERMUTA)   # Forma das linhas de permuta (não são dinheiro)

STATUS_PAGA = "Paga"   # coluna Status da parcela; vazio = em aberto

# Situação de UMA parcela
SIT_PAGA     = "paga"
SIT_ABERTA   = "aberta"
SIT_EM_BREVE = "em_breve"   # vence hoje ou nos próximos DIAS_EM_BREVE dias
SIT_ATRASADA = "atrasada"
DIAS_EM_BREVE = 3

# Situação da COBRANÇA inteira (a mais grave das parcelas)
CLI_ATRASADO = "atrasado"
CLI_EM_BREVE = "em_breve"
CLI_EM_DIA   = "em_dia"
CLI_QUITADO  = "quitado"
ROTULO_CLI = {CLI_ATRASADO: "Atrasado", CLI_EM_BREVE: "Vence em breve",
              CLI_EM_DIA: "Em dia", CLI_QUITADO: "Quitado"}
_GRAVIDADE = {CLI_ATRASADO: 0, CLI_EM_BREVE: 1, CLI_EM_DIA: 2, CLI_QUITADO: 3}

SITUACAO_ATIVA    = "Ativa"
SITUACAO_EXCLUIDA = "Excluída"

COBRANCAS_HEADERS = ["ID", "Tipo", "Cliente", "Turma", "Treinamento", "Valor Total",
                     "Criada em", "Criada por", "Situação", "Excluída em", "Observações", "Cidade",
                     "Telefone"]
PARCELAS_HEADERS = ["ID Cobrança", "Nº", "Vencimento", "Valor", "Status", "Pago em",
                    "Comprovante", "Marcado por", "Registrado em", "Observação", "Vezes no cartão",
                    "Forma", "Produto"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ── Texto ─────────────────────────────────────────────────────────────────────

def _txt(v) -> str:
    return "" if v is None else str(v).strip()


_RE_SINAIS = re.compile(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def texto_limpo(v) -> str:
    """
    Nome digitado (cliente, advogado, turma): uma linha só, espaços simples, sem < > nem caracteres
    de controle. Parênteses, & e outros sinais de nome de verdade ficam. A proteção contra Markdown
    (imagem/link) é feita na hora de MOSTRAR: _e() no HTML e _rotulo() nos rótulos (app.py).
    """
    return " ".join(_RE_SINAIS.sub(" ", _txt(v)).split())


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", _txt(s))
                   if unicodedata.category(c) != "Mn")


def chave_busca(v) -> str:
    """Texto para comparar: sem acento, minúsculas, espaços únicos."""
    return " ".join(sem_acento(v).lower().split())


# ── Turma ─────────────────────────────────────────────────────────────────────

_RE_TURMA = re.compile(r"([A-Z])0*(\d+)")


def normalizar_turma(texto) -> str | None:
    """
    'L00345', 'l345', 'L 345', 'l-0345' → 'L345'. Só valem a letra inicial e o
    número sem os zeros da frente. None se não for letra conhecida + número.
    """
    limpo = re.sub(r"[^A-Z0-9]", "", sem_acento(texto).upper())
    m = _RE_TURMA.fullmatch(limpo)
    if not m or m.group(1) not in TREINAMENTOS or int(m.group(2)) == 0:
        return None
    return f"{m.group(1)}{int(m.group(2))}"


def treinamento_da_turma(turma) -> str:
    t = normalizar_turma(turma)
    return TREINAMENTOS[t[0]] if t else ""


# Uma cobrança pode valer para MAIS DE UMA turma (ex.: o cliente fechou LORAP e
# Vendas juntos). Na planilha a coluna Turma guarda "L345, V12" e a Treinamento
# "LORAP, Vendas"; na tela elas aparecem como "L345 + V12".
_RE_SEPARA_TURMAS = re.compile(r"[,;/+&]|\s+e\s+", re.IGNORECASE)
SEP_TURMAS_PLANILHA = ", "
SEP_TURMAS_TELA = " + "


def normalizar_turmas(texto) -> list[str] | None:
    """
    'L345, v12', 'L345 + V12' ou 'L345 e V12' → ['L345', 'V12'] (sem repetir).
    [] se vazio; None se algum pedaço não for turma.
    """
    partes = [p for p in _RE_SEPARA_TURMAS.split(_txt(texto)) if p.strip()]
    turmas = [normalizar_turma(p) for p in partes]
    if any(t is None for t in turmas):
        return None
    return list(dict.fromkeys(turmas))


def treinamentos_das_turmas(turmas: list[str]) -> list[str]:
    return list(dict.fromkeys(treinamento_da_turma(t) for t in turmas if treinamento_da_turma(t)))


# ── Valores ───────────────────────────────────────────────────────────────────

VALOR_MAXIMO_LIDO = 1e10   # R$ 10 bilhões: acima disso, valor da planilha/campo é tratado como ilegível

_RE_BR      = re.compile(r"\d{1,3}(\.\d{3})+(,\d+)?|\d+(,\d+)?")
_RE_DECIMAL = re.compile(r"\d+\.\d{1,2}")


def valor_para_float(v) -> float | None:
    """
    Valor digitado ou lido da planilha → reais. None se vazio ou ilegível.
    '1500' = 1500 reais; '1.500,50' e '1500,5' no formato brasileiro;
    '1500.50' (ponto com 1-2 casas) também é aceito.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    txt = _txt(v).lstrip("'").replace("R$", "").replace(" ", "")
    if not txt:
        return None
    negativo = txt.startswith("-")
    if negativo:
        txt = txt[1:]
    if txt.isdigit():
        val = float(txt)
    elif _RE_BR.fullmatch(txt):
        val = float(txt.replace(".", "").replace(",", "."))
    elif _RE_DECIMAL.fullmatch(txt):
        val = float(txt)
    else:
        return None
    # Número absurdo (ex.: 2 seguido de 300 zeros) vira "ilegível": senão as contas da tela
    # estouram e a lista inteira cai para todo mundo (achado da auditoria de 04/11)
    if not math.isfinite(val) or val > VALOR_MAXIMO_LIDO:
        return None
    return -val if negativo else val


def formatar_brl(x: float) -> str:
    """1518.46 → 'R$ 1.518,46'."""
    txt = f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {txt}" if x < 0 else f"R$ {txt}"


def valor_planilha(x: float) -> str:
    """Formato gravado na planilha: '1500,00' (sempre com vírgula e 2 casas)."""
    return f"{x:.2f}".replace(".", ",")


def centavos(x: float) -> int:
    return int(round((x or 0) * 100))


def dividir_valor(total: float, n: int) -> list[float]:
    """Divide em n partes iguais; a sobra de centavos vai para a última."""
    if n <= 0:
        return []
    c = centavos(total)
    base = c // n
    partes = [base] * n
    partes[-1] += c - base * n
    return [p / 100 for p in partes]


# ── Datas ─────────────────────────────────────────────────────────────────────

def parse_data(s) -> date | None:
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    txt = _txt(s).split(" ")[0] if _txt(s) else ""
    if not txt:
        return None
    try:
        return datetime.strptime(txt, "%d/%m/%Y").date()
    except ValueError:
        return None


def data_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def mes_mais(d: date, n: int, dia: int | None = None) -> date:
    """Soma n meses no dia `dia` (padrão d.day); 31 em fevereiro vira o último dia."""
    ano, mes0 = divmod(d.year * 12 + d.month - 1 + n, 12)
    ultimo = calendar.monthrange(ano, mes0 + 1)[1]
    return date(ano, mes0 + 1, min(d.day if dia is None else dia, ultimo))


def datas_continuas(primeira: date, n: int) -> list[date]:
    """n vencimentos mensais sempre no dia de `primeira`."""
    return [mes_mais(primeira, k, primeira.day) for k in range(n)]


def nome_mes(d: date) -> str:
    return f"{MESES[d.month - 1]} de {d.year}"


def inicio_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── Leitura das abas ──────────────────────────────────────────────────────────

def linhas_de_valores(values: list[list]) -> list[dict]:
    """get_all_values() → lista de dicts pelo cabeçalho; pula linhas vazias."""
    if not values:
        return []
    cab = [_txt(h) for h in values[0]]
    registros = []
    for i, linha in enumerate(values[1:], start=2):
        if not any(_txt(c) for c in linha):
            continue
        reg = {}
        for j, nome in enumerate(cab):
            if nome and nome not in reg:
                reg[nome] = _txt(linha[j]) if j < len(linha) else ""
        reg["_row_index"] = i
        registros.append(reg)
    return registros


# ── Montagem das parcelas no cadastro ─────────────────────────────────────────

def _ja_paga(linha: dict, paga: bool) -> dict:
    """Parcela que já foi paga quando a cobrança foi cadastrada: paga na data dela."""
    return {**linha, "Status": STATUS_PAGA, "Pago em": linha["Vencimento"]} if paga else linha


def parcelas_pix(entrada: float, data_entrada: date | None, valores: list[float],
                 datas: list[date], hoje: date, ja_pagas: list[bool] | None = None) -> list[dict]:
    """
    Linhas de _Parcelas de uma cobrança Pix nova.

    A entrada é o que a pessoa pagou primeiro: entra como paga na data dela.
    Se a data da entrada ainda não chegou, fica em aberto para ser cobrada.
    `ja_pagas[k]` = a parcela k já tinha sido paga (cobrança antiga cadastrada agora).
    """
    linhas = []
    if entrada and entrada > 0 and data_entrada:
        paga = data_entrada <= hoje
        linhas.append({"Nº": 0, "Vencimento": data_entrada, "Valor": entrada,
                       "Status": STATUS_PAGA if paga else "",
                       "Pago em": data_entrada if paga else None})
    pagas = list(ja_pagas or []) + [False] * len(valores)
    for k, (v, d) in enumerate(zip(valores, datas), start=1):
        linhas.append(_ja_paga({"Nº": k, "Vencimento": d, "Valor": v, "Status": "", "Pago em": None},
                               pagas[k - 1]))
    return linhas


def parcelas_cartao(ja_pago: float, hoje: date, valores: list[float],
                    datas: list[date], vezes: list[int] | None = None,
                    ja_passou: list[bool] | None = None) -> list[dict]:
    """
    Linhas de uma cobrança no cartão: o já pago (Nº 0) + cada data de passar.
    `vezes[k]` = em quantas parcelas aquela passada foi (ou vai ser) dividida NO
    CARTÃO (R$ 8.000 em 8x). É só registro: quem recebe parcelado é a maquininha,
    para a cobrança o que importa é a data de passar e o valor cheio.
    """
    vezes = vezes or [1] * len(valores)
    passou = list(ja_passou or []) + [False] * len(valores)
    linhas = []
    if ja_pago and ja_pago > 0:
        linhas.append({"Nº": 0, "Vencimento": hoje, "Valor": ja_pago,
                       "Status": STATUS_PAGA, "Pago em": hoje})
    for k, (v, d, x) in enumerate(zip(valores, datas, vezes), start=1):
        linhas.append(_ja_paga({"Nº": k, "Vencimento": d, "Valor": v, "Status": "", "Pago em": None,
                                "Vezes no cartão": max(int(x or 1), 1)}, passou[k - 1]))
    return linhas


def parcelas_hibrido(entrada: float, data_entrada: date | None, valores_pix: list[float],
                     datas_pix: list[date], valores_cartao: list[float], datas_cartao: list[date],
                     vezes: list[int] | None, ja_passou: list[bool] | None, hoje: date,
                     pix_pagas: list[bool] | None = None, creditos: list = (), retiradas: list = (),
                     quem: str = "") -> list[dict]:
    """
    Linhas de uma cobrança híbrida nova: a parte do Pix (entrada Nº 0 + parcelas)
    e, continuando a numeração, cada passada do cartão. Toda linha leva a Forma.
    `ja_passou[k]` = aquela passada já foi feita: entra como paga na data dela
    (igual à entrada do Pix, que entra paga quando a data já chegou); `pix_pagas`
    faz o mesmo com as parcelas do Pix.
    Parte na permuta (pedido 06/11): `creditos` [(data, valor)] e `retiradas` [(produto, data, valor)]
    viram as mesmas linhas de uma permuta (parcelas_permuta), continuando a numeração.
    Qualquer parte pode faltar (Pix + permuta não tem cartão; cartão + permuta não tem Pix).
    """
    linhas = [{**l, "Forma": TIPO_PIX}
              for l in parcelas_pix(entrada, data_entrada, valores_pix, datas_pix, hoje, pix_pagas)]
    depois_do_pix = len(valores_pix)
    for l in parcelas_cartao(0, hoje, valores_cartao, datas_cartao, vezes, ja_passou):
        linhas.append({**l, "Nº": depois_do_pix + l["Nº"], "Forma": TIPO_CARTAO})
    if creditos or retiradas:
        depois = max((l["Nº"] for l in linhas), default=0)
        linhas += [{**l, "Nº": depois + l["Nº"]} for l in parcelas_permuta(retiradas, quem, creditos)]
    return linhas


def dividir_recebimento(p: dict, valor_outra: float, novo_n: int, vezes_cartao: int,
                        pagamento: dict) -> tuple[dict, dict]:
    """
    Pagamento híbrido de UMA parcela: o cliente pagou uma parte na forma dela e
    o resto na outra (Pix + cartão). A parcela fica só com a parte da forma dela
    e nasce uma linha nova, já paga, com `valor_outra` na outra forma: a soma
    das duas é o valor que a parcela tinha, então o total da cobrança não muda.

    `pagamento` = o que vale para as duas (Pago em, Marcado por, Comprovante,
    Observação). Devolve (campos a gravar na parcela, linha nova).
    """
    outra = TIPO_CARTAO if p["tipo"] == TIPO_PIX else TIPO_PIX
    fica = (centavos(p["valor"]) - centavos(valor_outra)) / 100
    comum = {**pagamento, "Status": STATUS_PAGA}
    da_parcela = {**comum, "Valor": fica, "Forma": p["tipo"]}
    nova = {**comum, "Nº": novo_n, "Vencimento": p["vencimento"], "Valor": float(valor_outra),
            "Forma": outra}
    (nova if outra == TIPO_CARTAO else da_parcela)["Vezes no cartão"] = max(int(vezes_cartao or 1), 1)
    return da_parcela, nova


def texto_vezes(valor: float, vezes: int) -> str:
    """'8x de R$ 1.000,00' ou 'à vista'."""
    return "à vista" if vezes <= 1 else f"{vezes}x de {formatar_brl(valor / vezes)}"


def resolver_valores(restante: float, digitados: list) -> list[float]:
    """
    Valores das parcelas: o que foi digitado fica; o que ficou em branco (None)
    divide igualmente o que sobrou do `restante`.
    """
    fixos = sum(v for v in digitados if v is not None)
    vazios = [i for i, v in enumerate(digitados) if v is None]
    divididos = iter(dividir_valor(restante - fixos, len(vazios)))
    return [next(divididos) if v is None else v for v in digitados]


def proximo_numero(parcelas: list[dict]) -> int:
    """Nº da parcela nova: um depois da maior que já existe."""
    return max((p["n"] for p in parcelas), default=0) + 1


def conferir_total(total: float, partes: list[float]) -> float:
    """Diferença (total - soma das partes), em reais; 0 quando fecha."""
    return (centavos(total) - sum(centavos(p) for p in partes)) / 100


# ── Situação ──────────────────────────────────────────────────────────────────

def situacao_parcela(p: dict, hoje: date) -> str:
    if p.get("paga"):
        return SIT_PAGA
    venc = p.get("vencimento")
    if venc is None:
        return SIT_ABERTA
    if venc < hoje:
        return SIT_ATRASADA
    if (venc - hoje).days <= DIAS_EM_BREVE:
        return SIT_EM_BREVE
    return SIT_ABERTA


def rotulo_parcela(tipo: str, n: int, total: int, hibrida: bool = False) -> str:
    """Na cobrança híbrida o nome diz a forma e a conta é por forma: 'Pix 2 de 3', 'Cartão 1 de 2'."""
    if hibrida:
        if n == 0:
            return "Entrada no Pix" if tipo == TIPO_PIX else "Já pago no cartão"
        return f"{tipo} {n} de {total}"
    if n == 0:
        return "Entrada" if tipo == TIPO_PIX else "Já pago antes"
    if tipo == TIPO_CARTAO:
        return f"Cartão {n} de {total}"
    return f"Parcela {n} de {total}"


def forma_da_parcela(gravada, tipo_cobranca: str) -> str:
    """Forma de UMA parcela: a que está na coluna Forma; em branco = a forma da cobrança."""
    f = chave_busca(gravada)
    if f == "pix":
        return TIPO_PIX
    if f == "cartao":
        return TIPO_CARTAO
    if f == chave_busca(TIPO_CREDITO):
        return TIPO_CREDITO
    if f == "permuta" or tipo_cobranca == TIPO_PERMUTA:
        return TIPO_PERMUTA
    return TIPO_CARTAO if tipo_cobranca == TIPO_CARTAO else TIPO_PIX


def _vezes(v) -> int:
    try:
        return max(int(float(_txt(v) or 1)), 1)   # sem limite de vezes (pedido 17/10)
    except ValueError:
        return 1


def _parcela(linha: dict, tipo: str) -> dict:
    try:
        n = int(float(_txt(linha.get("Nº")) or 0))
    except ValueError:
        n = 0
    return {
        "n": n,
        "vencimento": parse_data(linha.get("Vencimento")),
        "valor": valor_para_float(linha.get("Valor")) or 0.0,
        "paga": _txt(linha.get("Status")).lower() == STATUS_PAGA.lower(),
        "pago_em": parse_data(linha.get("Pago em")),
        "comprovante": _txt(linha.get("Comprovante")),
        "marcado_por": _txt(linha.get("Marcado por")),
        "observacao": _txt(linha.get("Observação")),
        "vezes": _vezes(linha.get("Vezes no cartão")),
        "tipo": forma_da_parcela(linha.get("Forma"), tipo),   # Pix ou Cartão, desta parcela
        "produto": _txt(linha.get("Produto")),                 # só na retirada de uma permuta
    }


def _soma_da_forma(ps: list[dict], forma: str) -> dict:
    dela = [p for p in ps if p["tipo"] == forma]
    pago = sum(p["valor"] for p in dela if p["paga"])
    falta = sum(p["valor"] for p in dela if not p["paga"])
    return {"pago": pago, "falta": falta, "total": pago + falta, "n": len(dela)}


def montar_cobrancas(cobrancas: list[dict], parcelas: list[dict], hoje: date,
                     incluir_excluidas: bool = False) -> list[dict]:
    """
    Junta as duas abas e calcula tudo que a tela e o Telegram mostram:
    pago, falta, atrasado, próxima cobrança e a situação (cor) da cobrança.
    """
    por_id: dict[str, list] = {}
    for linha in parcelas:
        por_id.setdefault(_txt(linha.get("ID Cobrança")), []).append(linha)

    saida = []
    for c in cobrancas:
        cid = _txt(c.get("ID"))
        if not cid:
            continue
        excluida = _txt(c.get("Situação")) == SITUACAO_EXCLUIDA
        if excluida and not incluir_excluidas:
            continue
        gravado = _txt(c.get("Tipo"))
        gravado = gravado if gravado in TIPOS else TIPO_PIX
        ps = sorted((_parcela(p, gravado) for p in por_id.get(cid, [])), key=lambda p: p["n"])
        permuta = gravado == TIPO_PERMUTA
        if permuta:
            # na permuta inteira, toda linha que não é valor que entrou é retirada
            for p in ps:
                if p["tipo"] != TIPO_CREDITO:
                    p["tipo"] = TIPO_PERMUTA
        # Linhas de permuta (a permuta inteira, ou a parte de permuta de uma híbrida, pedido 06/11):
        # valor que entrou (crédito) ou retirada; as duas já aconteceram e NÃO são dinheiro.
        parte_perm = [p for p in ps if p["tipo"] in LINHAS_PERMUTA]
        for p in parte_perm:
            p["paga"] = True
        dinheiro = [p for p in ps if p["tipo"] in FORMAS]
        if permuta:
            formas, tipo, hibrida = [TIPO_PERMUTA], TIPO_PERMUTA, False
        else:
            # A forma da cobrança sai das parcelas: mais de uma forma junta = híbrida
            # (Pix + cartão, Pix + permuta, cartão + permuta ou as três).
            formas = ([f for f in FORMAS if any(p["tipo"] == f for p in dinheiro)]
                      + ([TIPO_PERMUTA] if parte_perm else []))
            hibrida = len(formas) > 1
            tipo = TIPO_HIBRIDO if hibrida else (formas[0] if formas else gravado)
        # "Parcela 3 de 10" conta pela POSIÇÃO, não pelo Nº gravado: se uma
        # parcela do meio for removida, as outras não ficam com buraco.
        # Na híbrida a conta é separada por forma ("Pix 2 de 3", "Cartão 1 de 2").
        por_forma_n = {f: sum(1 for p in dinheiro if p["n"] > 0 and p["tipo"] == f) for f in FORMAS}
        total_n = sum(por_forma_n.values())
        posicao = {f: 0 for f in FORMAS}
        geral = 0
        for p in ps:
            p["situacao"] = situacao_parcela(p, hoje)
            p["id_cobranca"] = cid
            if p["tipo"] in LINHAS_PERMUTA:
                if p["tipo"] == TIPO_CREDITO:
                    p["rotulo"] = "Valor da permuta"
                else:
                    p["rotulo"] = f"Retirada: {p['produto']}" if p["produto"] else "Retirada"
                p["total_n"] = len(parte_perm)
                continue
            if p["n"] > 0:
                geral += 1
                posicao[p["tipo"]] += 1
            pos, de = (posicao[p["tipo"]], por_forma_n[p["tipo"]]) if hibrida else (geral, total_n)
            p["rotulo"] = rotulo_parcela(p["tipo"], pos if p["n"] > 0 else 0, de, hibrida)
            p["total_n"] = de

        # Pago, falta, atraso e situação: só o DINHEIRO (Pix e cartão). A permuta tem o saldo dela.
        pago = sum(p["valor"] for p in dinheiro if p["paga"])
        falta = sum(p["valor"] for p in dinheiro if not p["paga"])
        atrasadas = [p for p in dinheiro if p["situacao"] == SIT_ATRASADA]
        abertas = sorted((p for p in dinheiro if not p["paga"] and p["vencimento"]),
                         key=lambda p: p["vencimento"])
        futuras = [p for p in abertas if p["vencimento"] >= hoje]
        ultima = max((p["vencimento"] for p in (dinheiro or ps) if p["vencimento"]), default=None)

        if atrasadas:
            sit = CLI_ATRASADO
        elif dinheiro and not abertas and falta == 0:
            sit = CLI_QUITADO
        elif any(p["situacao"] == SIT_EM_BREVE for p in dinheiro):
            sit = CLI_EM_BREVE
        else:
            sit = CLI_EM_DIA
        creditos = [p for p in parte_perm if p["tipo"] == TIPO_CREDITO]
        retiradas = [p for p in parte_perm if p["tipo"] == TIPO_PERMUTA]
        retirado = sum(p["valor"] for p in retiradas)
        # total da permuta = soma dos valores que entraram. Só na permuta INTEIRA sem linha de valor
        # (as primeiras) vale o "Valor Total"; na híbrida o "Valor Total" é o combinado de tudo.
        total_permuta = sum(p["valor"] for p in creditos)
        if permuta and not creditos:
            total_permuta = valor_para_float(c.get("Valor Total")) or 0.0
        saldo = (centavos(total_permuta) - centavos(retirado)) / 100 if (permuta or parte_perm) else 0.0
        if permuta:
            # o que falta é o SALDO para retirar; nunca atrasa (não tem data para cobrar)
            pago = retirado
            falta, atrasadas, futuras = max(saldo, 0.0), [], []
            sit = CLI_EM_DIA if centavos(saldo) > 0 else CLI_QUITADO
        elif parte_perm and not dinheiro:
            # híbrida que ficou só com a permuta (o Pix e o cartão foram removidos): vale o saldo
            sit = CLI_EM_DIA if centavos(saldo) > 0 else CLI_QUITADO
        por_forma = {f: _soma_da_forma(ps, f) for f in FORMAS}
        por_forma[TIPO_PERMUTA] = {"pago": retirado, "falta": max(saldo, 0.0), "total": total_permuta,
                                   "n": len(parte_perm), "saldo": saldo}

        # Uma turma (o normal) ou várias ("L345, V12"); texto que não é turma fica como está
        turmas = normalizar_turmas(c.get("Turma")) or ([_txt(c.get("Turma"))] if _txt(c.get("Turma")) else [])
        turma = SEP_TURMAS_TELA.join(turmas)
        if len(turmas) > 1:
            treinos = treinamentos_das_turmas(turmas)
        else:
            treinos = [_txt(c.get("Treinamento")) or treinamento_da_turma(turma)]
        treinos = [t for t in treinos if t]
        saida.append({
            "id": cid,
            "tipo": tipo,
            "hibrida": hibrida,
            "permuta": permuta,                 # a cobrança INTEIRA é permuta (Tipo "Permuta")
            # formas presentes, nesta ordem: ["Pix"], ["Pix", "Permuta"], ["Pix", "Cartão", "Permuta"]...
            "formas": formas,
            "com_permuta": bool(permuta or parte_perm),   # permuta inteira OU híbrida com parte na permuta
            # da permuta (inteira ou a parte de uma híbrida):
            "saldo": saldo,                     # total - retiradas (negativo = passou)
            "total_permuta": total_permuta,     # soma dos valores que entraram
            "retirado": retirado,               # soma das retiradas
            "creditos": creditos,               # cada valor que entrou, com a data
            "retiradas": retiradas,             # o que já foi pegado
            # quanto de cada forma: {"Pix": {"pago", "falta", "total", "n"}, "Cartão": {...},
            # "Permuta": {..., "saldo"}} (na permuta, "pago" = retirado e "falta" = saldo)
            "por_forma": por_forma,
            "cliente": _txt(c.get("Cliente")),
            "turma": turma,                     # "L345" ou "L345 + V12"
            "turmas": turmas,                   # ["L345", "V12"]
            "treinamento": SEP_TURMAS_TELA.join(treinos),
            "treinamentos": treinos,
            "valor_total": valor_para_float(c.get("Valor Total")),
            "criada_em": parse_data(c.get("Criada em")),
            "criada_por": _txt(c.get("Criada por")),
            "cidade": _txt(c.get("Cidade")),   # texto livre: "Lajeado", "Laj", "SCS"...
            "telefone": _txt(c.get("Telefone")),   # opcional (pedido 26/10): "(51) 99999-8888"
            "observacoes": _txt(c.get("Observações")),
            # tem anotação na cobrança OU em alguma parcela (ex.: "pago em permuta")
            "tem_obs": bool(_txt(c.get("Observações")) or any(p["observacao"] for p in ps)),
            "excluida": excluida,
            "excluida_em": parse_data(c.get("Excluída em")),
            "parcelas": ps,
            "pago": pago,
            "falta": falta,
            "atrasado": sum(p["valor"] for p in atrasadas),
            "n_atrasadas": len(atrasadas),
            "dias_atraso": max(((hoje - p["vencimento"]).days for p in atrasadas), default=0),
            "proxima": futuras[0] if futuras else None,
            "ultima": ultima,
            "situacao": sit,
        })
    return saida


# ── Telefone do cliente (opcional, pedido 26/10) ──────────────────────────────
# Gravado já formatado, "(51) 99999-8888": com parênteses a planilha nunca o
# confunde com número (e nunca come zero da frente).

def _estrangeiro(txt) -> bool:
    """'+1 415…' é de fora; '+55…' é do Brasil."""
    t = _txt(txt).lstrip()
    return t.startswith("+") and not re.sub(r"\D", "", t).startswith("55")


def digitos_telefone(txt) -> str:
    """Só os números; tira o 55 do Brasil quando vem junto (5551999998888)."""
    d = re.sub(r"\D", "", _txt(txt))
    if not _estrangeiro(txt) and d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    return d


def formatar_telefone(txt) -> str:
    """'51999998888' → '(51) 99999-8888'; '5133334444' → '(51) 3333-4444'; sem DDD fica
    '99999-8888'. O que não parece telefone brasileiro fica como foi escrito."""
    bruto = " ".join(_txt(txt).split())
    if _estrangeiro(bruto):
        return bruto
    d = digitos_telefone(bruto)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    if len(d) == 9:
        return f"{d[:5]}-{d[5:]}"
    if len(d) == 8:
        return f"{d[:4]}-{d[4:]}"
    return bruto


def telefone_valido(txt) -> bool:
    """Vazio vale (é opcional). Preenchido precisa ter de 8 a 13 números."""
    d = re.sub(r"\D", "", _txt(txt))
    return not _txt(txt) or 8 <= len(d) <= 13


def link_whatsapp(txt) -> str:
    """https://wa.me/5551999998888, só quando tem DDD (10 ou 11 números)."""
    d = digitos_telefone(txt)
    if _estrangeiro(txt):
        return f"https://wa.me/{d}" if len(d) >= 8 else ""
    return f"https://wa.me/55{d}" if len(d) in (10, 11) else ""


def link_ligar(txt) -> str:
    d = digitos_telefone(txt)
    if len(d) < 8:
        return ""
    if _estrangeiro(txt):
        return f"tel:+{d}"
    return f"tel:{'+55' + d if len(d) in (10, 11) else d}"


def telefone_do_cliente(cobs: list[dict], cliente: str) -> str:
    """Telefone já anotado em outra cobrança do mesmo cliente ('' se nenhuma tem)."""
    alvo = chave_busca(cliente)
    if not alvo:
        return ""
    for c in cobs:
        if chave_busca(c["cliente"]) == alvo and c.get("telefone") and not c.get("excluida"):
            return c["telefone"]
    return ""


def cidade_da_turma(cobs: list[dict], turma: str) -> str:
    """Cidade mais usada nas cobranças já cadastradas daquela turma ('' se nenhuma tem)."""
    contagem: dict[str, int] = {}
    for c in cobs:
        if turma in c.get("turmas", [c["turma"]]) and c.get("cidade"):
            contagem[c["cidade"]] = contagem.get(c["cidade"], 0) + 1
    return max(contagem, key=contagem.get) if contagem else ""


def local_da_cobranca(c: dict) -> str:
    """'L345 · LORAP · Lajeado' (a cidade só aparece se foi preenchida)."""
    return " · ".join(x for x in (c["turma"], c["treinamento"], c.get("cidade", "")) if x)


def ordenar_para_cobrar(cobs: list[dict]) -> list[dict]:
    """Atrasados primeiro (o mais atrasado no topo), depois quem vence antes; quitados no fim."""
    def chave(c):
        prox = c["proxima"]["vencimento"] if c["proxima"] else date.max
        return (_GRAVIDADE[c["situacao"]], -c["dias_atraso"], prox, chave_busca(c["cliente"]))
    return sorted(cobs, key=chave)


# ── Busca e filtros ───────────────────────────────────────────────────────────

def casa_busca(c: dict, termo: str) -> bool:
    """
    Procura no nome do cliente, na turma e no treinamento, sem ligar para
    acento e maiúsculas. 'l0345' acha a turma L345; várias palavras = todas
    precisam aparecer ('maria lorap').
    """
    termo = _txt(termo)
    if not termo:
        return True
    turma_buscada = normalizar_turma(termo)
    if turma_buscada and turma_buscada in c.get("turmas", [c["turma"]]):
        return True
    notas = " ".join([c.get("observacoes", "")] + [p.get("observacao", "") for p in c.get("parcelas", [])]
                     + [p.get("produto", "") for p in c.get("parcelas", [])])
    tel = c.get("telefone", "")
    # híbrida com parte na permuta também é achada por "permuta"
    perm = TIPO_PERMUTA if c.get("com_permuta") and c["tipo"] != TIPO_PERMUTA else ""
    alvo = chave_busca(f"{c['cliente']} {c['turma']} {c['treinamento']} {c['tipo']} {perm} {c.get('cidade', '')}"
                       f" {notas} {tel} {digitos_telefone(tel)}")
    return all(palavra in alvo for palavra in chave_busca(termo).split())


def casa_forma(c: dict, tipos) -> bool:
    """
    Filtro Forma: Pix e Cartão continuam só as cobranças de uma forma só; "Híbrido" = todas as
    híbridas; "Permuta" = as permutas E as híbridas com parte na permuta (todas têm saldo para
    retirar, que é o que soma a linha "Saldo para retirar" do relatório).
    """
    return c["tipo"] in tipos or (TIPO_PERMUTA in tipos and bool(c.get("com_permuta")))


def filtrar(cobs: list[dict], termo: str = "", situacoes=None, tipos=None,
            treinamentos=None, turma: str = "", obs: str = "") -> list[dict]:
    """`obs`: "com" = só cobranças com observação; "sem" = só as sem; vazio = todas."""
    turma_n = normalizar_turma(turma) if _txt(turma) else None
    saida = []
    for c in cobs:
        if not casa_busca(c, termo):
            continue
        if situacoes and c["situacao"] not in situacoes:
            continue
        if tipos and not casa_forma(c, tipos):
            continue
        if treinamentos and not any(t in treinamentos for t in c.get("treinamentos", [c["treinamento"]])):
            continue
        if _txt(turma) and (turma_n or _txt(turma).upper()) not in c.get("turmas", [c["turma"]]):
            continue
        if obs == "com" and not c["tem_obs"]:
            continue
        if obs == "sem" and c["tem_obs"]:
            continue
        saida.append(c)
    return saida


def agenda(cobs: list[dict], de: date, ate: date, com_atrasadas: bool = True) -> list[tuple]:
    """
    Parcelas em aberto para cobrar no período, em ordem de data:
    lista de (parcela, cobrança). Com `com_atrasadas`, as vencidas antes de
    `de` também entram (atrasado continua sendo cobrança a fazer).
    """
    itens = []
    for c in cobs:
        for p in c["parcelas"]:
            if p["paga"] or not p["vencimento"]:
                continue
            no_periodo = de <= p["vencimento"] <= ate
            atrasada = com_atrasadas and p["situacao"] == SIT_ATRASADA and p["vencimento"] < de
            if no_periodo or atrasada:
                itens.append((p, c))
    itens.sort(key=lambda it: (it[0]["vencimento"], chave_busca(it[1]["cliente"])))
    return itens


def resumo(cobs: list[dict]) -> dict:
    """Totais do topo do relatório. Permuta não é dinheiro: tem a sua própria conta (saldo a retirar).
    Na híbrida com parte na permuta, o Pix e o cartão entram no dinheiro e a parte da permuta,
    no saldo para retirar (pedido 06/11)."""
    dinheiro = [c for c in cobs if not c.get("permuta")]
    permutas = [c for c in cobs if c.get("com_permuta", c.get("permuta"))]
    return {
        "recebido": sum(c["pago"] for c in dinheiro),
        "a_receber": sum(c["falta"] for c in dinheiro),
        "atrasado": sum(c["atrasado"] for c in dinheiro),
        "n_atrasados": sum(1 for c in dinheiro if c["situacao"] == CLI_ATRASADO),
        "n_cobrancas": len(cobs),
        "n_permutas": len(permutas),
        "saldo_permuta": sum(max(c["saldo"], 0) for c in permutas),
    }


def parcelas_permuta(retiradas: list, quem: str = "", creditos: list = ()) -> list[dict]:
    """
    Linhas de _Parcelas de uma permuta nova: primeiro cada valor que entrou (data, valor),
    depois cada retirada (produto, data, valor). Tudo já aconteceu, então entra pago na
    data dele. Cada grupo em ordem de data.
    """
    linhas = [{"Vencimento": d, "Valor": v, "Status": STATUS_PAGA, "Pago em": d,
               "Forma": TIPO_CREDITO, "Marcado por": quem}
              for d, v in sorted(creditos, key=lambda r: r[0])]
    linhas += [{"Vencimento": d, "Valor": v, "Status": STATUS_PAGA, "Pago em": d,
                "Forma": TIPO_PERMUTA, "Produto": produto, "Marcado por": quem}
               for produto, d, v in sorted(retiradas, key=lambda r: r[1])]
    return [{"Nº": k, **l} for k, l in enumerate(linhas, start=1)]


def permutas_do_cliente(cobs: list[dict], cliente: str, menos: str = "") -> list[dict]:
    """As permutas (ativas) do mesmo cliente, pelo nome sem ligar para acento e maiúscula."""
    alvo = chave_busca(cliente)
    return [c for c in cobs if c.get("permuta") and not c["excluida"] and c["id"] != menos
            and alvo and chave_busca(c["cliente"]) == alvo]


# ── Pessoas e aparelhos (aba _Config) ─────────────────────────────────────────
# O Streamlit Cloud não informa o e-mail de quem está logado, então a trava é
# por APARELHO: a primeira escolha de nome prende aquele aparelho naquele nome.
#   pessoas            "Pedro, Gabi, Ana" (o primeiro é quem administra, salvo `admin`)
#   admin              nome de quem tem a tela Configurações
#   aparelho:<id>      nome preso àquele aparelho
#   liberado:<nome>    "sim" = pode ser escolhido em MAIS UM aparelho (gasta ao escolher)
# Nome com aparelho preso não aparece para outro aparelho escolher: quem troca
# de celular pede para o administrador liberar.

def pessoas_da_config(config: dict) -> list[str]:
    return [p.strip() for p in _txt(config.get("pessoas")).split(",") if p.strip()]


def administrador(config: dict) -> str:
    pessoas = pessoas_da_config(config)
    adm = _txt(config.get("admin"))
    return adm if adm in pessoas else (pessoas[0] if pessoas else "")


def aparelhos_por_pessoa(config: dict) -> dict[str, list[str]]:
    pessoas = pessoas_da_config(config)
    saida = {p: [] for p in pessoas}
    for chave, valor in config.items():
        if chave.startswith("aparelho:") and _txt(valor) in saida:
            saida[_txt(valor)].append(chave[len("aparelho:"):])
    return saida


def nome_do_aparelho(config: dict, aparelho: str) -> str:
    nome = _txt(config.get(f"aparelho:{aparelho}")) if aparelho else ""
    return nome if nome in pessoas_da_config(config) else ""


# ── Entrada com Google (pedido 26/10) ─────────────────────────────────────────
# Cada pessoa ligada a UM Gmail; quem entra com aquele Gmail, em qualquer aparelho,
# é aquela pessoa. Fica na _Config (os e-mails NUNCA vão para o código: o repositório
# da demonstração é público):
#   email:<nome>     Gmail daquela pessoa
#   login_google     "sim" = a entrada com Google vale para todo mundo (no lugar do aparelho)

def normalizar_email(txt) -> str:
    return _txt(txt).strip().lower()


def email_valido(txt) -> bool:
    return bool(re.fullmatch(r"[^@\s,:]+@[^@\s,:]+\.[a-z]{2,}", normalizar_email(txt)))


def emails_por_pessoa(config: dict) -> dict[str, str]:
    """{nome: email} de quem está na lista de pessoas ('' se ainda não tem)."""
    return {p: normalizar_email(config.get(f"email:{p}")) for p in pessoas_da_config(config)}


def pessoa_do_email(config: dict, email: str) -> str:
    """Nome ligado àquele Gmail ('' se nenhum). Só vale para quem ainda está na lista."""
    alvo = normalizar_email(email)
    if not alvo:
        return ""
    return next((p for p, e in emails_por_pessoa(config).items() if e == alvo), "")


def dono_do_email(config: dict, email: str, menos: str = "") -> str:
    """Outra pessoa que já usa esse Gmail (para não ligar o mesmo e-mail em dois nomes)."""
    alvo = normalizar_email(email)
    return next((p for p, e in emails_por_pessoa(config).items() if e == alvo and p != menos), "")


def login_google_ligado(config: dict) -> bool:
    return chave_busca(config.get("login_google", "")) == "sim"


def codigo_aparelho(aparelho) -> str:
    """Código curto (6 letras) que o aparelho novo mostra na tela, para o administrador liberar SÓ ele."""
    return re.sub(r"[^a-f0-9]", "", _txt(aparelho).lower())[:6].upper()


def liberacao_por_codigo(config: dict) -> bool:
    """Existe (ou já existiu) alguém Só Jurídico: na trava por aparelho, celular novo só entra com o
    código liberado pelo administrador. A marca "liberacao_por_codigo" fica mesmo depois de a pessoa
    sair, senão a aba que ela deixou aberta voltaria a poder escolher um nome livre."""
    return bool(pessoas_restritas(config)) or chave_busca(config.get("liberacao_por_codigo", "")) == "sim"


def nomes_livres(config: dict, aparelho: str = "") -> list[str]:
    """
    Nomes que um aparelho novo pode escolher (só na trava por aparelho, sem a entrada com Google).
    Normal: sem aparelho preso, ou liberados pelo administrador ("sim").
    Com liberacao_por_codigo (pedido 04/11, acesso Só Jurídico): SÓ o nome que o administrador
    liberou para ESTE aparelho. A liberação guarda o código COMPLETO do aparelho (24 letras): o curto
    de 6 letras que aparece na tela só serve para o app achar o aparelho certo (3ª auditoria: as 6
    letras dava para fabricar mexendo no endereço).
    """
    presos = aparelhos_por_pessoa(config)
    if liberacao_por_codigo(config):
        meu = _txt(aparelho).lower()
        return [p for p in pessoas_da_config(config)
                if len(meu) >= 16 and _txt(config.get(f"liberado:{p}", "")).lower() == meu]
    return [p for p in pessoas_da_config(config)
            if not presos[p] or chave_busca(config.get(f"liberado:{p}", "")) == "sim"]


# ── Acesso por pessoa (pedido 04/11) ──────────────────────────────────────────
# _Config "acesso:<nome>" = "juridico" → a pessoa só vê o Jurídico (cobranças judiciais e protestos):
# nada de cobranças, relatório, notificações, feriados ou configurações, e não recebe aviso no
# Telegram. Qualquer outro valor (ou nada) = acesso a tudo, como sempre foi. O administrador
# sempre tem acesso a tudo (senão ficaria sem a tela de Configurações).

ACESSO_TUDO = ""
ACESSO_JURIDICO = "juridico"


def acesso_da_pessoa(config: dict, nome: str, fora_da_lista_restringe: bool = True) -> str:
    """
    Fecha por padrão (auditoria de 04/11): acesso a TUDO só para o administrador, ou para quem está
    na lista de pessoas com o acesso vazio ou "tudo". Quem saiu da lista, ou tem qualquer outra coisa
    escrita (ex.: "só jurídico" digitado à mão na planilha), fica só com o Jurídico.
    """
    if not _txt(nome):
        return ACESSO_TUDO   # ninguém identificado: quem barra é a tela de entrada, não esta regra
    if nome == administrador(config):
        return ACESSO_TUDO
    if fora_da_lista_restringe and nome not in pessoas_da_config(config):
        return ACESSO_JURIDICO
    return ACESSO_TUDO if chave_busca(config.get(f"acesso:{nome}", "")) in ("", "tudo") else ACESSO_JURIDICO


def so_juridico(config: dict, nome: str, fora_da_lista_restringe: bool = True) -> bool:
    return acesso_da_pessoa(config, nome, fora_da_lista_restringe) == ACESSO_JURIDICO


def pessoas_restritas(config: dict) -> list[str]:
    return [p for p in pessoas_da_config(config) if so_juridico(config, p)]


# ── Preferências de notificação (aba _Config, iguais para todo mundo) ─────────
#   telegram:<nome>   chat do Telegram daquela pessoa
#   avisos:<nome>     "nao" pausa os avisos só para ela
#   avisar_atrasadas / avisar_hoje / avisar_amanha / resumo_semanal   "nao" desliga

OPCOES_AVISO = {
    "avisar_atrasadas": "Cobranças atrasadas",
    "avisar_hoje": "O que é para cobrar hoje",
    "avisar_amanha": "O que é para cobrar amanhã",
    "resumo_semanal": "Resumo da semana (toda segunda)",
    "avisar_juridico": "Jurídico: parcelas dos acordos (atrasadas, de hoje e de amanhã)",
}


def _ligado(config: dict, chave: str) -> bool:
    """Tudo começa ligado; só o texto 'nao' desliga."""
    return chave_busca(config.get(chave, "")) not in ("nao", "não", "0", "false")


def opcoes_avisos(config: dict) -> dict:
    return {k: _ligado(config, k) for k in OPCOES_AVISO}


def destinatarios(config: dict) -> list[tuple]:
    """[(nome, chat_id)] de quem está conectado e não pausou os avisos. Só quem ainda está na lista de
    pessoas e tem acesso a TUDO: quem foi removido, ou só vê o Jurídico, não recebe as cobranças."""
    saida = []
    pessoas = pessoas_da_config(config)
    for chave, valor in config.items():
        if chave.startswith("telegram:") and _txt(valor):
            nome = chave[len("telegram:"):]
            if nome not in pessoas or so_juridico(config, nome):
                continue
            if _ligado(config, f"avisos:{nome}"):
                saida.append((nome, _txt(valor)))
    return sorted(saida)


def destinatarios_juridico(config: dict) -> list[tuple]:
    """[(nome, chat_id)] de quem recebe os avisos do JURÍDICO (pedido 04/11): todo mundo da lista de
    pessoas que conectou o Telegram e não pausou, inclusive quem é Só Jurídico."""
    pessoas = pessoas_da_config(config)
    return sorted((nome, _txt(valor)) for chave, valor in config.items()
                  if chave.startswith("telegram:") and _txt(valor)
                  and (nome := chave[len("telegram:"):]) in pessoas and _ligado(config, f"avisos:{nome}"))


def avisos(cobs: list[dict], hoje: date) -> dict:
    """O que o Telegram avisa: atrasadas, hoje, amanhã e o resto da semana."""
    amanha = hoje + timedelta(days=1)
    domingo = inicio_semana(hoje) + timedelta(days=6)
    r = {"atrasadas": [], "hoje": [], "amanha": [], "semana": []}
    for p, c in agenda(cobs, hoje, domingo):
        if p["vencimento"] < hoje:
            r["atrasadas"].append((p, c))
        elif p["vencimento"] == hoje:
            r["hoje"].append((p, c))
        elif p["vencimento"] == amanha:
            r["amanha"].append((p, c))
        else:
            r["semana"].append((p, c))
    # Mais atrasado primeiro
    r["atrasadas"].sort(key=lambda it: it[0]["vencimento"])
    return r


# ── Jurídico (pedido 03/11) ───────────────────────────────────────────────────
# Duas listas à parte, cada uma na sua aba:
#   _Judicial   cliente que a Vithall colocou na justiça por não pagar: o que foi cobrado,
#               desde quando está com o jurídico, o advogado e o ACORDO (à vista ou parcelado)
#   _Protestos  título (cheque, promissória ou ficha) protestado em cartório, e se já foi pago
# Nada daqui entra no relatório de cobranças, na agenda nem nos avisos do Telegram.
#
# As parcelas do acordo ficam numa célula só (coluna "Acordo"), uma por linha:
#     1 | 500,00 | 10/12/2026 | Paga | 08/12/2026 | ANA
#     2 | 500,00 | 10/01/2027
# (número | valor | vencimento | Paga | pago em | quem marcou). Uma célula só = mudar o
# acordo é UMA gravação, e o acordo nunca fica pela metade na planilha.

OBJETOS = ["Cheque", "Promissória", "Ficha"]

NEG_SEM       = ""            # ainda sem acordo
NEG_A_VISTA   = "À vista"
NEG_PARCELADO = "Parcelado"

JUD_SEM_ACORDO = "sem_acordo"   # situação da cobrança judicial que ainda não tem acordo
ROTULO_JUD = {JUD_SEM_ACORDO: "Sem acordo", **ROTULO_CLI}
_GRAVIDADE_JUD = {CLI_ATRASADO: 0, CLI_EM_BREVE: 1, JUD_SEM_ACORDO: 2, CLI_EM_DIA: 3, CLI_QUITADO: 4}

JUDICIAL_HEADERS = ["ID", "Cliente", "Turma", "Objeto", "Valor cobrado", "No jurídico desde", "Advogado",
                    "Negociação", "Valor do acordo", "Acordo", "Cadastrada por", "Criada em",
                    "Situação", "Excluída em", "Alterada por", "Alterada em", "Excluída por"]
PROTESTOS_HEADERS = ["ID", "Cliente", "Turma", "Objeto", "Protestado em", "Pago", "Pago em", "Marcado por",
                     "Cadastrado por", "Criado em", "Situação", "Excluído em", "Alterado por", "Alterado em",
                     "Excluído por"]
# Histórico do Jurídico (auditoria de 04/11): toda gravação acrescenta uma linha, nunca apaga nem muda.
# Guarda como a linha estava ANTES e como ficou, para saber quem mexeu e desfazer à mão.
HISTORICO_HEADERS = ["Quando", "Quem", "Aba", "ID", "Ação", "Antes", "Depois"]

MAX_PARCELAS_ACORDO = 120   # acordo maior que isso é engano (ou tentativa de travar o app)

_SEP_ACORDO = " | "


def _limpo_acordo(txt) -> str:
    """Texto que vai dentro da célula do acordo: sem '|' nem quebra de linha (que separam as partes)."""
    return " ".join(_txt(txt).replace("|", " ").split())


def acordo_para_texto(parcelas: list[dict]) -> str:
    """Parcelas do acordo → o texto da célula "Acordo" (ver o começo desta seção)."""
    linhas = []
    for i, p in enumerate(parcelas, start=1):
        partes = [str(i), valor_planilha(p.get("valor") or 0.0), data_br(p.get("vencimento"))]
        if p.get("paga"):
            partes += [STATUS_PAGA, data_br(p.get("pago_em")), _limpo_acordo(p.get("marcado_por"))]
        while partes and not partes[-1]:
            partes.pop()
        linhas.append(_SEP_ACORDO.join(partes))
    return "\n".join(linhas)


def acordo_do_texto(txt) -> list[dict]:
    """O contrário de acordo_para_texto. Linha ilegível (mexida à mão) vira parcela de R$ 0,00 sem
    data, para continuar aparecendo na tela em vez de sumir calada."""
    parcelas = []
    for linha in _txt(txt).splitlines():
        if len(parcelas) >= MAX_PARCELAS_ACORDO:
            break   # célula gigante (mexida à mão) não trava a ficha
        partes = [x.strip() for x in linha.split("|")]
        if not any(partes):
            continue
        partes += [""] * (6 - len(partes))
        paga = chave_busca(partes[3]) == chave_busca(STATUS_PAGA)
        parcelas.append({
            "valor": valor_para_float(partes[1]) or 0.0,
            "vencimento": parse_data(partes[2]),
            "paga": paga,
            "pago_em": parse_data(partes[4]) if paga else None,
            "marcado_por": partes[5] if paga else "",
        })
    return parcelas


def parcelas_do_acordo(valores: list[float], datas: list, anteriores: list[dict] = ()) -> list[dict]:
    """
    Parcelas novas do acordo (cadastro ou edição). Na edição, a parcela que JÁ estava paga continua
    paga (com a data e quem marcou), pela posição: a 1ª continua sendo a 1ª.
    """
    ps = []
    for i, (v, d) in enumerate(zip(valores, datas)):
        ant = anteriores[i] if i < len(anteriores) else {}
        paga = bool(ant.get("paga"))
        ps.append({"valor": v, "vencimento": d, "paga": paga,
                   "pago_em": ant.get("pago_em") if paga else None,
                   "marcado_por": ant.get("marcado_por", "") if paga else ""})
    return ps


def marcar_parcela_acordo(parcelas: list[dict], n: int, paga: bool, quando: date | None = None,
                          quem: str = "") -> list[dict]:
    """Cópia das parcelas com a n-ésima (1, 2, 3...) marcada como paga, ou desmarcada."""
    novas = [dict(p) for p in parcelas]
    if 1 <= n <= len(novas):
        novas[n - 1].update({"paga": paga, "pago_em": quando if paga else None,
                             "marcado_por": quem if paga else ""})
    return novas


def _turmas_da_linha(texto) -> list[str]:
    return normalizar_turmas(texto) or ([_txt(texto)] if _txt(texto) else [])


def montar_judiciais(linhas: list[dict], hoje: date, incluir_excluidas: bool = False) -> list[dict]:
    """Linhas da aba _Judicial → o que a tela mostra (com as contas do acordo)."""
    saida = []
    for l in linhas:
        jid = _txt(l.get("ID"))
        if not jid:
            continue
        excluida = _txt(l.get("Situação")) == SITUACAO_EXCLUIDA
        if excluida and not incluir_excluidas:
            continue
        neg = _txt(l.get("Negociação"))
        ps = acordo_do_texto(l.get("Acordo")) if neg in (NEG_A_VISTA, NEG_PARCELADO) else []
        if not ps:
            neg = NEG_SEM
        for i, p in enumerate(ps, start=1):
            p["n"] = i
            p["situacao"] = situacao_parcela(p, hoje)
            p["rotulo"] = "Acordo à vista" if neg == NEG_A_VISTA else f"Parcela {i} de {len(ps)}"
        pago = sum(p["valor"] for p in ps if p["paga"])
        falta = sum(p["valor"] for p in ps if not p["paga"])
        atrasadas = [p for p in ps if p["situacao"] == SIT_ATRASADA]
        futuras = sorted((p for p in ps if not p["paga"] and p["vencimento"] and p["vencimento"] >= hoje),
                         key=lambda p: p["vencimento"])
        if not ps:
            sit = JUD_SEM_ACORDO
        elif atrasadas:
            sit = CLI_ATRASADO
        elif all(p["paga"] for p in ps):
            sit = CLI_QUITADO
        elif any(p["situacao"] == SIT_EM_BREVE for p in ps):
            sit = CLI_EM_BREVE
        else:
            sit = CLI_EM_DIA
        turmas = _turmas_da_linha(l.get("Turma"))
        saida.append({
            "id": jid,
            "cliente": texto_limpo(l.get("Cliente")),
            "turma": texto_limpo(SEP_TURMAS_TELA.join(turmas)),   # "L345" ou "L345 + V12"
            "turmas": turmas,
            "objeto": texto_limpo(l.get("Objeto")),
            "valor": valor_para_float(l.get("Valor cobrado")) or 0.0,
            "desde": parse_data(l.get("No jurídico desde")),
            "advogado": texto_limpo(l.get("Advogado")),
            "negociacao": neg,
            "valor_acordo": valor_para_float(l.get("Valor do acordo")) or sum(p["valor"] for p in ps),
            "parcelas": ps,
            "pago": pago,
            "falta": falta,
            "atrasado": sum(p["valor"] for p in atrasadas),
            "dias_atraso": max(((hoje - p["vencimento"]).days for p in atrasadas), default=0),
            "proxima": futuras[0] if futuras else None,
            "situacao": sit,
            "criada_por": _txt(l.get("Cadastrada por")),
            "criada_em": parse_data(l.get("Criada em")),
            "excluida": excluida,
            "excluida_em": parse_data(l.get("Excluída em")),
        })
    return saida


def ordenar_judiciais(itens: list[dict]) -> list[dict]:
    """Atrasado primeiro, depois vence em breve, sem acordo, em dia e quitado; dentro de cada um, pelo nome."""
    return sorted(itens, key=lambda j: (_GRAVIDADE_JUD.get(j["situacao"], 9), chave_busca(j["cliente"])))


def montar_protestos(linhas: list[dict], incluir_excluidos: bool = False) -> list[dict]:
    saida = []
    for l in linhas:
        pid = _txt(l.get("ID"))
        if not pid:
            continue
        excluido = _txt(l.get("Situação")) == SITUACAO_EXCLUIDA
        if excluido and not incluir_excluidos:
            continue
        turmas = _turmas_da_linha(l.get("Turma"))
        pago = chave_busca(l.get("Pago")) in ("sim", "pago", "x")
        saida.append({
            "id": pid,
            "cliente": texto_limpo(l.get("Cliente")),
            "turma": texto_limpo(SEP_TURMAS_TELA.join(turmas)),
            "turmas": turmas,
            "objeto": texto_limpo(l.get("Objeto")),
            "protestado_em": parse_data(l.get("Protestado em")),
            "pago": pago,
            "pago_em": parse_data(l.get("Pago em")) if pago else None,
            "marcado_por": _txt(l.get("Marcado por")) if pago else "",
            "criado_por": _txt(l.get("Cadastrado por")),
            "criado_em": parse_data(l.get("Criado em")),
            "excluido": excluido,
        })
    return saida


def ordenar_protestos(itens: list[dict]) -> list[dict]:
    """Em aberto primeiro (o protesto mais antigo no topo); os pagos no fim (o pago mais recente antes)."""
    abertos = sorted((p for p in itens if not p["pago"]),
                     key=lambda p: (p["protestado_em"] or date.max, chave_busca(p["cliente"])))
    pagos = sorted((p for p in itens if p["pago"]),
                   key=lambda p: (p["pago_em"] or date.min, chave_busca(p["cliente"])), reverse=True)
    return abertos + pagos


def casa_busca_juridico(item: dict, termo: str) -> bool:
    """Busca por nome, turma (L00345 acha L345), objeto ou advogado."""
    t = chave_busca(termo)
    if not t:
        return True
    turma = normalizar_turma(termo)
    if turma and turma in item.get("turmas", []):
        return True
    texto = " ".join([item.get("cliente", ""), item.get("turma", ""), item.get("objeto", ""),
                      item.get("advogado", "")])
    return t in chave_busca(texto)


def advogados_usados(judiciais: list[dict]) -> list[str]:
    """Advogados que já aparecem nas cobranças judiciais (o mais usado primeiro), para sugerir no cadastro."""
    contagem: dict[str, list] = {}
    for j in judiciais:
        if j["advogado"]:
            contagem.setdefault(chave_busca(j["advogado"]), [j["advogado"], 0])[1] += 1
    return [nome for nome, _ in sorted(contagem.values(), key=lambda x: (-x[1], chave_busca(x[0])))]


def avisos_juridico(judiciais: list[dict], hoje: date) -> dict:
    """Parcelas de acordo ainda não pagas, no mesmo jeito dos avisos das cobranças: atrasadas, hoje,
    amanhã e o resto da semana. Cada item é (parcela, cobrança judicial)."""
    amanha = hoje + timedelta(days=1)
    domingo = inicio_semana(hoje) + timedelta(days=6)
    r = {"atrasadas": [], "hoje": [], "amanha": [], "semana": []}
    for j in judiciais:
        if j.get("excluida"):
            continue
        for p in j["parcelas"]:
            d = p.get("vencimento")
            if p.get("paga") or not d or d > domingo:
                continue
            chave = ("atrasadas" if d < hoje else "hoje" if d == hoje else "amanha" if d == amanha else "semana")
            r[chave].append((p, j))
    for itens in r.values():
        itens.sort(key=lambda it: (it[0]["vencimento"], chave_busca(it[1]["cliente"])))
    return r


def resumo_juridico(judiciais: list[dict], protestos: list[dict]) -> dict:
    return {
        "n_judiciais": len(judiciais),
        "n_atrasados": sum(1 for j in judiciais if j["situacao"] == CLI_ATRASADO),
        "n_sem_acordo": sum(1 for j in judiciais if j["situacao"] == JUD_SEM_ACORDO),
        "cobrado": sum(j["valor"] for j in judiciais),
        "n_protestos": len(protestos),
        "n_protestos_abertos": sum(1 for p in protestos if not p["pago"]),
        "acordo_pago": sum(j["pago"] for j in judiciais),
        "acordo_falta": sum(j["falta"] for j in judiciais),
        "acordo_atrasado": sum(j["atrasado"] for j in judiciais),
    }

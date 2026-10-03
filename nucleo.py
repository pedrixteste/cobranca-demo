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

Pagamento híbrido (uma parte no Pix, outra no cartão): cada parcela tem a sua
FORMA (coluna Forma: Pix ou Cartão). Em branco = a forma da cobrança, que é
como estão todas as parcelas anteriores a essa coluna. A cobrança aparece como
"Híbrido" quando tem parcela das duas formas: isso é CALCULADO pelas parcelas,
então vale tanto para a cobrança que já nasce híbrida quanto para a que vira
híbrida depois (uma parcela trocou de forma, ou foi recebida metade em cada).
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta

# ── Constantes ────────────────────────────────────────────────────────────────

# A letra da turma define o treinamento (L345 = turma 345 do LORAP)
TREINAMENTOS = {"L": "LORAP", "V": "Vendas", "I": "Impacto", "P": "Perfil"}

TIPO_PIX     = "Pix"
TIPO_CARTAO  = "Cartão"
TIPO_HIBRIDO = "Híbrido"                  # parte no Pix, parte no cartão
TIPOS        = [TIPO_PIX, TIPO_CARTAO, TIPO_HIBRIDO]
FORMAS       = [TIPO_PIX, TIPO_CARTAO]    # forma de UMA parcela (nunca "Híbrido")

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
                     "Criada em", "Criada por", "Situação", "Excluída em", "Observações", "Cidade"]
PARCELAS_HEADERS = ["ID Cobrança", "Nº", "Vencimento", "Valor", "Status", "Pago em",
                    "Comprovante", "Marcado por", "Registrado em", "Observação", "Vezes no cartão",
                    "Forma"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ── Texto ─────────────────────────────────────────────────────────────────────

def _txt(v) -> str:
    return "" if v is None else str(v).strip()


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


# ── Valores ───────────────────────────────────────────────────────────────────

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

def parcelas_pix(entrada: float, data_entrada: date | None, valores: list[float],
                 datas: list[date], hoje: date) -> list[dict]:
    """
    Linhas de _Parcelas de uma cobrança Pix nova.

    A entrada é o que a pessoa pagou primeiro: entra como paga na data dela.
    Se a data da entrada ainda não chegou, fica em aberto para ser cobrada.
    """
    linhas = []
    if entrada and entrada > 0 and data_entrada:
        paga = data_entrada <= hoje
        linhas.append({"Nº": 0, "Vencimento": data_entrada, "Valor": entrada,
                       "Status": STATUS_PAGA if paga else "",
                       "Pago em": data_entrada if paga else None})
    for k, (v, d) in enumerate(zip(valores, datas), start=1):
        linhas.append({"Nº": k, "Vencimento": d, "Valor": v, "Status": "", "Pago em": None})
    return linhas


MAX_VEZES_CARTAO = 24


def parcelas_cartao(ja_pago: float, hoje: date, valores: list[float],
                    datas: list[date], vezes: list[int] | None = None) -> list[dict]:
    """
    Linhas de uma cobrança no cartão: o já pago (Nº 0) + cada data de passar.
    `vezes[k]` = em quantas parcelas aquela passada foi (ou vai ser) dividida NO
    CARTÃO (R$ 8.000 em 8x). É só registro: quem recebe parcelado é a maquininha,
    para a cobrança o que importa é a data de passar e o valor cheio.
    """
    vezes = vezes or [1] * len(valores)
    linhas = []
    if ja_pago and ja_pago > 0:
        linhas.append({"Nº": 0, "Vencimento": hoje, "Valor": ja_pago,
                       "Status": STATUS_PAGA, "Pago em": hoje})
    for k, (v, d, x) in enumerate(zip(valores, datas, vezes), start=1):
        linhas.append({"Nº": k, "Vencimento": d, "Valor": v, "Status": "", "Pago em": None,
                       "Vezes no cartão": max(int(x or 1), 1)})
    return linhas


def parcelas_hibrido(entrada: float, data_entrada: date | None, valores_pix: list[float],
                     datas_pix: list[date], valores_cartao: list[float], datas_cartao: list[date],
                     vezes: list[int] | None, ja_passou: list[bool] | None, hoje: date) -> list[dict]:
    """
    Linhas de uma cobrança híbrida nova: a parte do Pix (entrada Nº 0 + parcelas)
    e, continuando a numeração, cada passada do cartão. Toda linha leva a Forma.
    `ja_passou[k]` = aquela passada já foi feita: entra como paga na data dela
    (igual à entrada do Pix, que entra paga quando a data já chegou).
    """
    linhas = [{**l, "Forma": TIPO_PIX}
              for l in parcelas_pix(entrada, data_entrada, valores_pix, datas_pix, hoje)]
    passou = list(ja_passou or []) + [False] * len(valores_cartao)
    depois_do_pix = len(valores_pix)
    for l, ok in zip(parcelas_cartao(0, hoje, valores_cartao, datas_cartao, vezes), passou):
        if ok:
            l = {**l, "Status": STATUS_PAGA, "Pago em": l["Vencimento"]}
        linhas.append({**l, "Nº": depois_do_pix + l["Nº"], "Forma": TIPO_CARTAO})
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
    return TIPO_CARTAO if tipo_cobranca == TIPO_CARTAO else TIPO_PIX


def _vezes(v) -> int:
    try:
        return min(max(int(float(_txt(v) or 1)), 1), MAX_VEZES_CARTAO)
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
        # A forma da cobrança sai das parcelas: as duas formas juntas = híbrida.
        formas = {p["tipo"] for p in ps}
        tipo = TIPO_HIBRIDO if len(formas) > 1 else (formas.pop() if formas else gravado)
        hibrida = tipo == TIPO_HIBRIDO
        # "Parcela 3 de 10" conta pela POSIÇÃO, não pelo Nº gravado: se uma
        # parcela do meio for removida, as outras não ficam com buraco.
        # Na híbrida a conta é separada por forma ("Pix 2 de 3", "Cartão 1 de 2").
        por_forma_n = {f: sum(1 for p in ps if p["n"] > 0 and p["tipo"] == f) for f in FORMAS}
        total_n = sum(por_forma_n.values())
        posicao = {f: 0 for f in FORMAS}
        geral = 0
        for p in ps:
            if p["n"] > 0:
                geral += 1
                posicao[p["tipo"]] += 1
            pos, de = (posicao[p["tipo"]], por_forma_n[p["tipo"]]) if hibrida else (geral, total_n)
            p["situacao"] = situacao_parcela(p, hoje)
            p["rotulo"] = rotulo_parcela(p["tipo"], pos if p["n"] > 0 else 0, de, hibrida)
            p["total_n"] = de
            p["id_cobranca"] = cid

        pago = sum(p["valor"] for p in ps if p["paga"])
        falta = sum(p["valor"] for p in ps if not p["paga"])
        atrasadas = [p for p in ps if p["situacao"] == SIT_ATRASADA]
        abertas = sorted((p for p in ps if not p["paga"] and p["vencimento"]),
                         key=lambda p: p["vencimento"])
        futuras = [p for p in abertas if p["vencimento"] >= hoje]
        ultima = max((p["vencimento"] for p in ps if p["vencimento"]), default=None)

        if atrasadas:
            sit = CLI_ATRASADO
        elif ps and not abertas and falta == 0:
            sit = CLI_QUITADO
        elif any(p["situacao"] == SIT_EM_BREVE for p in ps):
            sit = CLI_EM_BREVE
        else:
            sit = CLI_EM_DIA

        turma = normalizar_turma(c.get("Turma")) or _txt(c.get("Turma"))
        saida.append({
            "id": cid,
            "tipo": tipo,
            "hibrida": hibrida,
            # quanto de cada forma: {"Pix": {"pago", "falta", "total", "n"}, "Cartão": {...}}
            "por_forma": {f: _soma_da_forma(ps, f) for f in FORMAS},
            "cliente": _txt(c.get("Cliente")),
            "turma": turma,
            "treinamento": _txt(c.get("Treinamento")) or treinamento_da_turma(turma),
            "valor_total": valor_para_float(c.get("Valor Total")),
            "criada_em": parse_data(c.get("Criada em")),
            "criada_por": _txt(c.get("Criada por")),
            "cidade": _txt(c.get("Cidade")),   # texto livre: "Lajeado", "Laj", "SCS"...
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


def cidade_da_turma(cobs: list[dict], turma: str) -> str:
    """Cidade mais usada nas cobranças já cadastradas daquela turma ('' se nenhuma tem)."""
    contagem: dict[str, int] = {}
    for c in cobs:
        if c["turma"] == turma and c.get("cidade"):
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
    if turma_buscada and turma_buscada == c["turma"]:
        return True
    notas = " ".join([c.get("observacoes", "")] + [p.get("observacao", "") for p in c.get("parcelas", [])])
    alvo = chave_busca(f"{c['cliente']} {c['turma']} {c['treinamento']} {c['tipo']} {c.get('cidade', '')} {notas}")
    return all(palavra in alvo for palavra in chave_busca(termo).split())


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
        if tipos and c["tipo"] not in tipos:
            continue
        if treinamentos and c["treinamento"] not in treinamentos:
            continue
        if _txt(turma) and c["turma"] != (turma_n or _txt(turma).upper()):
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
    """Totais do topo do relatório."""
    return {
        "recebido": sum(c["pago"] for c in cobs),
        "a_receber": sum(c["falta"] for c in cobs),
        "atrasado": sum(c["atrasado"] for c in cobs),
        "n_atrasados": sum(1 for c in cobs if c["situacao"] == CLI_ATRASADO),
        "n_cobrancas": len(cobs),
    }


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


def nomes_livres(config: dict) -> list[str]:
    """Nomes que um aparelho novo pode escolher: sem aparelho preso, ou liberados pelo administrador."""
    presos = aparelhos_por_pessoa(config)
    return [p for p in pessoas_da_config(config)
            if not presos[p] or chave_busca(config.get(f"liberado:{p}", "")) == "sim"]


# ── Preferências de notificação (aba _Config, iguais para todo mundo) ─────────
#   telegram:<nome>   chat do Telegram daquela pessoa
#   avisos:<nome>     "nao" pausa os avisos só para ela
#   avisar_atrasadas / avisar_hoje / avisar_amanha / resumo_semanal   "nao" desliga

OPCOES_AVISO = {
    "avisar_atrasadas": "Cobranças atrasadas",
    "avisar_hoje": "O que é para cobrar hoje",
    "avisar_amanha": "O que é para cobrar amanhã",
    "resumo_semanal": "Resumo da semana (toda segunda)",
}


def _ligado(config: dict, chave: str) -> bool:
    """Tudo começa ligado; só o texto 'nao' desliga."""
    return chave_busca(config.get(chave, "")) not in ("nao", "não", "0", "false")


def opcoes_avisos(config: dict) -> dict:
    return {k: _ligado(config, k) for k in OPCOES_AVISO}


def destinatarios(config: dict) -> list[tuple]:
    """[(nome, chat_id)] de quem está conectado e não pausou os avisos."""
    saida = []
    for chave, valor in config.items():
        if chave.startswith("telegram:") and _txt(valor):
            nome = chave[len("telegram:"):]
            if _ligado(config, f"avisos:{nome}"):
                saida.append((nome, _txt(valor)))
    return sorted(saida)


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

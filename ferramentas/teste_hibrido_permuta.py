"""
Teste da COBRANÇA HÍBRIDA COM ESCOLHA DE FORMAS (pedido 06/11/2026): Pix, cartão e permuta,
pelo menos duas. Pelas telas:
  0. o híbrido de sempre (Pix + cartão) continua vindo marcado e igual; mínimo de 2 formas;
  1. Pix + permuta: valor da permuta já preenchido, conferência do total (falta / passa / fecha),
     retirada que passa do total, ficha com "No Pix" e "Na permuta";
  2. pela ficha: receber uma parcela do Pix, anotar retirada, somar um valor de permuta (o total
     combinado NÃO muda sozinho; ajusta em Editar dados);
  3. cartão + permuta e 4. as três formas (só uma parte pode ficar em branco);
  5. relatório: etiquetas com as cores das formas, saldo no cartão, "Saldo para retirar",
     filtros Permuta / Híbrido / Pix, busca pelo produto e a agenda sem linha de permuta.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): recomeça o exemplo e cadastra.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
DLG = "[role=dialog]"
falhas = []


def esperar(page, ms=2200):
    page.wait_for_timeout(ms)
    for _ in range(40):
        # pronto = sem o indicador de "rodando" E sem pedaço da tela anterior ainda esmaecido
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(600)
    if page.locator("[data-testid=stException]").count():
        falhas.append("ERRO NA TELA: " + page.locator("[data-testid=stException]").first.inner_text()[:300])


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra if not cond else "")
    if not cond:
        falhas.append(nome)


def tocar(page, alvo):
    loc = page.locator(alvo).first if isinstance(alvo, str) else alvo.first
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def por(page, rotulo, valor, dentro=""):
    c = page.locator(f"{dentro} input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def por_data(page, indice: int, d: date, dentro=""):
    """Campo de data do Streamlit (o N-ésimo): foca o pedaço do DIA e digita dia, mês e ano."""
    caixa = page.locator(f"{dentro} [data-testid=stDateInput]").nth(indice)
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1500)


def texto(page, sel):
    """Texto visível, com o espaço que não quebra ("R$&nbsp;10.000,00") virando espaço comum."""
    loc = page.locator(sel)
    return loc.first.inner_text().replace("\n", " ").replace("\xa0", " ") if loc.count() else ""


def textos(page, sel):
    return [x.inner_text().replace("\n", " ").replace("\xa0", " ") for x in page.locator(sel).all()]


def forma(page, nome):
    """Marca/desmarca uma forma no topo da cobrança híbrida."""
    page.locator(".st-key-sec_hb0 button", has_text=nome).first.click()
    esperar(page, 1200)


def marcadas(page):
    return [x.inner_text() for x in page.locator(".st-key-sec_hb0 button").all()
            if x.get_attribute("aria-pressed") == "true"]


def inicio(page):
    for _ in range(5):
        if page.locator(".st-key-hm_rel").count():
            return
        botao(page, "Voltar")


def nova_hibrida(page):
    inicio(page)
    tocar(page, ".st-key-hm_nova .hm-card")
    tocar(page, ".st-key-hm_hibrido .hm-card")


def relatorio(page):
    inicio(page)
    tocar(page, ".st-key-hm_rel .hm-card")


def filtro(page, nome):
    page.locator("[data-testid=stExpander] button", has_text=nome).first.click()
    esperar(page)


def falta_ou_passa(page):
    return texto(page, ".st-key-sec_hb5 .cx-falta") or texto(page, ".st-key-sec_hb5 .cx-passa") \
        or texto(page, ".st-key-sec_hb5 .cx-ok")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1900}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Permuta Híbrida"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    hoje = date.today()
    depois = hoje + timedelta(days=30)

    # ── 0. o híbrido de sempre e o mínimo de duas formas ──
    nova_hibrida(page)
    confere("vem marcado Pix + Cartão de crédito (como sempre)", marcadas(page) == ["Pix", "Cartão de crédito"],
            str(marcadas(page)))
    confere("as três formas para escolher",
            [x.inner_text() for x in page.locator(".st-key-sec_hb0 button").all()] == ["Pix", "Cartão de crédito", "Permuta"])
    confere("padrão: blocos do Pix e do cartão, sem o da permuta",
            page.locator(".st-key-sec_hb3").count() == 1 and page.locator(".st-key-sec_hb4").count() == 1
            and page.locator(".st-key-sec_hb_pm").count() == 0)
    por(page, "Valor total", "6000"); por(page, "Quanto vai no Pix", "2000")
    confere("padrão: o cartão continua sendo o resto (4.000)",
            "R$ 2.000,00" in texto(page, ".st-key-sec_hb2") and "R$ 4.000,00" in texto(page, ".st-key-sec_hb2")
            and page.locator(".st-key-sec_hb2 .tp-perm").count() == 0)
    page.screenshot(path=str(OUT / "hibperm_0_padrao.png"), full_page=True)
    forma(page, "Cartão de crédito")
    confere("com uma forma só: aviso de marcar pelo menos duas",
            page.locator(".st-key-sec_hb0 .cx-erro", has_text="pelo menos duas").count() == 1)
    confere("com uma forma só: somem os blocos de valores",
            page.locator(".st-key-sec_hb2").count() == 0 and page.locator(".st-key-sec_hb3").count() == 0)
    botao(page, "Salvar cobrança")
    confere("salvar com uma forma só não deixa", "Marque pelo menos duas formas" in texto(page, "[data-testid=stAlert]"),
            texto(page, "[data-testid=stAlert]")[:200])
    page.screenshot(path=str(OUT / "hibperm_1_uma_forma.png"), full_page=True)

    # ── 1. Pix + permuta: R$ 10.000 = Pix 6.000 (entrada 1.000 + 5x 1.000) + permuta 4.000 ──
    forma(page, "Permuta")
    confere("marcou Pix + Permuta", marcadas(page) == ["Pix", "Permuta"], str(marcadas(page)))
    confere("aparecem só os blocos do Pix e da permuta",
            page.locator(".st-key-sec_hb3").count() == 1 and page.locator(".st-key-sec_hb4").count() == 0
            and page.locator(".st-key-sec_hb_pm").count() == 1)
    por(page, "Nome do cliente", "Loja Teste Híbrida")
    por(page, "Turma", "l501")
    por(page, "Valor total", "10000")
    por(page, "Quanto vai no Pix", "")
    por(page, "Quanto vai na permuta", "4000")
    sec2 = texto(page, ".st-key-sec_hb2")
    confere("o Pix é o resto do total (6.000)", "R$ 6.000,00" in sec2 and "R$ 4.000,00" in sec2, sec2[-120:])
    v = page.locator(".st-key-hb_pm_cred_0 input[aria-label='Valor da permuta']").input_value()
    confere("o valor da permuta já vem preenchido (4.000,00)", v == "4.000,00", v)
    por(page, "Valor de entrada", "1000")
    por(page, "Número de parcelas", "5")
    page.locator(".st-key-hb_pm_ret_0 input[aria-label='Produto']").fill("camisetas")
    por(page, "Quanto desconta", "500", ".st-key-hb_pm_ret_0")
    confere("saldo da permuta ao vivo (3.500)", "Saldo para retirar: R$ 3.500,00" in texto(page, ".st-key-sec_hb_pm"))
    r = texto(page, ".st-key-sec_hb5")
    confere("resumo: parte do Pix", "Entrada de R$ 1.000,00" in r and "5x de R$ 1.000,00" in r, r[:300])
    confere("resumo: parte da permuta com retirada e saldo",
            "Valor de R$ 4.000,00" in r and "CAMISETAS · R$ 500,00" in r and "Saldo para retirar: R$ 3.500,00" in r, r)
    confere("resumo: fecha com o total (Pix + permuta)", "Fecha certinho com o total de R$ 10.000,00" in r)
    confere("resumo: avisa que a permuta não entra no dinheiro nem no Telegram",
            "A parte da permuta não entra no Recebido" in r)
    page.screenshot(path=str(OUT / "hibperm_2_pix_permuta.png"), full_page=True)
    por(page, "Valor da permuta", "3000", ".st-key-hb_pm_cred_0")
    confere("permuta menor: 'Faltam R$ 1.000,00'", "Faltam R$ 1.000,00" in falta_ou_passa(page), falta_ou_passa(page))
    por(page, "Valor da permuta", "5000", ".st-key-hb_pm_cred_0")
    confere("permuta maior: 'Passa R$ 1.000,00 do total'", "Passa R$ 1.000,00 do total" in falta_ou_passa(page),
            falta_ou_passa(page))
    por(page, "Valor da permuta", "", ".st-key-hb_pm_cred_0")
    confere("apagar o valor volta à conta (4.000) e fecha",
            page.locator(".st-key-hb_pm_cred_0 input[aria-label='Valor da permuta']").input_value() == "4.000,00"
            and "Fecha certinho" in texto(page, ".st-key-sec_hb5"))
    por(page, "Quanto desconta", "4500", ".st-key-hb_pm_ret_0")
    confere("retirada maior que a permuta: aviso", page.locator(".st-key-sec_hb_pm .cx-passa").count() == 1)
    botao(page, "Salvar cobrança")
    confere("e não deixa salvar", "As retiradas passam do total da permuta" in texto(page, "[data-testid=stAlert]"))
    por(page, "Quanto desconta", "500", ".st-key-hb_pm_ret_0")
    botao(page, "Salvar cobrança"); esperar(page, 2500)

    # ── ficha ──
    sub = texto(page, ".cx-sub")
    confere("ficha diz 'Híbrido (Pix + permuta)'", "Híbrido (Pix + permuta)" in sub, sub)
    confere("ficha: seções 'No Pix' e 'Na permuta'", textos(page, ".fc-grupo") == ["No Pix", "Na permuta"],
            str(textos(page, ".fc-grupo")))
    confere("ficha: total combinado de R$ 10.000,00", "R$ 10.000,00" in texto(page, ".fc-total"), texto(page, ".fc-total"))
    confere("ficha: sem aviso de total diferente", page.locator(".fc-aviso").count() == 0)
    fm = texto(page, ".fc-formas")
    confere("ficha: quanto de cada forma (Pix pago 1.000 de 6.000; permuta retirado 500 de 4.000, saldo 3.500)",
            "pago R$ 1.000,00 de R$ 6.000,00" in fm and "retirado R$ 500,00 de R$ 4.000,00" in fm
            and "saldo R$ 3.500,00" in fm, fm)
    nums = texto(page, ".fc-nums")
    confere("ficha: pago e falta só do dinheiro (1.000 / 5.000)", "R$ 1.000,00 Pago" in nums and "R$ 5.000,00 Falta" in nums,
            nums)
    perm = texto(page, ".fc-nums.fc-perm")
    confere("ficha: na permuta, total 4.000, retirado 500, saldo 3.500",
            "R$ 4.000,00 Total da permuta" in perm and "R$ 500,00 Retirado" in perm and "R$ 3.500,00 Saldo" in perm, perm)
    confere("ficha: 'Com saldo' na parte da permuta", page.locator(".fc .sit", has_text="Com saldo").count() == 1)
    confere("ficha: o valor e a retirada da permuta",
            page.locator(".pc.c-cred").count() == 1 and textos(page, ".pc.c-ret .pc-nome") == ["CAMISETAS"])
    confere("ficha: 5 'Recebi' (só o Pix) e botões da permuta",
            page.locator("button:visible", has_text="Recebi").count() == 5
            and page.locator("button:visible", has_text="Adicionar retirada").count() == 1
            and page.locator("button:visible", has_text="Adicionar valor").count() == 1
            and page.locator("button:visible", has_text="Adicionar parcela").count() == 1)
    page.screenshot(path=str(OUT / "hibperm_3_ficha.png"), full_page=True)

    # ── 2. pela ficha ──
    botao(page, "Recebi"); botao(page, "Confirmar", DLG); esperar(page, 2500)
    confere("receber uma parcela do Pix: pago 2.000 de 6.000",
            "pago R$ 2.000,00 de R$ 6.000,00" in texto(page, ".fc-formas"), texto(page, ".fc-formas"))
    botao(page, "Adicionar retirada")
    confere("janela da retirada mostra o saldo da permuta",
            page.locator(DLG, has_text="Saldo para retirar: R$ 3.500,00").count() == 1)
    por(page, "Produto", "bonés", DLG)
    por(page, "Quanto desconta do saldo", "1000", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    perm = texto(page, ".fc-nums.fc-perm")
    confere("retirada pela ficha desconta do saldo (2.500)", "R$ 1.500,00 Retirado" in perm and "R$ 2.500,00 Saldo" in perm,
            perm)
    confere("retirada não mexe no total combinado", "R$ 10.000,00" in texto(page, ".fc-total")
            and page.locator(".fc-aviso").count() == 0)
    botao(page, "Adicionar valor")
    confere("janela do valor avisa que o total combinado não muda sozinho",
            page.locator(f"{DLG} .cx-nota", has_text="continua o mesmo").count() == 1)
    por(page, "Valor da permuta", "500", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    perm = texto(page, ".fc-nums.fc-perm")
    confere("valor novo soma na permuta (4.500) e no saldo (3.000)",
            "R$ 4.500,00 Total da permuta" in perm and "R$ 3.000,00 Saldo" in perm, perm)
    confere("o 'Valor Total' combinado não foi regravado: aviso de diferença",
            "O total combinado é R$ 10.000,00, mas as partes somam R$ 10.500,00" in texto(page, ".fc-aviso"),
            texto(page, ".fc-aviso"))
    botao(page, "Editar dados")
    por(page, "Valor total", "10500", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    confere("Editar dados acerta o total combinado (10.500, sem aviso)",
            "R$ 10.500,00" in texto(page, ".fc-total") and page.locator(".fc-aviso").count() == 0)
    page.screenshot(path=str(OUT / "hibperm_4_ficha_depois.png"), full_page=True)

    # ── 3. cartão + permuta: R$ 5.000 = cartão 3.000 + permuta 2.000 ──
    nova_hibrida(page)
    forma(page, "Pix"); forma(page, "Permuta")
    confere("marcou Cartão + Permuta", marcadas(page) == ["Cartão de crédito", "Permuta"], str(marcadas(page)))
    por(page, "Nome do cliente", "Mercado Teste Híbrido")
    por(page, "Turma", "v20")
    por(page, "Valor total", "5000")
    por(page, "Quanto vai na permuta", "2000")
    confere("o cartão é o resto (3.000)", "R$ 3.000,00" in texto(page, ".st-key-sec_hb2"))
    por(page, "Quantas vezes você vai passar o cartão?", "1")
    por_data(page, 0, depois, ".st-key-hb_ct_linha_0")
    por(page, "Parcelado em quantas vezes (1ª passada)", "3")
    r = texto(page, ".st-key-sec_hb5")
    confere("resumo do cartão + permuta fecha", "Fecha certinho com o total de R$ 5.000,00" in r
            and "R$ 3.000,00 · 3x de R$ 1.000,00" in r and "Valor de R$ 2.000,00" in r, r)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    confere("ficha: 'Híbrido (cartão + permuta)'", "Híbrido (cartão + permuta)" in texto(page, ".cx-sub"),
            texto(page, ".cx-sub"))
    confere("ficha: seções 'No cartão' e 'Na permuta'", textos(page, ".fc-grupo") == ["No cartão", "Na permuta"],
            str(textos(page, ".fc-grupo")))
    confere("ficha: o botão de dinheiro é 'Adicionar data' (só cartão)",
            page.locator("button:visible", has_text="Adicionar data").count() == 1
            and page.locator("button:visible", has_text="Adicionar parcela").count() == 0)
    botao(page, "Adicionar data")
    marcado = page.locator(f"{DLG} [data-testid=stRadio] input:checked").first.get_attribute("value")
    confere("janela Adicionar vem no cartão", marcado in ("1", "Cartão"), str(marcado))
    page.keyboard.press("Escape"); esperar(page)
    page.screenshot(path=str(OUT / "hibperm_5_cartao_permuta.png"), full_page=True)

    # ── 4. as três: R$ 9.000 = Pix 3.000 (3x) + cartão 3.000 + permuta 3.000 ──
    nova_hibrida(page)
    forma(page, "Permuta")
    confere("marcou as três", marcadas(page) == ["Pix", "Cartão de crédito", "Permuta"], str(marcadas(page)))
    por(page, "Nome do cliente", "Três Formas Teste")
    por(page, "Turma", "i30")
    por(page, "Valor total", "9000")
    por(page, "Quanto vai no Pix", "3000")
    botao(page, "Salvar cobrança")
    confere("duas em branco: só uma pode ficar em branco",
            "só uma pode ficar em branco" in texto(page, "[data-testid=stAlert]"), texto(page, "[data-testid=stAlert]")[:300])
    por(page, "Quanto vai no cartão", "3000")
    sec2 = texto(page, ".st-key-sec_hb2")
    confere("a permuta é o resto (3.000) e as três etiquetas aparecem",
            sec2.count("R$ 3.000,00") == 3 and page.locator(".st-key-sec_hb2 .tp").count() == 3, sec2[-160:])
    por(page, "Número de parcelas", "3")
    por(page, "Quantas vezes você vai passar o cartão?", "1")
    por_data(page, 0, depois, ".st-key-hb_ct_linha_0")
    r = texto(page, ".st-key-sec_hb5")
    confere("resumo das três fecha", "Fecha certinho com o total de R$ 9.000,00" in r and "A cobrança vai até" in r, r)
    page.screenshot(path=str(OUT / "hibperm_6_tres.png"), full_page=True)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    confere("ficha: seções 'No Pix', 'No cartão' e 'Na permuta'",
            textos(page, ".fc-grupo") == ["No Pix", "No cartão", "Na permuta"], str(textos(page, ".fc-grupo")))
    rot = [x.split(" · ")[0] for x in textos(page, ".pc-rot")]
    confere("rótulos por forma", rot[:4] == ["Pix 1 de 3", "Pix 2 de 3", "Pix 3 de 3", "Cartão 1 de 1"], str(rot))

    # ── 5. relatório ──
    relatorio(page)
    rs = texto(page, ".rs-perm")
    # PADARIA 3.500 + FLORICULTURA 2.400 + Loja 3.000 + Mercado 2.000 + Três 3.000
    confere("'Saldo para retirar' soma a permuta das híbridas (R$ 13.900,00 em 5)",
            "R$ 13.900,00" in rs and "5 permutas" in rs, rs)
    cards = {c.locator(".cc-nome").inner_text(): c for c in page.locator(".cc").all()}
    def classe(nome):
        return cards[nome].locator(".tp").first.get_attribute("class") if nome in cards else ""
    confere("etiqueta Pix + permuta (azul + verde-água)", "hb-px-pm" in classe("LOJA TESTE HÍBRIDA"), classe("LOJA TESTE HÍBRIDA"))
    confere("etiqueta cartão + permuta (rosa + verde-água)", "hb-ct-pm" in classe("MERCADO TESTE HÍBRIDO"))
    confere("etiqueta das três formas", "hb-tres" in classe("TRÊS FORMAS TESTE"))
    confere("etiqueta Pix + cartão continua a de sempre",
            classe("Juliana Martins (exemplo)").strip() == "tp tp-hib", classe("Juliana Martins (exemplo)"))
    loja = cards["LOJA TESTE HÍBRIDA"].inner_text().replace("\n", " ") if "LOJA TESTE HÍBRIDA" in cards else ""
    confere("cartão do relatório: falta do dinheiro e saldo da permuta",
            "falta R$ 4.000,00" in loja and "saldo R$ 3.000,00" in loja, loja)
    flor = cards.get("FLORICULTURA JARDIM (EXEMPLO)")
    confere("exemplo novo da demonstração: FLORICULTURA (Pix + permuta)",
            flor is not None and "hb-px-pm" in classe("FLORICULTURA JARDIM (EXEMPLO)")
            and "saldo R$ 2.400,00" in flor.inner_text().replace("\n", " "))
    alturas = [round(x.bounding_box()["height"]) for x in page.locator(".cc").all()]
    confere("cartões continuam compactos (até 80 px)", max(alturas) <= 80, str(alturas))
    page.screenshot(path=str(OUT / "hibperm_7_relatorio.png"), full_page=True)
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    filtro(page, "Permuta")
    nomes = sorted(textos(page, ".cc-nome"))
    confere("filtro Permuta: a permuta inteira + as 4 híbridas com permuta",
            nomes == sorted(["PADARIA BOM GOSTO (EXEMPLO)", "FLORICULTURA JARDIM (EXEMPLO)", "LOJA TESTE HÍBRIDA",
                             "MERCADO TESTE HÍBRIDO", "TRÊS FORMAS TESTE"]), str(nomes))
    topo = texto(page, ".rs")
    # dinheiro dessas: recebido FLORICULTURA 1.000 + Loja 2.000; a receber 4.000 + 4.000 + 3.000 + 6.000
    confere("filtro Permuta: Recebido / A receber só com o dinheiro das híbridas (3.000 / 17.000)",
            "R$3.000,00" in topo and "R$17.000,00" in topo and "R$13.900,00" in texto(page, ".rs-perm").replace(" ", ""),
            topo)
    filtro(page, "Permuta"); filtro(page, "Híbrido")
    confere("filtro Híbrido: todas as híbridas (5)", page.locator(".cc").count() == 5
            and page.locator(".cc .tp-hib").count() == 5, str(textos(page, ".cc-nome")))
    filtro(page, "Híbrido"); filtro(page, "Pix")
    confere("filtro Pix: nenhuma híbrida", page.locator(".cc .tp-hib").count() == 0 and page.locator(".cc").count() > 0)
    filtro(page, "Pix")
    por(page, "Buscar", "bones")
    confere("busca pelo produto retirado acha a híbrida",
            page.locator(".cc").count() == 1 and page.locator(".cc", has_text="LOJA TESTE HÍBRIDA").count() == 1)
    por(page, "Buscar", "")
    page.get_by_text("Agenda", exact=True).first.click(); esperar(page)
    page.get_by_text("Escolher datas", exact=True).first.click(); esperar(page)
    por_data(page, 1, hoje + timedelta(days=200))
    confere("agenda: só parcelas de dinheiro (nenhuma linha de permuta)",
            page.locator(".pc").count() > 0 and page.locator(".pc.c-cred, .pc.c-ret, .pc .tp-perm").count() == 0
            and page.locator(".pc .tp-pix").count() + page.locator(".pc .tp-cartao").count() == page.locator(".pc").count())
    page.screenshot(path=str(OUT / "hibperm_8_agenda.png"), full_page=True)

    # ── ficha do exemplo da demonstração ──
    page.get_by_text("Clientes", exact=True).first.click(); esperar(page)
    tocar(page, page.locator(".cc", has_text="FLORICULTURA"))
    confere("ficha do exemplo: 'No Pix' e 'Na permuta' com a retirada",
            textos(page, ".fc-grupo") == ["No Pix", "Na permuta"]
            and textos(page, ".pc.c-ret .pc-nome") == ["ARRANJOS DE FLORES PARA O EVENTO"], str(textos(page, ".fc-grupo")))
    page.screenshot(path=str(OUT / "hibperm_9_exemplo.png"), full_page=True)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

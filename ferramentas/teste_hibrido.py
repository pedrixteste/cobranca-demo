"""
Teste do PAGAMENTO HÍBRIDO (uma parte no Pix, outra no cartão), pelas telas:
  1. cadastro de uma cobrança híbrida e a ficha dela;
  2. receber UMA parcela metade em cada forma;
  3. cobrança Pix que vira híbrida (uma parcela troca de forma; outra é adicionada no cartão);
  4. relatório: etiqueta, filtro e agenda.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): cadastra e marca pagamento.
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
    print(("OK    " if cond else "FALHA ") + nome, extra)
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


def opcao(page, texto, dentro=""):
    """Escolhe uma opção de st.radio."""
    page.locator(f"{dentro} [data-testid=stRadio] label", has_text=texto).first.click()
    esperar(page, 1200)


def textos(page, sel):
    return [x.inner_text().replace("\n", " ") for x in page.locator(sel).all()]


def ir_ao_relatorio(page):
    for _ in range(4):
        if page.locator(".st-key-hm_rel").count():
            break
        botao(page, "Voltar")
    tocar(page, ".st-key-hm_rel .hm-card")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1900}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Híbrido"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    hoje = date.today()
    depois = hoje + timedelta(days=30)

    # ── 1. cadastro: R$ 6.000 = Pix 2.000 (entrada 500 + 3x 500) + cartão 4.000 (1.000 hoje em 2x + 3.000 em 6x) ──
    tocar(page, ".st-key-hm_nova .hm-card")
    confere("tela Nova cobrança tem o cartão 'Cobrança híbrida'", page.locator(".st-key-hm_hibrido .hm-card").count() == 1)
    page.screenshot(path=str(OUT / "hibrido_0_nova.png"), full_page=True)
    tocar(page, ".st-key-hm_hibrido .hm-card")
    por(page, "Nome do cliente", "Bruna Teste Híbrido")
    por(page, "Turma", "l500")
    por(page, "Valor total", "6000")
    por(page, "Quanto vai no Pix", "2000")
    sec2 = page.locator(".st-key-sec_hb2").inner_text()
    confere("o cartão é o resto do total (R$ 4.000,00)", "R$ 2.000,00" in sec2 and "R$ 4.000,00" in sec2,
            sec2.replace("\n", " | ")[-120:])
    por(page, "Valor de entrada", "500")
    por(page, "Número de parcelas", "3")
    por(page, "Quantas vezes você vai passar o cartão?", "2")
    # datas na tela: 0 = entrada, 1 = 1º vencimento, 2 e 3 = passadas do cartão
    por_data(page, 2, hoje); por_data(page, 3, depois)
    por(page, "Valor 1", "1000")
    por(page, "Parcelado em quantas vezes (1ª passada)", "2")
    por(page, "Parcelado em quantas vezes (2ª passada)", "6")
    caixa = page.locator("[data-testid=stCheckbox]", has_text="Já passou o cartão (1ª passada)")
    confere("passada com a data de hoje ganha a caixa 'Já passou', marcada",
            caixa.count() == 1 and caixa.locator("input").is_checked())
    confere("passada futura não tem a caixa",
            page.locator("[data-testid=stCheckbox]", has_text="Já passou o cartão (2ª passada)").count() == 0)
    caixa.locator("label").first.click(); esperar(page, 1200)
    confere("desmarcar a caixa tira o 'já passou' do resumo",
            "já passou" not in page.locator(".st-key-sec_hb5").inner_text())
    caixa.locator("label").first.click(); esperar(page, 1200)
    resumo = page.locator(".st-key-sec_hb5").inner_text().replace("\n", " | ")
    confere("resumo: entrada do Pix paga", "Entrada de R$ 500,00" in resumo and "(paga)" in resumo, resumo[:260])
    confere("resumo: 3x de R$ 500,00 no Pix", "3x de R$ 500,00" in resumo)
    confere("resumo: cartão de hoje em 2x, já passou", "R$ 1.000,00 · 2x de R$ 500,00 · já passou" in resumo)
    confere("resumo: o resto do cartão (R$ 3.000,00) em 6x", "R$ 3.000,00 · 6x de R$ 500,00" in resumo)
    confere("resumo: totais de cada forma", "Pix | R$ 2.000,00" in resumo.replace("  ", " ") or
            ("R$ 2.000,00" in resumo and "R$ 4.000,00" in resumo))
    confere("resumo: fecha com o total", "Fecha certinho" in resumo)
    por(page, "Observação (opcional)", "metade no pix, metade no cartão do pai")
    page.screenshot(path=str(OUT / "hibrido_1_cadastro.png"), full_page=True)
    botao(page, "Salvar cobrança"); esperar(page, 2500)

    # ── ficha ──
    sub = page.locator(".cx-sub").first.inner_text()
    confere("ficha diz que é Híbrido", "Híbrido" in sub, sub)
    formas = page.locator(".fc-formas").inner_text().replace("\n", " ")
    confere("ficha: quanto do Pix já entrou", "pago R$ 500,00 de R$ 2.000,00" in formas, formas)
    confere("ficha: quanto do cartão já passou", "passou R$ 1.000,00 de R$ 4.000,00" in formas)
    confere("ficha separada em 'No Pix' e 'No cartão'", textos(page, ".fc-grupo") == ["No Pix", "No cartão"])
    rot = textos(page, ".pc-rot")
    confere("rótulos por forma", [r.split(" · ")[0] for r in rot] ==
            ["Entrada no Pix", "Pix 1 de 3", "Pix 2 de 3", "Pix 3 de 3", "Cartão 1 de 2", "Cartão 2 de 2"], str(rot))
    confere("cartão mostra em quantas vezes", "2x de R$ 500,00" in rot[4] and "6x de R$ 500,00" in rot[5])
    confere("carimbos: PAGO no Pix e PASSOU no cartão",
            [c.split(" ")[0] for c in textos(page, ".pc-carimbo")] == ["PAGO", "PASSOU"], str(textos(page, ".pc-carimbo")))
    confere("cada parcela tem a etiqueta da forma dela",
            page.locator(".pc .tp-pix").count() == 4 and page.locator(".pc .tp-cartao").count() == 2)
    confere("botões: 3 'Recebi' (Pix) e 1 'Passou' (cartão)",
            page.locator("button:visible", has_text="Recebi").count() == 3
            and page.locator("button:visible", has_text="Passou").count() == 1)
    confere("valores pago e falta", "R$ 1.500,00" in page.locator(".fc-nums").inner_text()
            and "R$ 4.500,00" in page.locator(".fc-nums").inner_text())
    page.screenshot(path=str(OUT / "hibrido_2_ficha.png"), full_page=True)

    # ── 2. receber uma parcela do Pix (R$ 500) com R$ 200 no cartão ──
    botao(page, "Recebi")
    page.locator(f"{DLG} label", has_text="Pagamento híbrido").first.click(); esperar(page, 1200)
    por(page, "Quanto foi no cartão", "500", DLG)
    confere("não aceita a outra parte igual ao valor da parcela",
            page.locator(f"{DLG} .cx-erro", has_text="menor que R$ 500,00").count() == 1)
    por(page, "Quanto foi no cartão", "200", DLG)
    por(page, "No cartão, em quantas vezes", "2", DLG)
    janela = page.locator(DLG).inner_text().replace("\n", " ")
    confere("janela mostra a conta: Pix 300 + Cartão 200 em 2x",
            "R$ 300,00" in janela and "R$ 200,00" in janela and "2x de R$ 100,00" in janela, janela[-200:])
    page.screenshot(path=str(OUT / "hibrido_3_receber.png"), full_page=True)
    botao(page, "Confirmar", DLG); esperar(page, 2500)
    rot = textos(page, ".pc-rot")
    valores = textos(page, ".pc-valor")
    confere("a parcela do Pix ficou com R$ 300,00 e paga",
            rot[1].startswith("Pix 1 de 3") and valores[1] == "R$ 300,00" and "recebeu" in rot[1], f"{rot[1]} {valores[1]}")
    confere("nasceu a parte do cartão, R$ 200,00 em 2x, já passada",
            rot[-1].startswith("Cartão 3 de 3") and "2x de R$ 100,00" in rot[-1] and "passou" in rot[-1]
            and valores[-1] == "R$ 200,00", f"{rot[-1]} {valores[-1]}")
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("o total não mudou: pago 2.000, falta 4.000", "R$ 2.000,00" in nums and "R$ 4.000,00" in nums, nums)
    formas = page.locator(".fc-formas").inner_text().replace("\n", " ")
    confere("por forma: Pix 800 de 1.800 e cartão 1.200 de 4.200",
            "pago R$ 800,00 de R$ 1.800,00" in formas and "passou R$ 1.200,00 de R$ 4.200,00" in formas, formas)
    confere("sem aviso de total diferente", page.locator(".fc-aviso").count() == 0)
    page.screenshot(path=str(OUT / "hibrido_4_ficha_depois.png"), full_page=True)

    # ── 3. cobrança Pix que vira híbrida ──
    ir_ao_relatorio(page)
    tocar(page, page.locator(".cc", has_text="Roberto Almeida"))
    confere("antes: cobrança Pix comum, rótulos de sempre",
            [r.split(" · ")[0] for r in textos(page, ".pc-rot")] == ["Entrada", "Parcela 1 de 2", "Parcela 2 de 2"]
            and page.locator(".fc-formas").count() == 0, str(textos(page, ".pc-rot")))
    botao(page, "Alterar")
    confere("janela Alterar vem na forma da parcela (Pix)",
            page.locator(f"{DLG} [data-testid=stRadio] input:checked").first.get_attribute("value") in ("0", "Pix"))
    opcao(page, "Cartão", DLG)
    por(page, "Parcelado em quantas vezes", "3", DLG)
    page.screenshot(path=str(OUT / "hibrido_5_alterar.png"), full_page=True)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    rot = textos(page, ".pc-rot")
    confere("virou híbrida: uma parcela no cartão em 3x",
            "Híbrido" in page.locator(".cx-sub").first.inner_text()
            and any(r.startswith("Cartão 1 de 1") and "3x de" in r for r in rot)
            and any(r.startswith("Pix 1 de 1") for r in rot) and any(r.startswith("Entrada no Pix") for r in rot), str(rot))
    confere("botão passa a ser 'Adicionar parcela ou data'",
            page.locator("button:visible", has_text="Adicionar parcela ou data").count() == 1)
    botao(page, "Adicionar parcela ou data")
    opcao(page, "Cartão", DLG)
    por_data(page, 0, depois, DLG)
    por(page, "Valor", "300", DLG)
    por(page, "Parcelado em quantas vezes", "2", DLG)
    botao(page, "Adicionar", DLG); esperar(page, 2500)
    rot = textos(page, ".pc-rot")
    confere("adicionou uma data de cartão em 2x", any(r.startswith("Cartão 2 de 2") and "2x de R$ 150,00" in r for r in rot), str(rot))
    page.screenshot(path=str(OUT / "hibrido_6_virou_hibrida.png"), full_page=True)

    # ── 4. relatório ──
    ir_ao_relatorio(page)
    hib = [x.inner_text().split("\n")[0] for x in page.locator(".cc").all() if x.locator(".tp-hib").count()]
    confere("relatório: 3 cobranças com a etiqueta Híbrido", len(hib) == 3, str(hib))
    juliana = page.locator(".cc", has_text="Juliana Martins").inner_text().replace("\n", " ")
    confere("cartão do relatório diz a forma da próxima", "no cartão" in juliana or "no Pix" in juliana, juliana)
    alturas = [round(x.bounding_box()["height"]) for x in page.locator(".cc").all()]
    confere("cartões do relatório continuam compactos (até 80 px)", max(alturas) <= 80, str(alturas))
    total = page.locator(".cc").count()
    page.screenshot(path=str(OUT / "hibrido_7_relatorio.png"), full_page=True)
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Híbrido").first.click(); esperar(page)
    confere("filtro 'Híbrido' mostra só as 3", page.locator(".cc").count() == 3 and page.locator(".cc .tp-hib").count() == 3)
    page.locator("[data-testid=stExpander] button", has_text="Híbrido").first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Pix").first.click(); esperar(page)
    confere("filtro 'Pix' não traz híbrida", page.locator(".cc .tp-hib").count() == 0 and 0 < page.locator(".cc").count() < total,
            f"{page.locator('.cc').count()} de {total}")
    page.locator("[data-testid=stExpander] button", has_text="Pix").first.click(); esperar(page)
    page.get_by_text("Agenda", exact=True).first.click(); esperar(page)
    page.get_by_text("Este mês", exact=True).first.click(); esperar(page)
    confere("agenda: nenhuma parcela aparece como 'Híbrido', cada uma diz Pix ou Cartão",
            page.locator(".pc .tp-hib").count() == 0 and page.locator(".pc .tp").count() == page.locator(".pc").count()
            and page.locator(".pc").count() > 0, f"{page.locator('.pc').count()} parcelas")
    page.screenshot(path=str(OUT / "hibrido_8_agenda.png"), full_page=True)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

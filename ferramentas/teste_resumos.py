"""
Teste do Resumo no jeito do Pix nas outras formas (pedido 21/10): Cartão, Híbrida e Permuta.
O resumo aparece desde o começo (passada sem data = "falta escolher"), mostra o já pago e,
na permuta, o saldo. Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612).
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
falhas = []


def esperar(page, ms=2000):
    page.wait_for_timeout(ms)
    for _ in range(40):
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(600)
    if page.locator("[data-testid=stException]").count():
        falhas.append("ERRO NA TELA: " + page.locator("[data-testid=stException]").first.inner_text()[:200])


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra)
    if not cond:
        falhas.append(nome)


def tocar(page, sel):
    box = page.locator(sel).first.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def por(page, rotulo, valor, dentro=""):
    c = page.locator(f"{dentro} input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def por_data(page, indice: int, d: date):
    caixa = page.locator("[data-testid=stDateInput]").nth(indice)
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1500)


def texto(page, sec):
    return page.locator(f".st-key-{sec}").inner_text().replace("\n", " | ")


def nova(page, chave):
    for _ in range(4):
        if page.locator(".st-key-hm_nova").count():
            break
        botao(page, "Voltar")
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, f".st-key-{chave} .hm-card")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Resumo"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")
    hoje = date.today()
    antes, depois = hoje - timedelta(days=3), hoje + timedelta(days=30)

    # ── Cartão ──
    nova(page, "hm_cartao")
    r = texto(page, "sec_ct4")
    confere("cartão: sem nada preenchido, pede quantas vezes", "Diga quantas vezes vai passar o cartão" in r, r)
    por(page, "Nome do cliente", "Cartão Teste Resumo"); por(page, "Turma", "l400")
    por(page, "Valor total", "12000"); por(page, "Valor que já foi pago", "2000")
    por(page, "Quantas vezes você vai passar o cartão?", "2")
    r = texto(page, "sec_ct4")
    confere("cartão: resumo já aparece SEM as datas", "Data 1: falta escolher" in r and "Data 2: falta escolher" in r, r[:260])
    confere("cartão: mostra o já pago", "Já pago: R$ 2.000,00" in r)
    confere("cartão: diz quantas passadas e quanto somam", "Cartão em 2 passadas, somando R$ 10.000,00" in r)
    confere("cartão: cada passada com o valor (5.000)", "falta escolher · R$ 5.000,00 · à vista" in r)
    confere("cartão: já confere o total", "Fecha certinho" in r)
    confere("cartão: sem datas ainda não diz até quando vai", "vai até" not in r)
    page.locator(".st-key-sec_ct4").screenshot(path=str(OUT / "resumo_cartao_1_sem_datas.png"))

    por_data(page, 1, depois)
    r = texto(page, "sec_ct4")
    confere("cartão: passada com data vem antes da que falta",
            r.find(depois.strftime("%d/%m/%Y")) != -1 and r.find(depois.strftime("%d/%m/%Y")) < r.find("Data 1: falta"), r[:260])
    por_data(page, 0, antes)
    por(page, "Parcelado em quantas vezes (1ª passada)", "8")
    por(page, "Valor 1", "4000")
    r = texto(page, "sec_ct4")
    confere("cartão: passada antiga em 8x e já passou",
            f"{antes.strftime('%d/%m/%Y')} · R$ 4.000,00 · 8x de R$ 500,00 · já passou" in r, r[:300])
    confere("cartão: o resto vai para a outra passada (6.000)", f"{depois.strftime('%d/%m/%Y')} · R$ 6.000,00 · à vista" in r)
    confere("cartão: em ordem de data", r.find(antes.strftime("%d/%m/%Y")) < r.find(depois.strftime("%d/%m/%Y")))
    confere("cartão: com todas as datas diz até quando vai", "A cobrança vai até" in r)
    confere("cartão: some o 'falta escolher'", "falta escolher" not in r)
    confere("cartão: continua fechando", "Fecha certinho" in r)
    page.locator(".st-key-sec_ct4").screenshot(path=str(OUT / "resumo_cartao_2_completo.png"))
    por(page, "Valor 2", "5000")
    r = texto(page, "sec_ct4")
    confere("cartão: valor que não fecha avisa a diferença", "Faltam R$ 1.000,00" in r, r[-160:])
    por(page, "Valor 2", "")
    confere("cartão: apagar o valor volta a fechar", "Fecha certinho" in texto(page, "sec_ct4"))
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    rot = " ".join(x.inner_text().replace("\n", " ") for x in page.locator(".pc-rot").all())
    confere("cartão: salvou com as 2 passadas", "Cartão 1 de 2" in rot and "Cartão 2 de 2" in rot, rot[:200])

    # ── Híbrida ──
    nova(page, "hm_hibrido")
    r = texto(page, "sec_hb5")
    confere("híbrida: sem valores, pede o total", "Preencha o valor total" in r, r)
    por(page, "Nome do cliente", "Híbrida Teste Resumo"); por(page, "Turma", "l500")
    por(page, "Valor total", "6000"); por(page, "Quanto vai no Pix", "2000")
    r = texto(page, "sec_hb5")
    confere("híbrida: com o total dividido já mostra as duas partes",
            "R$ 2.000,00" in r and "R$ 4.000,00" in r and "Falta preencher a parte do Pix" in r
            and "Falta preencher a parte do cartão" in r, r[:260])
    confere("híbrida: sem as partes não confere o total ainda", "Fecha certinho" not in r and "Faltam" not in r)
    por(page, "Valor de entrada", "500"); por(page, "Número de parcelas", "3")
    r = texto(page, "sec_hb5")
    confere("híbrida: parte do Pix aparece", "Entrada de R$ 500,00" in r and "3x de R$ 500,00" in r, r[:260])
    confere("híbrida: cartão ainda falta", "Falta preencher a parte do cartão" in r)
    por(page, "Quantas vezes você vai passar o cartão?", "2")
    r = texto(page, "sec_hb5")
    confere("híbrida: passadas sem data aparecem", "Data 1: falta escolher · R$ 2.000,00" in r, r[:320])
    confere("híbrida: sem a linha 'Cartão em 2 passadas' (a etiqueta já soma)", "passadas, somando" not in r)
    confere("híbrida: já confere o total", "Fecha certinho" in r)
    page.locator(".st-key-sec_hb5").screenshot(path=str(OUT / "resumo_hibrido_1_sem_datas.png"))
    n = page.locator("[data-testid=stDateInput]").count()
    por_data(page, n - 2, hoje); por_data(page, n - 1, depois)
    r = texto(page, "sec_hb5")
    confere("híbrida: com as datas diz até quando vai", "A cobrança vai até" in r and "falta escolher" not in r, r[-200:])
    confere("híbrida: passada de hoje já passou", f"{hoje.strftime('%d/%m/%Y')} · R$ 2.000,00 · à vista · já passou" in r)
    page.locator(".st-key-sec_hb5").screenshot(path=str(OUT / "resumo_hibrido_2_completo.png"))

    # ── Permuta ──
    botao(page, "Voltar")
    nova(page, "hm_permuta")
    por(page, "Nome do cliente", "Permuta Teste Resumo"); por(page, "Turma", "l600")
    por(page, "Valor da permuta", "5000")
    r = texto(page, "sec_pm4")
    confere("permuta: resumo mostra o saldo inteiro", "Saldo para retirar: R$ 5.000,00" in r, r)
    por(page, "Produto", "10 camisetas"); por(page, "Quanto desconta", "800")
    r = texto(page, "sec_pm4")
    confere("permuta: resumo com a retirada e o saldo", "10 CAMISETAS" in r and "Saldo para retirar: R$ 4.200,00" in r, r)
    page.locator(".st-key-sec_pm4").screenshot(path=str(OUT / "resumo_permuta.png"))
    por(page, "Quanto desconta", "9000")
    confere("permuta: resumo avisa quando passa do total",
            page.locator(".st-key-sec_pm4 .cx-perigo", has_text="passam do total").count() == 1)
    b.close()

print("\nFALHAS:" if falhas else "\nTUDO OK", *falhas, sep="\n- " if falhas else "")
sys.exit(1 if falhas else 0)

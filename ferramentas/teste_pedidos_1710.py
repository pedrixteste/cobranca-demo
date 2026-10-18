"""
Teste dos pedidos de 17/10/2026:
  1. sem limite de parcelas (Pix), de datas do cartão e de vezes no cartão;
  2. no modo Parcial, o valor de cada parcela já aparece preenchido (10x de R$ 1.000 = R$ 100,00)
     e dá para mudar um mês: os outros dividem o resto e o total continua fechando.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612).
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
falhas = []


def esperar(page, ms=2000):
    page.wait_for_timeout(ms)
    for _ in range(60):
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


def tocar(page, sel):
    loc = page.locator(sel).first
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def botao(page, texto):
    page.locator("button:visible", has_text=texto).first.click()
    esperar(page)


def campo(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']").first


def por(page, rotulo, valor):
    c = campo(page, rotulo)
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def valores_parciais(page, n):
    return [campo(page, f"Valor da {k}ª").input_value() for k in range(1, n + 1)]


def inicio(page):
    for _ in range(5):
        if page.locator(".st-key-hm_nova").count():
            return
        botao(page, "Voltar")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1900}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste 17/10"); botao(page, "Entrar")

    # ── Pix parcial: valor de cada parcela já preenchido ──
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_pix .hm-card")
    por(page, "Valor total", "1000")
    por(page, "Número de parcelas", "10")
    page.get_by_text("Parcial", exact=True).nth(0).click(); esperar(page)
    v = valores_parciais(page, 10)
    confere("Parcial: as 10 parcelas já vêm com 100,00", v == ["100,00"] * 10, str(v))
    por(page, "Valor da 3ª", "190")
    v = valores_parciais(page, 10)
    confere("mudou a 3ª para 190: ela fica, as outras dividem o resto (90,00)",
            v[2] == "190,00" and all(x == "90,00" for i, x in enumerate(v) if i != 2), str(v))
    resumo = page.locator(".st-key-sec_px4").inner_text()
    confere("o total continua fechando", "Fecha certinho" in resumo, resumo.replace("\n", " | ")[:160])
    page.screenshot(path=str(OUT / "pedidos1710_1_parcial.png"), full_page=True)
    c = campo(page, "Valor da 3ª")
    c.click(); page.keyboard.press("Control+A"); page.keyboard.press("Backspace"); c.press("Enter"); esperar(page)
    v = valores_parciais(page, 10)
    confere("apagar a 3ª devolve ela à conta: todas 100,00 de novo", v == ["100,00"] * 10, str(v))
    por(page, "Valor total", "2000")
    v = valores_parciais(page, 10)
    confere("mudou o total para 2.000: as parcelas viram 200,00", v == ["200,00"] * 10, str(v))
    por(page, "Valor total", "1000")
    por(page, "Valor de entrada", "100")
    v = valores_parciais(page, 10)
    confere("com entrada de 100: as parcelas dividem o resto (90,00)", v == ["90,00"] * 10, str(v))

    # ── sem limite de parcelas no Pix ──
    page.get_by_text("Contínuo", exact=True).nth(0).click(); esperar(page)
    por(page, "Número de parcelas", "100")
    resumo = page.locator(".st-key-sec_px4").inner_text()
    confere("Pix aceita 100 parcelas", campo(page, "Número de parcelas").input_value() == "100"
            and "100x de R$ 9,00" in resumo, resumo.replace("\n", " | ")[:160])

    # ── cartão: sem limite de datas nem de vezes, valores já preenchidos ──
    inicio(page)
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_cartao .hm-card")
    por(page, "Valor total", "25000")
    por(page, "Quantas vezes você vai passar o cartão?", "25")
    confere("cartão aceita 25 datas", page.locator("[data-testid=stDateInput]").count() == 25,
            str(page.locator("[data-testid=stDateInput]").count()))
    v = [campo(page, f"Valor {k}").input_value() for k in (1, 13, 25)]
    confere("cada passada já vem com o valor (1.000,00)", v == ["1.000,00"] * 3, str(v))
    por(page, "Parcelado em quantas vezes (1ª passada)", "36")
    confere("aceita parcelar em 36 vezes",
            campo(page, "Parcelado em quantas vezes (1ª passada)").input_value() == "36")
    page.screenshot(path=str(OUT / "pedidos1710_2_cartao.png"), full_page=True)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

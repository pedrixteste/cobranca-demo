"""Seta de voltar do celular: Relatório -> voltar -> Início; Nova -> Pix -> voltar -> Nova -> voltar -> Início."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
falhas = []


def esperar(page, ms=2500):
    page.wait_for_timeout(ms)
    for _ in range(40):
        # pronto = sem o indicador de "rodando" E sem pedaço da tela anterior ainda esmaecido
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)


def abrir(page, espera=5000):
    """Abre o app já identificado como 'Robo'; na 1ª vez passa pela tela 'Quem está usando?'."""
    page.goto(URL.rstrip("/") + "/?quem=Robo")
    esperar(page, espera)
    campo_nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if campo_nome.count():
        if "auditar" in globals():
            auditar(page, "00_quem_esta_usando")
        campo_nome.first.fill("Robo")
        page.locator("button:visible", has_text="Entrar").first.click()
        esperar(page, 3000)

def tocar(page, sel):
    box = page.locator(sel).first.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def tela(page):
    t = page.locator(".cx-titulo").first
    if t.count():
        return t.inner_text()
    return "INICIO" if page.locator(".hm-marca").count() else "?"


def conferir(page, esperado, passo):
    atual = tela(page)
    ok = (atual == esperado) and page.url.startswith(URL)
    print(("OK   " if ok else "FALHA"), passo, "->", atual, "|", page.url)
    if not ok:
        falhas.append(passo)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices["Pixel 5"])
    page = ctx.new_page()
    abrir(page, 6000)
    conferir(page, "INICIO", "abriu")
    tocar(page, ".st-key-hm_rel .hm-card")
    conferir(page, "Relatório de cobranças", "tocou relatório")
    page.go_back()
    esperar(page)
    conferir(page, "INICIO", "voltar do relatório")
    tocar(page, ".st-key-hm_nova .hm-card")
    tocar(page, ".st-key-hm_pix .hm-card")
    conferir(page, "Cobrança Pix", "foi até o Pix")
    page.go_back()
    esperar(page)
    conferir(page, "Nova cobrança", "voltar do Pix")
    page.go_back()
    esperar(page)
    conferir(page, "INICIO", "voltar da Nova")
    alt = page.evaluate("Math.max(...[...document.querySelectorAll('iframe')].map(f => f.getBoundingClientRect().height), 0)")
    print("altura do iframe na tela:", alt)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

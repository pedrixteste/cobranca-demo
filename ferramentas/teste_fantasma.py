"""
Depois de escolher o nome, a tela "Quem está usando?" não pode deixar pedaços
apagados na tela inicial. Roda contra a demonstração local (porta 8612).
"""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"


def esperar(page, ms):
    page.wait_for_timeout(ms)
    for _ in range(40):
        if not page.locator("[data-testid=stStatusWidget]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)


def sobras(page):
    return {"botao Entrar": page.locator("button:visible", has_text="Entrar").count(),
            "campo de nome": page.locator("input[aria-label='Seu nome']:visible, input[aria-label='Outra pessoa']:visible").count(),
            "titulo Quem está usando": page.get_by_text("Quem está usando?").count(),
            "tela inicial": page.locator(".st-key-hm_nova").count()}


falhou = False
with sync_playwright() as p:
    b = p.chromium.launch()
    for rodada, modo in enumerate(("digitando um nome novo", "tocando num nome que já existe"), start=1):
        page = b.new_context(**p.devices["Pixel 5"]).new_page()
        page.goto(URL); esperar(page, 7000)
        if modo.startswith("digitando"):
            page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']").first.fill(f"Fantasma{rodada}")
            page.locator("button:visible", has_text="Entrar").first.click()
        else:
            page.locator("button:visible", has_text="Fantasma1").first.click()
        esperar(page, 5000)
        s = sobras(page)
        ok = s["tela inicial"] == 1 and s["botao Entrar"] == 0 and s["campo de nome"] == 0 and s["titulo Quem está usando"] == 0
        print(("OK    " if ok else "FALHA ") + f"entrar {modo}: {s}")
        falhou = falhou or not ok
    b.close()
print("\nTUDO CERTO" if not falhou else "\nSOBROU PEDAÇO DA TELA DE NOME")
sys.exit(1 if falhou else 0)

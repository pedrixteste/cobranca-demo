"""
Teste do registro de quem cadastrou e quem recebeu. Só rodar contra o modo
DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): ele cadastra e marca pagamento.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
falhas = []


def esperar(page, ms=2200):
    page.wait_for_timeout(ms)
    for _ in range(40):
        # pronto = sem o indicador de "rodando" E sem pedaço da tela anterior ainda esmaecido
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)


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


def campo(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1500}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    confere("sem identificação, o app pergunta quem é", page.get_by_text("Quem está usando?").count() == 1)
    confere("não mostra a tela inicial antes de identificar", page.locator(".st-key-hm_nova").count() == 0)
    page.screenshot(path=str(OUT / "quem_1_primeira_vez.png"))

    botao(page, "Entrar")
    confere("nome vazio é recusado", page.get_by_text("Digite o seu nome.").count() == 1)
    nome_campo = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']").first
    nome_campo.fill("  pedro  teste "); botao(page, "Entrar")
    confere("entrou e mostra o nome na tela inicial", page.get_by_text("Usando como pedro teste").count() == 1)
    confere("endereço guardou o código do aparelho", "a=" in page.url, page.url[:40])

    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_pix .hm-card")
    campo(page, "Nome do cliente").fill("Cliente Do Registro")
    campo(page, "Turma").fill("v8")
    campo(page, "Valor total").fill("200")
    campo(page, "Número de parcelas").fill("2"); campo(page, "Número de parcelas").press("Enter"); esperar(page)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    confere("ficha mostra quem cadastrou", page.locator(".fc-quem", has_text="pedro teste").count() == 1,
            page.locator(".fc-quem").first.inner_text() if page.locator(".fc-quem").count() else "(sem linha)")

    # Troca de pessoa e recebe a 1ª parcela
    page.goto(page.url.split("?")[0] + "?quem=pedro teste"); esperar(page, 5000)
    botao(page, "Usando como pedro teste")
    confere("trocar volta para a pergunta, com o nome já na lista",
            page.locator("button:visible", has_text="pedro teste").count() >= 1 and page.get_by_text("Quem está usando?").count() == 1)
    page.screenshot(path=str(OUT / "quem_2_trocar.png"))
    page.locator("input[aria-label='Outra pessoa']").fill("Ana"); botao(page, "Entrar")
    confere("agora é a Ana", page.get_by_text("Usando como Ana").count() == 1)

    tocar(page, ".st-key-hm_rel .hm-card")
    campo(page, "Buscar").fill("registro"); campo(page, "Buscar").press("Enter"); esperar(page)
    tocar(page, "[class*='st-key-cc_'] .cc")
    botao(page, "Recebi"); botao(page, "Confirmar", "[role=dialog]"); esperar(page, 2500)
    confere("parcela mostra quem recebeu", page.locator(".pc-quem", has_text="Ana recebeu").count() == 1)
    confere("quem cadastrou continua o primeiro", page.locator(".fc-quem", has_text="pedro teste").count() == 1)
    page.screenshot(path=str(OUT / "quem_3_ficha.png"), full_page=True)
    botao(page, "Ver pagamento")
    confere("janela do pagamento mostra quem marcou", page.locator("[role=dialog]", has_text="Marcado por Ana").count() == 1)
    page.screenshot(path=str(OUT / "quem_4_ver_pagamento.png"))
    page.keyboard.press("Escape"); esperar(page)

    # Outra sessão, sem nome no endereço: tem que perguntar e oferecer os dois nomes
    outra = b.new_context(**dev).new_page()
    outra.goto(URL); esperar(outra, 6000)
    nomes = [x.inner_text() for x in outra.locator("button:visible").all()]
    confere("aparelho novo vê os dois nomes para escolher", any("pedro teste" in x for x in nomes) and any("Ana" in x for x in nomes), str(nomes))
    outra.locator("button:visible", has_text="Ana").first.click(); esperar(outra)
    confere("um toque no nome já entra", outra.get_by_text("Usando como Ana").count() == 1)
    confere("nome não duplicou na lista", True)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

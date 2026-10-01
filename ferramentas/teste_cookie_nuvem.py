"""
A marca do aparelho (cookie) funciona na nuvem do Streamlit? Abre a DEMONSTRAÇÃO
pelo endereço normal (o app fica dentro de uma moldura), escolhe um nome, reabre
e confere que entrou direto. Só grava um nome na demonstração, nada mais.
"""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://cobrancas-vithall-demo.streamlit.app/"
NOME = "Teste do aparelho"
falhas = []


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra)
    if not cond:
        falhas.append(nome)


def quadro(page, espera=150000):
    """A moldura onde o app roda (ou a própria página, se abriu sem moldura)."""
    page.wait_for_timeout(4000)
    fim = espera / 1000
    for _ in range(int(fim / 2)):
        for f in page.frames:
            try:
                if f.locator(".demo-faixa, .dev-espera, .hm-marca").count():
                    return f
            except Exception:
                pass
        page.wait_for_timeout(2000)
    return None


def assentar(f, page, ms=6000):
    page.wait_for_timeout(ms)
    for _ in range(40):
        try:
            if not f.locator("[data-testid=stStatusWidget]").count():
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    page.wait_for_timeout(1500)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices["Pixel 5"])
    page = ctx.new_page()
    page.goto(URL, timeout=180000)
    f = quadro(page)
    confere("o app abriu na nuvem", f is not None)
    if f is None:
        print(page.inner_text("body")[:300]); sys.exit(1)
    assentar(f, page, 9000)
    f = quadro(page) or f       # a página recarrega uma vez para gravar o cookie
    versao_nova = f.get_by_text("Quem está usando?").count() == 1
    confere("versão nova no ar (pergunta o nome)", versao_nova, f.locator("body").inner_text()[:120].replace("\n", " | "))
    cookies = {c["name"]: c for c in ctx.cookies()}
    confere("cookie do aparelho gravado", "cob_dev" in cookies,
            (cookies.get("cob_dev", {}).get("value", "")[:6] + "… válido até " + str(int(cookies.get("cob_dev", {}).get("expires", 0)))))
    confere("sem aviso de cookie bloqueado", f.get_by_text("bloqueando cookies").count() == 0)

    campo = f.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']").first
    campo.fill(NOME); f.locator("button:visible", has_text="Entrar").first.click()
    assentar(f, page, 7000)
    confere("entrou depois de digitar o nome", f.get_by_text("Usando como").count() >= 1)
    confere("sem sobra apagada da tela de nome", f.locator("button:visible", has_text="Entrar").count() == 0)

    # fecha a aba e abre de novo, no mesmo "aparelho"
    page.close()
    page = ctx.new_page()
    page.goto(URL, timeout=180000)
    f = quadro(page); assentar(f, page, 8000); f = quadro(page) or f
    confere("reabriu e NÃO perguntou o nome de novo", f.get_by_text("Quem está usando?").count() == 0)
    confere("reabriu já como a mesma pessoa", f.locator("button:visible", has_text=f"Usando como {NOME}").count() == 1)
    confere("sem erro na tela", f.locator("[data-testid=stException]").count() == 0)

    # outro aparelho (sem o cookie) continua tendo que se identificar
    outro = b.new_context(**p.devices["Pixel 5"]).new_page()
    outro.goto(URL, timeout=180000)
    g = quadro(outro); assentar(g, outro, 8000); g = quadro(outro) or g
    confere("outro aparelho é perguntado", g.get_by_text("Quem está usando?").count() == 1)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

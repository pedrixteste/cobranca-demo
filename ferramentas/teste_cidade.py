"""
Teste do campo Cidade (texto livre, abaixo da Turma). Só contra a DEMONSTRAÇÃO local (porta 8612).
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


def inicio(page):
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Cidade"); botao(page, "Entrar")


def cadastrar_pix(page, cliente, turma, cidade):
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_pix .hm-card")
    por(page, "Nome do cliente", cliente); por(page, "Turma", turma)
    dica = page.locator(".cx-dica").first.inner_text() if page.locator(".cx-dica").count() else ""
    if cidade is not None:
        por(page, "Cidade da turma", cidade)
    por(page, "Valor total", "300"); por(page, "Número de parcelas", "3")
    return dica


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1500}
    page = b.new_context(**dev).new_page()
    inicio(page)
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    # 1. cadastro com cidade
    dica = cadastrar_pix(page, "Larissa Cidade", "l700", "  Lajeado  ")
    ordem = [x.get_attribute("aria-label") for x in page.locator(".st-key-sec_px1 input").all()]
    confere("campo Cidade fica logo abaixo da Turma", ordem == ["Nome do cliente", "Turma", "Cidade da turma"], str(ordem))
    confere("turma nova não tem sugestão de cidade", dica == "", dica)
    page.screenshot(path=str(OUT / "cidade_1_form.png"))
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    sub = page.locator(".cx-sub").first.inner_text()
    confere("ficha mostra a cidade", "L700 · LORAP · Lajeado" in sub, sub)

    # 2. mesma turma de novo: sugere a cidade já usada; cadastro SEM cidade é aceito
    inicio(page)
    dica = cadastrar_pix(page, "Marcos Sem Cidade", "L0700", None)
    confere("turma repetida sugere a cidade já usada", "Lajeado" in dica, dica)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    sub = page.locator(".cx-sub").first.inner_text()
    confere("cidade é opcional (salvou sem)", "Marcos" in page.locator(".cx-titulo").first.inner_text() and "Lajeado" not in sub, sub)

    # 3. editar: escrever qualquer coisa
    botao(page, "Editar dados")
    por(page, "Cidade da turma", "SCS", "[role=dialog]"); botao(page, "Salvar", "[role=dialog]"); esperar(page, 2500)
    sub = page.locator(".cx-sub").first.inner_text()
    confere("Editar dados troca a cidade", "L700 · LORAP · SCS" in sub, sub)

    # 4. relatório: aparece no cartão e a busca acha
    inicio(page); tocar(page, ".st-key-hm_rel .hm-card")
    linhas = [x.inner_text() for x in page.locator(".cc-turma").all()]
    confere("relatório mostra a cidade no cartão", any("LAJEADO" in x.upper() for x in linhas) and any("SCS" in x.upper() for x in linhas), str(linhas))
    por(page, "Buscar", "lajeado")
    confere("busca por cidade", page.locator(".cc").count() == 1 and page.locator(".cc", has_text="Larissa").count() == 1)
    por(page, "Buscar", "scs")
    confere("busca pela outra cidade", page.locator(".cc").count() == 1 and page.locator(".cc", has_text="Marcos").count() == 1)
    por(page, "Buscar", "")
    page.screenshot(path=str(OUT / "cidade_2_relatorio.png"))
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

"""
Teste do telefone do cliente, opcional (pedido 26/10): cadastro, ficha com Ligar e WhatsApp,
sugestão do telefone de outra cobrança, Editar dados e busca.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612).
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


def nova(page, chave):
    for _ in range(4):
        if page.locator(".st-key-hm_nova").count():
            break
        botao(page, "Voltar")
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, f".st-key-{chave} .hm-card")


def links(page):
    return {a.inner_text().strip(): a.get_attribute("href")
            for a in page.locator(".st-key-fc_contato a").all()}


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Telefone"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")
    hoje = date.today()

    # ── cadastro Pix com telefone ──
    nova(page, "hm_pix")
    campo = page.locator("input[aria-label='Telefone (opcional)']")
    confere("cadastro tem o campo 'Telefone (opcional)'", campo.count() == 1)
    confere("o campo abre o teclado de telefone", campo.first.get_attribute("inputmode") == "tel",
            str(campo.first.get_attribute("inputmode")))
    por(page, "Nome do cliente", "Telefone Teste Um")
    por(page, "Telefone (opcional)", "5199")
    confere("telefone incompleto avisa embaixo do campo",
            page.locator(".cx-erro", has_text="Telefone incompleto").count() == 1)
    por(page, "Telefone (opcional)", "51 9 9999 8888")
    confere("telefone completo tira o aviso", page.locator(".cx-erro", has_text="Telefone incompleto").count() == 0)
    por(page, "Turma", "l345")
    por(page, "Valor total", "1200")
    por(page, "Número de parcelas", "3")
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    contato = page.locator(".st-key-fc_contato")
    confere("ficha mostra o telefone já formatado", contato.count() == 1 and "(51) 99999-8888" in contato.inner_text(),
            contato.inner_text().replace("\n", " | ") if contato.count() else "sem contato")
    l = links(page)
    confere("botão Ligar com o número", any(h == "tel:+5551999998888" for h in l.values()), str(l))
    confere("botão WhatsApp com o número", any(h == "https://wa.me/5551999998888" for h in l.values()))
    page.screenshot(path=str(OUT / "telefone_1_ficha.png"), full_page=False)

    # ── Editar dados troca o telefone ──
    botao(page, "Editar dados")
    dlg = "[role=dialog]"
    confere("Editar dados já traz o telefone",
            page.locator(f"{dlg} input[aria-label='Telefone (opcional)']").input_value() == "(51) 99999-8888")
    por(page, "Telefone (opcional)", "(51) 3333-4444", dlg)
    botao(page, "Salvar", dlg); esperar(page, 2000)
    confere("ficha mostra o telefone novo (fixo)", "(51) 3333-4444" in page.locator(".st-key-fc_contato").inner_text())

    # ── outra cobrança do mesmo cliente: sugere o telefone ──
    botao(page, "Voltar")
    nova(page, "hm_cartao")
    por(page, "Nome do cliente", "telefone teste um")
    confere("sugere o telefone da outra cobrança do cliente",
            page.locator(".cx-dica", has_text="(51) 3333-4444").count() == 1)
    botao(page, "Usar esse telefone")
    confere("'Usar esse telefone' preenche o campo",
            page.locator("input[aria-label='Telefone (opcional)']").input_value() == "(51) 3333-4444")
    confere("com o campo preenchido a sugestão some", page.locator(".cx-dica", has_text="(51) 3333-4444").count() == 0)

    # ── sem telefone: nada aparece na ficha ──
    nova(page, "hm_pix")
    por(page, "Nome do cliente", "Telefone Teste Dois")
    por(page, "Turma", "v12"); por(page, "Valor total", "300"); por(page, "Número de parcelas", "1")
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    confere("cobrança sem telefone salva sem erro e sem caixa de contato",
            page.locator(".st-key-fc_contato").count() == 0 and "TELEFONE TESTE DOIS" in page.locator("body").inner_text())

    # ── permuta com telefone ──
    nova(page, "hm_permuta")
    por(page, "Nome do cliente", "Telefone Permuta")
    por(page, "Telefone (opcional)", "51988887777")
    por(page, "Turma", "l600"); por(page, "Valor da permuta", "2000")
    botao(page, "Salvar permuta"); esperar(page, 2500)
    confere("ficha da permuta também mostra o telefone",
            "(51) 98888-7777" in (page.locator(".st-key-fc_contato").inner_text() if page.locator(".st-key-fc_contato").count() else ""))

    # ── busca no relatório pelo número ──
    botao(page, "Voltar")
    for _ in range(3):
        if page.locator(".st-key-tq_rel").count():
            break
        botao(page, "Voltar")
    page.locator(".st-key-tq_rel button").first.click(); esperar(page)
    por(page, "Buscar", "33334444")
    nomes = [x.inner_text().split("\n")[0] for x in page.locator(".cc").all()]
    confere("busca pelo número acha a cobrança", len(nomes) == 1 and "TELEFONE TESTE UM" in nomes[0].upper(), str(nomes))
    b.close()

print("\nFALHAS:" if falhas else "\nTUDO OK", *falhas, sep="\n- " if falhas else "")
sys.exit(1 if falhas else 0)

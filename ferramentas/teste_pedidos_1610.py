"""
Teste dos pedidos de 16/10/2026, pelas telas:
  1. valor com ponto do milhar e ",00" aparecendo ENQUANTO digita (tecla por tecla);
  2. tudo que se digita em MAIÚSCULA (na tela e gravado);
  3. mais de uma turma na mesma cobrança (adicionar, tirar, editar);
  4. cobrança de datas antigas: parcela com data que já passou entra como já paga.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): cadastra cobranças.
"""
import sys
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
DLG = "[role=dialog]"
falhas = []


def esperar(page, ms=2000):
    page.wait_for_timeout(ms)
    for _ in range(40):
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


def campo(page, rotulo, dentro=""):
    return page.locator(f"{dentro} input[aria-label='{rotulo}']").first


def por(page, rotulo, valor, dentro=""):
    c = campo(page, rotulo, dentro)
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def digitar(page, rotulo, teclas, dentro=""):
    """Digita tecla por tecla, como no celular (sem Enter)."""
    c = campo(page, rotulo, dentro)
    c.click(); page.wait_for_timeout(150)
    page.keyboard.type(teclas, delay=90)
    page.wait_for_timeout(300)
    return c.input_value()


def por_data(page, indice, d, dentro=""):
    caixa = page.locator(f"{dentro} [data-testid=stDateInput]").nth(indice)
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1500)


def textos(page, sel):
    return [x.inner_text().replace("\n", " ") for x in page.locator(sel).all()]


def inicio(page):
    """Volta à tela inicial pelo botão Voltar (recarregar a página trocaria o aparelho de nome)."""
    for _ in range(5):
        if page.locator(".st-key-hm_nova").count():
            return
        botao(page, "Voltar")
    page.screenshot(path=str(OUT / "pedidos_erro_inicio.png"), full_page=True)


def nova(page, cartao_tipo):
    inicio(page)
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, f".st-key-hm_{cartao_tipo} .hm-card")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1900}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste 16/10"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")
    hoje = date.today()

    # ── 1. valor formatado enquanto digita ──
    nova(page, "pix")
    c_total = campo(page, "Valor total")
    confere("campo de valor abre o teclado de números", c_total.get_attribute("inputmode") == "decimal")
    v = digitar(page, "Valor total", "1")
    confere("digitou 1: já aparece 1,00", v == "1,00", v)
    page.keyboard.type("500", delay=90); page.wait_for_timeout(300)
    v = c_total.input_value()
    confere("digitou 1500: aparece 1.500,00", v == "1.500,00", v)
    page.keyboard.type("0", delay=90); page.wait_for_timeout(300)
    v = c_total.input_value()
    confere("mais um 0: 15.000,00 (o número continua antes da vírgula)", v == "15.000,00", v)
    page.keyboard.type(",", delay=90); page.wait_for_timeout(200)
    page.keyboard.type("5", delay=90); page.wait_for_timeout(300)
    v = c_total.input_value()
    confere("vírgula pula para os centavos: 15.000,50", v == "15.000,50", v)
    page.keyboard.type("5", delay=90); page.wait_for_timeout(300)
    v = c_total.input_value()
    confere("segundo centavo: 15.000,55", v == "15.000,55", v)
    page.keyboard.press("Enter"); esperar(page, 900)
    v = digitar(page, "Valor de entrada", "2000.5")
    confere("ponto também pula para os centavos: 2.000,50", v == "2.000,50", v)
    page.keyboard.press("Enter"); esperar(page, 900)
    c = campo(page, "Valor de entrada")
    c.click(); page.keyboard.press("Control+A"); page.keyboard.press("Backspace"); page.wait_for_timeout(300)
    confere("apagar tudo deixa o campo vazio (vazio = sem entrada)", c.input_value() == "", c.input_value())
    v = digitar(page, "Valor de entrada", "1234567")
    confere("milhão: 1.234.567,00", v == "1.234.567,00", v)
    c.click(); page.keyboard.press("Control+A"); page.keyboard.press("Backspace")
    v = digitar(page, "Valor de entrada", "2000")
    page.keyboard.press("Enter"); esperar(page, 900)
    por(page, "Número de parcelas", "2")
    resumo = page.locator(".st-key-sec_px4").inner_text().replace("\n", " | ")
    confere("o app entendeu os valores (total 15.000,55 = entrada 2.000 + 2 parcelas somando 13.000,55)",
            "Entrada de R$ 2.000,00" in resumo and "R$ 13.000,55" in resumo and "Fecha certinho" in resumo, resumo[:200])
    page.screenshot(path=str(OUT / "pedidos_1_valores.png"), full_page=True)

    # ── 2 e 3. maiúscula e várias turmas ──
    v = digitar(page, "Nome do cliente", "maria joão teste")
    estilo = campo(page, "Nome do cliente").evaluate("e => getComputedStyle(e).textTransform")
    confere("nome aparece em maiúscula enquanto digita", estilo == "uppercase", estilo)
    confere("teclado do celular abre em maiúscula",
            campo(page, "Nome do cliente").get_attribute("autocapitalize") == "characters")
    page.keyboard.press("Enter"); esperar(page, 900)
    por(page, "Turma", "l345")
    botao(page, "Adicionar outra turma")
    confere("apareceu o campo da 2ª turma", campo(page, "2ª turma").count() == 1)
    por(page, "2ª turma", "v12")
    botao(page, "Adicionar outra turma")
    por(page, "3ª turma", "i7")
    infos = page.locator(".st-key-sec_px1").inner_text()
    confere("cada turma mostra o treinamento", "L345 · LORAP" in infos and "V12 · Vendas" in infos and "I7 · Impacto" in infos,
            infos.replace("\n", " | ")[:200])
    page.locator(".st-key-px_tirar_1 button:visible").first.click(); esperar(page)
    confere("tirar a 2ª: a 3ª sobe para o lugar dela",
            campo(page, "2ª turma").input_value().lower() == "i7" and campo(page, "3ª turma").count() == 0,
            campo(page, "2ª turma").input_value())
    por(page, "2ª turma", "x9")
    confere("turma errada avisa", page.locator(".st-key-sec_px1 .cx-erro").count() == 1)
    por(page, "2ª turma", "i7")
    por(page, "Cidade da turma", "lajeado")
    por(page, "Observação (opcional)", "pago parte em permuta")
    page.screenshot(path=str(OUT / "pedidos_2_turmas.png"), full_page=True)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    titulo = page.locator(".cx-titulo").first.inner_text()
    sub = page.locator(".cx-sub").first.inner_text()
    confere("nome gravado em MAIÚSCULA", titulo == "MARIA JOÃO TESTE", titulo)
    confere("ficha com as duas turmas e a cidade em maiúscula", "L345 + I7" in sub and "LORAP + Impacto" in sub
            and "LAJEADO" in sub, sub)
    confere("observação gravada em maiúscula", page.locator(".ob", has_text="PAGO PARTE EM PERMUTA").count() == 1)
    confere("valor total certo (15.000,55)", "15.000,55" in page.locator(".fc").inner_text().replace("\n", " ")
            or "R$ 0,00" in page.locator(".fc").inner_text())
    page.screenshot(path=str(OUT / "pedidos_3_ficha.png"), full_page=True)

    botao(page, "Editar dados")
    por(page, "Turma", "L345, V12, I7", DLG)
    confere("editar: aceita várias turmas separadas por vírgula",
            page.locator(DLG, has_text="V12 · Vendas").count() == 1)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    sub = page.locator(".cx-sub").first.inner_text()
    confere("editar gravou as três turmas", "L345 + V12 + I7" in sub, sub)

    # relatório: a cobrança aparece pela turma e pelo treinamento de qualquer uma
    inicio(page)
    tocar(page, ".st-key-hm_rel .hm-card")
    por(page, "Buscar", "v12")
    confere("busca pela 2ª turma acha a cobrança", page.locator(".cc", has_text="MARIA JOÃO TESTE").count() == 1)
    por(page, "Buscar", "")

    # ── 4. cobrança antiga (Pix): parcelas que já passaram entram como já pagas ──
    nova(page, "pix")
    por(page, "Nome do cliente", "Cliente Antigo")
    por(page, "Turma", "p3")
    por(page, "Valor total", "4000")
    por(page, "Valor de entrada", "1000")
    por_data(page, 0, date(2025, 3, 15))
    por(page, "Número de parcelas", "3")
    por_data(page, 1, date(2025, 4, 15))
    caixas = page.locator("[data-testid=stCheckbox]", has_text="já paga")
    confere("as 3 parcelas com data que já passou ganham a caixa 'já paga', marcadas",
            caixas.count() == 3 and all(x.locator("input").is_checked() for x in caixas.all()), str(caixas.count()))
    caixas.nth(2).locator("label").first.click(); esperar(page, 1200)
    resumo = page.locator(".st-key-sec_px4").inner_text().replace("\n", " | ")
    confere("resumo: entrada antiga paga e 2 parcelas já pagas", "(paga)" in resumo and "2 parcelas já pagas" in resumo,
            resumo[:250])
    page.screenshot(path=str(OUT / "pedidos_4_antiga.png"), full_page=True)
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    carimbos = textos(page, ".pc-carimbo")
    confere("ficha: entrada + 2 parcelas pagas, na data delas", len(carimbos) == 3 and "15/04/25" in carimbos[1]
            and "15/05/25" in carimbos[2], str(carimbos))
    confere("a parcela desmarcada ficou em aberto (atrasada)", page.locator(".pc.c-atraso").count() == 1)

    # cartão antigo: a passada que já passou entra como passada
    nova(page, "cartao")
    por(page, "Nome do cliente", "Cartão Antigo")
    por(page, "Turma", "v20")
    por(page, "Valor total", "2000")
    por(page, "Quantas vezes você vai passar o cartão?", "1")
    por_data(page, 0, date(2025, 6, 10))
    cx = page.locator("[data-testid=stCheckbox]", has_text="Já passou")
    confere("cartão: data antiga ganha 'Já passou', marcada", cx.count() == 1 and cx.locator("input").is_checked())
    botao(page, "Salvar cobrança"); esperar(page, 2500)
    confere("cartão antigo salvo como PASSOU", any(t.startswith("PASSOU") for t in textos(page, ".pc-carimbo"))
            and page.locator(".pc.c-atraso").count() == 0)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

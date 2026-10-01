"""
Teste das observações, do parcelamento no cartão e do relatório compacto.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): cadastra e marca pagamento.
"""
import sys
from datetime import date, timedelta
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


def campo(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']")


def por(page, rotulo, valor, dentro=""):
    c = page.locator(f"{dentro} input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def por_data(page, indice: int, d: date):
    """Campo de data do Streamlit (o N-ésimo da tela): foca o pedaço do DIA e digita dia, mês e ano."""
    caixa = page.locator("[data-testid=stDateInput]").nth(indice)
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1500)


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Obs"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    hoje = date.today()
    d1, d2 = hoje + timedelta(days=5), hoje + timedelta(days=240)

    # ── cadastro no cartão: 2 passadas, cada uma parcelada ──
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_cartao .hm-card")
    por(page, "Nome do cliente", "Larissa Teste Cartão")
    por(page, "Turma", "l400")
    por(page, "Valor total", "12000")
    por(page, "Quantas vezes você vai passar o cartão?", "2")
    por_data(page, 0, d1); por_data(page, 1, d2)
    por(page, "Valor 1", "8000"); por(page, "Valor 2", "4000")
    por(page, "Parcelado em quantas vezes (1ª passada)", "8")
    por(page, "Parcelado em quantas vezes (2ª passada)", "4")
    resumo_txt = page.locator(".st-key-sec_ct4").inner_text()
    confere("resumo mostra 8x de R$ 1.000,00", "8x de R$ 1.000,00" in resumo_txt, resumo_txt.replace("\n", " | ")[:160])
    confere("resumo mostra 4x de R$ 1.000,00", "4x de R$ 1.000,00" in resumo_txt)
    confere("fecha com o total", "Fecha certinho" in resumo_txt)
    por(page, "Observação (opcional)", "cartão do marido")
    page.screenshot(path=str(OUT / "cartao_1_form.png"), full_page=True)
    botao(page, "Salvar cobrança"); esperar(page, 2500)

    # ── ficha ──
    rot = [x.inner_text().replace("\n", " ") for x in page.locator(".pc-rot").all()]
    confere("ficha: 1ª passada em 8x", any("Cartão 1 de 2" in r and "8x de R$ 1.000,00" in r for r in rot), str(rot))
    confere("ficha: 2ª passada em 4x", any("Cartão 2 de 2" in r and "4x de R$ 1.000,00" in r for r in rot))
    confere("ficha mostra a observação do cadastro", page.locator(".ob", has_text="cartão do marido").count() == 1)

    botao(page, "Passou")
    dlg = "[role=dialog]"
    confere("janela Passou já vem com 8 vezes", page.locator(f"{dlg} input[aria-label='Passou em quantas vezes']").input_value() == "8")
    por(page, "Passou em quantas vezes", "10", dlg)
    confere("janela recalcula para 10x de R$ 800,00", page.locator(dlg, has_text="10x de R$ 800,00").count() == 1)
    por(page, "Observação (opcional)", "limite não deu em 8, passou em 10", dlg)
    botao(page, "Confirmar", dlg); esperar(page, 2500)
    rot = [x.inner_text().replace("\n", " ") for x in page.locator(".pc-rot").all()]
    confere("parcela ficou em 10x de R$ 800,00", any("10x de R$ 800,00" in r for r in rot), str(rot))
    confere("parcela mostra a observação", page.locator(".pc-obs", has_text="passou em 10").count() == 1)
    confere("parcela mostra quem passou", page.locator(".pc-quem", has_text="passou").count() == 1)

    botao(page, "Editar observação")
    area = page.locator(f"{dlg} textarea").first
    area.fill("cartão do marido\nparte foi PERMUTA de serviço"); botao(page, "Salvar", dlg); esperar(page, 2000)
    confere("observação da cobrança editada", page.locator(".ob", has_text="PERMUTA").count() == 1)
    page.screenshot(path=str(OUT / "cartao_2_ficha.png"), full_page=True)

    botao(page, "Ver pagamento")
    confere("Ver pagamento traz a observação da parcela",
            page.locator(f"{dlg} input[aria-label='Observação']").input_value().startswith("limite"))
    page.keyboard.press("Escape"); esperar(page)

    # ── relatório compacto, etiqueta, filtro e busca ──
    botao(page, "Voltar"); esperar(page)
    if not page.locator(".st-key-hm_rel").count():
        botao(page, "Voltar")
    tocar(page, ".st-key-hm_rel .hm-card")
    alturas = [round(x.bounding_box()["height"]) for x in page.locator(".cc").all()]
    confere("cartões do relatório compactos (até 80 px cada)", alturas and max(alturas) <= 80, str(alturas))
    confere("cobrança com observação tem a etiqueta 'obs'",
            page.locator(".cc", has_text="Larissa Teste Cartão").locator(".cc-nota").count() == 1)
    total = page.locator(".cc").count()
    page.screenshot(path=str(OUT / "relatorio_compacto.png"), full_page=True)
    por(page, "Buscar", "permuta")
    confere("busca por palavra da observação acha a cobrança",
            page.locator(".cc").count() == 1 and page.locator(".cc", has_text="Larissa").count() == 1)
    por(page, "Buscar", "")
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Com observação").first.click(); esperar(page)
    confere("filtro 'Com observação'", page.locator(".cc").count() == 1)
    page.locator("[data-testid=stExpander] button", has_text="Sem observação").first.click(); esperar(page)
    confere("filtro 'Sem observação'", page.locator(".cc").count() == total - 1, f"{page.locator('.cc').count()} de {total}")
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

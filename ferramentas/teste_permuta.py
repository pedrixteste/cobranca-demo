"""
Teste da PERMUTA (pedidos de 20/10/2026): treinamento trocado por produtos da empresa do cliente.
Cadastro com VÁRIOS valores (cada um com a sua data, botão "+") e retiradas (+ e X); ficha com o
total, o retirado e o saldo; valor novo / alterado; retirada nova / alterada / removida; aviso de
que o cliente já tem permuta; relatório.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): cadastra cobranças.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
DLG = "[role=dialog]"
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


def tocar(page, alvo):
    loc = page.locator(alvo).first if isinstance(alvo, str) else alvo.first
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def por(page, rotulo, valor, dentro=""):
    c = page.locator(f"{dentro} input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def por_data(page, dentro, d):
    """Campo de data (o primeiro dentro de `dentro`): foca o pedaço do DIA e digita dia, mês e ano."""
    caixa = page.locator(f"{dentro} [data-testid=stDateInput]").first
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1500)


def textos(page, sel):
    return [x.inner_text().replace("\n", " ") for x in page.locator(sel).all()]


def numeros(page):
    return page.locator(".fc-nums").inner_text().replace("\n", " ")


def inicio(page):
    for _ in range(6):
        if page.locator(".st-key-hm_nova").count():
            return
        botao(page, "Voltar")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 2400}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Permuta"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")
    hoje = date.today()
    antes = hoje - timedelta(days=60)

    # ── cadastro: dois valores (cada um com a data) e duas retiradas ──
    tocar(page, ".st-key-hm_nova .hm-card")
    confere("Nova cobrança tem o cartão 'Permuta'", page.locator(".st-key-hm_permuta .hm-card").count() == 1)
    tocar(page, ".st-key-hm_permuta .hm-card")
    por(page, "Nome do cliente", "Loja Teste Permuta")
    por(page, "Turma", "v30")
    por(page, "Valor da permuta", "3000", ".st-key-pm_cred_0")
    por_data(page, ".st-key-pm_cred_0", antes)
    botao(page, "Adicionar outro valor")
    confere("o '+' abre o 2º valor, com data própria",
            page.locator(".st-key-pm_cred_1 input[aria-label='Valor da permuta']").count() == 1
            and page.locator(".st-key-pm_cred_1 [data-testid=stDateInput]").count() == 1)
    por(page, "Valor da permuta", "2000", ".st-key-pm_cred_1")
    botao(page, "Adicionar outro valor")
    por(page, "Valor da permuta", "999", ".st-key-pm_cred_2")
    page.locator(".st-key-pm_tirar_cred_2 button:visible").first.click(); esperar(page)
    confere("o X tira o valor", page.locator(".st-key-pm_cred_2").count() == 0)
    sec = page.locator(".st-key-sec_pm2").inner_text()
    confere("mostra o total somando os valores (5.000)", "Total da permuta: R$ 5.000,00" in sec, sec[-60:])
    por(page, "Produto", "camisetas", ".st-key-pm_ret_0")
    por(page, "Quanto desconta", "1200", ".st-key-pm_ret_0")
    botao(page, "Adicionar retirada")
    por(page, "Produto", "bonés", ".st-key-pm_ret_1")
    por(page, "Quanto desconta", "9000", ".st-key-pm_ret_1")
    confere("avisa quando as retiradas passam do total",
            page.locator(".st-key-sec_pm3 .cx-passa", has_text="passam do total").count() == 1)
    por(page, "Quanto desconta", "800", ".st-key-pm_ret_1")
    saldo = page.locator(".st-key-sec_pm3").inner_text()
    confere("saldo = valores - retiradas (3.000)", "Saldo para retirar: R$ 3.000,00" in saldo, saldo[-80:])
    resumo = page.locator(".st-key-sec_pm4").inner_text().replace("\n", " | ")
    confere("resumo lista cada valor com a data e as retiradas",
            f"{antes.strftime('%d/%m/%Y')} · valor de R$ 3.000,00" in resumo and "valor de R$ 2.000,00" in resumo
            and "CAMISETAS" in resumo and "BONÉS" in resumo, resumo[:300])
    page.screenshot(path=str(OUT / "permuta_1_cadastro.png"), full_page=True)
    botao(page, "Salvar permuta"); esperar(page, 2500)

    # ── ficha ──
    confere("ficha diz que é Permuta", "Permuta" in page.locator(".cx-sub").first.inner_text())
    nums = numeros(page)
    confere("ficha: total 5.000, retirado 2.000, saldo 3.000",
            "R$ 5.000,00 Total da permuta" in nums and "R$ 2.000,00 Retirado" in nums and "R$ 3.000,00 Saldo" in nums, nums)
    cred = textos(page, ".pc.c-cred")
    confere("ficha: os dois valores, cada um com a data (o mais antigo primeiro)",
            len(cred) == 2 and "3.000,00" in cred[0] and "2.000,00" in cred[1], str(cred))
    confere("ficha: as duas retiradas", textos(page, ".pc.c-ret .pc-nome") == ["CAMISETAS", "BONÉS"],
            str(textos(page, ".pc.c-ret .pc-nome")))
    page.screenshot(path=str(OUT / "permuta_2_ficha.png"), full_page=True)

    # outro valor depois (a pessoa fechou mais uma permuta)
    botao(page, "Adicionar valor")
    por(page, "Valor da permuta", "1500", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    nums = numeros(page)
    confere("valor novo soma no total e no saldo (6.500 / 4.500)",
            "R$ 6.500,00 Total da permuta" in nums and "R$ 4.500,00 Saldo" in nums, nums)
    confere("agora são 3 valores", page.locator(".pc.c-cred").count() == 3)
    page.locator("[class*='st-key-pc_cr_']").first.locator("button:visible", has_text="Alterar").first.click()
    esperar(page)
    por(page, "Valor da permuta", "3500", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    nums = numeros(page)
    confere("alterar um valor muda o total (7.000) e o saldo (5.000)",
            "R$ 7.000,00 Total da permuta" in nums and "R$ 5.000,00 Saldo" in nums, nums)

    # retiradas: nova, alterada e removida
    botao(page, "Adicionar retirada")
    confere("janela da retirada mostra o saldo", page.locator(DLG, has_text="Saldo para retirar: R$ 5.000,00").count() == 1)
    por(page, "Produto", "brindes", DLG)
    por(page, "Quanto desconta do saldo", "1000", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    confere("retirada nova desconta do saldo (4.000)", "R$ 4.000,00 Saldo" in numeros(page), numeros(page))
    page.locator("[class*='st-key-pc_rt_']", has_text="BONÉS").locator("button:visible", has_text="Alterar").first.click()
    esperar(page)
    por(page, "Quanto desconta do saldo", "300", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    confere("alterar a retirada muda o saldo (4.500)", "R$ 4.500,00 Saldo" in numeros(page), numeros(page))
    page.locator("[class*='st-key-pc_rt_']", has_text="CAMISETAS").locator("button:visible", has_text="Alterar").first.click()
    esperar(page)
    botao(page, "Remover esta retirada", DLG)
    botao(page, "Sim, remover", DLG); esperar(page, 2500)
    confere("remover a retirada devolve ao saldo (5.700)",
            "R$ 5.700,00 Saldo" in numeros(page) and page.locator(".pc.c-ret").count() == 2, numeros(page))
    page.screenshot(path=str(OUT / "permuta_3_ficha_depois.png"), full_page=True)

    # ── o mesmo cliente de novo em Nova cobrança: avisa e leva à permuta dele ──
    inicio(page)
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_permuta .hm-card")
    por(page, "Nome do cliente", "loja teste permuta")
    confere("avisa que o cliente já tem permuta e explica o 'Adicionar valor'",
            page.locator(".cx-dica", has_text="Adicionar valor").count() == 1)
    botao(page, "Abrir a permuta de LOJA TESTE PERMUTA")
    confere("o botão abre a permuta dele", "R$ 5.700,00 Saldo" in numeros(page), numeros(page))

    # ── relatório ──
    inicio(page)
    tocar(page, ".st-key-hm_rel .hm-card")
    cards = [x.inner_text().replace("\n", " ") for x in page.locator(".cc").all() if x.locator(".tp-perm").count()]
    confere("relatório: 2 permutas (a do exemplo + a nova)", len(cards) == 2, str(len(cards)))
    confere("cartão da permuta mostra saldo e quanto já foi retirado do total",
            any("saldo R$ 5.700,00" in x and "Retirado R$ 1.300,00 de R$ 7.000,00" in x for x in cards), str(cards)[:300])
    rs = page.locator(".rs-perm").inner_text().replace("\n", " ")
    confere("topo: saldo das permutas separado do dinheiro", "Saldo para retirar" in rs and "2 permutas" in rs, rs)
    page.screenshot(path=str(OUT / "permuta_4_relatorio.png"), full_page=True)
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Permuta").first.click(); esperar(page)
    topo = page.locator(".rs").inner_text().replace("\n", " ")
    confere("filtro Permuta: só permutas, fora do Recebido/A receber",
            page.locator(".cc").count() == 2 and topo.count("R$0,00") == 3, topo)
    page.locator("[data-testid=stExpander] button", has_text="Permuta").first.click(); esperar(page)
    por(page, "Buscar", "brindes")
    confere("busca pelo produto retirado acha a permuta",
            page.locator(".cc").count() == 1 and page.locator(".cc", has_text="LOJA TESTE PERMUTA").count() == 1)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

"""
Teste da PERMUTA (pedido 20/10/2026): treinamento trocado por produtos da empresa do cliente.
Cadastro com retiradas (+ e X), ficha com saldo, retirada nova / alterada / removida, segunda
permuta do mesmo cliente e o relatório.
Só rodar contra o modo DEMONSTRAÇÃO (COBRANCA_DEMO=1, porta 8612): cadastra cobranças.
"""
import sys
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


def textos(page, sel):
    return [x.inner_text().replace("\n", " ") for x in page.locator(sel).all()]


def inicio(page):
    for _ in range(6):
        if page.locator(".st-key-hm_nova").count():
            return
        botao(page, "Voltar")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 2200}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Permuta"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    # ── cadastro ──
    tocar(page, ".st-key-hm_nova .hm-card")
    confere("Nova cobrança tem o cartão 'Permuta'", page.locator(".st-key-hm_permuta .hm-card").count() == 1)
    tocar(page, ".st-key-hm_permuta .hm-card")
    por(page, "Nome do cliente", "Loja Teste Permuta")
    por(page, "Turma", "v30")
    por(page, "Valor total da permuta", "5000")
    por(page, "Produto", "camisetas", ".st-key-pm_ret_0")
    por(page, "Quanto desconta", "1200", ".st-key-pm_ret_0")
    saldo = page.locator(".st-key-sec_pm3").inner_text()
    confere("mostra o saldo depois da retirada (3.800)", "Saldo para retirar: R$ 3.800,00" in saldo, saldo[-80:])
    botao(page, "Adicionar retirada")
    por(page, "Produto", "bonés", ".st-key-pm_ret_1")
    por(page, "Quanto desconta", "5000", ".st-key-pm_ret_1")
    confere("avisa quando as retiradas passam do total",
            page.locator(".st-key-sec_pm3 .cx-perigo", has_text="passam do total").count() == 1)
    por(page, "Quanto desconta", "800", ".st-key-pm_ret_1")
    botao(page, "Adicionar retirada")
    por(page, "Produto", "errado", ".st-key-pm_ret_2")
    page.locator(".st-key-pm_tirar_ret_2 button:visible").first.click(); esperar(page)
    confere("o X tira a retirada", page.locator(".st-key-pm_ret_2").count() == 0)
    saldo = page.locator(".st-key-sec_pm3").inner_text()
    confere("saldo com as duas retiradas (3.000)", "Saldo para retirar: R$ 3.000,00" in saldo, saldo[-80:])
    resumo = page.locator(".st-key-sec_pm4").inner_text().replace("\n", " | ")
    confere("resumo lista as retiradas", "CAMISETAS" in resumo and "BONÉS" in resumo and "R$ 5.000,00" in resumo,
            resumo[:200])
    page.screenshot(path=str(OUT / "permuta_1_cadastro.png"), full_page=True)
    botao(page, "Salvar permuta"); esperar(page, 2500)

    # ── ficha ──
    sub = page.locator(".cx-sub").first.inner_text()
    confere("ficha diz que é Permuta", "Permuta" in sub, sub)
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("ficha: total 5.000, retirado 2.000, saldo 3.000",
            "R$ 5.000,00 Total da permuta" in nums and "R$ 2.000,00 Retirado" in nums and "R$ 3.000,00 Saldo" in nums, nums)
    confere("ficha: etiqueta 'Com saldo'", page.locator(".fc .sit", has_text="Com saldo").count() == 1)
    confere("ficha: as duas retiradas", textos(page, ".pc.c-ret .pc-nome") == ["CAMISETAS", "BONÉS"],
            str(textos(page, ".pc.c-ret .pc-nome")))
    confere("ficha: diz quem registrou", page.locator(".pc.c-ret .pc-quem", has_text="registrou").count() == 2)
    confere("ficha: ainda sem outras permutas desse cliente", page.locator(".cx-dica", has_text="Nenhuma outra").count() == 1)
    page.screenshot(path=str(OUT / "permuta_2_ficha.png"), full_page=True)

    botao(page, "Adicionar retirada")
    confere("janela mostra o saldo", page.locator(DLG, has_text="Saldo para retirar: R$ 3.000,00").count() == 1)
    por(page, "Produto", "brindes", DLG)
    por(page, "Quanto desconta do saldo", "1000", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("retirada nova desconta do saldo (2.000)", "R$ 2.000,00 Saldo" in nums, nums)

    # alterar a dos bonés (800 → 300) e remover a das camisetas (1.200)
    page.locator("[class*='st-key-pc_rt_']", has_text="BONÉS").locator("button:visible", has_text="Alterar").first.click()
    esperar(page)
    por(page, "Quanto desconta do saldo", "300", DLG)
    botao(page, "Salvar", DLG); esperar(page, 2500)
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("alterar a retirada muda o saldo (2.500)", "R$ 2.500,00 Saldo" in nums, nums)
    page.locator("[class*='st-key-pc_rt_']", has_text="CAMISETAS").locator("button:visible", has_text="Alterar").first.click()
    esperar(page)
    botao(page, "Remover esta retirada", DLG)
    botao(page, "Sim, remover", DLG); esperar(page, 2500)
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("remover devolve ao saldo (3.700)", "R$ 3.700,00 Saldo" in nums and page.locator(".pc.c-ret").count() == 2, nums)

    # ── segunda permuta do mesmo cliente ──
    botao(page, "Nova permuta para LOJA TESTE PERMUTA")
    confere("nova permuta já vem com o nome do cliente",
            page.locator("input[aria-label='Nome do cliente']").input_value() == "LOJA TESTE PERMUTA")
    confere("avisa que o cliente já tem 1 permuta", page.locator(".cx-dica", has_text="já tem 1 permuta").count() == 1)
    por(page, "Turma", "i40")
    por(page, "Valor total da permuta", "2000")
    botao(page, "Salvar permuta"); esperar(page, 2500)
    confere("ficha da 2ª mostra a 1ª em 'Outras permutas'",
            page.locator(".cc", has_text="LOJA TESTE PERMUTA").count() == 1)
    confere("soma o saldo das duas (5.700)", page.locator(".cx-info", has_text="R$ 5.700,00").count() == 1)
    page.screenshot(path=str(OUT / "permuta_3_segunda.png"), full_page=True)
    tocar(page, ".cc")
    nums = page.locator(".fc-nums").inner_text().replace("\n", " ")
    confere("tocar abre a 1ª permuta", "R$ 3.700,00 Saldo" in nums, nums)

    # ── relatório ──
    inicio(page)
    tocar(page, ".st-key-hm_rel .hm-card")
    cards = [x.inner_text().replace("\n", " ") for x in page.locator(".cc").all() if x.locator(".tp-perm").count()]
    confere("relatório: 4 permutas com a etiqueta (2 do exemplo + 2 novas)", len(cards) == 4, str(len(cards)))
    confere("cartão da permuta mostra o saldo", any("saldo R$ 3.700,00" in x for x in cards), str(cards)[:300])
    rs = page.locator(".rs-perm").inner_text().replace("\n", " ")
    confere("topo: saldo das permutas separado do dinheiro", "Saldo para retirar" in rs and "4 permutas" in rs, rs)
    page.screenshot(path=str(OUT / "permuta_4_relatorio.png"), full_page=True)
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Permuta").first.click(); esperar(page)
    topo = page.locator(".rs").inner_text().replace("\n", " ")
    confere("filtro Permuta: só permutas, e elas não entram no Recebido/A receber",
            page.locator(".cc").count() == 4 and topo.count("R$0,00") == 3, topo)
    page.locator("[data-testid=stExpander] button", has_text="Permuta").first.click(); esperar(page)
    por(page, "Buscar", "brindes")
    confere("busca pelo produto retirado acha a permuta",
            page.locator(".cc").count() == 1 and page.locator(".cc", has_text="LOJA TESTE PERMUTA").count() == 1)
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

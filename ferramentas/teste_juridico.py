"""
Teste do Jurídico (pedido 03/11): botão na tela inicial, cobranças judiciais (cadastro, acordo à vista
e parcelado com valor e data por parcela, marcar/desfazer pago, editar, busca, excluir), protestos
(cadastro, marcar pago, desmarcar, excluir) e o Total na ficha da cobrança.
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
HOJE = date.today()


def esperar(page, ms=1500):
    page.wait_for_timeout(ms)
    for _ in range(40):
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)
    if page.locator("[data-testid=stException]").count():
        falhas.append("ERRO NA TELA: " + page.locator("[data-testid=stException]").first.inner_text()[:200])
    # Aviso amarelo do Streamlit (ex.: campo com valor padrão E valor guardado) também é defeito
    for a in page.locator("[data-testid=stAlert]").all():
        t = a.inner_text()
        if "Session State" in t or "widget" in t.lower():
            falhas.append("AVISO DO STREAMLIT: " + t[:200])


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra)
    if not cond:
        falhas.append(nome)


def tocar(page, sel):
    page.locator(sel).first.click(force=True)
    esperar(page)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def por(page, rotulo, valor, dentro=""):
    c = page.locator(f"{dentro} input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def valor_de(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']").first.input_value()


def por_data(page, rotulo, d, dentro=""):
    """Campo de data pelo rótulo: foca o pedaço do DIA e digita dia, mês e ano."""
    caixa = page.locator(f"{dentro} [data-testid=stDateInput]").filter(
        has=page.get_by_text(rotulo, exact=True)).first
    caixa.locator("[role=spinbutton]").first.focus()
    page.keyboard.type(d.strftime("%d%m%Y"), delay=60)
    page.keyboard.press("Tab"); page.keyboard.press("Tab")
    esperar(page, 1200)


def texto(page, sel="body"):
    loc = page.locator(sel)
    return loc.first.inner_text() if loc.count() else ""


def abrir_cartao(page, prefixo, nome):
    """Toca no cartão da lista (cc_j... ou cc_p...) que tem esse nome."""
    page.locator(f"[class*='st-key-{prefixo}']").filter(has_text=nome).first.locator("button").first.click(force=True)
    esperar(page)


def inicio(page):
    for _ in range(6):
        if page.locator(".st-key-hm_nova").count():
            return
        botao(page, "Voltar")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    nome = page.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']")
    if nome.count():
        nome.first.fill("Teste Juridico"); botao(page, "Entrar")
    if page.locator("button:visible", has_text="Recomeçar o exemplo do zero").count():
        botao(page, "Recomeçar o exemplo do zero")

    # ── tela inicial ──
    card = texto(page, ".st-key-hm_jur")
    confere("tela inicial tem o cartão Jurídico", "Jurídico" in card and "Cobranças judiciais e protestos" in card)
    confere("cartão mostra as contagens do exemplo",
            "1 acordo atrasado" in card and "2 na justiça" in card and "1 protesto em aberto" in card,
            card.replace("\n", " | "))
    tocar(page, ".st-key-tq_jur button")
    confere("Jurídico abre as duas opções",
            page.locator(".st-key-hm_jud").count() == 1 and page.locator(".st-key-hm_prot").count() == 1)
    page.screenshot(path=str(OUT / "juridico_1_opcoes.png"))

    # ── cobrança judicial nova: avisos do que falta ──
    tocar(page, ".st-key-tq_jud button")
    confere("lista mostra as 2 do exemplo, a atrasada primeiro",
            page.locator(".cc").count() == 2 and "LOJA PONTO CERTO" in page.locator(".cc").first.inner_text())
    botao(page, "Nova cobrança judicial")
    botao(page, "Salvar cobrança judicial")
    erro = texto(page, "[data-testid=stAlert]")
    confere("salvar vazio lista o que falta",
            all(t in erro for t in ["Falta o nome do cliente", "Falta a turma", "Falta escolher o objeto",
                                    "Falta o valor que está sendo cobrado"]), erro.replace("\n", " | "))

    # ── preenche: parcelado em 3, muda a 1ª ──
    por(page, "Nome do cliente", "Fulano Judicial")
    por(page, "Turma", "l00350")
    confere("turma escrita do jeito livre vira L350", "Turma L350" in texto(page, ".st-key-sec_jf1"))
    botao(page, "Promissória")
    por(page, "Valor que está sendo cobrado", "3000")
    confere("'Já usados' sugere o advogado do exemplo", page.locator("button:visible", has_text="DRA. ADVOGADA (EXEMPLO)").count() == 1)
    botao(page, "DRA. ADVOGADA (EXEMPLO)")
    confere("tocar no advogado sugerido preenche o campo", valor_de(page, "Advogado responsável") == "DRA. ADVOGADA (EXEMPLO)")
    page.get_by_text("Parcelado", exact=True).first.click(); esperar(page)
    confere("valor do acordo em branco mostra o valor cobrado",
            page.locator("input[aria-label='Valor do acordo']").get_attribute("placeholder") == "3.000,00")
    por(page, "Em quantas parcelas?", "3")
    primeira = HOJE + timedelta(days=10)
    por_data(page, "1º vencimento", primeira)
    vals = [valor_de(page, f"Valor da {k}ª") for k in (1, 2, 3)]
    confere("cada parcela já vem com a sua parte (3 x 1.000,00)", vals == ["1.000,00"] * 3, str(vals))
    por(page, "Valor da 1ª", "1500")
    vals = [valor_de(page, f"Valor da {k}ª") for k in (1, 2, 3)]
    confere("mudar a 1ª divide o resto entre as outras", vals == ["1.500,00", "750,00", "750,00"], str(vals))
    confere("conferência fecha com o acordo", "Fecha certinho" in texto(page, ".st-key-sec_jf3"))
    datas = [page.locator("[data-testid=stDateInput]").filter(has=page.get_by_text(f"Vencimento da {k}ª", exact=True))
             .locator("input").first.input_value() for k in (1, 2, 3)]
    confere("vencimentos todo mês no mesmo dia", len(set(d[:2] for d in datas)) == 1 and len(set(datas)) == 3, str(datas))
    terceira = HOJE + timedelta(days=75)
    por_data(page, "Vencimento da 3ª", terceira)
    page.screenshot(path=str(OUT / "juridico_2_cadastro.png"), full_page=True)
    botao(page, "Salvar cobrança judicial"); esperar(page, 2000)
    ficha = texto(page, ".fc")
    confere("salvou e abriu a ficha", "FULANO JUDICIAL" in texto(page, ".cx-titulo"), texto(page, ".cx-titulo"))
    confere("ficha: valor cobrado, advogado e acordo", "R$ 3.000,00" in ficha and "DRA. ADVOGADA (EXEMPLO)" in ficha
            and "Acordo em 3 parcelas" in ficha, ficha.replace("\n", " | "))
    confere("ficha: 3 parcelas, a 3ª com a data mudada", page.locator(".pc").count() == 3
            and str(terceira.day) in page.locator(".pc").nth(2).inner_text())
    confere("subtítulo com turma e objeto", "Turma L350 · Promissória" in texto(page, ".cx-sub"))

    # ── marcar a 1ª como paga e desfazer ──
    botao(page, "Marcar como paga")
    confere("abre a janela de confirmar pagamento", page.locator("[role=dialog]").count() == 1)
    botao(page, "Confirmar pagamento", "[role=dialog]"); esperar(page, 1500)
    p1 = page.locator(".pc").first.inner_text()
    confere("1ª parcela ficou PAGO com quem marcou", "PAGO" in p1 and "Teste Juridico marcou" in p1, p1.replace("\n", " | "))
    confere("contas do acordo atualizadas", "R$ 1.500,00" in texto(page, ".fc-nums").split("\n")[0], texto(page, ".fc-nums"))
    page.screenshot(path=str(OUT / "juridico_3_ficha.png"), full_page=True)

    # ── editar: 4 parcelas; a paga continua paga ──
    botao(page, "Editar")
    confere("editar já vem preenchido", valor_de(page, "Nome do cliente") == "FULANO JUDICIAL"
            and valor_de(page, "Valor da 1ª") == "1.500,00" and valor_de(page, "Turma") == "L350")
    confere("editar avisa que a 1ª já está paga", "Já paga em" in texto(page, ".st-key-sec_jf3"))
    por(page, "Em quantas parcelas?", "4")
    vals = [valor_de(page, f"Valor da {k}ª") for k in (1, 2, 3, 4)]
    confere("4 parcelas dividem o acordo (750,00 cada)", vals == ["750,00"] * 4, str(vals))
    botao(page, "Salvar alterações"); esperar(page, 2000)
    confere("editado: 4 parcelas e a 1ª continua PAGO",
            page.locator(".pc").count() == 4 and "PAGO" in page.locator(".pc").first.inner_text())
    botao(page, "Desfazer pagamento")
    botao(page, "Sim, desfazer", "[role=dialog]"); esperar(page, 1500)
    confere("desfazer tira o PAGO", "PAGO" not in texto(page, ".pc"))

    # ── editar para à vista ──
    botao(page, "Editar")
    page.get_by_text("Acordo à vista", exact=True).first.click(); esperar(page)
    por(page, "Valor do acordo", "2500")
    botao(page, "Salvar alterações")
    confere("à vista sem data não salva", "Falta o vencimento do acordo" in texto(page, "[data-testid=stAlert]"))
    por_data(page, "Vencimento", HOJE + timedelta(days=2))
    botao(page, "Salvar alterações"); esperar(page, 2000)
    ficha = texto(page, ".fc")
    confere("ficha: acordo à vista de 2.500,00, vence em breve",
            "Acordo à vista de R$ 2.500,00" in ficha and "Vence em breve" in ficha, ficha.replace("\n", " | "))

    # ── busca e excluir ──
    botao(page, "Voltar")
    por(page, "Buscar", "advogada")
    confere("busca pelo advogado acha as 3", page.locator(".cc").count() == 3)
    por(page, "Buscar", "l350")
    confere("busca pela turma acha só a nova", page.locator(".cc").count() == 1)
    por(page, "Buscar", "")
    tocar(page, "[class*='st-key-tq_j'] button >> nth=1")   # 2ª da lista (vence em breve)
    titulo = texto(page, ".cx-titulo")
    botao(page, "Excluir")
    botao(page, "Sim, excluir", "[role=dialog]"); esperar(page, 1500)
    confere("excluir volta para a lista sem ela", page.locator(".cc").count() == 2
            and titulo not in texto(page, ".cc-nome"), titulo)

    # ── protestos ──
    botao(page, "Voltar")
    tocar(page, ".st-key-tq_prot button")
    confere("protestos: em aberto em cima, pago embaixo",
            "Em aberto" in page.locator(".cc").first.inner_text() and "Pago" in page.locator(".cc").nth(1).inner_text())
    botao(page, "Novo protesto")
    botao(page, "Salvar protesto")
    confere("protesto vazio lista o que falta", "Falta o nome do cliente" in texto(page, "[data-testid=stAlert]"))
    por(page, "Nome do cliente", "Beltrano Protesto")
    por(page, "Turma", "v12")
    botao(page, "Cheque")
    por_data(page, "Data de inclusão do protesto", HOJE - timedelta(days=200))
    botao(page, "Salvar protesto"); esperar(page, 1500)
    novo = page.locator(".cc").first.inner_text()
    confere("salvou e o mais antigo em aberto vem primeiro", "BELTRANO PROTESTO" in novo and "Em aberto" in novo,
            novo.replace("\n", " | "))
    abrir_cartao(page, "cc_p", "BELTRANO")
    page.get_by_text("Já foi pago", exact=True).first.click(); esperar(page)
    confere("marcar pago mostra a data do pagamento", page.locator("[data-testid=stDateInput]").filter(
        has=page.get_by_text("Pago em", exact=True)).count() == 1)
    botao(page, "Salvar alterações"); esperar(page, 1500)
    pago = [c.inner_text() for c in page.locator(".cc").all() if "BELTRANO" in c.inner_text()]
    confere("protesto pago: selo Pago e quem marcou", pago and "Pago" in pago[0] and "Teste Juridico marcou" in pago[0],
            str(pago))
    nomes = [c.inner_text().split("\n")[0] for c in page.locator(".cc").all()]
    confere("pago mais recente vem antes do pago antigo", nomes.index("BELTRANO PROTESTO") < nomes.index("JOÃO RIBEIRO (EXEMPLO)"),
            str(nomes))
    abrir_cartao(page, "cc_p", "BELTRANO")
    confere("abre o protesto certo", valor_de(page, "Nome do cliente") == "BELTRANO PROTESTO")
    page.get_by_text("Já foi pago", exact=True).first.click(); esperar(page)
    botao(page, "Salvar alterações"); esperar(page, 1500)
    volta = [c.inner_text() for c in page.locator(".cc").all() if "BELTRANO" in c.inner_text()]
    confere("desmarcar volta para Em aberto", volta and "Em aberto" in volta[0] and "marcou" not in volta[0], str(volta))
    abrir_cartao(page, "cc_p", "BELTRANO")
    botao(page, "Excluir protesto")
    botao(page, "Sim, excluir", "[role=dialog]"); esperar(page, 1500)
    confere("protesto excluído some da lista", "BELTRANO" not in texto(page) and page.locator(".cc").count() == 2)
    page.screenshot(path=str(OUT / "juridico_4_protestos.png"), full_page=True)

    # ── Total na ficha da cobrança ──
    inicio(page)
    tocar(page, ".st-key-tq_rel button")
    por(page, "Buscar", "maria")
    tocar(page, "[class*='st-key-tq_'] button >> nth=0")
    total = texto(page, ".fc-total")
    confere("ficha da cobrança mostra o Total", "Total" in total and "R$ 5.000,00" in total, total.replace("\n", " "))

    # ── o Jurídico não mexe no relatório de cobranças ──
    inicio(page)
    tocar(page, ".st-key-tq_rel button")
    confere("relatório de cobranças não mostra ninguém do Jurídico",
            "LOJA PONTO CERTO" not in texto(page) and "AUTO PEÇAS" not in texto(page))
    b.close()

print("\n" + ("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S):\n- " + "\n- ".join(falhas)))
sys.exit(1 if falhas else 0)

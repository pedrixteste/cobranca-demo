"""
Teste da trava por aparelho. Rodar contra um app LOCAL FORA do modo demonstração
e com arquivo VAZIO (a trava só existe fora da demo):

    COBRANCA_LOCAL=vazio.local.json  streamlit run app.py --server.port 8613

Cada "contexto" do navegador é um aparelho diferente (cookies separados).
"""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8613"
falhas = []


def esperar(page, ms=2200):
    page.wait_for_timeout(ms)
    for _ in range(40):
        # pronto = sem o indicador de "rodando" E sem pedaço da tela anterior ainda esmaecido
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(600)


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra)
    if not cond:
        falhas.append(nome)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def tem(page, texto):
    return page.get_by_text(texto).count() > 0


def botoes(page):
    return [" ".join(b.inner_text().split()) for b in page.locator("button:visible").all()]


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = p.devices["Pixel 5"]

    def aparelho(endereco=URL):
        pg = b.new_context(**dev).new_page()
        pg.goto(endereco); esperar(pg, 7000)
        return pg

    # 1. Primeira pessoa do app: digita o nome e vira administradora
    A = aparelho()
    confere("1ª pessoa: o app pede o nome", A.locator("input[aria-label='Seu nome']").count() == 1)
    A.locator("input[aria-label='Seu nome']").fill("Pedro"); botao(A, "Entrar")
    confere("entrou como Pedro", tem(A, "Usando como"), str(botoes(A))[:90])
    confere("não existe botão de trocar", not any("trocar" in x for x in botoes(A)))
    confere("Pedro tem Configurações", any("Configurações" in x for x in botoes(A)))
    confere("endereço guardou o código do aparelho", "a=" in A.url)
    endereco_pedro = A.url

    # 2. Reabrir sem nada no endereço: o cookie reconhece
    A.goto(URL); esperar(A, 6000)
    confere("reabriu pelo endereço limpo e entrou direto", tem(A, "Usando como") and not tem(A, "Quem está usando?"))

    # 3. Aparelho novo, sem ninguém liberado
    B = aparelho()
    confere("aparelho novo é barrado", tem(B, "ainda não tem acesso"))
    confere("aparelho novo não pode digitar um nome", B.locator("input[aria-label='Seu nome'], input[aria-label='Outra pessoa']").count() == 0)
    confere("aparelho novo não vê o nome Pedro para escolher", not any(x.endswith("Pedro") for x in botoes(B)))

    # 4. Tentar entrar como Pedro pelo endereço antigo
    X = aparelho(URL + "/?quem=Pedro")
    confere("?quem=Pedro não deixa entrar como Pedro", tem(X, "ainda não tem acesso") and not tem(X, "Usando como"))

    # 5. Pedro adiciona a Gabi
    botao(A, "Configurações")
    A.locator("input[aria-label='Nome']").fill("Gabi"); botao(A, "Adicionar")
    confere("Gabi aparece em Configurações como 'Ainda não entrou'", tem(A, "Ainda não entrou"))

    # 6. A Gabi escolhe o nome no aparelho dela
    botao(B, "tentar de novo")
    confere("agora o aparelho novo vê Gabi", any(x.endswith("Gabi") for x in botoes(B)), str(botoes(B)))
    botao(B, "Gabi")
    confere("entrou como Gabi", tem(B, "Usando como") and "Gabi" in B.locator(".hm-quem").inner_text())
    confere("Gabi não tem Configurações", not any("Configurações" in x for x in botoes(B)))
    confere("Gabi não tem botão de trocar", not any("trocar" in x for x in botoes(B)))
    endereco_gabi = B.url
    B.goto(URL); esperar(B, 6000)
    confere("Gabi reabre e entra direto", tem(B, "Usando como") and "Gabi" in B.locator(".hm-quem").inner_text())

    # 7. Terceiro aparelho: Gabi já está presa, não aparece
    C = aparelho()
    confere("3º aparelho não consegue escolher Gabi", tem(C, "ainda não tem acesso"))

    # 8. Pedro libera um aparelho novo para a Gabi
    A.goto(endereco_pedro); esperar(A, 6000); botao(A, "Configurações")
    botao(A, "Liberar novo aparelho", ".st-key-sec_cf_1")   # cartão da Gabi (o 0 é o do Pedro)
    confere("Configurações mostra a liberação", tem(A, "Liberado para 1 aparelho novo"))
    botao(C, "tentar de novo")
    confere("3º aparelho agora vê Gabi", any(x.endswith("Gabi") for x in botoes(C)))
    botao(C, "Gabi")
    confere("3º aparelho entrou como Gabi", tem(C, "Usando como"))
    D = aparelho()
    confere("a liberação valeu para UM aparelho só", tem(D, "ainda não tem acesso"))

    # 9. Sem cookie (iPhone após dias sem uso), mas com o atalho que tem o código
    E = aparelho(endereco_gabi)
    confere("atalho com o código entra mesmo sem cookie", tem(E, "Usando como") and "Gabi" in E.locator(".hm-quem").inner_text())

    # 10. Migração: atalho antigo ?quem=Nome de uma pessoa ainda sem aparelho
    A.goto(endereco_pedro); esperar(A, 6000); botao(A, "Configurações")
    A.locator("input[aria-label='Nome']").fill("Ana"); botao(A, "Adicionar")
    F = aparelho(URL + "/?quem=Ana")
    confere("atalho antigo ?quem=Ana entra direto e prende", tem(F, "Usando como") and "Ana" in F.locator(".hm-quem").inner_text())
    G = aparelho(URL + "/?quem=Ana")
    confere("o mesmo atalho antigo não serve num 2º aparelho", tem(G, "ainda não tem acesso"))

    # 11. Desligar os aparelhos da Gabi
    A.goto(endereco_pedro); esperar(A, 6000); botao(A, "Configurações")
    botao(A, "Desligar aparelhos", ".st-key-sec_cf_1")
    B.goto(URL); esperar(B, 6000)
    confere("aparelho da Gabi perdeu o acesso (volta a pedir o nome)", tem(B, "Quem está usando?"))

    # 12. Registro: o que a Ana cadastra sai no nome dela
    confere("Pedro continua administrador depois de tudo", any("Configurações" in x for x in botoes(aparelho(endereco_pedro))))
    b.close()

print("\nTUDO CERTO" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)

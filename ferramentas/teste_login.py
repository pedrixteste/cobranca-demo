"""
Teste da entrada com Google (pedido 26/10), com o Google de mentira do modo de teste.
Rodar contra um app LOCAL, FORA da demonstração, com arquivo VAZIO e o Google de teste:

    COBRANCA_LOCAL=vazio2.local.json COBRANCA_SEM_COOKIE=1 COBRANCA_LOGIN_TESTE=1 \
        streamlit run app.py --server.port 8614

Cada "contexto" do navegador é um aparelho diferente.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8614"
falhas = []
OUT = Path(__file__).parent.parent / ".fotos_teste"
OUT.mkdir(exist_ok=True)
PEDRO, GABI, ANA = "pedro.teste@gmail.com", "gabi.teste@gmail.com", "ana.teste@gmail.com"


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


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def tem(page, texto):
    return page.get_by_text(texto).count() > 0


def botoes(page):
    return [" ".join(b.inner_text().split()) for b in page.locator("button:visible").all()]


def por(page, rotulo, valor):
    c = page.locator(f"input[aria-label='{rotulo}']").first
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def entrar_google(page, email, rotulo="Entrar com Google"):
    """O Google de mentira: digita o e-mail e toca no botão."""
    page.locator("input[aria-label='E-mail do Google (teste)']").first.fill(email)
    botao(page, rotulo)


def salvar_gmail(page, pessoa, email):
    page.locator(f"input[aria-label='Gmail de {pessoa}']").first.fill(email)
    i = [x.inner_text().split("\n")[0] for x in page.locator("[class*='st-key-sec_cf_'] .nt-pessoa").all()]
    caixa = page.locator("[class*='st-key-sec_cf_']", has=page.locator(f"input[aria-label='Gmail de {pessoa}']"))
    caixa.locator("button:visible", has_text="Salvar").first.click()
    esperar(page)


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = p.devices["Pixel 5"]

    def aparelho():
        pg = b.new_context(**dev).new_page()
        pg.goto(URL); esperar(pg, 7000)
        return pg

    # 1. Antes de ligar: tudo como hoje (trava por aparelho)
    A = aparelho()
    confere("antes de ligar: pede o nome, como hoje", A.locator("input[aria-label='Seu nome']").count() == 1)
    A.locator("input[aria-label='Seu nome']").fill("Pedro"); botao(A, "Entrar")
    botao(A, "Configurações")
    sec = A.locator(".st-key-sec_cf_google")
    confere("Configurações tem a seção 'Entrada com Google', desligada",
            sec.count() == 1 and "Desligada" in sec.inner_text(), sec.inner_text()[:120] if sec.count() else "")
    confere("sem o Gmail do Pedro ainda não dá para testar", not any("Testar com o Google" in x for x in botoes(A)))

    # 2. Gmails: inválido, salvar, repetido
    salvar_gmail(A, "Pedro", "pedro.teste")
    confere("e-mail inválido é recusado", tem(A, "não parece certo"))
    salvar_gmail(A, "Pedro", "Pedro.Teste@Gmail.com")
    confere("Gmail do Pedro salvo (em minúscula)",
            A.locator("input[aria-label='Gmail de Pedro']").first.input_value() == PEDRO)
    campo = A.locator("input[aria-label='Gmail de Pedro']").first
    confere("campo de Gmail aparece em minúscula e abre teclado de e-mail",
            campo.evaluate("e => getComputedStyle(e).textTransform") == "none"
            and campo.get_attribute("inputmode") == "email")
    por(A, "Nome", "Gabi"); A.locator("input[aria-label='Gmail']").first.fill(PEDRO); botao(A, "Adicionar")
    confere("Gmail que já é de outra pessoa é recusado", tem(A, "já é de Pedro"))
    A.locator("input[aria-label='Gmail']").first.fill(GABI); botao(A, "Adicionar")
    confere("Gabi adicionada com Gmail", A.locator("input[aria-label='Gmail de Gabi']").first.input_value() == GABI)
    por(A, "Nome", "Ana"); A.locator("input[aria-label='Gmail']").first.fill(""); botao(A, "Adicionar")
    confere("Ana adicionada sem Gmail (antes de ligar pode)", A.locator("input[aria-label='Gmail de Ana']").count() == 1)

    # 3. Teste com o Gmail errado e depois com o certo
    confere("com o Gmail do Pedro aparece 'Testar com o Google'", any("Testar com o Google" in x for x in botoes(A)))
    entrar_google(A, GABI, "Testar com o Google")
    confere("Gmail errado: avisa e não deixa ligar",
            tem(A, "Entre com o Gmail certo") and not any("Ligar entrada" in x for x in botoes(A)))
    botao(A, "Entrar com outro Gmail")
    if not A.locator(".st-key-sec_cf_google").count():
        botao(A, "Configurações")
    entrar_google(A, PEDRO, "Testar com o Google")
    A.screenshot(path=str(OUT / "login_1_config_teste_ok.png"), full_page=True)
    confere("Gmail certo: 'Deu certo' e avisa quem está sem Gmail",
            tem(A, "Deu certo") and A.locator(".st-key-sec_cf_google .cx-falta", has_text="Ana").count() == 1)
    botao(A, "Ligar entrada com Google para todos")
    confere("ligou", "Ligada" in A.locator(".st-key-sec_cf_google").inner_text())
    confere("com a entrada ligada some 'Liberar novo aparelho'", not any("Liberar novo aparelho" in x for x in botoes(A)))
    confere("o Gmail do administrador fica travado",
            A.locator("input[aria-label='Gmail de Pedro']").count() == 0 and tem(A, "desligue a entrada com Google"))
    por(A, "Nome", "Bia"); botao(A, "Adicionar")
    confere("com a entrada ligada, pessoa nova precisa de Gmail", tem(A, "precisa de um Gmail"))

    # 4. Gabi em qualquer aparelho
    G = aparelho()
    confere("aparelho novo: tela 'Entrar com Google'", any("Entrar com Google" in x for x in botoes(G))
            and G.locator("input[aria-label='Seu nome']").count() == 0)
    G.screenshot(path=str(OUT / "login_2_tela_entrar.png"), full_page=True)
    entrar_google(G, GABI.upper())
    confere("Gabi entrou pelo Gmail", tem(G, "Usando como Gabi"), str(botoes(G))[-120:])
    confere("Gabi não vê Configurações", not any("Configurações" in x for x in botoes(G)))
    G2 = aparelho(); entrar_google(G2, GABI)
    confere("o mesmo Gmail entra em outro aparelho também", tem(G2, "Usando como Gabi"))

    # 5. Gmail desconhecido e Ana sem Gmail
    X = aparelho(); entrar_google(X, "estranho@gmail.com")
    confere("Gmail desconhecido é barrado", tem(X, "não tem acesso a este app") and not tem(X, "Usando como"))
    X.screenshot(path=str(OUT / "login_3_barrado.png"), full_page=True)
    botao(X, "Entrar com outro Gmail")
    confere("'Entrar com outro Gmail' volta para a tela de entrar", any("Entrar com Google" in x for x in botoes(X)))

    # 6. Pedro em outro aparelho é administrador
    P = aparelho(); entrar_google(P, PEDRO)
    confere("Pedro entra pelo Gmail em aparelho novo e tem Configurações",
            tem(P, "Usando como Pedro") and any("Configurações" in x for x in botoes(P)))

    # 7. Pedro apaga o Gmail da Gabi: ela perde o acesso na próxima tela
    botao(P, "Configurações")
    salvar_gmail(P, "Gabi", "")
    botao(G, "Notificações")
    confere("Gabi sem Gmail perde o acesso na hora", tem(G, "não tem acesso a este app"), str(botoes(G))[:100])
    salvar_gmail(P, "Gabi", GABI)

    # 8. Sair
    G3 = aparelho(); entrar_google(G3, GABI)
    botao(G3, "sair")
    confere("'sair' volta para 'Entrar com Google'", any("Entrar com Google" in x for x in botoes(G3)))

    # 9. Desligar volta para a trava por aparelho
    if not P.locator(".st-key-sec_cf_google").count():
        botao(P, "Configurações")
    botao(P, "Desligar e voltar para a trava por aparelho")
    N = aparelho()
    confere("desligado: aparelho novo volta para 'Quem está usando?'",
            tem(N, "Quem está usando?") and not any("Entrar com Google" in x for x in botoes(N)))
    b.close()

print("\nFALHAS:" if falhas else "\nTUDO CERTO", *falhas, sep="\n- " if falhas else "")
sys.exit(1 if falhas else 0)

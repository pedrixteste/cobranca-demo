"""
Teste do acesso SÓ JURÍDICO (pedido 04/11: "garanta que essa pessoa não vai ter acesso a nada").
Liga o PRÓPRIO app na porta 8615 com um arquivo local (cobranças de exemplo, nunca a planilha real)
e o Google de mentira (COBRANCA_LOGIN_TESTE=1). Cada contexto do navegador é um aparelho.
  1. Pedro (admin) cadastra "Jurista" com acesso Só Jurídico
  2. Jurista entra: só vê o Jurídico; nenhum nome de cliente das cobranças aparece em lugar nenhum
  3. tenta furar: Voltar, seta do celular, ?quem=Pedro no endereço, recarregar, trocar de aparelho
  4. Pedro muda o acesso dela com ela usando o app: vale no próximo toque
  5. entrada com Google desligada (trava por aparelho): aparelho novo não pega nome de ninguém
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

PASTA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PASTA))
import dados  # noqa: E402
import demo  # noqa: E402

PORTA = 8615
URL = f"http://localhost:{PORTA}"
OUT = PASTA / ".fotos_teste"
OUT.mkdir(exist_ok=True)
PEDRO, ANA, JUR = "pedro.teste@gmail.com", "ana.teste@gmail.com", "jurista.teste@gmail.com"
falhas = []


def esperar(page, ms=1800):
    page.wait_for_timeout(ms)
    for _ in range(60):
        if not page.locator("[data-testid=stStatusWidget]").count() and not page.locator("[data-stale=true]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)
    if page.locator("[data-testid=stException]").count():
        falhas.append("ERRO NA TELA: " + page.locator("[data-testid=stException]").first.inner_text()[:200])


def confere(nome, cond, extra=""):
    print(("OK    " if cond else "FALHA ") + nome, extra)
    if not cond:
        falhas.append(nome)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def corpo(page):
    return page.locator("body").inner_text()


def entrar(page, email):
    page.locator("input[aria-label='E-mail do Google (teste)']").first.fill(email)
    botao(page, "Entrar com Google")


# Nomes que só existem nas COBRANÇAS do exemplo: nenhum pode aparecer para a Jurista
CLIENTES_COBRANCA = ["Maria José", "Carlos Pereira", "Ana Fernandes", "Roberto Almeida", "Fernanda Costa",
                     "Juliana Martins", "PADARIA BOM GOSTO"]
PROIBIDOS = ["Pix, cartão, híbrido ou permuta", "Relatório de cobranças", "Configurações", "Notificações", "Feriados",
             "Cobranças excluídas", "Tamanho do texto"]


def nada_de_cobranca(page, onde):
    t = corpo(page)
    vazou = [x for x in CLIENTES_COBRANCA + PROIBIDOS if x.lower() in t.lower()]
    confere(f"{onde}: nada das cobranças nem dos menus aparece", not vazou, str(vazou))


tmp = Path(tempfile.mkdtemp(prefix="cobranca_sojur_"))
arquivo = tmp / "planilha.local.json"
banco = dados.Local(str(arquivo))
demo.semear(banco, date.today())
for k, v in {"pessoas": "Pedro, Ana", "admin": "Pedro", "email:Pedro": PEDRO, "email:Ana": ANA,
             "login_google": "sim", "telegram:Ana": "123"}.items():
    banco.save_config(k, v)
env = {**os.environ, "COBRANCA_LOCAL": str(arquivo), "COBRANCA_SEM_COOKIE": "1", "COBRANCA_LOGIN_TESTE": "1"}
env.pop("COBRANCA_DEMO", None)
srv = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(PASTA / "app.py"), "--server.port", str(PORTA),
                        "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                       cwd=PASTA, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2)
            break
        except Exception:
            time.sleep(1)

    with sync_playwright() as p:
        b = p.chromium.launch()
        dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1500}

        def aparelho(url=URL):
            pg = b.new_context(**dev).new_page()
            pg.goto(url); esperar(pg, 6000)
            return pg

        # 1. Pedro cadastra a Jurista com acesso Só Jurídico
        P = aparelho()
        entrar(P, PEDRO)
        confere("Pedro entra e vê tudo", "Relatório de cobranças" in corpo(P) and "Jurídico" in corpo(P))
        botao(P, "Configurações")
        P.locator("input[aria-label='Nome']").first.fill("Jurista")
        P.locator("input[aria-label='Gmail']").first.fill(JUR)
        botao(P, "Adicionar")
        confere("Adicionar sem escolher o acesso não cadastra (nada de 'Tudo' por engano)",
                "Escolha o acesso" in corpo(P) and "acesso:Jurista" not in arquivo.read_text(encoding="utf-8")
                and "Jurista" not in json.loads(arquivo.read_text(encoding="utf-8"))["config"]["pessoas"])
        P.locator(".st-key-cf_novo_acesso button", has_text="Só Jurídico").first.click(); esperar(P)
        botao(P, "Adicionar")
        cfg = json.loads(arquivo.read_text(encoding="utf-8"))["config"]
        confere("gravou acesso:Jurista = juridico", cfg.get("acesso:Jurista") == "juridico", str(cfg.get("acesso:Jurista")))
        linha = P.locator("[class*='st-key-sec_cf_']", has_text="Jurista").first.inner_text()
        confere("Configurações mostra 'Só Jurídico' e que ela não recebe Telegram",
                "Só Jurídico" in linha and "Não recebe aviso no Telegram" in linha, linha.replace("\n", " | "))
        confere("o administrador não tem a opção de se restringir",
                P.locator("[class*='st-key-cf_acesso_']").count() == 2)   # Ana e Jurista, não o Pedro

        # 2. A Jurista entra
        J = aparelho()
        entrar(J, JUR)
        t = corpo(J)
        confere("Jurista cai direto no Jurídico", "Jurídico" in t and J.locator(".st-key-hm_jud").count() == 1
                and J.locator(".st-key-hm_prot").count() == 1, t[:150].replace("\n", " | "))
        confere("tela inicial dela não tem 'Voltar'", J.locator(".st-key-voltar_topo").count() == 0)
        confere("mostra 'Usando como Jurista · sair'", "Usando como Jurista" in t)
        nada_de_cobranca(J, "tela inicial da Jurista")
        J.screenshot(path=str(OUT / "sojur_1_inicio.png"), full_page=True)

        # usa o Jurídico normalmente
        J.locator(".st-key-tq_jud button").first.click(force=True); esperar(J)
        confere("abre as cobranças judiciais", "LOJA PONTO CERTO" in corpo(J))
        nada_de_cobranca(J, "lista judicial")
        J.locator("[class*='st-key-tq_j'] button").first.click(force=True); esperar(J)
        confere("abre a ficha judicial", J.locator(".fc").count() == 1)
        nada_de_cobranca(J, "ficha judicial")
        botao(J, "Voltar"); botao(J, "Voltar")
        confere("Voltar volta para o Jurídico (não para as cobranças)",
                J.locator(".st-key-hm_jud").count() == 1 and J.locator(".st-key-hm_nova").count() == 0)

        # 3. tentativas de furar
        J.locator(".st-key-tq_prot button").first.click(force=True); esperar(J)
        J.go_back(); esperar(J, 2500)
        J.go_back(); esperar(J, 2500)
        confere("seta do celular nunca leva às cobranças", J.locator(".st-key-hm_nova").count() == 0
                and "Relatório de cobranças" not in corpo(J))
        for extra in ("?quem=Pedro", "?quem=Ana", "?quem=pedro&a=0123456789abcdef0123"):
            X = aparelho(URL + "/" + extra)
            if X.locator("input[aria-label='E-mail do Google (teste)']").count():
                entrar(X, JUR)
            confere(f"endereço com {extra}: continua só Jurídico",
                    "Usando como Jurista" in corpo(X) and X.locator(".st-key-hm_nova").count() == 0)
            nada_de_cobranca(X, f"endereço {extra}")
            X.context.close()
        confere("na tela de partida, a seta do celular sai do app (não abre outra tela)", "localhost" not in J.url
                or J.locator(".st-key-hm_nova").count() == 0, J.url)
        J.goto(URL); esperar(J, 6000)
        if J.locator("input[aria-label='E-mail do Google (teste)']").count():
            entrar(J, JUR)
        nada_de_cobranca(J, "depois de recarregar a página")
        Z = aparelho()
        entrar(Z, "desconhecido.teste@gmail.com")
        confere("Gmail que não está no app não entra", "não tem acesso a este app" in corpo(Z)
                and Z.locator(".st-key-hm_jud").count() == 0 and Z.locator(".st-key-hm_nova").count() == 0)
        Z.context.close()

        # 4. Pedro muda o acesso com ela usando o app
        botao(P, "Voltar"); botao(P, "Configurações")
        caixa_jur = lambda: P.locator("[class*='st-key-sec_cf_']", has_text="Jurista").first
        caixa_jur().locator("button", has_text="Tudo").first.click(); esperar(P)
        confere("Pedro trocou para 'Tudo'", json.loads(arquivo.read_text(encoding="utf-8"))["config"].get("acesso:Jurista") == "")
        J.locator(".st-key-tq_jud button").first.click(force=True); esperar(J)
        botao(J, "Voltar")
        confere("com 'Tudo', o Jurídico dela ganha o Voltar para a tela inicial", J.locator(".st-key-voltar_topo").count() == 1)
        botao(J, "Voltar")
        confere("com 'Tudo', ela vê as cobranças", "Relatório de cobranças" in corpo(J))
        caixa_jur().locator("button", has_text="Só Jurídico").first.click(); esperar(P)
        J.locator(".st-key-tq_rel button").first.click(force=True); esperar(J)
        confere("voltou para Só Jurídico: o próximo toque já cai no Jurídico", J.locator(".st-key-hm_jud").count() == 1
                and "Maria José" not in corpo(J))
        nada_de_cobranca(J, "depois de tirar o acesso com o app aberto")

        # 5. nome com imagem/link/quebra de linha não vira imagem na tela de ninguém
        J.locator(".st-key-tq_prot button").first.click(force=True); esperar(J)
        botao(J, "Novo protesto")
        J.locator("input[aria-label='Nome do cliente']").first.fill("![](http://127.0.0.1:9/rastreio.png) [CLIQUE](http://x) <b>Z</b>")
        J.locator("input[aria-label='Nome do cliente']").first.press("Enter"); esperar(J, 900)
        J.locator("input[aria-label='Turma']").first.fill("L1"); J.locator("input[aria-label='Turma']").first.press("Enter")
        esperar(J, 900)
        botao(J, "Ficha")
        botao(J, "Salvar protesto")
        gravado = [x["Cliente"] for x in json.loads(arquivo.read_text(encoding="utf-8")).get("protestos", [])]
        confere("o nome é gravado numa linha só e sem < >", any("RASTREIO" in g and "<" not in g and "\n" not in g
                                                               for g in gravado), str(gravado[-1:]))
        botao(P, "Voltar")
        P.locator(".st-key-tq_jur button").first.click(force=True); esperar(P)
        P.locator(".st-key-tq_prot button").first.click(force=True); esperar(P)
        confere("na tela do Pedro nenhuma imagem de fora e nenhum link de fora aparecem",
                P.locator("img[src*='rastreio'], a[href*='127.0.0.1'], a[href='http://x']").count() == 0)

        # 6. ela exclui; só o Pedro vê os excluídos e restaura; tudo fica no histórico
        J.locator("[class*='st-key-cc_p']", has_text="RASTREIO").first.locator("button").first.click(force=True); esperar(J)
        botao(J, "Excluir protesto")
        botao(J, "Sim, excluir", "[role=dialog]"); esperar(J, 1500)
        confere("ela não vê a lista de excluídos", "Excluídos" not in corpo(J))
        P.reload(); esperar(P, 6000)
        if P.locator("input[aria-label='E-mail do Google (teste)']").count():
            entrar(P, PEDRO)
        P.locator(".st-key-tq_jur button").first.click(force=True); esperar(P)
        P.locator(".st-key-tq_prot button").first.click(force=True); esperar(P)
        P.get_by_text("Excluídos (1)").first.click(); esperar(P)
        botao(P, "Restaurar")
        confere("Pedro restaura o protesto excluído", "RASTREIO" in corpo(P) and "Excluídos" not in corpo(P))
        dados_json = json.loads(arquivo.read_text(encoding="utf-8"))
        hist = dados_json.get("historico", [])
        acoes = [(h["Quem"], h["Ação"]) for h in hist]
        confere("histórico registra quem fez o quê", ("Jurista", "cadastro") in acoes and ("Jurista", "exclusão") in acoes
                and ("Pedro", "restaurou") in acoes, str(acoes))
        prot = [x for x in dados_json["protestos"] if "RASTREIO" in x["Cliente"]][0]
        confere("a linha guarda quem excluiu", prot.get("Excluído por") == "" and prot.get("Situação") == "Ativa", str(prot))

        # 7. número de parcelas absurdo não passa
        J.locator(".st-key-tq_jud button").first.click(force=True) if J.locator(".st-key-tq_jud").count() else None
        esperar(J)
        botao(J, "Voltar")
        J.locator(".st-key-tq_jud button").first.click(force=True); esperar(J)
        botao(J, "Nova cobrança judicial")
        J.get_by_text("Parcelado", exact=True).first.click(); esperar(J)
        campo = J.locator("input[aria-label='Em quantas parcelas?']").first
        campo.fill("1000000"); campo.press("Enter"); esperar(J, 2500)
        confere("1.000.000 de parcelas: no máximo 120 campos aparecem",
                J.locator("[class*='st-key-jf_linha_']").count() <= 120, str(J.locator("[class*='st-key-jf_linha_']").count()))
        botao(J, "Voltar")

        # 7b. limite de gravações seguidas (3 por minuto) e a opção "Sem limite" de Configurações
        def novo_protesto(nome):
            botao(J, "Novo protesto")
            for rotulo, valor in (("Nome do cliente", nome), ("Turma", "L2")):
                c = J.locator(f"input[aria-label='{rotulo}']").first
                c.fill(valor); c.press("Enter"); esperar(J, 700)
            botao(J, "Cheque")
            botao(J, "Salvar protesto")
            barrou = "Muitas tentativas seguidas" in corpo(J)
            if barrou:
                botao(J, "Voltar")
            return barrou

        botao(J, "Voltar")
        J.locator(".st-key-tq_prot button").first.click(force=True); esperar(J)
        barrou_em = next((k for k in range(1, 6) if novo_protesto(f"LIMITE {k}")), None)
        confere("sem a opção, o limite barra gravações seguidas (até a 4ª)", barrou_em is not None and barrou_em <= 4,
                str(barrou_em))
        botao(P, "Voltar"); botao(P, "Voltar")
        botao(P, "Configurações")
        P.locator("[class*='st-key-sec_cf_']", has_text="Jurista").first.get_by_text(
            "Sem limite de gravações (pessoa de confiança)").click(); esperar(P)
        confere("Configurações grava sem_limite:Jurista",
                json.loads(arquivo.read_text(encoding="utf-8"))["config"].get("sem_limite:Jurista") == "sim")
        confere("com 'Sem limite', ela volta a gravar na hora", not novo_protesto("LIMITE LIVRE")
                and "LIMITE LIVRE" in corpo(J))
        botao(J, "Voltar")
        J.locator(".st-key-tq_jud button").first.click(force=True); esperar(J)

        # 8. Pedro remove a pessoa com ela usando o app: o próximo toque já barra
        caixa_jur = lambda: P.locator("[class*='st-key-sec_cf_']", has_text="Jurista").first
        if "Adicionar pessoa" not in corpo(P):   # (já está em Configurações depois do teste do limite)
            botao(P, "Voltar"); botao(P, "Voltar")
            botao(P, "Configurações")
        confere("com alguém Só Jurídico, não dá para desligar a entrada com Google",
                P.locator("button:visible", has_text="Desligar e voltar para a trava por aparelho").count() == 0
                and "não pode ser desligada" in corpo(P))
        caixa_jur().locator("button", has_text="Remover Jurista").first.click(); esperar(P)
        botao(P, "Sim, remover")
        botao(J, "Voltar")   # qualquer toque
        confere("removida: o próximo toque já barra (nada do Jurídico nem das cobranças)",
                "não tem acesso a este app" in corpo(J) and J.locator(".st-key-hm_jud").count() == 0
                and J.locator(".st-key-hm_nova").count() == 0, corpo(J)[:150].replace("\n", " | "))

        # 9. se a entrada com Google sair (ex.: [auth] tirado dos Secrets) com alguém Só Jurídico: aparelho novo não entra
        cfg = json.loads(arquivo.read_text(encoding="utf-8"))
        cfg["config"]["login_google"] = ""
        cfg["config"]["acesso:Ana"] = "juridico"
        arquivo.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        caixa_ana = P.locator("[class*='st-key-sec_cf_']", has_text="Ana").first
        caixa_ana.locator("button", has_text="Só Jurídico").first.click(); esperar(P)   # grava e limpa o cache
        N = aparelho()
        t = corpo(N)
        codigo = N.locator(".cf-codigo").first.inner_text() if N.locator(".cf-codigo").count() else ""
        confere("sem o Google e com alguém Só Jurídico: aparelho novo mostra o código e não escolhe nome",
                "Este aparelho ainda não tem acesso" in t and len(codigo) == 6
                and N.locator("input[aria-label='Seu nome']").count() == 0
                and N.locator("[class*='st-key-quem_']:not(.st-key-quem_denovo) button:visible").count() == 0,
                t[:200].replace("\n", " | "))
        N2 = aparelho(URL + "/?quem=Pedro")
        confere("...nem pelo atalho ?quem=Pedro", "Este aparelho ainda não tem acesso" in corpo(N2)
                and "Usando como Pedro" not in corpo(N2))
        # o administrador libera a Ana COM O CÓDIGO do aparelho N (como faria em Configurações)
        from urllib.parse import parse_qs, urlparse
        completo = parse_qs(urlparse(N.url).query).get("a", [""])[0]
        confere("o código curto é o começo do código do aparelho", completo.upper().startswith(codigo) and len(completo) >= 16)
        cfg = json.loads(arquivo.read_text(encoding="utf-8"))
        cfg["config"]["liberado:Ana"] = codigo   # só as 6 letras NÃO bastam
        arquivo.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        N.locator("button:visible", has_text="Já liberaram, tentar de novo").first.click(); esperar(N)
        confere("liberação só com as 6 letras não vale", N.locator("button:visible", has_text="Ana").count() == 0)
        N.wait_for_timeout(21000)   # a releitura forçada vale uma vez a cada 20 s para o app inteiro
        cfg = json.loads(arquivo.read_text(encoding="utf-8"))
        cfg["config"]["liberado:Ana"] = completo.upper()   # o que Configurações grava
        arquivo.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        N.locator("button:visible", has_text="Já liberaram, tentar de novo").first.click(); esperar(N)
        N2.locator("button:visible", has_text="Já liberaram, tentar de novo").first.click(); esperar(N2)
        confere("outro aparelho NÃO pega a liberação feita para o aparelho da Ana",
                N2.locator("[class*='st-key-quem_']:not(.st-key-quem_denovo) button:visible").count() == 0)
        confere("o aparelho certo vê o nome liberado", N.locator("button:visible", has_text="Ana").count() == 1)
        N.locator("button:visible", has_text="Ana").first.click(); esperar(N)
        confere("e entra como Ana (que agora é Só Jurídico: cai no Jurídico)",
                N.locator(".st-key-hm_jud").count() == 1 and N.locator(".st-key-hm_nova").count() == 0)
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except Exception:
        srv.kill()

print("\n" + ("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S):\n- " + "\n- ".join(falhas)))
sys.exit(1 if falhas else 0)

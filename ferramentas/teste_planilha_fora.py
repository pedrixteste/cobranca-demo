"""
Teste da planilha FORA DO AR (problema relatado em 03/11: o app demorava, ficava parado e, mesmo
atualizando, partes da tela não apareciam). Liga o PRÓPRIO app na porta 8613 com um arquivo local
de teste (nunca a planilha real) e liga/desliga a falha criando/apagando um arquivo:
  1. abriu com a planilha fora: aviso com "Tentar de novo" (nunca "Quem está usando?" vazio)
  2. a planilha volta: "Tentar de novo" entra normal
  3. cai de novo com o app aberto: aviso, mas a pessoa continua reconhecida (nome e Configurações)
  4. volta: tudo normal
Rodar: python ferramentas/teste_planilha_fora.py   (precisa do Streamlit novo, ver memória)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

PASTA = Path(__file__).resolve().parent.parent
PORTA = 8613
URL = f"http://localhost:{PORTA}"
OUT = PASTA / ".fotos_teste"
OUT.mkdir(exist_ok=True)
falhas = []
AVISO = "A planilha do Google não respondeu agora"


def esperar(page, ms=1500):
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


def botao(page, texto):
    page.locator("button:visible", has_text=texto).first.click()
    esperar(page)


def corpo(page):
    return page.locator("body").inner_text()


tmp = Path(tempfile.mkdtemp(prefix="cobranca_fora_"))
arquivo = tmp / "planilha.local.json"
falha = tmp / "planilha_fora.flag"
arquivo.write_text(json.dumps({"cobrancas": [], "parcelas": [], "config": {"pessoas": "Pedro, Ana", "admin": "Pedro"}},
                              ensure_ascii=False), encoding="utf-8")
falha.touch()   # já começa fora do ar
env = {**os.environ, "COBRANCA_LOCAL": str(arquivo), "COBRANCA_FALHA": str(falha), "COBRANCA_SEM_COOKIE": "1"}
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
        dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1400}
        page = b.new_context(**dev).new_page()

        # 1. abre com a planilha fora
        page.goto(URL); esperar(page, 6000)
        t = corpo(page)
        confere("1. planilha fora ao abrir: aviso com 'Tentar de novo'", AVISO in t and "Tentar de novo" in t)
        confere("1. não mostra 'Quem está usando?' nem o campo de primeiro nome",
                "Quem está usando?" not in t and page.locator("input[aria-label='Seu nome']").count() == 0)
        page.screenshot(path=str(OUT / "fora_1_aviso.png"))

        # 2. volta
        falha.unlink()
        botao(page, "Tentar de novo")
        t = corpo(page)
        confere("2. planilha voltou: pede o nome com Pedro e Ana na lista",
                "Quem está usando?" in t and page.locator("button:visible", has_text="Pedro").count() >= 1
                and page.locator("button:visible", has_text="Ana").count() >= 1)
        botao(page, "Pedro")
        t = corpo(page)
        confere("2. entrou como Pedro (administrador)", "Usando como Pedro" in t and "Configurações" in t)

        # 3. cai de novo com o app aberto
        falha.touch()
        page.locator(".st-key-tq_rel button").first.click(force=True); esperar(page)
        botao(page, "Atualizar")   # força ler a planilha de novo
        t = corpo(page)
        confere("3. relatório com a planilha fora: aviso, sem tela de erro", AVISO in t)
        botao(page, "Tentar de novo")   # relê também a configuração, que agora falha
        botao(page, "Voltar")
        t = corpo(page)
        confere("3. a pessoa continua reconhecida (última configuração boa)",
                "Usando como Pedro" in t and "Configurações" in t and "Quem está usando?" not in t)
        confere("3. tela inicial mostra o aviso uma vez só", t.count(AVISO) == 1, str(t.count(AVISO)))
        page.screenshot(path=str(OUT / "fora_2_reconhecido.png"))

        # 3b. outra pessoa abre o app (aparelho novo) com a planilha fora: lista de nomes certa
        outra = b.new_context(**dev).new_page()
        outra.goto(URL); esperar(outra, 6000)
        t = corpo(outra)
        confere("3b. aparelho novo com a planilha fora: lista de nomes da última leitura boa",
                ("Quem está usando?" in t and "Ana" in t and outra.locator("input[aria-label='Seu nome']").count() == 0),
                t[:200].replace("\n", " | "))

        # 4. volta de novo
        falha.unlink()
        botao(page, "Tentar de novo")
        t = corpo(page)
        confere("4. planilha voltou: tela inicial normal, sem aviso", AVISO not in t and "Usando como Pedro" in t
                and "Relatório de cobranças" in t and "Jurídico" in t)
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except Exception:
        srv.kill()

print("\n" + ("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S):\n- " + "\n- ".join(falhas)))
sys.exit(1 if falhas else 0)

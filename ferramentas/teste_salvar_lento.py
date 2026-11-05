"""
Teste do cadastro que "não salvava" (relato de 05/11/2026: tentou cadastrar 4 vezes, o app parecia
não salvar, mas gravou 3 cobranças do mesmo aluno; e logo depois de salvar o relatório não mostrava).
Liga o PRÓPRIO app na porta 8613 com um arquivo local de teste (nunca a planilha real) e imita o
Google devagar com COBRANCA_LENTO=<arquivo> (ver dados.Local._gravacao_simulada):
  A. gravação lenta + toque duplo no Salvar: aparece "Salvando a cobrança", grava UMA vez e abre a ficha
  B. gravação lenta + Voltar no meio: a gravação não se perde (a ficha abre quando termina), grava uma vez
  C. o Google grava mas a resposta estoura o prazo: o app confere, diz que salvou e não duplica
  D. idem, e o relatório mostra a cobrança NA HORA (sem esperar a leitura guardada vencer)
  E. falha de verdade (nada gravado): diz que NÃO salvou, mantém o formulário; tentar de novo grava uma vez
  F. a mesma cobrança digitada de novo logo depois (ex.: celular recarregou): não duplica
Rodar: python ferramentas/teste_salvar_lento.py   (precisa do Streamlit novo, ver memória)
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

sys.stdout.reconfigure(errors="replace")   # o registro do app vem com acento em outra codificação
PASTA = Path(__file__).resolve().parent.parent
PORTA = 8613
URL = f"http://localhost:{PORTA}"
OUT = PASTA / ".fotos_teste"
OUT.mkdir(exist_ok=True)
falhas = []


def esperar(page, ms=1500, max_s=40):
    page.wait_for_timeout(ms)
    for _ in range(int(max_s * 4)):
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


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def campo(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']").first


def por(page, rotulo, valor):
    c = campo(page, rotulo)
    c.fill(valor); c.press("Enter"); esperar(page, 900)


def corpo(page):
    return page.locator("body").inner_text()


def inicio(page):
    for _ in range(6):
        if page.locator(".st-key-hm_nova").count():
            return
        if page.locator("button:visible", has_text="Voltar").count():
            botao(page, "Voltar")
        else:
            page.wait_for_timeout(1000)


def preencher_pix(page, cliente):
    inicio(page)
    page.locator(".st-key-hm_nova button").first.click(force=True); esperar(page)
    page.locator(".st-key-hm_pix button").first.click(force=True); esperar(page)
    por(page, "Nome do cliente", cliente)
    por(page, "Turma", "L316")
    por(page, "Valor total", "3000")
    por(page, "Número de parcelas", "3")


def salvar_botao(page):
    return page.locator("button:visible", has_text="Salvar cobrança").first


def lento(cfg):
    if cfg is None:
        LENTO.unlink(missing_ok=True)
    else:
        LENTO.write_text(json.dumps(cfg), encoding="utf-8")


def gravadas(cliente):
    d = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    cobs = [c for c in d["cobrancas"] if c.get("Cliente") == cliente and c.get("Situação") != "Excluída"]
    ids = {c["ID"] for c in cobs}
    parc = [p for p in d["parcelas"] if p.get("ID Cobrança") in ids]
    return len(cobs), len(parc)


def na_ficha(page, cliente):
    return page.locator(".cx-titulo", has_text=cliente).count() == 1 and "Salvar cobrança" not in corpo(page)


def no_relatorio(page, cliente):
    inicio(page)
    page.locator(".st-key-tq_rel button").first.click(force=True); esperar(page)
    por(page, "Buscar", cliente)
    achou = page.locator(".cc", has_text=cliente).count() >= 1
    por(page, "Buscar", "")
    return achou


tmp = Path(tempfile.mkdtemp(prefix="cobranca_lento_"))
ARQUIVO = tmp / "planilha.local.json"
LENTO = tmp / "google_lento.json"
LOG = tmp / "app.log"
ARQUIVO.write_text(json.dumps({"cobrancas": [], "parcelas": [], "config": {"pessoas": "Pedro, Ana", "admin": "Pedro"}},
                              ensure_ascii=False), encoding="utf-8")
env = {**os.environ, "COBRANCA_LOCAL": str(ARQUIVO), "COBRANCA_LENTO": str(LENTO), "COBRANCA_SEM_COOKIE": "1"}
env.pop("COBRANCA_DEMO", None)
env.pop("COBRANCA_FALHA", None)
log = open(LOG, "w", encoding="utf-8")
srv = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(PASTA / "app.py"), "--server.port", str(PORTA),
                        "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                       cwd=PASTA, env=env, stdout=log, stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2)
            break
        except Exception:
            time.sleep(1)

    with sync_playwright() as p:
        b = p.chromium.launch()
        dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
        page = b.new_context(**dev).new_page()
        page.goto(URL); esperar(page, 5000)
        botao(page, "Pedro")
        confere("entrou como Pedro", "Usando como Pedro" in corpo(page))

        # ── A. lenta + toque duplo ──
        cli = "CLIENTE TOQUE DUPLO"
        preencher_pix(page, cli)
        lento({"segundos": 6})
        salvar_botao(page).click()
        page.wait_for_timeout(1500)
        aviso = page.locator(".cx-salvando:visible").count() >= 1
        page.screenshot(path=str(OUT / "lento_A_salvando.png"))
        salvar_botao(page).click()   # a pessoa achou que não foi e tocou de novo
        esperar(page, 2500)
        lento(None)
        confere("A. mostra 'Salvando a cobrança' enquanto grava", aviso)
        confere("A. toque duplo: gravou UMA vez (com as 3 parcelas)", gravadas(cli) == (1, 3), str(gravadas(cli)))
        confere("A. toque duplo: abre a ficha da cobrança salva", na_ficha(page, cli), corpo(page)[:160].replace("\n", " | "))
        page.screenshot(path=str(OUT / "lento_A_fim.png"))

        # ── B. lenta + Voltar no meio ──
        cli = "CLIENTE VOLTOU NO MEIO"
        preencher_pix(page, cli)
        lento({"segundos": 6})
        salvar_botao(page).click()
        page.wait_for_timeout(1500)
        page.locator("button:visible", has_text="Voltar").first.click()   # impaciente: voltou
        esperar(page, 2500)
        lento(None)
        confere("B. Voltar no meio: gravou UMA vez", gravadas(cli) == (1, 3), str(gravadas(cli)))
        confere("B. Voltar no meio: a gravação não se perdeu (abre a ficha salva)", na_ficha(page, cli),
                corpo(page)[:160].replace("\n", " | "))
        confere("B. e aparece no relatório", no_relatorio(page, cli))

        # ── C. o Google grava, mas a resposta estoura o prazo ──
        cli = "CLIENTE ESTOUROU O PRAZO"
        preencher_pix(page, cli)
        lento({"segundos": 2, "falha_depois": True})
        salvar_botao(page).click(); esperar(page, 2500)
        lento(None)
        t = corpo(page)
        confere("C. estourou o prazo mas gravou: o app confere e diz que salvou (abre a ficha)", na_ficha(page, cli),
                t[:200].replace("\n", " | "))
        page.screenshot(path=str(OUT / "lento_C.png"), full_page=True)
        if "Salvar cobrança" in t:   # (antes do conserto) a pessoa vê erro e tenta de novo
            salvar_botao(page).click(); esperar(page, 2500)
        confere("C. não duplicou", gravadas(cli) == (1, 3), str(gravadas(cli)))

        # ── D. idem: o relatório mostra NA HORA ──
        cli = "CLIENTE DO RELATORIO"
        preencher_pix(page, cli)
        no_relatorio(page, "QUALQUER")   # deixa a leitura guardada (como quem abriu o relatório antes)
        preencher_pix(page, cli)
        lento({"segundos": 1, "falha_depois": True})
        salvar_botao(page).click(); esperar(page, 2500)
        lento(None)
        confere("D. gravou uma vez", gravadas(cli) == (1, 3), str(gravadas(cli)))
        confere("D. o relatório mostra a cobrança logo depois de salvar", no_relatorio(page, cli))

        # ── E. falha de verdade: nada gravado ──
        cli = "CLIENTE FALHA DE VERDADE"
        preencher_pix(page, cli)
        lento({"falha_antes": True})
        salvar_botao(page).click(); esperar(page, 2500)
        t = corpo(page)
        confere("E. avisa que NÃO salvou e que nada foi gravado", "Não salvou" in t and "nada foi gravado" in t,
                t[-300:].replace("\n", " | "))
        confere("E. o formulário continua preenchido", campo(page, "Nome do cliente").input_value() == cli)
        confere("E. nada gravado", gravadas(cli) == (0, 0), str(gravadas(cli)))
        page.screenshot(path=str(OUT / "lento_E.png"), full_page=True)
        lento(None)
        salvar_botao(page).click(); esperar(page, 2500)
        confere("E. tentar de novo: grava uma vez e abre a ficha", gravadas(cli) == (1, 3) and na_ficha(page, cli),
                str(gravadas(cli)))

        # ── F. a mesma cobrança digitada de novo logo depois (ex.: o celular recarregou a página) ──
        cli = "CLIENTE DIGITOU DE NOVO"
        preencher_pix(page, cli)
        lento({"segundos": 2, "falha_depois": True})
        salvar_botao(page).click(); esperar(page, 2500)
        lento(None)
        preencher_pix(page, cli)
        salvar_botao(page).click(); esperar(page, 2500)
        confere("F. a mesma cobrança de novo em seguida: não duplica (abre a que já estava salva)",
                gravadas(cli) == (1, 3) and na_ficha(page, cli), str(gravadas(cli)))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except Exception:
        srv.kill()
    log.close()

erros_log = [l for l in LOG.read_text(encoding="utf-8", errors="replace").splitlines() if "[erro]" in l]
print("\nRegistro do app ([erro]):", *(erros_log or ["(nenhum)"]), sep="\n  ")
print("\n" + ("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S):\n- " + "\n- ".join(falhas)))
sys.exit(1 if falhas else 0)

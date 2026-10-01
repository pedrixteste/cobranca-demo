"""
COMO USAR: suba o app em modo demonstração (COBRANCA_DEMO=1, porta 8612) e rode
`py ferramentas/auditoria_contraste.py`. NUNCA aponte para o app de verdade: o
roteiro recomeça o exemplo, cadastra e exclui cobranças.

Auditoria de leitura no modo noturno: em cada tela e janela, mede o contraste de
TODO texto visível contra o fundo real dele (subindo pelos elementos até achar
um fundo opaco ou gradiente). Lista o que ficar abaixo de 4,5 (3,0 para letra grande).
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8612"
OUT = Path(__file__).parent / "fotos_noite"
OUT.mkdir(exist_ok=True)

JS = r"""
() => {
  const rgb = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
                     const p = m[1].split(',').map(x => parseFloat(x)); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4); };
                     return .2126*f(c.r) + .7152*f(c.g) + .0722*f(c.b); };
  const mistura = (cima, baixo) => ({ r: cima.r*cima.a + baixo.r*(1-cima.a), g: cima.g*cima.a + baixo.g*(1-cima.a),
                                      b: cima.b*cima.a + baixo.b*(1-cima.a), a: 1 });
  const fundo = el => {
    const camadas = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage.includes('gradient')) {
        const cores = cs.backgroundImage.match(/rgba?\([^)]+\)/g) || [];
        if (cores.length) { camadas.push({...rgb(cores[Math.floor(cores.length/2)]), a: 1}); break; }
      }
      const c = rgb(cs.backgroundColor);
      if (c && c.a > 0) { camadas.push(c); if (c.a >= .99) break; }
    }
    let base = {r: 20, g: 22, b: 27, a: 1};
    for (let i = camadas.length - 1; i >= 0; i--) base = mistura(camadas[i], base);
    return base;
  };
  const ruins = []; let total = 0;
  const vistos = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) {
    const n = tw.currentNode; const txt = n.textContent.trim();
    if (!txt) continue;
    const el = n.parentElement; if (!el || vistos.has(el)) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    let opac = 1, escondido = false;
    for (let e = el; e; e = e.parentElement) { const o = getComputedStyle(e); opac *= parseFloat(o.opacity);
      if (o.display === 'none' || o.visibility === 'hidden') escondido = true; }
    if (escondido || opac < .05) continue;          // botões invisíveis de toque
    if (el.closest('style, script, [class*="st-key-tq_"], .st-key-_btn_voltar_hw')) continue;
    vistos.add(el); total++;
    const bg = fundo(el);
    let cor = rgb(cs.color); if (!cor) continue;
    cor = mistura({...cor, a: cor.a * opac}, bg);
    const L1 = lum(cor), L2 = lum(bg);
    const cr = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const px = parseFloat(cs.fontSize); const negrito = parseInt(cs.fontWeight) >= 700;
    const grande = px >= 24 || (px >= 18.5 && negrito);
    if (cr < (grande ? 3 : 4.5))
      ruins.push({texto: txt.slice(0, 40), contraste: +cr.toFixed(2), cor: cs.color, fundo: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`,
                  onde: (el.className && el.className.toString().slice(0, 40)) || el.tagName, px: Math.round(px)});
  }
  // texto digitado dentro dos campos e o texto de exemplo (placeholder)
  document.querySelectorAll("input, textarea").forEach(el => {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === "hidden" || cs.display === "none") return;
    if (el.closest('[class*="st-key-tq_"]')) return;
    const bg = fundo(el);
    const medir = (corTxt, rot) => { let cor = rgb(corTxt); if (!cor) return; cor = mistura(cor, bg);
      const L1 = lum(cor), L2 = lum(bg); const cr = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05); total++;
      if (cr < (rot === "exemplo" ? 3 : 4.5)) ruins.push({texto: rot + ": " + (el.getAttribute("aria-label") || el.placeholder || "").slice(0, 28),
        contraste: +cr.toFixed(2), cor: corTxt, fundo: `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`, onde: "campo", px: Math.round(parseFloat(cs.fontSize))}); };
    medir(cs.color, "digitado");
    if (el.placeholder) medir(getComputedStyle(el, "::placeholder").color, "exemplo");
  });
  return {total, ruins};
}
"""

resultado = {}
erros_tela = []


def esperar(page, ms=2200):
    page.wait_for_timeout(ms)
    for _ in range(40):
        if not page.locator("[data-testid=stStatusWidget]").count():
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(500)
    if page.locator("[data-testid=stException]").count():
        erros_tela.append(page.locator("[data-testid=stException]").first.inner_text()[:300])


def auditar(page, nome):
    esperar(page, 300)
    page.screenshot(path=str(OUT / f"{nome}.png"), full_page=True)
    r = page.evaluate(JS)
    resultado[nome] = r
    print(f"{nome:28s} textos {r['total']:3d} | fracos {len(r['ruins'])}")


def tocar(page, sel):
    box = page.locator(sel).first.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    esperar(page)


def botao(page, texto, dentro=""):
    page.locator(f"{dentro} button:visible", has_text=texto).first.click()
    esperar(page)


def campo(page, rotulo):
    return page.locator(f"input[aria-label='{rotulo}']")


with sync_playwright() as p:
    b = p.chromium.launch()
    dev = dict(p.devices["Pixel 5"]); dev["viewport"] = {"width": 393, "height": 1700}
    page = b.new_context(**dev).new_page()
    page.goto(URL); esperar(page, 7000)
    botao(page, "Recomeçar o exemplo do zero")
    auditar(page, "01_inicio")

    tocar(page, ".st-key-hm_nova .hm-card"); auditar(page, "02_nova")
    tocar(page, ".st-key-hm_pix .hm-card"); auditar(page, "03_pix_vazio")
    botao(page, "Salvar cobrança"); auditar(page, "04_pix_erros")
    campo(page, "Nome do cliente").fill("Teste Noturno")
    campo(page, "Turma").fill("x9"); campo(page, "Turma").press("Enter"); esperar(page)
    auditar(page, "05_pix_turma_invalida")
    campo(page, "Turma").fill("l0350")
    campo(page, "Valor total").fill("3000")
    campo(page, "Valor de entrada").fill("abc"); campo(page, "Valor de entrada").press("Enter"); esperar(page)
    auditar(page, "06_pix_valor_invalido")
    campo(page, "Valor de entrada").fill("500")
    campo(page, "Número de parcelas").fill("3"); campo(page, "Número de parcelas").press("Enter"); esperar(page)
    page.get_by_text("Parcial", exact=True).nth(0).click(); esperar(page)
    page.get_by_text("Parcial", exact=True).nth(1).click(); esperar(page)
    campo(page, "Valor da 1ª").fill("100"); campo(page, "Valor da 1ª").press("Enter"); esperar(page)
    auditar(page, "07_pix_parcial_cheio")
    campo(page, "Valor da 2ª").fill("100"); campo(page, "Valor da 3ª").fill("100")
    campo(page, "Valor da 3ª").press("Enter"); esperar(page)
    auditar(page, "08_pix_nao_fecha")
    try:
        page.locator("[data-testid=stDateInput] input").first.evaluate("e => { e.focus(); e.click(); }"); esperar(page, 1200)
        print("calendário aberto:", page.locator("[data-baseweb=calendar], [role=dialog] [aria-label*=alendar], [data-baseweb=popover]").count() > 0)
        auditar(page, "09_calendario_aberto")
    except Exception as e:
        print("não abriu o calendário:", type(e).__name__)
    page.keyboard.press("Escape"); esperar(page, 500)

    page.goto(URL); esperar(page, 5000)
    tocar(page, ".st-key-hm_nova .hm-card"); tocar(page, ".st-key-hm_cartao .hm-card")
    campo(page, "Valor total").fill("10000"); campo(page, "Valor que já foi pago").fill("2000")
    campo(page, "Em quantas vezes vai passar?").fill("20"); campo(page, "Em quantas vezes vai passar?").press("Enter"); esperar(page)
    print("campos de data no cartão:", page.locator("[data-testid=stDateInput]").count())
    auditar(page, "10_cartao_20_datas")
    botao(page, "Salvar cobrança"); auditar(page, "11_cartao_erros")

    page.goto(URL); esperar(page, 5000)
    tocar(page, ".st-key-hm_rel .hm-card"); auditar(page, "12_relatorio")
    page.get_by_text("Filtros", exact=True).first.click(); esperar(page)
    page.locator("[data-testid=stExpander] button", has_text="Atrasado").first.click(); esperar(page)
    auditar(page, "13_filtros_abertos")
    page.locator("[data-testid=stExpander] button", has_text="Atrasado").first.click(); esperar(page)
    campo(page, "Buscar").fill("zzzz"); campo(page, "Buscar").press("Enter"); esperar(page)
    auditar(page, "14_busca_vazia")
    campo(page, "Buscar").fill(""); campo(page, "Buscar").press("Enter"); esperar(page)
    page.get_by_text("Agenda", exact=True).first.click(); esperar(page); auditar(page, "15_agenda")
    page.get_by_text("Escolher datas", exact=True).first.click(); esperar(page); auditar(page, "16_agenda_datas")
    page.get_by_text("Clientes", exact=True).first.click(); esperar(page)

    tocar(page, "[class*='st-key-cc_'] .cc"); auditar(page, "17_ficha")
    botao(page, "Recebi"); auditar(page, "18_dlg_recebi"); page.keyboard.press("Escape"); esperar(page)
    botao(page, "Alterar"); auditar(page, "19_dlg_alterar")
    botao(page, "Remover esta parcela", "[role=dialog]"); auditar(page, "20_dlg_remover")
    page.keyboard.press("Escape"); esperar(page)
    botao(page, "Ver pagamento"); auditar(page, "21_dlg_ver")
    botao(page, "Desmarcar pagamento", "[role=dialog]"); auditar(page, "22_dlg_desmarcar")
    page.keyboard.press("Escape"); esperar(page)
    botao(page, "Adicionar parcela"); auditar(page, "23_dlg_adicionar"); page.keyboard.press("Escape"); esperar(page)
    botao(page, "Editar dados"); auditar(page, "24_dlg_editar"); page.keyboard.press("Escape"); esperar(page)
    botao(page, "Excluir"); auditar(page, "25_dlg_excluir")
    botao(page, "Sim, excluir", "[role=dialog]"); auditar(page, "26_depois_excluir_toast")

    page.goto(URL); esperar(page, 5000)
    botao(page, "Cobranças excluídas"); auditar(page, "27_excluidas")
    page.goto(URL); esperar(page, 5000)
    page.get_by_text("Grande", exact=True).first.click(); esperar(page); auditar(page, "28_inicio_letra_grande")
    page.get_by_text("Médio", exact=True).first.click(); esperar(page)
    b.close()

print("\n==== TEXTOS COM POUCO CONTRASTE ====")
vistos = set()
for nome, r in resultado.items():
    for x in r["ruins"]:
        chave = (x["texto"], x["cor"], x["fundo"])
        if chave in vistos:
            continue
        vistos.add(chave)
        print(f"[{nome}] {x['contraste']:>5}  '{x['texto']}'  cor {x['cor']} sobre {x['fundo']}  ({x['onde']}, {x['px']}px)")
print(f"\ntotal de textos medidos: {sum(r['total'] for r in resultado.values())} | fracos (únicos): {len(vistos)}")
print("erros de tela:", erros_tela or "nenhum")

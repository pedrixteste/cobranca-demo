"""
Cobrança híbrida com parte na PERMUTA (pedido 06/11/2026): a pessoa escolhe as formas
(Pix, cartão, permuta; pelo menos duas). A parte da permuta são as mesmas linhas de uma
permuta (valor que entra + retiradas), dentro da mesma cobrança híbrida.
"""
import io
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dados  # noqa: E402
import notifier  # noqa: E402
import nucleo as n  # noqa: E402

HOJE = date(2026, 9, 30)   # quarta-feira


def cob(cid="h1", tipo="Híbrido", cliente="Loja Teste", total="10000,00"):
    return {"ID": cid, "Tipo": tipo, "Cliente": cliente, "Turma": "L345", "Treinamento": "",
            "Valor Total": total, "Situação": "Ativa"}


def planilha(linhas, cid="h1"):
    """Como as linhas ficam depois de gravadas e lidas de volta da planilha."""
    cab = n.PARCELAS_HEADERS
    return [dict(zip(cab, dados._linha(cab, {**l, "ID Cobrança": cid}))) for l in linhas]


def pix_permuta(retiradas=(("CAMISETAS", date(2026, 9, 25), 500.0),), quem="Gabi"):
    # R$ 10.000 = Pix 6.000 (entrada 1.000 paga + 5x 1.000, a 1ª vence amanhã) + permuta 4.000
    return n.parcelas_hibrido(1000, date(2026, 9, 20), [1000.0] * 5, n.datas_continuas(date(2026, 10, 1), 5),
                              [], [], None, None, HOJE, creditos=[(date(2026, 9, 20), 4000.0)],
                              retiradas=list(retiradas), quem=quem)


def cartao_permuta():
    # R$ 5.000 = cartão 3.000 (1.500 já passou + 1.500 a passar) + permuta 2.000
    return n.parcelas_hibrido(0, None, [], [], [1500.0, 1500.0], [date(2026, 9, 10), date(2026, 10, 10)],
                              [3, 3], [True, False], HOJE, creditos=[(date(2026, 9, 1), 2000.0)])


def tres_formas():
    # R$ 9.000 = Pix 3.000 (3x 1.000, a 1ª atrasada) + cartão 3.000 + permuta 3.000 (dois valores)
    return n.parcelas_hibrido(0, None, [1000.0] * 3, n.datas_continuas(date(2026, 9, 25), 3),
                              [3000.0], [date(2026, 10, 20)], [6], [False], HOJE,
                              creditos=[(date(2026, 8, 1), 1000.0), (date(2026, 9, 1), 2000.0)],
                              retiradas=[("JANTAR", date(2026, 9, 5), 300.0)])


def montar(linhas, cid="h1", total="10000,00", **kw):
    return n.montar_cobrancas([cob(cid, total=total, **kw)], planilha(linhas, cid), HOJE)[0]


class LinhasDoCadastro(unittest.TestCase):
    def test_pix_e_permuta(self):
        linhas = pix_permuta()
        self.assertEqual([l["Nº"] for l in linhas], [0, 1, 2, 3, 4, 5, 6, 7])   # numeração única
        self.assertEqual([l["Forma"] for l in linhas], ["Pix"] * 6 + ["Crédito de permuta", "Permuta"])
        self.assertEqual([l["Status"] for l in linhas], ["Paga"] + [""] * 5 + ["Paga", "Paga"])
        self.assertEqual(linhas[7]["Produto"], "CAMISETAS")
        self.assertEqual((linhas[6]["Marcado por"], linhas[7]["Marcado por"]), ("Gabi", "Gabi"))
        self.assertEqual(linhas[6]["Pago em"], date(2026, 9, 20))
        # Pix + valor da permuta = total (retirada não entra na conta do total)
        self.assertEqual(n.conferir_total(10000, [l["Valor"] for l in linhas[:7]]), 0)

    def test_cartao_e_permuta(self):
        linhas = cartao_permuta()
        self.assertEqual([(l["Nº"], l["Forma"]) for l in linhas],
                         [(1, "Cartão"), (2, "Cartão"), (3, "Crédito de permuta")])

    def test_as_tres(self):
        linhas = tres_formas()
        self.assertEqual([(l["Nº"], l["Forma"]) for l in linhas],
                         [(1, "Pix"), (2, "Pix"), (3, "Pix"), (4, "Cartão"), (5, "Crédito de permuta"),
                          (6, "Crédito de permuta"), (7, "Permuta")])

    def test_sem_permuta_continua_igual(self):
        antes = n.parcelas_hibrido(1000, date(2026, 9, 20), [1000.0], [date(2026, 10, 20)], [1500.0],
                                   [date(2026, 10, 14)], [3], [False], HOJE)
        self.assertEqual([(l["Nº"], l["Forma"]) for l in antes], [(0, "Pix"), (1, "Pix"), (2, "Cartão")])


class Montagem(unittest.TestCase):
    def test_pix_e_permuta(self):
        c = montar(pix_permuta())
        self.assertEqual((c["tipo"], c["hibrida"], c["permuta"], c["com_permuta"]), ("Híbrido", True, False, True))
        self.assertEqual(c["formas"], ["Pix", "Permuta"])
        self.assertEqual([p["rotulo"] for p in c["parcelas"]],
                         ["Entrada no Pix", "Pix 1 de 5", "Pix 2 de 5", "Pix 3 de 5", "Pix 4 de 5", "Pix 5 de 5",
                          "Valor da permuta", "Retirada: CAMISETAS"])
        # pago e falta: só o dinheiro; a permuta tem o saldo dela
        self.assertEqual((c["pago"], c["falta"], c["atrasado"]), (1000, 5000, 0))
        self.assertEqual((c["total_permuta"], c["retirado"], c["saldo"]), (4000, 500, 3500))
        self.assertEqual([p["valor"] for p in c["creditos"]], [4000])
        self.assertEqual([p["produto"] for p in c["retiradas"]], ["CAMISETAS"])
        self.assertEqual(c["por_forma"]["Pix"], {"pago": 1000, "falta": 5000, "total": 6000, "n": 6})
        self.assertEqual(c["por_forma"]["Cartão"]["n"], 0)
        self.assertEqual(c["por_forma"]["Permuta"],
                         {"pago": 500, "falta": 3500, "total": 4000, "n": 2, "saldo": 3500})
        self.assertEqual(c["situacao"], n.CLI_EM_BREVE)   # a 1ª do Pix vence amanhã
        self.assertEqual(c["proxima"]["rotulo"], "Pix 1 de 5")
        self.assertEqual(c["ultima"], date(2027, 2, 1))   # última do Pix (a permuta não tem data de cobrar)

    def test_cartao_e_permuta(self):
        c = montar(cartao_permuta(), total="5000,00")
        self.assertEqual((c["tipo"], c["formas"]), ("Híbrido", ["Cartão", "Permuta"]))
        self.assertEqual([p["rotulo"] for p in c["parcelas"]], ["Cartão 1 de 2", "Cartão 2 de 2", "Valor da permuta"])
        self.assertEqual((c["pago"], c["falta"], c["saldo"]), (1500, 1500, 2000))
        self.assertEqual(c["situacao"], n.CLI_EM_DIA)

    def test_as_tres(self):
        c = montar(tres_formas(), total="9000,00")
        self.assertEqual(c["formas"], ["Pix", "Cartão", "Permuta"])
        self.assertEqual((c["pago"], c["falta"], c["atrasado"]), (0, 6000, 1000))
        self.assertEqual(c["situacao"], n.CLI_ATRASADO)   # a 1ª do Pix venceu em 25/09
        self.assertEqual((c["total_permuta"], c["saldo"]), (3000, 2700))
        self.assertEqual([p["rotulo"] for p in c["parcelas"]],
                         ["Pix 1 de 3", "Pix 2 de 3", "Pix 3 de 3", "Cartão 1 de 1",
                          "Valor da permuta", "Valor da permuta", "Retirada: JANTAR"])

    def test_quitada_quando_o_dinheiro_foi_pago_mesmo_com_saldo(self):
        linhas = [{**l, "Status": "Paga", "Pago em": l["Vencimento"]} for l in pix_permuta()]
        c = montar(linhas)
        self.assertEqual((c["situacao"], c["falta"]), (n.CLI_QUITADO, 0))
        self.assertEqual(c["saldo"], 3500)   # o saldo da permuta continua para retirar

    def test_valor_total_e_o_combinado_e_nao_o_da_permuta(self):
        # na híbrida o "Valor Total" (10.000) é tudo; a permuta é só a soma dos valores dela (4.000)
        c = montar(pix_permuta(), total="10000,00")
        self.assertEqual((c["valor_total"], c["total_permuta"]), (10000, 4000))
        # sem valor de permuta (só a retirada) o total da permuta é zero, nunca o "Valor Total"
        sem_valor = [l for l in pix_permuta() if l["Forma"] != n.TIPO_CREDITO]
        c = montar(sem_valor)
        self.assertEqual((c["total_permuta"], c["saldo"]), (0, -500))

    def test_retirada_que_passa_nao_mexe_na_situacao_do_dinheiro(self):
        c = montar(pix_permuta(retiradas=[("TUDO", date(2026, 9, 25), 4500.0)]))
        self.assertEqual((c["saldo"], c["por_forma"]["Permuta"]["falta"]), (-500, 0))
        self.assertEqual(c["situacao"], n.CLI_EM_BREVE)

    def test_sobrou_so_a_permuta(self):
        # o Pix foi todo removido: fica a parte da permuta, que vale pelo saldo
        so_perm = [l for l in pix_permuta() if l["Forma"] in n.LINHAS_PERMUTA]
        c = montar(so_perm)
        self.assertEqual((c["tipo"], c["hibrida"], c["permuta"], c["com_permuta"]), ("Permuta", False, False, True))
        self.assertEqual((c["pago"], c["falta"], c["saldo"], c["situacao"]), (0, 0, 3500, n.CLI_EM_DIA))

    def test_pix_e_cartao_nao_muda(self):
        linhas = n.parcelas_hibrido(1000, date(2026, 9, 20), [1000.0], [date(2026, 10, 20)], [1500.0],
                                    [date(2026, 10, 14)], [3], [False], HOJE)
        c = montar(linhas, total="3500,00")
        self.assertEqual((c["tipo"], c["formas"], c["com_permuta"]), ("Híbrido", ["Pix", "Cartão"], False))
        self.assertEqual((c["saldo"], c["total_permuta"], c["creditos"], c["retiradas"]), (0, 0, [], []))
        self.assertEqual(c["por_forma"]["Pix"], {"pago": 1000, "falta": 1000, "total": 2000, "n": 2})

    def test_permuta_inteira_continua_igual(self):
        linhas = n.parcelas_permuta([("CESTAS", date(2026, 8, 1), 800.0)], "Gabi",
                                    creditos=[(date(2026, 7, 1), 3000.0)])
        c = n.montar_cobrancas([cob("p1", tipo="Permuta", total="3000,00")], planilha(linhas, "p1"), HOJE)[0]
        self.assertEqual((c["tipo"], c["permuta"], c["com_permuta"], c["formas"]), ("Permuta", True, True, ["Permuta"]))
        self.assertEqual((c["pago"], c["falta"], c["saldo"], c["retirado"]), (800, 2200, 2200, 800))


class RelatorioEAvisos(unittest.TestCase):
    def cobs(self):
        pix = n.montar_cobrancas([cob("a1", tipo="Pix", cliente="Maria", total="900,00")],
                                 planilha([{"Nº": 1, "Vencimento": date(2026, 9, 28), "Valor": 900.0}], "a1"),
                                 HOJE)[0]
        perm = n.montar_cobrancas([cob("p1", tipo="Permuta", cliente="Padaria", total="2000,00")],
                                  planilha(n.parcelas_permuta([("BOLOS", date(2026, 9, 1), 500.0)],
                                                              creditos=[(date(2026, 8, 1), 2000.0)]), "p1"),
                                  HOJE)[0]
        return [pix, perm, montar(pix_permuta()), montar(cartao_permuta(), cid="h2", total="5000,00"),
                montar(tres_formas(), cid="h3", total="9000,00")]

    def test_resumo_dinheiro_e_saldo_para_retirar(self):
        r = n.resumo(self.cobs())
        # dinheiro: Pix 900 atrasado + híbridas (Pix/cartão); permuta inteira fora
        self.assertEqual(r["recebido"], 0 + 1000 + 1500 + 0)
        self.assertEqual(r["a_receber"], 900 + 5000 + 1500 + 6000)
        self.assertEqual(r["atrasado"], 900 + 1000)
        self.assertEqual(r["n_atrasados"], 2)
        # saldo para retirar: a permuta inteira (1.500) + a parte da permuta das três híbridas
        self.assertEqual((r["n_permutas"], r["saldo_permuta"]), (4, 1500 + 3500 + 2000 + 2700))

    def test_agenda_e_telegram_so_com_dinheiro(self):
        cobs = self.cobs()
        itens = n.agenda(cobs, date(2026, 9, 1), date(2026, 12, 31))
        self.assertTrue(itens)
        self.assertTrue(all(p["tipo"] in n.FORMAS for p, _ in itens))
        txt = notifier.montar_diario(cobs, HOJE)
        self.assertNotIn("permuta", txt.lower())
        self.assertNotIn("CAMISETAS", txt)
        self.assertIn("pix 1 de 5 (híbrido) · 01/10", txt)   # amanhã, da Loja Teste
        semanal = notifier.montar_semanal(cobs, HOJE)
        self.assertIn("Recebido: R$ 2.500,00", semanal)

    def test_filtro_forma(self):
        cobs = self.cobs()
        ids = lambda tipos: sorted(c["id"] for c in n.filtrar(cobs, tipos=tipos))
        self.assertEqual(ids(["Permuta"]), ["h1", "h2", "h3", "p1"])   # a permuta inteira E as híbridas com permuta
        self.assertEqual(ids(["Híbrido"]), ["h1", "h2", "h3"])
        self.assertEqual(ids(["Pix"]), ["a1"])                          # Pix continua só as de Pix
        self.assertEqual(ids(["Cartão"]), [])

    def test_busca(self):
        cobs = self.cobs()
        ids = lambda termo: sorted(c["id"] for c in n.filtrar(cobs, termo))
        self.assertEqual(ids("camisetas"), ["h1"])     # produto retirado
        self.assertEqual(ids("jantar"), ["h3"])
        self.assertEqual(ids("permuta"), ["h1", "h2", "h3", "p1"])

    def test_avisos_nunca_trazem_linha_de_permuta(self):
        a = n.avisos(self.cobs(), HOJE)
        todos = a["atrasadas"] + a["hoje"] + a["amanha"] + a["semana"]
        self.assertTrue(todos)
        self.assertTrue(all(p["tipo"] in n.FORMAS for p, _ in todos))


class Backup(unittest.TestCase):
    def test_excel_com_hibrida_e_permuta(self):
        import backup
        from openpyxl import load_workbook
        cab_c, cab_p = n.COBRANCAS_HEADERS, n.PARCELAS_HEADERS
        linha = lambda cab, campos: [str(campos.get(h, "")) for h in cab]
        parcelas = [linha(cab_p, l) for l in planilha(pix_permuta())]
        copia = {"feito_em": "2026-09-30T10:00:00-03:00", "impressao": "x", "planilha": "teste", "abas": {
            "_Cobrancas": [cab_c, linha(cab_c, {**cob(), "Cliente": "Loja Teste"})],
            "_Parcelas": [cab_p] + parcelas}}
        wb = load_workbook(io.BytesIO(backup.gerar_xlsx(copia)))
        resumo = [[c.value for c in r] for r in wb[backup.ABAS_LEITURA[0]].iter_rows()]
        self.assertTrue(any("Loja Teste" in r and "Híbrido" in r for r in resumo))
        formas = [r[3] for r in [[c.value for c in r] for r in wb[backup.ABAS_LEITURA[1]].iter_rows()][1:]]
        self.assertEqual(formas, ["Pix"] * 6 + ["Crédito de permuta", "Permuta"])


if __name__ == "__main__":
    unittest.main()

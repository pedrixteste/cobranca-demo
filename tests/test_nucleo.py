import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feriados as fer  # noqa: E402
import nucleo as n  # noqa: E402
import notifier  # noqa: E402

HOJE = date(2026, 9, 30)   # quarta-feira


def cob(cid="a1", tipo="Pix", cliente="Maria Souza", turma="L345", total="3000,00", sit="Ativa"):
    return {"ID": cid, "Tipo": tipo, "Cliente": cliente, "Turma": turma, "Treinamento": "",
            "Valor Total": total, "Situação": sit}


def parc(cid, num, venc, valor, status="", pago_em=""):
    return {"ID Cobrança": cid, "Nº": str(num), "Vencimento": venc, "Valor": valor,
            "Status": status, "Pago em": pago_em}


class Turma(unittest.TestCase):
    def test_formas_iguais(self):
        for t in ["L00345", "l345", "L 345", "l-0345", " L345 "]:
            self.assertEqual(n.normalizar_turma(t), "L345", t)

    def test_letras(self):
        self.assertEqual(n.treinamento_da_turma("v12"), "Vendas")
        self.assertEqual(n.treinamento_da_turma("I007"), "Impacto")
        self.assertEqual(n.treinamento_da_turma("p1"), "Perfil")
        self.assertEqual(n.treinamento_da_turma("L345"), "LORAP")

    def test_invalidas(self):
        for t in ["", "X345", "345", "L", "L0", "LL345", "L34A"]:
            self.assertIsNone(n.normalizar_turma(t), t)


class Valores(unittest.TestCase):
    def test_leitura(self):
        self.assertEqual(n.valor_para_float("1500"), 1500.0)
        self.assertEqual(n.valor_para_float("1.500,50"), 1500.5)
        self.assertEqual(n.valor_para_float("R$ 450,00"), 450.0)
        self.assertEqual(n.valor_para_float("1500.5"), 1500.5)
        self.assertIsNone(n.valor_para_float("abc"))

    def test_dividir_sobra_na_ultima(self):
        self.assertEqual(n.dividir_valor(1000, 3), [333.33, 333.33, 333.34])

    def test_resolver_valores(self):
        self.assertEqual(n.resolver_valores(1000, [None, 400, None]), [300.0, 400, 300.0])
        self.assertEqual(n.resolver_valores(900, [None, None, None]), [300.0, 300.0, 300.0])

    def test_conferir(self):
        self.assertEqual(n.conferir_total(3000, [500, 1250, 1250]), 0)
        self.assertEqual(n.conferir_total(3000, [500, 1000, 1250]), 250)


class Datas(unittest.TestCase):
    def test_continuas_fim_de_mes(self):
        self.assertEqual(n.datas_continuas(date(2026, 1, 31), 3),
                         [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_parcelas_pix_entrada_paga(self):
        linhas = n.parcelas_pix(500, date(2026, 9, 10), [250] * 2,
                                [date(2026, 10, 10), date(2026, 11, 10)], HOJE)
        self.assertEqual(linhas[0]["Nº"], 0)
        self.assertEqual(linhas[0]["Status"], n.STATUS_PAGA)
        self.assertEqual([l["Nº"] for l in linhas], [0, 1, 2])

    def test_entrada_futura_fica_aberta(self):
        linhas = n.parcelas_pix(500, date(2026, 10, 5), [250], [date(2026, 11, 5)], HOJE)
        self.assertEqual(linhas[0]["Status"], "")

    def test_sem_entrada(self):
        linhas = n.parcelas_pix(0, None, [250], [date(2026, 11, 5)], HOJE)
        self.assertEqual([l["Nº"] for l in linhas], [1])


class Situacao(unittest.TestCase):
    def montar(self, parcelas, **kw):
        return n.montar_cobrancas([cob(**kw)], parcelas, HOJE)[0]

    def test_atrasado_vence_tudo(self):
        c = self.montar([parc("a1", 1, "20/09/2026", "500,00"),
                         parc("a1", 2, "01/10/2026", "500,00")])
        self.assertEqual(c["situacao"], n.CLI_ATRASADO)
        self.assertEqual(c["dias_atraso"], 10)
        self.assertEqual(c["atrasado"], 500)
        self.assertEqual(c["parcelas"][1]["situacao"], n.SIT_EM_BREVE)

    def test_em_breve_ate_3_dias(self):
        c = self.montar([parc("a1", 1, "03/10/2026", "500,00")])
        self.assertEqual(c["situacao"], n.CLI_EM_BREVE)
        c = self.montar([parc("a1", 1, "04/10/2026", "500,00")])
        self.assertEqual(c["situacao"], n.CLI_EM_DIA)
        self.assertEqual(c["parcelas"][0]["situacao"], n.SIT_ABERTA)

    def test_vence_hoje_nao_e_atraso(self):
        c = self.montar([parc("a1", 1, "30/09/2026", "500,00")])
        self.assertEqual(c["situacao"], n.CLI_EM_BREVE)

    def test_quitado(self):
        c = self.montar([parc("a1", 0, "01/09/2026", "500,00", "Paga", "01/09/2026"),
                         parc("a1", 1, "20/09/2026", "500,00", "Paga", "19/09/2026")])
        self.assertEqual(c["situacao"], n.CLI_QUITADO)
        self.assertEqual(c["pago"], 1000)
        self.assertEqual(c["falta"], 0)

    def test_rotulos_por_posicao(self):
        # A parcela 2 foi removida: as outras continuam "1 de 2" e "2 de 2"
        c = self.montar([parc("a1", 0, "01/09/2026", "500,00", "Paga"),
                         parc("a1", 1, "01/10/2026", "500,00"),
                         parc("a1", 3, "01/12/2026", "500,00")])
        self.assertEqual([p["rotulo"] for p in c["parcelas"]],
                         ["Entrada", "Parcela 1 de 2", "Parcela 2 de 2"])
        self.assertEqual(n.proximo_numero(c["parcelas"]), 4)

    def test_rotulos_cartao(self):
        c = self.montar([parc("a1", 0, "30/09/2026", "1000,00", "Paga"),
                         parc("a1", 1, "05/10/2026", "1000,00")], tipo="Cartão")
        self.assertEqual([p["rotulo"] for p in c["parcelas"]], ["Já pago antes", "Cartão 1 de 1"])

    def test_quem_cadastrou_e_quem_marcou(self):
        c = n.montar_cobrancas([{**cob(), "Criada por": "Pedro"}],
                               [{**parc("a1", 1, "20/09/2026", "500,00", "Paga", "19/09/2026"), "Marcado por": "Ana"}],
                               HOJE)[0]
        self.assertEqual(c["criada_por"], "Pedro")
        self.assertEqual(c["parcelas"][0]["marcado_por"], "Ana")

    def test_excluida_some(self):
        cobs = n.montar_cobrancas([cob(sit="Excluída")], [parc("a1", 1, "01/09/2026", "1,00")], HOJE)
        self.assertEqual(cobs, [])


class BuscaEFiltros(unittest.TestCase):
    def setUp(self):
        self.cobs = n.montar_cobrancas(
            [cob("a1", cliente="Maria José", turma="L345"),
             cob("b2", tipo="Cartão", cliente="João Pedro", turma="V12"),
             cob("c3", cliente="Ana Lúcia", turma="I7")],
            [parc("a1", 1, "20/09/2026", "100,00"), parc("b2", 1, "02/10/2026", "100,00"),
             parc("c3", 1, "10/10/2026", "100,00", "Paga")], HOJE)

    def nomes(self, lista):
        return sorted(c["cliente"] for c in lista)

    def test_busca_sem_acento(self):
        self.assertEqual(self.nomes(n.filtrar(self.cobs, "jose")), ["Maria José"])
        self.assertEqual(self.nomes(n.filtrar(self.cobs, "ANA LUCIA")), ["Ana Lúcia"])

    def test_busca_por_turma_com_zeros(self):
        self.assertEqual(self.nomes(n.filtrar(self.cobs, "l00345")), ["Maria José"])
        self.assertEqual(self.nomes(n.filtrar(self.cobs, "lorap")), ["Maria José"])

    def test_filtros(self):
        self.assertEqual(self.nomes(n.filtrar(self.cobs, tipos=["Cartão"])), ["João Pedro"])
        self.assertEqual(self.nomes(n.filtrar(self.cobs, situacoes=[n.CLI_QUITADO])), ["Ana Lúcia"])
        self.assertEqual(self.nomes(n.filtrar(self.cobs, treinamentos=["Impacto"])), ["Ana Lúcia"])
        self.assertEqual(self.nomes(n.filtrar(self.cobs, turma="v012")), ["João Pedro"])

    def test_ordem_atrasado_primeiro(self):
        self.assertEqual([c["cliente"] for c in n.ordenar_para_cobrar(self.cobs)],
                         ["Maria José", "João Pedro", "Ana Lúcia"])

    def test_agenda_da_semana(self):
        itens = n.agenda(self.cobs, date(2026, 9, 28), date(2026, 10, 4))
        self.assertEqual([c["cliente"] for _, c in itens], ["Maria José", "João Pedro"])
        # Sem as atrasadas, a de 20/09 (fora da semana) sai
        itens = n.agenda(self.cobs, date(2026, 9, 28), date(2026, 10, 4), com_atrasadas=False)
        self.assertEqual([c["cliente"] for _, c in itens], ["João Pedro"])
        # Atrasada DENTRO do período aparece mesmo sem a opção
        itens = n.agenda(self.cobs, date(2026, 9, 1), date(2026, 9, 30), com_atrasadas=False)
        self.assertEqual([c["cliente"] for _, c in itens], ["Maria José"])

    def test_resumo(self):
        r = n.resumo(self.cobs)
        self.assertEqual((r["recebido"], r["a_receber"], r["atrasado"], r["n_atrasados"]),
                         (100, 200, 100, 1))


class Telegram(unittest.TestCase):
    def test_diario(self):
        cobs = n.montar_cobrancas(
            [cob("a1", cliente="Maria <b>"), cob("b2", tipo="Cartão", cliente="João", turma="V12")],
            [parc("a1", 1, "28/09/2026", "450,00"), parc("b2", 1, "01/10/2026", "1000,00")], HOJE)
        txt = notifier.montar_diario(cobs, HOJE)
        self.assertIn("Atrasadas", txt)
        self.assertIn("2 dias de atraso", txt)
        self.assertIn("Cobrar amanhã", txt)
        self.assertIn("passar cartão", txt)
        self.assertIn("Maria &lt;b&gt;", txt)   # nome escapado

    def test_nada_a_avisar(self):
        cobs = n.montar_cobrancas([cob()], [parc("a1", 1, "20/10/2026", "450,00")], HOJE)
        self.assertIsNone(notifier.montar_diario(cobs, HOJE))
        self.assertIn("A receber: R$ 450,00", notifier.montar_semanal(cobs, HOJE))


class PessoasEAparelhos(unittest.TestCase):
    CFG = {"pessoas": "Pedro, Gabi, Ana", "aparelho:aaaa": "Pedro", "aparelho:bbbb": "Gabi",
           "aparelho:cccc": "Fulano", "aparelho:dddd": ""}

    def test_admin_e_o_primeiro_ou_o_escolhido(self):
        self.assertEqual(n.administrador(self.CFG), "Pedro")
        self.assertEqual(n.administrador({**self.CFG, "admin": "Gabi"}), "Gabi")
        self.assertEqual(n.administrador({**self.CFG, "admin": "Quem"}), "Pedro")
        self.assertEqual(n.administrador({}), "")

    def test_aparelho_preso(self):
        self.assertEqual(n.nome_do_aparelho(self.CFG, "bbbb"), "Gabi")
        self.assertEqual(n.nome_do_aparelho(self.CFG, "cccc"), "")   # pessoa removida
        self.assertEqual(n.nome_do_aparelho(self.CFG, "dddd"), "")   # aparelho desligado
        self.assertEqual(n.nome_do_aparelho(self.CFG, "zzzz"), "")
        self.assertEqual(n.nome_do_aparelho(self.CFG, ""), "")

    def test_so_nome_sem_aparelho_fica_livre(self):
        self.assertEqual(n.nomes_livres(self.CFG), ["Ana"])

    def test_liberar_deixa_escolher_de_novo(self):
        self.assertEqual(n.nomes_livres({**self.CFG, "liberado:Gabi": "sim"}), ["Gabi", "Ana"])
        self.assertEqual(n.nomes_livres({**self.CFG, "liberado:Gabi": ""}), ["Ana"])

    def test_desligar_aparelho_libera_o_nome(self):
        self.assertEqual(n.nomes_livres({**self.CFG, "aparelho:bbbb": ""}), ["Gabi", "Ana"])


class Observacoes(unittest.TestCase):
    def setUp(self):
        self.cobs = n.montar_cobrancas(
            [{**cob("a1", cliente="Maria"), "Observações": "metade em permuta"},
             cob("b2", cliente="João", turma="V12"),
             cob("c3", cliente="Ana", turma="I7")],
            [parc("a1", 1, "20/10/2026", "100,00"),
             {**parc("b2", 1, "20/10/2026", "100,00"), "Observação": "pagou com serviço de pintura"},
             parc("c3", 1, "20/10/2026", "100,00")], HOJE)

    def test_tem_obs_na_cobranca_ou_na_parcela(self):
        self.assertEqual({c["cliente"]: c["tem_obs"] for c in self.cobs},
                         {"Maria": True, "João": True, "Ana": False})
        self.assertEqual(self.cobs[1]["parcelas"][0]["observacao"], "pagou com serviço de pintura")

    def test_filtro_com_e_sem(self):
        self.assertEqual(sorted(c["cliente"] for c in n.filtrar(self.cobs, obs="com")), ["João", "Maria"])
        self.assertEqual([c["cliente"] for c in n.filtrar(self.cobs, obs="sem")], ["Ana"])
        self.assertEqual(len(n.filtrar(self.cobs)), 3)

    def test_busca_acha_palavra_da_observacao(self):
        self.assertEqual([c["cliente"] for c in n.filtrar(self.cobs, "permuta")], ["Maria"])
        self.assertEqual([c["cliente"] for c in n.filtrar(self.cobs, "pintura")], ["João"])


class CartaoParcelado(unittest.TestCase):
    def test_vezes_de_cada_passada(self):
        linhas = n.parcelas_cartao(0, HOJE, [8000.0, 4000.0], [date(2026, 10, 5), date(2027, 6, 5)], [8, 4])
        self.assertEqual([l["Vezes no cartão"] for l in linhas], [8, 4])
        self.assertEqual([l["Nº"] for l in linhas], [1, 2])

    def test_sem_vezes_e_a_vista(self):
        linhas = n.parcelas_cartao(1000, HOJE, [500.0], [date(2026, 10, 5)])
        self.assertEqual(linhas[1]["Vezes no cartão"], 1)
        self.assertNotIn("Vezes no cartão", linhas[0])      # o "já pago" não tem parcelamento

    def test_texto(self):
        self.assertEqual(n.texto_vezes(8000, 8), "8x de R$ 1.000,00")
        self.assertEqual(n.texto_vezes(8000, 1), "à vista")
        self.assertEqual(n.texto_vezes(1000, 3), "3x de R$ 333,33")

    def test_leitura_da_planilha(self):
        c = n.montar_cobrancas([cob(tipo="Cartão")],
                               [{**parc("a1", 1, "05/10/2026", "8000,00"), "Vezes no cartão": "8"},
                                {**parc("a1", 2, "05/06/2027", "4000,00"), "Vezes no cartão": ""},
                                {**parc("a1", 3, "05/07/2027", "100,00"), "Vezes no cartão": "abc"}], HOJE)[0]
        self.assertEqual([p["vezes"] for p in c["parcelas"]], [8, 1, 1])

    def test_aviso_do_telegram_diz_em_quantas_vezes(self):
        cobs = n.montar_cobrancas([cob(tipo="Cartão")],
                                  [{**parc("a1", 1, "30/09/2026", "8000,00"), "Vezes no cartão": "8"}], HOJE)
        self.assertIn("passar cartão em 8x", notifier.montar_diario(cobs, HOJE))


class Cidade(unittest.TestCase):
    def setUp(self):
        self.cobs = n.montar_cobrancas(
            [{**cob("a1", cliente="Maria", turma="L345"), "Cidade": "Lajeado"},
             {**cob("b2", cliente="João", turma="L345"), "Cidade": "Lajeado"},
             {**cob("c3", cliente="Ana", turma="L345"), "Cidade": "Laj"},
             {**cob("d4", cliente="Rui", turma="V12"), "Cidade": "SCS"},
             cob("e5", cliente="Bia", turma="I7")],
            [parc(i, 1, "20/10/2026", "100,00") for i in ("a1", "b2", "c3", "d4", "e5")], HOJE)

    def test_texto_livre_e_opcional(self):
        self.assertEqual([c["cidade"] for c in self.cobs], ["Lajeado", "Lajeado", "Laj", "SCS", ""])

    def test_local(self):
        self.assertEqual(n.local_da_cobranca(self.cobs[0]), "L345 · LORAP · Lajeado")
        self.assertEqual(n.local_da_cobranca(self.cobs[4]), "I7 · Impacto")

    def test_busca_por_cidade(self):
        self.assertEqual(sorted(c["cliente"] for c in n.filtrar(self.cobs, "lajeado")), ["João", "Maria"])
        self.assertEqual([c["cliente"] for c in n.filtrar(self.cobs, "scs")], ["Rui"])

    def test_sugestao_e_a_mais_usada_da_turma(self):
        self.assertEqual(n.cidade_da_turma(self.cobs, "L345"), "Lajeado")
        self.assertEqual(n.cidade_da_turma(self.cobs, "I7"), "")
        self.assertEqual(n.cidade_da_turma(self.cobs, "P1"), "")

    def test_aviso_do_telegram_leva_a_cidade(self):
        cobs = n.montar_cobrancas([{**cob(), "Cidade": "Lajeado"}], [parc("a1", 1, "30/09/2026", "450,00")], HOJE)
        self.assertIn("(L345 · Lajeado)", notifier.montar_diario(cobs, HOJE))


class Notificacoes(unittest.TestCase):
    CFG = {"telegram:Pedro": "111", "telegram:Ana": "222", "avisos:Ana": "nao", "telegram:Zé": "",
           "avisar_amanha": "não", "pessoas": "Pedro, Ana, Zé"}

    def test_destinatarios_respeita_pausa_e_sem_chat(self):
        self.assertEqual(n.destinatarios(self.CFG), [("Pedro", "111")])

    def test_opcoes_comecam_ligadas(self):
        self.assertEqual(n.opcoes_avisos({}), {k: True for k in n.OPCOES_AVISO})
        self.assertFalse(n.opcoes_avisos(self.CFG)["avisar_amanha"])

    def test_secao_desligada_some_da_mensagem(self):
        cobs = n.montar_cobrancas([cob()], [parc("a1", 1, "28/09/2026", "450,00"),
                                            parc("a1", 2, "01/10/2026", "450,00")], HOJE)
        txt = notifier.montar_diario(cobs, HOJE, n.opcoes_avisos(self.CFG))
        self.assertIn("Atrasadas", txt)
        self.assertNotIn("Cobrar amanhã", txt)
        so_amanha = n.montar_cobrancas([cob()], [parc("a1", 1, "01/10/2026", "450,00")], HOJE)
        self.assertIsNone(notifier.montar_diario(so_amanha, HOJE, n.opcoes_avisos(self.CFG)))


class Feriados(unittest.TestCase):
    def test_pascoa(self):
        self.assertEqual(fer.pascoa(2026), date(2026, 4, 5))
        self.assertEqual(fer.pascoa(2027), date(2027, 3, 28))
        self.assertEqual(fer.pascoa(2025), date(2025, 4, 20))

    def test_nacionais_de_2026(self):
        nac = [(f["data"], f["nome"]) for f in fer.feriados(2026) if f["nacional"]]
        self.assertEqual(len(nac), 10)
        self.assertIn((date(2026, 4, 3), "Sexta-feira Santa (Paixão de Cristo)"), nac)
        self.assertIn((date(2026, 11, 20), "Dia da Consciência Negra"), nac)
        self.assertEqual([d for d, _ in nac], sorted(d for d, _ in nac))

    def test_facultativos(self):
        fac = {f["nome"]: f["data"] for f in fer.feriados(2026) if not f["nacional"]}
        self.assertEqual(fac["Carnaval (terça)"], date(2026, 2, 17))
        self.assertEqual(fac["Corpus Christi"], date(2026, 6, 4))

    def test_proximo(self):
        self.assertEqual(fer.proximo(HOJE)["nome"], "Nossa Senhora Aparecida")
        self.assertEqual(fer.proximo(date(2026, 12, 26))["data"], date(2027, 1, 1))


if __name__ == "__main__":
    unittest.main()

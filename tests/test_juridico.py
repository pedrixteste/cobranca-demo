"""
Jurídico (pedido 03/11): cobranças judiciais e protestos, e a leitura da planilha com prazo e
nova tentativa (a lentidão / tela pela metade relatada no mesmo dia).
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dados  # noqa: E402
import notifier  # noqa: E402
import nucleo as n  # noqa: E402

HOJE = date(2026, 11, 3)


def linha_jud(jid="j1", neg="", acordo="", valor="4800,00", sit="Ativa", adv="DRA. X", cliente="LOJA A"):
    return {"ID": jid, "Cliente": cliente, "Turma": "L340", "Objeto": "Cheque", "Valor cobrado": valor,
            "No jurídico desde": "01/08/2026", "Advogado": adv, "Negociação": neg,
            "Valor do acordo": "", "Acordo": acordo, "Situação": sit}


class Acordo(unittest.TestCase):
    def test_texto_ida_e_volta(self):
        ps = n.parcelas_do_acordo([500.0, 500.5], [date(2026, 12, 10), date(2027, 1, 10)])
        ps = n.marcar_parcela_acordo(ps, 1, True, date(2026, 12, 8), "Ana")
        txt = n.acordo_para_texto(ps)
        self.assertEqual(txt, "1 | 500,00 | 10/12/2026 | Paga | 08/12/2026 | Ana\n2 | 500,50 | 10/01/2027")
        volta = n.acordo_do_texto(txt)
        self.assertEqual([p["valor"] for p in volta], [500.0, 500.5])
        self.assertEqual(volta[0]["pago_em"], date(2026, 12, 8))
        self.assertEqual(volta[0]["marcado_por"], "Ana")
        self.assertFalse(volta[1]["paga"])

    def test_nome_com_barra_nao_quebra_a_celula(self):
        ps = n.marcar_parcela_acordo(n.parcelas_do_acordo([10.0], [HOJE]), 1, True, HOJE, "A|B\nC")
        volta = n.acordo_do_texto(n.acordo_para_texto(ps))
        self.assertEqual(len(volta), 1)
        self.assertEqual(volta[0]["marcado_por"], "A B C")

    def test_linha_estragada_continua_aparecendo(self):
        volta = n.acordo_do_texto("1 | abc | xx\n\n2 | 300,00 | 10/01/2027")
        self.assertEqual(len(volta), 2)
        self.assertEqual(volta[0]["valor"], 0.0)
        self.assertIsNone(volta[0]["vencimento"])

    def test_edicao_mantem_as_pagas_pela_posicao(self):
        antes = n.marcar_parcela_acordo(n.parcelas_do_acordo([100.0] * 3, [HOJE] * 3), 2, True, HOJE, "Gabi")
        depois = n.parcelas_do_acordo([50.0] * 4, [HOJE] * 4, antes)
        self.assertEqual([p["paga"] for p in depois], [False, True, False, False])
        self.assertEqual(depois[1]["marcado_por"], "Gabi")

    def test_desmarcar(self):
        ps = n.marcar_parcela_acordo(n.parcelas_do_acordo([100.0], [HOJE]), 1, True, HOJE, "Ana")
        ps = n.marcar_parcela_acordo(ps, 1, False)
        self.assertEqual((ps[0]["paga"], ps[0]["pago_em"], ps[0]["marcado_por"]), (False, None, ""))

    def test_marcar_fora_da_lista_nao_mexe(self):
        ps = n.parcelas_do_acordo([100.0], [HOJE])
        self.assertEqual(n.marcar_parcela_acordo(ps, 5, True, HOJE), ps)


class Judiciais(unittest.TestCase):
    def test_sem_acordo(self):
        j = n.montar_judiciais([linha_jud()], HOJE)[0]
        self.assertEqual(j["situacao"], n.JUD_SEM_ACORDO)
        self.assertEqual(j["valor"], 4800.0)
        self.assertEqual(j["desde"], date(2026, 8, 1))
        self.assertEqual(j["parcelas"], [])

    def test_acordo_atrasado_e_contas(self):
        txt = "1 | 600,00 | 01/09/2026 | Paga | 01/09/2026 | Ana\n2 | 600,00 | 01/10/2026\n3 | 600,00 | 01/12/2026"
        j = n.montar_judiciais([linha_jud(neg="Parcelado", acordo=txt)], HOJE)[0]
        self.assertEqual(j["situacao"], n.CLI_ATRASADO)
        self.assertEqual((j["pago"], j["falta"], j["atrasado"]), (600.0, 1200.0, 600.0))
        self.assertEqual(j["dias_atraso"], 33)
        self.assertEqual(j["proxima"]["vencimento"], date(2026, 12, 1))
        self.assertEqual(j["parcelas"][1]["rotulo"], "Parcela 2 de 3")
        self.assertEqual(j["valor_acordo"], 1800.0)   # sem "Valor do acordo": a soma das parcelas

    def test_a_vista_quitado_e_em_breve(self):
        pago = n.montar_judiciais([linha_jud(neg="À vista", acordo="1 | 900,00 | 01/11/2026 | Paga | 01/11/2026")],
                                  HOJE)[0]
        self.assertEqual(pago["situacao"], n.CLI_QUITADO)
        self.assertEqual(pago["parcelas"][0]["rotulo"], "Acordo à vista")
        breve = n.montar_judiciais([linha_jud(neg="À vista", acordo="1 | 900,00 | 05/11/2026")], HOJE)[0]
        self.assertEqual(breve["situacao"], n.CLI_EM_BREVE)

    def test_negociacao_sem_parcela_vira_sem_acordo(self):
        j = n.montar_judiciais([linha_jud(neg="Parcelado", acordo="")], HOJE)[0]
        self.assertEqual((j["negociacao"], j["situacao"]), (n.NEG_SEM, n.JUD_SEM_ACORDO))

    def test_acordo_ignorado_sem_negociacao(self):
        j = n.montar_judiciais([linha_jud(neg="", acordo="1 | 900,00 | 05/11/2026")], HOJE)[0]
        self.assertEqual(j["parcelas"], [])

    def test_excluida_some(self):
        linhas = [linha_jud("a"), linha_jud("b", sit="Excluída"), {"ID": ""}]
        self.assertEqual([j["id"] for j in n.montar_judiciais(linhas, HOJE)], ["a"])
        self.assertEqual(len(n.montar_judiciais(linhas, HOJE, incluir_excluidas=True)), 2)

    def test_ordem(self):
        linhas = [linha_jud("quit", "À vista", "1 | 1,00 | 01/10/2026 | Paga | 01/10/2026", cliente="A"),
                  linha_jud("sem", cliente="B"),
                  linha_jud("atr", "À vista", "1 | 1,00 | 01/10/2026", cliente="C"),
                  linha_jud("dia", "À vista", "1 | 1,00 | 01/12/2026", cliente="D")]
        ids = [j["id"] for j in n.ordenar_judiciais(n.montar_judiciais(linhas, HOJE))]
        self.assertEqual(ids, ["atr", "sem", "dia", "quit"])

    def test_busca(self):
        j = n.montar_judiciais([linha_jud(adv="DR. FULANO DE TAL")], HOJE)[0]
        for termo in ["loja", "l00340", "cheque", "fulano", ""]:
            self.assertTrue(n.casa_busca_juridico(j, termo), termo)
        self.assertFalse(n.casa_busca_juridico(j, "v12"))

    def test_advogados_usados(self):
        js = n.montar_judiciais([linha_jud("a", adv="DRA. B"), linha_jud("b", adv="DR. A"),
                                 linha_jud("c", adv="dra. b"), linha_jud("d", adv="")], HOJE)
        self.assertEqual(n.advogados_usados(js), ["DRA. B", "DR. A"])


class Protestos(unittest.TestCase):
    def test_montar_e_ordem(self):
        linhas = [
            {"ID": "p1", "Cliente": "A", "Turma": "I5", "Objeto": "Ficha", "Protestado em": "01/09/2026"},
            {"ID": "p2", "Cliente": "B", "Turma": "L1", "Objeto": "Cheque", "Protestado em": "01/07/2026"},
            {"ID": "p3", "Cliente": "C", "Turma": "L2", "Objeto": "Cheque", "Protestado em": "01/06/2026",
             "Pago": "Sim", "Pago em": "01/10/2026", "Marcado por": "Ana"},
            {"ID": "p4", "Cliente": "D", "Situação": "Excluída"},
        ]
        ps = n.ordenar_protestos(n.montar_protestos(linhas))
        self.assertEqual([p["id"] for p in ps], ["p2", "p1", "p3"])
        self.assertTrue(ps[2]["pago"])
        self.assertEqual(ps[2]["pago_em"], date(2026, 10, 1))
        r = n.resumo_juridico([], ps)
        self.assertEqual((r["n_protestos"], r["n_protestos_abertos"]), (3, 2))

    def test_pago_desmarcado_ignora_data_velha(self):
        p = n.montar_protestos([{"ID": "x", "Pago": "", "Pago em": "01/10/2026", "Marcado por": "Ana"}])[0]
        self.assertEqual((p["pago"], p["pago_em"], p["marcado_por"]), (False, None, ""))


class AcessoSoJuridico(unittest.TestCase):
    """Pedido 04/11: pessoa com acesso só ao Jurídico não pode chegar em mais nada."""
    CFG = {"pessoas": "Pedro, Ana, Jur", "admin": "Pedro", "acesso:Jur": "juridico",
           "telegram:Pedro": "1", "telegram:Ana": "2", "telegram:Jur": "3", "telegram:Removida": "4"}

    def test_quem_e_restrito(self):
        self.assertTrue(n.so_juridico(self.CFG, "Jur"))
        self.assertFalse(n.so_juridico(self.CFG, "Ana"))
        self.assertFalse(n.so_juridico(self.CFG, ""))
        self.assertEqual(n.pessoas_restritas(self.CFG), ["Jur"])
        self.assertTrue(n.so_juridico({**self.CFG, "acesso:Jur": " JURÍDICO "}, "Jur"))   # escrito à mão na planilha

    def test_administrador_nunca_fica_restrito(self):
        self.assertFalse(n.so_juridico({**self.CFG, "acesso:Pedro": "juridico"}, "Pedro"))

    def test_fecha_por_padrao(self):
        # auditoria 04/11: só vazio ou "tudo" dá acesso a tudo; qualquer outra coisa restringe
        self.assertTrue(n.so_juridico({**self.CFG, "acesso:Ana": "outra coisa"}, "Ana"))
        self.assertTrue(n.so_juridico({**self.CFG, "acesso:Ana": "só jurídico"}, "Ana"))
        self.assertFalse(n.so_juridico({**self.CFG, "acesso:Ana": "Tudo"}, "Ana"))
        # quem saiu da lista de pessoas (removida com o app aberto) não tem acesso a tudo
        self.assertTrue(n.so_juridico(self.CFG, "Removida"))
        self.assertTrue(n.so_juridico({**self.CFG, "pessoas": "Pedro, Ana"}, "Jur"))

    def test_telegram_nao_vai_para_restrito_nem_para_removido(self):
        self.assertEqual(n.destinatarios(self.CFG), [("Ana", "2"), ("Pedro", "1")])

    def test_trava_por_aparelho_com_restrito_libera_por_codigo(self):
        sem_restrito = {k: v for k, v in self.CFG.items() if k != "acesso:Jur"}
        self.assertEqual(n.nomes_livres(sem_restrito), ["Pedro", "Ana", "Jur"])   # como sempre foi
        aparelho = "ab12cd" + "0" * 18
        self.assertEqual(n.nomes_livres(self.CFG, aparelho), [])                  # ninguém pega nome alheio
        # liberação antiga ("sim") não vale mais para qualquer aparelho
        self.assertEqual(n.nomes_livres({**self.CFG, "liberado:Ana": "sim"}, aparelho), [])
        # liberada para ESTE aparelho (código completo): só ele vê o nome
        cfg = {**self.CFG, "liberado:Ana": aparelho.upper()}
        self.assertEqual(n.nomes_livres(cfg, aparelho), ["Ana"])
        self.assertEqual(n.nomes_livres(cfg, "ffffff" + "0" * 18), [])
        self.assertEqual(n.nomes_livres(cfg, ""), [])
        # as 6 letras curtas não bastam (dava para fabricar um aparelho começando com elas)
        self.assertEqual(n.nomes_livres({**self.CFG, "liberado:Ana": "AB12CD"}, aparelho), [])
        self.assertEqual(n.nomes_livres(cfg, "ab12cd" + "1" * 18), [])

    def test_liberacao_por_codigo_continua_depois_que_a_restrita_sai(self):
        cfg = {"pessoas": "Pedro, Ana", "admin": "Pedro", "liberacao_por_codigo": "sim"}
        self.assertTrue(n.liberacao_por_codigo(cfg))
        self.assertEqual(n.nomes_livres(cfg, "ab12cd" + "0" * 18), [])
        self.assertFalse(n.liberacao_por_codigo({"pessoas": "Pedro, Ana"}))

    def test_demonstracao_fora_da_lista_nao_restringe(self):
        self.assertFalse(n.so_juridico({"pessoas": ""}, "Visitante", fora_da_lista_restringe=False))
        self.assertTrue(n.so_juridico({"pessoas": "", "acesso:V": "juridico"}, "V", fora_da_lista_restringe=False))


class Blindagem(unittest.TestCase):
    """Achados da auditoria de 04/11: entrada que derrubava a tela ou virava imagem de outro site."""

    def test_valor_absurdo_vira_ilegivel(self):
        self.assertIsNone(n.valor_para_float("2" + "0" * 306))
        self.assertIsNone(n.valor_para_float("99999999999"))
        self.assertEqual(n.valor_para_float("9.999.999.999,00"), 9999999999.0)

    def test_acordo_com_valor_absurdo_nao_derruba_as_contas(self):
        j = n.montar_judiciais([linha_jud(neg="À vista", acordo="1 | " + "2" + "0" * 306 + " | 01/10/2026 | Paga")],
                               HOJE)[0]
        self.assertEqual(j["pago"], 0.0)

    def test_acordo_gigante_e_cortado(self):
        txt = "\n".join(f"{i} | 1,00 | 01/01/2027" for i in range(1, 5000))
        self.assertEqual(len(n.acordo_do_texto(txt)), n.MAX_PARCELAS_ACORDO)

    def test_texto_limpo_uma_linha_sem_html(self):
        self.assertEqual(n.texto_limpo("FULANO\n\n<img src=x>\x07 B"), "FULANO img src=x B")
        # sinais de nome de verdade ficam (a proteção contra Markdown é na hora de mostrar)
        self.assertEqual(n.texto_limpo("JOSÉ (FILHO) & CIA_LTDA. D'ÁVILA / 2"), "JOSÉ (FILHO) & CIA_LTDA. D'ÁVILA / 2")
        j = n.montar_judiciais([linha_jud(cliente="A\n\nB", adv="C\r\nD")], HOJE)[0]
        self.assertEqual((j["cliente"], j["advogado"]), ("A B", "C D"))


class LocalJuridico(unittest.TestCase):
    """O arquivo de teste (Local) grava e relê as abas novas igual à planilha."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.banco = dados.Local(os.path.join(self.tmp.name, "b.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_criar_atualizar_e_reler(self):
        jid = self.banco.criar_registro(dados.ABA_JUDICIAL, {"Cliente": "X", "Valor cobrado": 100.0,
                                                             "No jurídico desde": HOJE, "Situação": "Ativa"})
        pid = self.banco.criar_registro(dados.ABA_PROTESTOS, {"Cliente": "Y", "Pago": True, "Situação": "Ativa"})
        self.assertTrue(self.banco.atualizar_registro(dados.ABA_JUDICIAL, jid, {"Advogado": "DR. Z"}))
        self.assertFalse(self.banco.atualizar_registro(dados.ABA_PROTESTOS, "nao-existe", {"Pago": False}))
        d = self.banco.carregar()
        self.assertEqual(d["judiciais"][0]["Valor cobrado"], "100,00")
        self.assertEqual(d["judiciais"][0]["No jurídico desde"], "03/11/2026")
        self.assertEqual(d["judiciais"][0]["Advogado"], "DR. Z")
        self.assertEqual(d["protestos"][0]["Pago"], "Sim")
        self.assertEqual(d["protestos"][0]["ID"], pid)

    def test_historico_guarda_antes_e_depois(self):
        h = {"Quando": "04/11/2026 10:00:00", "Quem": "Jur", "Ação": "cadastro"}
        jid = self.banco.criar_registro(dados.ABA_JUDICIAL, {"Cliente": "X", "Advogado": "A"}, historico=h)
        self.banco.atualizar_registro(dados.ABA_JUDICIAL, jid, {"Advogado": "B"}, historico={**h, "Ação": "edição"})
        self.banco.atualizar_registro(dados.ABA_JUDICIAL, jid, {"Cliente": "Y"})   # sem histórico: não registra
        hist = self.banco.historico()
        self.assertEqual([x["Ação"] for x in hist], ["cadastro", "edição"])
        self.assertEqual(json.loads(hist[1]["Antes"]), {"Advogado": "A"})
        self.assertEqual(json.loads(hist[1]["Depois"]), {"Advogado": "B"})
        self.assertEqual((hist[1]["Quem"], hist[1]["Aba"], hist[1]["ID"]), ("Jur", dados.ABA_JUDICIAL, jid))

    def test_arquivo_antigo_sem_as_abas_novas(self):
        d = self.banco.carregar()
        self.assertEqual((d["judiciais"], d["protestos"]), ([], []))

    def test_falha_simulada(self):
        flag = os.path.join(self.tmp.name, "fora")
        with mock.patch.dict(os.environ, {"COBRANCA_FALHA": flag}):
            self.banco.carregar()   # sem o arquivo: normal
            Path(flag).touch()
            with self.assertRaises(RuntimeError):
                self.banco.carregar()


class ClientePaciente(unittest.TestCase):
    """Leitura tenta de novo em falha passageira; gravação nunca (repetir podia duplicar linha)."""

    def setUp(self):
        import requests
        from gspread.exceptions import APIError
        self.requests, self.APIError = requests, APIError
        self.Cliente = dados._cliente_paciente()

    def _erro(self, codigo):
        resp = mock.Mock(status_code=codigo)
        resp.json.return_value = {"error": {"code": codigo, "message": "x", "status": "x"}}
        return self.APIError(resp)

    def _rodar(self, metodo, efeitos):
        cliente = self.Cliente.__new__(self.Cliente)
        with mock.patch("gspread.http_client.HTTPClient.request", side_effect=efeitos) as req, \
                mock.patch("dados.time.sleep") as dorme:
            try:
                return cliente.request(metodo, "url"), req.call_count, dorme.call_count
            except Exception as e:
                return e, req.call_count, dorme.call_count

    def test_leitura_tenta_de_novo_e_consegue(self):
        r, chamadas, esperas = self._rodar("get", [self._erro(429), self.requests.Timeout(), "ok"])
        self.assertEqual((r, chamadas, esperas), ("ok", 3, 2))

    def test_leitura_desiste_depois_de_3(self):
        r, chamadas, _ = self._rodar("get", [self._erro(503)] * 5)
        self.assertIsInstance(r, self.APIError)
        self.assertEqual(chamadas, 3)

    def test_erro_que_nao_passa_nao_repete(self):
        r, chamadas, _ = self._rodar("get", [self._erro(403), "ok"])
        self.assertIsInstance(r, self.APIError)
        self.assertEqual(chamadas, 1)

    def test_gravacao_nunca_repete(self):
        for metodo in ("post", "put"):
            r, chamadas, _ = self._rodar(metodo, [self.requests.Timeout(), "ok"])
            self.assertIsInstance(r, self.requests.Timeout)
            self.assertEqual(chamadas, 1, metodo)

    def test_planilha_tem_prazo(self):
        with mock.patch("gspread.service_account_from_dict") as sa:
            dados.Planilha("id", {})
        _, kwargs = sa.call_args
        self.assertEqual(kwargs["http_client"].__mro__[1].__name__, "HTTPClient")
        sa.return_value.set_timeout.assert_called_once_with(dados.TEMPO_LIMITE)


class AvisosJuridico(unittest.TestCase):
    """Pedido 04/11: avisos do Jurídico no Telegram, no padrão das cobranças."""
    # HOJE = terça 03/11/2026; domingo da semana = 08/11
    TXT = ("1 | 600,00 | 01/09/2026 | Paga | 01/09/2026 | Ana\n2 | 600,00 | 30/10/2026\n"
           "3 | 600,00 | 03/11/2026\n4 | 600,00 | 04/11/2026\n5 | 600,00 | 06/11/2026\n6 | 600,00 | 30/11/2026")
    CFG = {"pessoas": "Pedro, Ana, Jur", "admin": "Pedro", "acesso:Jur": "juridico",
           "telegram:Pedro": "1", "telegram:Ana": "2", "telegram:Jur": "3", "avisos:Ana": "nao",
           "telegram:Removida": "9"}

    def judiciais(self):
        return n.montar_judiciais([linha_jud(neg="Parcelado", acordo=self.TXT, cliente="LOJA ACORDO"),
                                   linha_jud("j2", cliente="SEM ACORDO")], HOJE)

    def test_separa_como_as_cobrancas(self):
        a = n.avisos_juridico(self.judiciais(), HOJE)
        self.assertEqual([p["n"] for p, _ in a["atrasadas"]], [2])
        self.assertEqual([p["n"] for p, _ in a["hoje"]], [3])
        self.assertEqual([p["n"] for p, _ in a["amanha"]], [4])
        self.assertEqual([p["n"] for p, _ in a["semana"]], [5])   # a 6ª é depois do domingo

    def test_quem_recebe(self):
        self.assertEqual(n.destinatarios(self.CFG), [("Pedro", "1")])                       # cobranças
        self.assertEqual(n.destinatarios_juridico(self.CFG), [("Jur", "3"), ("Pedro", "1")])  # Jurídico

    def test_mensagem_diaria(self):
        txt = notifier.montar_juridico(self.judiciais(), [], HOJE)
        self.assertIn("⚖️ <b>Jurídico · terça, 03/11/2026</b>", txt)
        self.assertIn("🔴 <b>Acordos atrasados</b> (1 · R$ 600,00)", txt)
        self.assertIn("• <b>LOJA ACORDO</b> (L340 · Cheque) · R$ 600,00 · parcela 2 de 6 · 30/10 (4 dias de atraso)", txt)
        self.assertIn("🚨 <b>Vence hoje</b>", txt)
        self.assertIn("⚠️ <b>Vence amanhã</b>", txt)
        self.assertNotIn("Resto da semana", txt)

    def test_sem_nada_no_dia_nao_manda(self):
        sem = n.montar_judiciais([linha_jud(neg="À vista", acordo="1 | 100,00 | 30/12/2026")], HOJE)
        self.assertIsNone(notifier.montar_juridico(sem, [], HOJE))
        self.assertIsNone(notifier.montar_juridico([], [], HOJE, semanal=True))

    def test_semanal_tem_o_geral(self):
        prot = n.montar_protestos([{"ID": "p", "Cliente": "X"}, {"ID": "q", "Cliente": "Y", "Pago": "Sim"}])
        txt = notifier.montar_juridico(self.judiciais(), prot, HOJE, semanal=True)
        self.assertIn("Jurídico da semana · 03/11 a 08/11/2026", txt)
        self.assertIn("📅 <b>Resto da semana</b>", txt)
        self.assertIn("Na justiça: 2 (1 sem acordo)", txt)
        self.assertIn("Acordos: recebido R$ 600,00 · falta R$ 3.000,00 · atrasado R$ 600,00", txt)
        self.assertIn("Protestos em aberto: 1", txt)

    def test_desligado_na_tela_notificacoes(self):
        self.assertIsNone(notifier.montar_juridico(self.judiciais(), [], HOJE, opcoes={"avisar_juridico": False}))

    def test_cada_um_recebe_o_que_pode(self):
        msgs = notifier.mensagens_por_chat(self.CFG, "COBRANÇAS", "JURÍDICO", ["7"])
        self.assertEqual(msgs["1"], "COBRANÇAS\n\nJURÍDICO")   # Pedro: tudo
        self.assertEqual(msgs["3"], "JURÍDICO")                # Jur: nunca as cobranças
        self.assertEqual(msgs["7"], "COBRANÇAS\n\nJURÍDICO")   # TELEGRAM_CHAT_IDS antigo = tudo
        self.assertNotIn("2", msgs)                             # Ana pausou
        self.assertNotIn("9", msgs)                             # removida
        so_cob = notifier.mensagens_por_chat(self.CFG, "COBRANÇAS", None)
        self.assertEqual(set(so_cob), {"1"})                    # sem Jurídico no dia: a Jur não recebe nada
        self.assertEqual(notifier.mensagens_por_chat(self.CFG, None, None), {})

    def test_nome_com_html_no_telegram(self):
        j = n.montar_judiciais([linha_jud(neg="À vista", acordo="1 | 100,00 | 03/11/2026", cliente="<b>X</b> & Y")], HOJE)
        txt = notifier.montar_juridico(j, [], HOJE)
        self.assertIn("b X /b &amp; Y", txt)
        self.assertNotIn("<b>X</b>", txt)


if __name__ == "__main__":
    unittest.main()

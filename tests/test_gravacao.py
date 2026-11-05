"""
Cadastro que "não salvava" (05/11/2026): a gravação de uma cobrança nova não pode duplicar nem ficar
pela metade. Com o mesmo ID numa nova tentativa, criar_cobranca não grava de novo o que já entrou.
(A parte da tela, rodada interrompida no meio da gravação, é testada por ferramentas/teste_salvar_lento.py)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dados  # noqa: E402
import nucleo as n  # noqa: E402

CAMPOS = {"Tipo": "Pix", "Cliente": "MARIA", "Turma": "L345", "Treinamento": "LORAP", "Valor Total": 3000.0,
          "Criada em": date(2026, 11, 5), "Criada por": "Ana"}
PARCELAS = n.parcelas_pix(0, None, [1000.0] * 3, n.datas_continuas(date(2026, 12, 5), 3), date(2026, 11, 5))


class LocalNaoDuplica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caminho = os.path.join(self.tmp.name, "t.local.json")
        self.banco = dados.Local(self.caminho)

    def tearDown(self):
        self.tmp.cleanup()

    def contar(self, cid):
        d = json.loads(Path(self.caminho).read_text(encoding="utf-8"))
        return (sum(1 for c in d["cobrancas"] if c["ID"] == cid),
                sum(1 for p in d["parcelas"] if p["ID Cobrança"] == cid))

    def test_mesmo_id_duas_vezes_grava_uma(self):
        self.assertEqual(self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345"), "abc12345")
        self.assertEqual(self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345"), "abc12345")
        self.assertEqual(self.contar("abc12345"), (1, 3))
        self.assertTrue(self.banco.cobranca_existe("abc12345"))
        self.assertFalse(self.banco.cobranca_existe("outro"))

    def test_sem_id_continua_gerando_um_novo(self):
        a = self.banco.criar_cobranca(CAMPOS, PARCELAS)
        b = self.banco.criar_cobranca(CAMPOS, PARCELAS)
        self.assertNotEqual(a, b)

    def test_parcelas_ja_gravadas_sem_a_cobranca_grava_so_a_cobranca(self):
        d = json.loads(Path(self.caminho).read_text(encoding="utf-8"))
        d["parcelas"] = [{h: "" for h in n.PARCELAS_HEADERS} | {"ID Cobrança": "meio1234", "Nº": str(i)}
                         for i in (1, 2, 3)]
        Path(self.caminho).write_text(json.dumps(d), encoding="utf-8")
        self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="meio1234")
        self.assertEqual(self.contar("meio1234"), (1, 3))

    def test_estourou_o_prazo_mas_gravou(self):
        """Simulação do teste: o Google grava e a resposta não chega. A nova tentativa não duplica."""
        lento = os.path.join(self.tmp.name, "lento.json")
        Path(lento).write_text(json.dumps({"falha_depois": True}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"COBRANCA_LENTO": lento}):
            with self.assertRaises(TimeoutError):
                self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="lento123")
            self.assertTrue(self.banco.cobranca_existe("lento123"))
            self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="lento123")   # já está lá: não grava, não dá erro
        self.assertEqual(self.contar("lento123"), (1, 3))

    def test_falha_antes_nao_grava_nada(self):
        lento = os.path.join(self.tmp.name, "lento.json")
        Path(lento).write_text(json.dumps({"falha_antes": True}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"COBRANCA_LENTO": lento}):
            with self.assertRaises(TimeoutError):
                self.banco.criar_cobranca(CAMPOS, PARCELAS, cid="nada1234")
        self.assertEqual(self.contar("nada1234"), (0, 0))

    def test_registro_do_juridico_com_mesmo_id_nao_duplica(self):
        campos = {"Cliente": "LOJA", "Turma": "L1", "Objeto": "Cheque", "Situação": "Ativa"}
        hist = {"Quando": "05/11/2026 10:00:00", "Quem": "Ana", "Ação": "cadastro"}
        self.banco.criar_registro(dados.ABA_JUDICIAL, campos, historico=hist, rid="jur12345")
        self.banco.criar_registro(dados.ABA_JUDICIAL, campos, historico=hist, rid="jur12345")
        self.assertEqual(len(self.banco.carregar()["judiciais"]), 1)
        self.assertTrue(self.banco.registro_existe(dados.ABA_JUDICIAL, "jur12345"))
        self.assertFalse(self.banco.registro_existe(dados.ABA_PROTESTOS, "jur12345"))


class _PlanilhaFalsa:
    """Imita as abas do Google: guarda as linhas e conta os pedidos."""

    def __init__(self, id_na_coluna_a=True):
        cab_c = list(n.COBRANCAS_HEADERS)
        if not id_na_coluna_a:   # alguém mexeu na ordem das colunas na planilha
            cab_c = cab_c[1:2] + cab_c[:1] + cab_c[2:]
        self.abas = {dados.ABA_COBRANCAS: [cab_c], dados.ABA_PARCELAS: [list(n.PARCELAS_HEADERS)]}
        self.leituras = 0
        self.gravacoes = []
        self.falhar_na = None

    def values_batch_get(self, sid, faixas):
        self.leituras += 1
        blocos = []
        for f in faixas:
            nome, faixa = f.split("!")
            linhas = self.abas[nome.strip("'")]
            blocos.append({"values": [linhas[0]]} if faixa == "1:1" else {"values": [[l[0]] if l else [] for l in linhas]})
        return {"valueRanges": blocos}

    def aba(self, nome, headers):
        falsa = self

        class Aba:
            def append_rows(self, linhas, **kw):
                falsa._gravar(nome, linhas)

            def append_row(self, linha, **kw):
                falsa._gravar(nome, [linha])

            def col_values(self, col):
                falsa.leituras += 1
                return [l[col - 1] if len(l) >= col else "" for l in falsa.abas[nome]]
        return Aba()

    def _gravar(self, nome, linhas):
        if self.falhar_na == nome:
            raise TimeoutError("caiu")
        self.gravacoes.append(nome)
        self.abas[nome].extend(linhas)


def _planilha(falsa):
    p = dados.Planilha.__new__(dados.Planilha)
    p._id, p._abertas = "planilha-de-teste", {}
    p._gc = SimpleNamespace(http_client=falsa)
    p._aba = mock.Mock(side_effect=falsa.aba)
    return p


class PlanilhaNaoDuplica(unittest.TestCase):
    def test_grava_cobranca_e_parcelas_com_poucos_pedidos(self):
        falsa = _PlanilhaFalsa()
        p = _planilha(falsa)
        self.assertEqual(p.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345"), "abc12345")
        self.assertEqual(falsa.gravacoes, [dados.ABA_PARCELAS, dados.ABA_COBRANCAS])   # parcelas primeiro
        self.assertEqual(falsa.leituras, 1)
        cob = dict(zip(falsa.abas[dados.ABA_COBRANCAS][0], falsa.abas[dados.ABA_COBRANCAS][1]))
        self.assertEqual((cob["ID"], cob["Cliente"], cob["Valor Total"], cob["Situação"]),
                         ("abc12345", "MARIA", "3000,00", "Ativa"))
        self.assertEqual(len(falsa.abas[dados.ABA_PARCELAS]), 4)
        # a 2ª cobrança não abre as abas de novo (antes: 2 pedidos a mais por aba, toda vez)
        p.criar_cobranca(CAMPOS, PARCELAS, cid="def67890")
        self.assertEqual(p._aba.call_count, 2)

    def test_mesmo_id_ja_gravado_nao_grava_nada(self):
        falsa = _PlanilhaFalsa()
        p = _planilha(falsa)
        p.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345")
        falsa.gravacoes.clear()
        p.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345")
        self.assertEqual(falsa.gravacoes, [])
        self.assertTrue(p.cobranca_existe("abc12345"))
        self.assertFalse(p.cobranca_existe("zzz"))

    def test_caiu_depois_das_parcelas_nova_tentativa_grava_so_a_cobranca(self):
        falsa = _PlanilhaFalsa()
        p = _planilha(falsa)
        falsa.falhar_na = dados.ABA_COBRANCAS
        with self.assertRaises(TimeoutError):
            p.criar_cobranca(CAMPOS, PARCELAS, cid="meio1234")
        self.assertEqual(p._abertas, {})   # erro: esquece as abas abertas
        self.assertFalse(p.cobranca_existe("meio1234"))
        falsa.falhar_na = None
        falsa.gravacoes.clear()
        p.criar_cobranca(CAMPOS, PARCELAS, cid="meio1234")
        self.assertEqual(falsa.gravacoes, [dados.ABA_COBRANCAS])
        self.assertEqual(len(falsa.abas[dados.ABA_PARCELAS]), 4)   # parcelas uma vez só

    def test_id_fora_da_coluna_a(self):
        falsa = _PlanilhaFalsa(id_na_coluna_a=False)
        p = _planilha(falsa)
        p.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345")
        self.assertTrue(p.cobranca_existe("abc12345"))
        falsa.gravacoes.clear()
        p.criar_cobranca(CAMPOS, PARCELAS, cid="abc12345")
        self.assertEqual(falsa.gravacoes, [])


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backup as b  # noqa: E402

DIA1 = datetime(2026, 10, 1, 7, 40, tzinfo=b.TIMEZONE)
DIA2 = datetime(2026, 10, 2, 13, 0, tzinfo=b.TIMEZONE)


def abas(cobrancas=2, parcelas=6, extra=None):
    d = {
        "_Cobrancas": [["ID", "Cliente", "Valor Total"]] +
                      [[f"c{i}", f"Cliente {i}", "1500,00"] for i in range(cobrancas)],
        "_Parcelas": [["ID Cobrança", "Nº", "Vencimento", "Valor"]] +
                     [[f"c{i % max(cobrancas, 1)}", str(i), "05/01/2027", "0250,50"] for i in range(parcelas)],
        "_Config": [["Chave", "Valor"], ["admin", "Pedro"]],
    }
    d.update(extra or {})
    return d


class Impressao(unittest.TestCase):
    def test_vazio_sobrando_nao_muda_a_impressao(self):
        a = abas()
        com_sobra = {k: [l + ["", ""] for l in v] + [[], [""]] for k, v in a.items()}
        self.assertEqual(b.impressao_digital(a), b.impressao_digital(com_sobra))

    def test_qualquer_celula_diferente_muda(self):
        a, outro = abas(), abas()
        outro["_Parcelas"][3][3] = "0250,51"
        self.assertNotEqual(b.impressao_digital(a), b.impressao_digital(outro))

    def test_celula_vazia_no_meio_conta(self):
        self.assertNotEqual(b.impressao_digital({"x": [["a", "", "b"]]}),
                            b.impressao_digital({"x": [["a", "b"]]}))


class Excel(unittest.TestCase):
    def test_volta_identico_inclusive_texto_perigoso(self):
        perigosos = [["Obs"], ["=1+1"], ["0012"], ["1500,00"], ["01/02/2027"], ["+5599999"],
                     ["  espaço na ponta "], ["linha\nquebrada"], ["", "depois de vazio"], ["TRUE"]]
        copia = b.montar("Teste", abas(extra={"_Obs": perigosos}), DIA1)
        self.assertEqual(b.ler_xlsx(b.gerar_xlsx(copia)), copia["abas"])

    def test_leia_me_nao_entra_na_volta(self):
        copia = b.montar("Teste", abas(), DIA1)
        self.assertNotIn(b.ABA_LEIAME, b.ler_xlsx(b.gerar_xlsx(copia)))


class Conferencia(unittest.TestCase):
    def test_planilha_sem_as_abas_do_app_nao_vale(self):
        self.assertTrue(b.conferir(b.montar("Outra", {"Página1": [["a"]]}, DIA1)))
        self.assertTrue(b.conferir(b.montar("Vazia", {"_Cobrancas": [], "_Parcelas": [["ID"]]}, DIA1)))
        self.assertEqual(b.conferir(b.montar("Certa", abas(0, 0), DIA1)), [])

    def test_encolheu(self):
        antes = b.montar("T", abas(5, 36), DIA1)
        self.assertEqual(b.encolheu(None, antes), [])
        self.assertEqual(b.encolheu(antes, b.montar("T", abas(6, 40), DIA2)), [])
        self.assertEqual(b.encolheu(antes, b.montar("T", abas(5, 34), DIA2)), [])   # tirou 2 parcelas: normal
        self.assertEqual(len(b.encolheu(antes, b.montar("T", abas(4, 36), DIA2))), 1)
        self.assertEqual(len(b.encolheu(antes, b.montar("T", abas(5, 20), DIA2))), 1)
        sem_config = abas(5, 36)
        del sem_config["_Config"]
        self.assertEqual(len(b.encolheu(antes, b.montar("T", sem_config, DIA2))), 1)


class Pasta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name) / "cofre"
        self.addCleanup(self._tmp.cleanup)

    def arquivos(self, raiz=None):
        raiz = raiz or self.pasta
        return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file())

    def test_grava_uma_vez_e_nao_repete_sem_mudanca(self):
        nome, gravou, sumiu = b.salvar_pasta(b.montar("T", abas(), DIA1), self.pasta)
        self.assertEqual((nome, gravou, sumiu), ("Cobrancas_2026-10-01_07h40", True, []))
        nome2, gravou2, _ = b.salvar_pasta(b.montar("T", abas(), DIA2), self.pasta)
        self.assertEqual((nome2, gravou2), (nome, False))
        self.assertEqual(self.arquivos(), ["2026/Cobrancas_2026-10-01_07h40.json",
                                           "2026/Cobrancas_2026-10-01_07h40.xlsx", b.MARCA])
        self.assertIn("02/10/2026 às 13:00", (self.pasta / b.MARCA).read_text(encoding="utf-8"))

    def test_mudou_grava_outra_e_guarda_a_antiga(self):
        b.salvar_pasta(b.montar("T", abas(2), DIA1), self.pasta)
        antiga = (self.pasta / "2026/Cobrancas_2026-10-01_07h40.json").read_bytes()
        _, gravou, _ = b.salvar_pasta(b.montar("T", abas(3), DIA2), self.pasta)
        self.assertTrue(gravou)
        self.assertEqual(len(self.arquivos()), 5)
        self.assertEqual((self.pasta / "2026/Cobrancas_2026-10-01_07h40.json").read_bytes(), antiga)

    def test_encolheu_guarda_a_copia_e_avisa(self):
        b.salvar_pasta(b.montar("T", abas(5), DIA1), self.pasta)
        _, gravou, sumiu = b.salvar_pasta(b.montar("T", abas(1), DIA2), self.pasta)
        self.assertTrue(gravou and sumiu)

    def test_json_guardado_reconstroi_a_planilha(self):
        copia = b.montar("T", abas(), DIA1)
        b.salvar_pasta(copia, self.pasta)
        lido = json.loads((self.pasta / "2026/Cobrancas_2026-10-01_07h40.json").read_text(encoding="utf-8"))
        self.assertEqual(lido["abas"], copia["abas"])
        self.assertEqual(b.impressao_digital(lido["abas"]), lido["impressao"])

    def test_json_cortado_no_meio_e_ignorado(self):
        b.salvar_pasta(b.montar("T", abas(2), DIA1), self.pasta)
        (self.pasta / "2026/Cobrancas_2026-10-05_09h00.json").write_text('{"abas": {', encoding="utf-8")
        self.assertEqual(b.ultima_copia(self.pasta)["feito_em"], DIA1.isoformat(timespec="seconds"))

    def test_espelho_leva_so_o_que_falta_e_nunca_apaga(self):
        destino = Path(self._tmp.name) / "servidor"
        b.salvar_pasta(b.montar("T", abas(2), DIA1), self.pasta)
        self.assertEqual(b.espelhar(self.pasta, destino), 3)
        self.assertEqual(b.espelhar(self.pasta, destino), 0)
        (destino / "so_no_servidor.txt").write_text("x", encoding="utf-8")
        b.salvar_pasta(b.montar("T", abas(3), DIA2), self.pasta)
        self.assertEqual(b.espelhar(self.pasta, destino), 3)   # 2 arquivos novos + a marca atualizada
        self.assertEqual(len(self.arquivos(destino)), 6)
        self.assertEqual((destino / b.MARCA).read_bytes(), (self.pasta / b.MARCA).read_bytes())


class Execucao(unittest.TestCase):
    def test_planilha_errada_nao_grava_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            erros = b.executar(b.montar("Outra", {"Página1": [["a"]]}, DIA1), Path(tmp) / "c", saida=lambda *_: None)
            self.assertTrue(erros)
            self.assertFalse((Path(tmp) / "c").exists())

    def test_espelho_fora_do_ar_nao_impede_a_pasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            bloqueio = Path(tmp) / "arquivo"
            bloqueio.write_text("x", encoding="utf-8")   # um arquivo no lugar da pasta: o espelho falha
            erros = b.executar(b.montar("T", abas(), DIA1), Path(tmp) / "c", bloqueio / "dentro",
                               saida=lambda *_: None)
            self.assertEqual(len(erros), 1)
            self.assertTrue((Path(tmp) / "c/2026/Cobrancas_2026-10-01_07h40.json").exists())

    def test_drive_sem_chave_e_pulado_sem_erro(self):
        import os
        os.environ.pop("DRIVE_OAUTH", None)
        with tempfile.TemporaryDirectory() as tmp:
            falas = []
            self.assertEqual(b.executar(b.montar("T", abas(), DIA1), Path(tmp) / "c", drive=True,
                                        saida=falas.append), [])
            self.assertTrue(any("pulando" in f for f in falas))


if __name__ == "__main__":
    unittest.main()

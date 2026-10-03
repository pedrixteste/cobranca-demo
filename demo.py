"""
Modo demonstração: cobranças de EXEMPLO (nomes inventados) num arquivo
temporário do servidor, para mostrar o app sem planilha e sem dado real.
Ligado pelo secret `modo_demo = true`. Tudo some quando o app reinicia.
"""
import os
import tempfile
from datetime import date, timedelta

from dados import Local
from nucleo import datas_continuas, parcelas_cartao, parcelas_hibrido, parcelas_pix

ARQUIVO_DEMO = os.path.join(tempfile.gettempdir(), "cobrancas_demo.local.json")


def semear(banco, hoje: date):
    d = lambda n: hoje + timedelta(days=n)
    # Atrasada: entrada paga, 1ª parcela venceu há 5 dias
    banco.criar_cobranca({"Tipo": "Pix", "Cliente": "Maria José da Silva (exemplo)", "Turma": "L345",
                          "Treinamento": "LORAP", "Valor Total": 5000.0},
                         parcelas_pix(1000, d(-35), [400.0] * 10, datas_continuas(d(-5), 10), hoje))
    # Vence em breve (amanhã), uma parcela já paga
    cid = banco.criar_cobranca({"Tipo": "Pix", "Cliente": "Carlos Pereira (exemplo)", "Turma": "V12",
                                "Treinamento": "Vendas", "Valor Total": 2400.0},
                               parcelas_pix(0, None, [600.0] * 4, datas_continuas(d(-29), 4), hoje))
    banco.atualizar_parcela(cid, 1, {"Status": "Paga", "Pago em": d(-29)})
    # Cartão em 3 datas, com parte já paga
    banco.criar_cobranca({"Tipo": "Cartão", "Cliente": "Ana Fernandes (exemplo)", "Turma": "I7",
                          "Treinamento": "Impacto", "Valor Total": 10000.0},
                         parcelas_cartao(4000, hoje, [2000.0] * 3, [d(0), d(9), d(20)]))
    # Em dia
    banco.criar_cobranca({"Tipo": "Pix", "Cliente": "Roberto Almeida (exemplo)", "Turma": "P3",
                          "Treinamento": "Perfil", "Valor Total": 1500.0},
                         parcelas_pix(500, d(-10), [500.0, 500.0], datas_continuas(d(20), 2), hoje))
    # Quitado
    cid = banco.criar_cobranca({"Tipo": "Pix", "Cliente": "Fernanda Costa (exemplo)", "Turma": "L340",
                                "Treinamento": "LORAP", "Valor Total": 1200.0},
                               parcelas_pix(600, d(-60), [600.0], [d(-30)], hoje))
    banco.atualizar_parcela(cid, 1, {"Status": "Paga", "Pago em": d(-31)})
    # Híbrida: metade no Pix (entrada + 2 parcelas) e metade no cartão (uma passada já feita)
    banco.criar_cobranca({"Tipo": "Híbrido", "Cliente": "Juliana Martins (exemplo)", "Turma": "L346",
                          "Treinamento": "LORAP", "Valor Total": 6000.0},
                         parcelas_hibrido(1000, d(-8), [1000.0, 1000.0], datas_continuas(d(22), 2),
                                          [1500.0, 1500.0], [d(-8), d(14)], [3, 3], [True, False], hoje))


def banco_demo(hoje: date, recomecar: bool = False) -> Local:
    if recomecar and os.path.exists(ARQUIVO_DEMO):
        os.remove(ARQUIVO_DEMO)
    novo = not os.path.exists(ARQUIVO_DEMO)
    banco = Local(ARQUIVO_DEMO)
    if novo:
        semear(banco, hoje)
    return banco

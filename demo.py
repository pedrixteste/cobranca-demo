"""
Modo demonstração: cobranças de EXEMPLO (nomes inventados) num arquivo
temporário do servidor, para mostrar o app sem planilha e sem dado real.
Ligado pelo secret `modo_demo = true`. Tudo some quando o app reinicia.
"""
import os
import tempfile
from datetime import date, timedelta

from dados import ABA_JUDICIAL, ABA_PROTESTOS, Local
from nucleo import (NEG_PARCELADO, acordo_para_texto, datas_continuas, marcar_parcela_acordo, parcelas_cartao,
                    parcelas_do_acordo, parcelas_hibrido, parcelas_permuta, parcelas_pix)

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
    # Permuta: treinamento trocado por produtos da empresa; 2 meses depois fechou outra (2º valor)
    banco.criar_cobranca({"Tipo": "Permuta", "Cliente": "PADARIA BOM GOSTO (EXEMPLO)", "Turma": "V12, I7",
                          "Treinamento": "Vendas, Impacto", "Valor Total": 5500.0},
                         parcelas_permuta([("CESTAS DE CAFÉ DA MANHÃ", d(-40), 800.0),
                                           ("BOLOS PARA O EVENTO", d(-12), 1200.0)],
                                          creditos=[(d(-70), 3000.0), (d(-10), 2500.0)]))

    # Jurídico (pedido 03/11): uma cobrança judicial com acordo parcelado (2 pagas, a 3ª atrasada),
    # outra ainda sem acordo; um protesto em aberto e um já pago
    acordo = parcelas_do_acordo([600.0] * 6, datas_continuas(d(-65), 6))
    acordo = marcar_parcela_acordo(acordo, 1, True, d(-66), "Ana")
    acordo = marcar_parcela_acordo(acordo, 2, True, d(-35), "Ana")
    banco.criar_registro(ABA_JUDICIAL, {
        "Cliente": "LOJA PONTO CERTO (EXEMPLO)", "Turma": "L340", "Objeto": "Cheque", "Valor cobrado": 4800.0,
        "No jurídico desde": d(-95), "Advogado": "DRA. ADVOGADA (EXEMPLO)", "Negociação": NEG_PARCELADO,
        "Valor do acordo": 3600.0, "Acordo": acordo_para_texto(acordo),
        "Cadastrada por": "Pedro", "Criada em": d(-95), "Situação": "Ativa"})
    banco.criar_registro(ABA_JUDICIAL, {
        "Cliente": "MARCOS VIEIRA (EXEMPLO)", "Turma": "V10", "Objeto": "Promissória", "Valor cobrado": 2500.0,
        "No jurídico desde": d(-20), "Advogado": "DRA. ADVOGADA (EXEMPLO)",
        "Cadastrada por": "Pedro", "Criada em": d(-20), "Situação": "Ativa"})
    banco.criar_registro(ABA_PROTESTOS, {
        "Cliente": "AUTO PEÇAS SUL (EXEMPLO)", "Turma": "I5", "Objeto": "Ficha", "Protestado em": d(-45),
        "Cadastrado por": "Ana", "Criado em": d(-45), "Situação": "Ativa"})
    banco.criar_registro(ABA_PROTESTOS, {
        "Cliente": "JOÃO RIBEIRO (EXEMPLO)", "Turma": "L338", "Objeto": "Cheque", "Protestado em": d(-120),
        "Pago": True, "Pago em": d(-30), "Marcado por": "Ana",
        "Cadastrado por": "Ana", "Criado em": d(-120), "Situação": "Ativa"})


def banco_demo(hoje: date, recomecar: bool = False) -> Local:
    if recomecar and os.path.exists(ARQUIVO_DEMO):
        os.remove(ARQUIVO_DEMO)
    novo = not os.path.exists(ARQUIVO_DEMO)
    banco = Local(ARQUIVO_DEMO)
    if novo:
        semear(banco, hoje)
    return banco

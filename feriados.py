"""
Feriados nacionais do Brasil (piada interna do time; para tirar do app basta
apagar este arquivo, a tela `tela_feriados` e o botão "Feriados" da tela inicial).

Feriado NACIONAL é o que está em lei federal e vale para quem trabalha de CLT
no país inteiro. Carnaval e Corpus Christi NÃO são feriado nacional (são ponto
facultativo, ou feriado só onde há lei estadual/municipal): entram na lista
marcados como "facultativo" para ninguém contar com eles sem conferir.
"""
from __future__ import annotations

from datetime import date, timedelta

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

FIXOS = [
    (1, 1, "Confraternização Universal (Ano-Novo)"),
    (21, 4, "Tiradentes"),
    (1, 5, "Dia do Trabalho"),
    (7, 9, "Independência do Brasil"),
    (12, 10, "Nossa Senhora Aparecida"),
    (2, 11, "Finados"),
    (15, 11, "Proclamação da República"),
    (20, 11, "Dia da Consciência Negra"),   # nacional desde a Lei 14.759/2023
    (25, 12, "Natal"),
]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados(ano: int) -> list[dict]:
    """Lista do ano em ordem de data: {data, nome, nacional, dia_semana, obs}."""
    p = pascoa(ano)
    itens = [(date(ano, mes, dia), nome, True) for dia, mes, nome in FIXOS]
    itens += [
        (p - timedelta(days=2), "Sexta-feira Santa (Paixão de Cristo)", True),
        (p - timedelta(days=48), "Carnaval (segunda)", False),
        (p - timedelta(days=47), "Carnaval (terça)", False),
        (p + timedelta(days=60), "Corpus Christi", False),
    ]
    saida = []
    for d, nome, nacional in sorted(itens):
        ds = d.weekday()
        if ds >= 5:
            obs = "cai no fim de semana"
        elif ds in (1, 3):
            obs = "dá para emendar"
        elif ds in (0, 4):
            obs = "feriadão"
        else:
            obs = "no meio da semana"
        saida.append({"data": d, "nome": nome, "nacional": nacional, "dia_semana": DIAS[ds], "obs": obs})
    return saida


def proximo(hoje: date) -> dict | None:
    """Próximo feriado NACIONAL a partir de hoje (hoje conta)."""
    for ano in (hoje.year, hoje.year + 1):
        for f in feriados(ano):
            if f["nacional"] and f["data"] >= hoje:
                return f
    return None

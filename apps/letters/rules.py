"""
Regras de negocio da estadia, num so lugar.

Estao aqui, e nao em `services.py`, para que tanto o assistente
(`forms`/`views`) quanto a geracao do PDF (`pdf_generation`) usem a MESMA
conta sem que um precise importar o outro -- `services` ja importa
`pdf_generation`, entao o caminho inverso fecharia um ciclo. Este modulo
nao importa nada do app de proposito.
"""

import datetime

# Contagem INCLUSIVA: conta o dia de chegada e o de partida. E a regra do
# documento oficial -- "du 10/10/2026 au 24/10/2026 (15 jours)": a
# diferenca entre as datas e 14, mas o documento declara 15.
#
# Limite legal da carta de curta duracao.
MAX_STAY_DAYS = 90


def stay_duration_days(arrival, departure):
    """
    Quantos dias dura a estadia, contando chegada e partida.

    Devolve None quando nao da para calcular: falta uma das datas, ou a
    partida e anterior a chegada (ai o erro e de validacao das datas, nao
    de duracao -- quem mostra a mensagem certa e o formulario).

    Chegada e partida no mesmo dia contam 1 dia.
    """
    if not isinstance(arrival, datetime.date) or not isinstance(departure, datetime.date):
        return None
    if departure < arrival:
        return None
    return (departure - arrival).days + 1


def exceeds_max_stay(days):
    """Se a duracao passa do limite da carta de curta duracao."""
    return days is not None and days > MAX_STAY_DAYS

"""
Dados de exemplo por modelo oficial (Etapa 3.4).

Servem a DOIS consumidores: o teste de integracao do renderer e o
comando `previa_documento`, que gera o PDF para conferencia visual. Ter
um lugar so evita a armadilha obvia -- a previa mostrar uma coisa e o
teste afirmar outra.

NAO SAO DADOS DO MODELO
-----------------------
Nada aqui e gravado. `DocumentTemplate` guarda o desenho; os valores
passam pelo renderer e vao embora. E o que permite o mesmo modelo servir
a todas as cartas.

De onde vieram: sao os valores visiveis no PDF oficial
(`pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf`), para que a previa
possa ser comparada com ele lado a lado. Sao ficticios -- "Claire
Dubois" e "Carlos Eduardo Silva" sao os nomes de amostra do proprio
documento oficial, nao pessoas.
"""

CARTA_CONVITE_FR = {
    "anfitriao.nome": "Claire Dubois",
    "anfitriao.nacionalidade": "belge",
    "anfitriao.data_nascimento": "14/03/1985",
    "anfitriao.documento_identidade": "00000000",
    "anfitriao.endereco": "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert",
    "anfitriao.cidade": "Woluwe-Saint-Lambert",
    "anfitriao.telefone": "+32 470 00 00 00",
    "convidado.nome": "Carlos Eduardo Silva",
    "convidado.nacionalidade": "Brésilienne",
    "convidado.data_nascimento": "22/07/1990",
    "convidado.passaporte": "YY000000",
    "estadia.chegada": "10/10/2026",
    "estadia.partida": "24/10/2026",
    "calculado.duracao_dias": "15",
    "calculado.data_documento": "09/09/2026",
}

# Por slug. Um modelo novo entra aqui quando tiver layout; sem entrada,
# a previa sai com os campos vazios -- o que ainda mostra a estrutura.
POR_SLUG = {
    "carta-convite-fr": CARTA_CONVITE_FR,
}


def para(slug):
    """Os dados de exemplo daquele modelo, ou `{}` se nao houver."""
    return dict(POR_SLUG.get(slug, {}))

"""
Dados de exemplo por modelo oficial (Etapa 3.4).

Servem a TRES consumidores: o teste de integracao do renderer, o
comando `previa_documento`, que gera o PDF para conferencia visual, e o
editor de modelos ("Ver com dados de exemplo" e o botao Visualizar). Ter
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

# EN/NL/PT (Etapa 3.6) usam os MESMOS valores: e a mesma pessoa
# ficticia, o mesmo endereco, as mesmas datas -- o que muda e so a
# nacionalidade, que no documento real vem do cadastro `Nationality` ja
# escrita no idioma da carta. Manter o resto identico e o que permite
# comparar as quatro previas lado a lado e ver SO a traducao.
NACIONALIDADES = {
    "en": {"anfitriao.nacionalidade": "Belgian", "convidado.nacionalidade": "Brazilian"},
    "nl": {"anfitriao.nacionalidade": "Belgische", "convidado.nacionalidade": "Braziliaanse"},
    "pt": {"anfitriao.nacionalidade": "belga", "convidado.nacionalidade": "brasileira"},
}

# Por slug. Um modelo novo entra aqui quando tiver layout; sem entrada,
# a previa sai com os campos vazios -- o que ainda mostra a estrutura.
POR_SLUG = {
    "carta-convite-fr": CARTA_CONVITE_FR,
    **{
        f"carta-convite-{idioma}": {**CARTA_CONVITE_FR, **valores}
        for idioma, valores in NACIONALIDADES.items()
    },
}


def para(slug):
    """Os dados de exemplo daquele modelo, ou `{}` se nao houver."""
    return dict(POR_SLUG.get(slug, {}))


# O que o EDITOR mostra para um modelo sem entrada propria (uma copia
# renomeada, um tipo de documento novo): a mesma pessoa ficticia, mais
# os dois campos de "documento" que a carta oficial nao imprime. Sao
# valores de amostra para se ver o desenho -- nenhum vai para o banco.
GENERICOS = {
    **CARTA_CONVITE_FR,
    "documento.numero": "CC-2026-0001",
    "documento.data": "09/09/2026",
    "anfitriao.email": "claire.dubois@exemplo.be",
}


def genericos():
    """Os dados de amostra do editor para um modelo qualquer."""
    return dict(GENERICOS)


def para_o_editor(slug):
    """
    Os dados de amostra que o editor usa para `slug`: os proprios do
    modelo, completados pelos genericos -- assim um campo que o modelo
    oficial nao usa (documento.numero) ainda tem valor de amostra quando
    o administrador o insere.
    """
    return {**GENERICOS, **POR_SLUG.get(slug, {})}

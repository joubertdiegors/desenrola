"""
A declaração do anfitrião dos quatro modelos oficiais ganha o texto novo
(Rodada 18).

O QUE MUDA
----------
Só o CONTEÚDO do elemento `<idioma>-declaracao` dos quatro oficiais
(`carta-convite-fr`, `-en`, `-nl`, `-pt`): os literais entre os campos e
a sequência de campos -- seis, cada dado uma vez (nome, nascimento,
nacionalidade, documento de identidade, endereço, telefone). A
nacionalidade deixou de aparecer duas vezes.

Posição, tamanho, tipografia, id e tipo do elemento não mudam, e nenhum
outro elemento é tocado. Os campos continuam ESTRUTURAIS (`kind:
field`), com o mesmo negrito de antes -- nada de "[nome]" em texto.

POR QUE UMA MIGRATION
---------------------
A mesma razão da 0018: os oficiais já existem nos bancos instalados, e
`reconstruir_modelos_oficiais` não reescreve um layout existente (nem
deve -- ver o comando). Mudar só `services.carta_convite` alcançaria
bancos novos e nenhum dos que já existem.

O QUE ELA NÃO TOCA
------------------
Só troca quando o conteúdo gravado ainda é EXATAMENTE o texto antigo --
o que a semeadura escreveu. Um oficial cuja declaração alguém já tenha
ajustado fica como está: a migration corrige o que veio da semente, não
o que foi decidido depois. Cópias (modelos não oficiais) não são
tocadas.

Os dois conteúdos estão CONGELADOS aqui, como literais: a migration não
pode depender de um módulo que muda depois.

A VOLTA
-------
Reversível: devolve o texto antigo, com a mesma condição.
"""

from django.db import migrations

# O conteúdo que a semeadura escreveu até a Rodada 17.
ANTIGA = {
    'fr': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Je soussignée, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', née le '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', de nationalité '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', titulaire de la carte d’identité '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' n° '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', domiciliée au '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', téléphone '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', invite par la présente :'}]},
    'en': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'I, the undersigned, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', born on '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', of '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' nationality, holder of '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' identity card no. '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', residing at '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telephone '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', hereby invite:'}]},
    'nl': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Ik, ondergetekende, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', geboren op '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', van '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' nationaliteit, houder van de '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' identiteitskaart nr. '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', wonende te '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telefoon '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', nodig hierbij uit:'}]},
    'pt': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Eu, abaixo assinada, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', nascida em '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', de nacionalidade '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', titular do cartão de identidade '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ' n.º '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', residente em '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telefone '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', convido pela presente:'}]},
}

# O conteúdo da Rodada 18 -- o mesmo de `services.carta_convite` agora.
NOVA = {
    'fr': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Je soussigné(e), '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', né(e) le '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', nationalité : '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', carte d’identité : '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', domicilié(e) à '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', téléphone : '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', invite par la présente :'}]},
    'en': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'I, the undersigned, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', born on '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', nationality: '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', identity card: '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', residing at '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telephone: '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', hereby invite:'}]},
    'nl': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Ik, ondergetekende, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', geboren op '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', nationaliteit: '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', identiteitskaart: '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', wonende te '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telefoon: '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', nodig hierbij uit:'}]},
    'pt': {'kind': 'mixed',
     'parts': [{'kind': 'text', 'value': 'Eu, '},
               {'kind': 'field', 'source': 'anfitriao.nome', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', nascido(a) em '},
               {'kind': 'field', 'source': 'anfitriao.data_nascimento'},
               {'kind': 'text', 'value': ', de nacionalidade '},
               {'kind': 'field', 'source': 'anfitriao.nacionalidade'},
               {'kind': 'text', 'value': ', titular do documento de identidade nº '},
               {'kind': 'field',
                'source': 'anfitriao.documento_identidade',
                'font_weight': 'bold'},
               {'kind': 'text', 'value': ', domiciliado(a) em '},
               {'kind': 'field', 'source': 'anfitriao.endereco', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', telefone: '},
               {'kind': 'field', 'source': 'anfitriao.telefone', 'font_weight': 'bold'},
               {'kind': 'text', 'value': ', convido pela presente:'}]},
}


def _trocar(apps, de, para):
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")

    for idioma in de:
        modelo = DocumentTemplate.objects.filter(slug=f"carta-convite-{idioma}").first()
        if modelo is None or not modelo.layout:
            continue
        layout = modelo.layout
        mudou = False
        for elemento in layout.get("elements", []):
            if elemento.get("id") != f"{idioma}-declaracao":
                continue
            propriedades = elemento.get("properties") or {}
            if propriedades.get("content") == de[idioma]:
                propriedades["content"] = para[idioma]
                mudou = True
        if mudou:
            # `update()`, e não `save()`: o modelo HISTÓRICO não tem as
            # travas da classe, e esta é a única coluna que muda.
            DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=layout)


def aplicar(apps, schema_editor):
    _trocar(apps, ANTIGA, NOVA)


def desfazer(apps, schema_editor):
    _trocar(apps, NOVA, ANTIGA)


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0019_um_modelo_ativo_por_idioma"),
    ]

    operations = [
        migrations.RunPython(aplicar, desfazer),
    ]

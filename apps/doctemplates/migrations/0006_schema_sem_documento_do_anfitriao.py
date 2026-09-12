"""
Publica o field_schema vigente, com duas mudancas:

  - o assistente deixa de pedir o documento de identidade do anfitriao
    (`host_document_label` e `host_document_number`). O NUMERO passou a
    ser dado do perfil (accounts.User.document_number) e o TIPO nunca
    variou -- "carte d'identite" ja e texto fixo impresso no documento;
  - os dois campos de nacionalidade viram do tipo `nationality`,
    escolhidos no cadastro administravel em vez de digitados.

O texto do documento NAO muda: o "belge" de "titulaire de la carte
d'identite belge n° ..." sempre foi a nacionalidade do anfitriao -- o
campo removido so tinha um rotulo enganoso ("Documento de identidade",
com placeholder "Ex.: Carte d'identite", mas recebendo "belge").

Como versao publicada e imutavel, isto entra criando a PROXIMA versao
publicada e desativando a anterior; as cartas ja emitidas seguem na
versao com que foram feitas.
"""

import importlib

from django.db import migrations

# O modulo da 0003 comeca com digito, entao nao da para importar pelo
# `import` normal -- e so por isso que esta linha existe.
etapa_anterior = importlib.import_module(
    "apps.doctemplates.migrations.0003_official_template_per_language"
)


def publicar_schema_vigente(apps, schema_editor):
    etapa_anterior.seed_official_templates(apps, schema_editor)


def nada_a_desfazer(apps, schema_editor):
    """
    Reverter nao apaga a versao publicada: ela pode ja estar em uso por
    uma carta, e a anterior continua guardada de qualquer forma. Voltar o
    texto do placeholder e assunto de uma nova versao, nunca de apagar
    uma existente.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0005_nationality"),
    ]

    operations = [
        migrations.RunPython(publicar_schema_vigente, nada_a_desfazer),
    ]

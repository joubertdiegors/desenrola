"""
Cria os dois documentos legais -- VAZIOS.

O QUE ESTA MIGRATION FAZ, E O QUE ELA DELIBERADAMENTE NÃO FAZ
-------------------------------------------------------------
Cria os `ContentBlock` `legal.terms_of_use` e `legal.privacy_policy`,
e mais nada: nenhuma tradução, nenhum texto.

Texto jurídico é do cliente, não do código. Escrever aqui um Termo de
Uso ou uma Política de Privacidade seria inventar um documento com valor
legal -- exatamente o que este projeto não pode fazer. O conteúdo entra
depois, pelo Django Admin, escrito por quem responde por ele.

POR QUE CRIAR O BLOCO VAZIO, ENTÃO
----------------------------------
Para que exista o LUGAR. Com o bloco criado, quem administra abre o
Django Admin e encontra os dois cadastros esperando texto, em vez de ter
de adivinhar a chave exata que o código procura. A estrutura é técnica e
nasce aqui; o conteúdo é jurídico e nasce depois.

ENQUANTO ESTIVEREM VAZIOS
-------------------------
`services.texto_legal()` devolve `None`, a página responde 404, e o link
NÃO aparece no rodapé, no cadastro nem no perfil. Nada de link morto --
é a mesma regra que vale para contato e redes sociais desde a Etapa F.

IDEMPOTENTE E REVERSÍVEL
------------------------
`get_or_create`: rodar de novo não toca no que já existe, e em especial
não apaga texto que o cliente tenha escrito. O reverso remove os blocos
-- e, em cascata, as traduções: reverter uma migration de dados é uma
decisão explícita de quem a roda.
"""

from django.db import migrations

# As mesmas chaves de `apps.content.services.PAGINAS_LEGAIS`. Repetidas
# aqui de propósito: uma migration é um registro histórico e não pode
# mudar de comportamento porque uma constante do código mudou depois.
CHAVES = ("legal.terms_of_use", "legal.privacy_policy")


def criar_os_blocos(apps, schema_editor):
    ContentBlock = apps.get_model("content", "ContentBlock")
    for chave in CHAVES:
        ContentBlock.objects.get_or_create(
            key=chave,
            defaults={"kind": "text", "is_active": True},
        )


def remover_os_blocos(apps, schema_editor):
    """
    Apaga os dois blocos e, em cascata, as traduções.

    Destrutivo: texto que o cliente tiver escrito vai junto.
    """
    ContentBlock = apps.get_model("content", "ContentBlock")
    ContentBlock.objects.filter(key__in=CHAVES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_permissao_de_configuracoes"),
    ]

    operations = [
        migrations.RunPython(criar_os_blocos, remover_os_blocos),
    ]

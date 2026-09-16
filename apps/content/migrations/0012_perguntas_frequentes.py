"""
A seção de Perguntas frequentes da Home.

O QUE MUDA NO ESQUEMA
---------------------
`FaqItem` -- uma pergunta, com resposta, ordem e ativação próprias.
Mesma forma de `MenuItem` e `Partner`: a QUANTIDADE de perguntas é
decisão de quem administra, e por isso é cadastro, não texto dentro do
JSON de uma seção.

O QUE A SEMENTE FAZ
-------------------
Cria a seção `faq` na Home, com o título e a chamada em português, logo
DEPOIS do "Como funciona" -- e empurra em um o que vinha a seguir (o
Mini Banner e o rodapé), respeitando qualquer reordenação que um
administrador já tenha feito.

O QUE ELA NÃO FAZ
-----------------
Não cria pergunta nenhuma. Sem perguntas a seção não aparece na Home, e
é esse o estado correto de uma instalação nova: inventar três perguntas
seria pôr conteúdo fictício permanente no banco de todo mundo. O
conteúdo de demonstração tem lugar próprio -- o comando
`conteudo_demonstrativo`.

A VOLTA
-------
Reversível: a seção sai e as ordens voltam a fechar. As perguntas
cadastradas somem junto com a tabela, na operação de esquema.
"""

from django.db import migrations, models

CHAVE_DA_PAGINA = "home"
CHAVE_DA_SECAO = "faq"
DEPOIS_DE = "how"

CONTEUDO_EM_PORTUGUES = {
    "title": "Perguntas frequentes",
    "lead": "As dúvidas que mais recebemos sobre a Carta Convite.",
    "cta_title": "Não encontrou sua dúvida?",
    "cta_text": "Fale com a gente. Respondemos em até um dia útil.",
    "cta": "Falar com o suporte",
}


def semear(apps, schema_editor):
    from django.conf import settings
    from django.db.models import F, Max

    Page = apps.get_model("content", "Page")
    PageSection = apps.get_model("content", "PageSection")
    PageSectionTranslation = apps.get_model("content", "PageSectionTranslation")

    pagina = Page.objects.filter(key=CHAVE_DA_PAGINA).first()
    if pagina is None:
        # Banco em que `content.0004` ainda não rodou. Nada a semear.
        return

    ja_existe = PageSection.objects.filter(page=pagina, key=CHAVE_DA_SECAO).first()
    if ja_existe is None:
        anterior = PageSection.objects.filter(page=pagina, key=DEPOIS_DE).first()
        if anterior is None:
            ultima = PageSection.objects.filter(page=pagina).aggregate(Max("order"))
            posicao = (ultima["order__max"] or 0) + 1
        else:
            posicao = anterior.order + 1
            # Abre espaço sem desfazer reordenação feita por alguém.
            PageSection.objects.filter(page=pagina, order__gte=posicao).update(
                order=F("order") + 1
            )
        ja_existe = PageSection.objects.create(
            page=pagina,
            key=CHAVE_DA_SECAO,
            kind="faq",
            order=posicao,
            layout="",
            is_active=True,
        )

    PageSectionTranslation.objects.get_or_create(
        section=ja_existe,
        language=settings.LANGUAGE_CODE,
        defaults={"content": CONTEUDO_EM_PORTUGUES},
    )


def remover(apps, schema_editor):
    from django.db.models import F

    PageSection = apps.get_model("content", "PageSection")

    secao = PageSection.objects.filter(
        page__key=CHAVE_DA_PAGINA, key=CHAVE_DA_SECAO
    ).first()
    if secao is None:
        return

    posicao = secao.order
    secao.delete()
    PageSection.objects.filter(page__key=CHAVE_DA_PAGINA, order__gt=posicao).update(
        order=F("order") - 1
    )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0011_permissoes_de_imagens"),
    ]

    operations = [
        migrations.CreateModel(
            name="FaqItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("question", models.CharField(max_length=200, verbose_name="pergunta")),
                (
                    "answer",
                    models.TextField(
                        help_text="Texto simples. Quebras de linha são respeitadas.",
                        verbose_name="resposta",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativa")),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Menor aparece primeiro.",
                        verbose_name="ordem",
                    ),
                ),
            ],
            options={
                "verbose_name": "pergunta frequente",
                "verbose_name_plural": "perguntas frequentes",
                "ordering": ["order", "pk"],
                "default_permissions": (),
            },
        ),
        migrations.RunPython(semear, remover),
    ]

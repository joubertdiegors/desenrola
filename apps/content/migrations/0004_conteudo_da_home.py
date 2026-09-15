"""
Semeia a Home no CMS com o conteúdo que hoje está no template.

POR QUE ESTA MIGRATION EXISTE
-----------------------------
A partir desta etapa `templates/core/home.html` lê os textos de
`Page`/`PageSection`. Sem semear, a Home apareceria vazia no primeiro
deploy -- e a página pública do produto não pode ficar em branco
esperando alguém preencher.

OS TEXTOS SÃO OS QUE JÁ ESTAVAM LÁ
----------------------------------
Copiados do template, palavra por palavra. Nada foi reescrito, com UMA
exceção, deliberada: o rótulo do selo dizia "pessoas já utilizaram" e o
número ao lado passou a contar CARTAS (ver `apps.letters.statistics`).
Um rótulo que não descreve o que o número conta é pior do que um texto
novo, então ele virou "cartas já geradas".

NÃO SOBRESCREVE EDIÇÃO
----------------------
Tudo por `get_or_create`: rodar de novo não desfaz o que um
administrador tiver mudado pela tela. É o mesmo cuidado de
`services.biblioteca.semear_carta_convite`.

O `\\n` do rótulo do selo é a quebra de linha do desenho; o template a
converte com `linebreaksbr`. Fica texto puro no banco -- marcação em
campo de conteúdo é o começo de um problema.
"""

from django.conf import settings
from django.db import migrations

CHAVE_DA_PAGINA = "home"

# (chave, tipo, ordem, conteúdo em português)
SECOES = (
    (
        "hero",
        "hero",
        1,
        {
            "badge_label": "cartas já geradas\ncom nossa ferramenta",
            "badge_note": "Atualizado em tempo real",
            "title": "Gere sua Carta Convite em poucos minutos",
            "lead": (
                "Preencha os dados, escolha o idioma e receba seu documento em "
                "PDF, pronto para imprimir, assinar e utilizar."
            ),
            "cta": "Criar minha conta",
            "login_prompt": "Já tem uma conta?",
            "login_link": "Fazer login",
            "art_caption": "Foto: cidade belga (Bruxelas / Antuérpia / Gante)",
        },
    ),
    (
        "trust",
        "features",
        2,
        {
            "cards": [
                {"icon": "ph-lock", "title": "Seus dados seguros"},
                {"icon": "ph-lightning", "title": "Processo rápido"},
                {"icon": "ph-file-text", "title": "Documento profissional"},
            ]
        },
    ),
    (
        "partners",
        "partners",
        3,
        {
            "title": "Nossos parceiros",
            "lead": "Serviços que também facilitam a sua vida na Europa.",
            "cta": "Conheça",
        },
    ),
    (
        "how",
        "features",
        4,
        {
            "title": "Como funciona?",
            "lead": "Veja como é simples gerar sua Carta Convite.",
            "cards": [
                {
                    "icon": "ph-file-text",
                    "title": "1. Preencha",
                    "text": (
                        "Informe os dados do convidado e da viagem. Os seus, de "
                        "anfitrião, já vêm da conta."
                    ),
                },
                {
                    "icon": "ph-globe",
                    "title": "2. Escolha",
                    "text": (
                        "Selecione o idioma da sua carta (francês, inglês ou "
                        "português)."
                    ),
                },
                {
                    "icon": "ph-download-simple",
                    "title": "3. Receba",
                    "text": "Baixe o PDF na hora, pronto para imprimir e assinar.",
                },
            ],
        },
    ),
    (
        "cta",
        "cta",
        5,
        {
            "title": "Facilite a visita de quem você gosta.",
            "text": "Documentação simples, prática e sem complicação.",
            "button": "Começar agora",
        },
    ),
)


def semear(apps, schema_editor):
    Page = apps.get_model("content", "Page")
    PageSection = apps.get_model("content", "PageSection")
    PageSectionTranslation = apps.get_model("content", "PageSectionTranslation")

    pagina, _criada = Page.objects.get_or_create(
        key=CHAVE_DA_PAGINA,
        defaults={"name": "Home", "is_active": True},
    )

    for chave, tipo, ordem, conteudo in SECOES:
        secao, _criada = PageSection.objects.get_or_create(
            page=pagina,
            key=chave,
            defaults={"kind": tipo, "order": ordem, "is_active": True},
        )
        PageSectionTranslation.objects.get_or_create(
            section=secao,
            language=settings.LANGUAGE_CODE,
            defaults={"content": conteudo},
        )


def remover(apps, schema_editor):
    """
    Apaga a página e, em cascata, as seções e traduções.

    Destrutivo: o que tiver sido editado pela tela vai junto. Reverter
    uma migration de dados é uma decisão explícita de quem a roda.
    """
    Page = apps.get_model("content", "Page")
    Page.objects.filter(key=CHAVE_DA_PAGINA).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0003_parceiros"),
    ]

    operations = [
        migrations.RunPython(semear, remover),
    ]

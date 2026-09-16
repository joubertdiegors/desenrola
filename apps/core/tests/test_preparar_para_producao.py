"""
O comando que deixa o banco como uma instalação nova.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que ele apague sem pedir.** Sem `--confirmar` não remove nada, e com
   `--confirmar` ainda pergunta. Apagar dado é a operação menos
   reversível que existe;
2. **Que ele apague o que não pode.** Os quatro modelos oficiais, as
   configurações do sistema, as permissões, o conteúdo da página
   inicial, os itens do menu e os superusuários ficam. Um deles a menos
   e a instalação "nova" nasce quebrada;
3. **Que ele confunda demonstração com realidade.** Contato de verdade e
   texto jurídico de verdade não podem sumir junto com os de
   demonstração -- e o comando distingue porque a demonstração se
   identifica (`exemplo.test`, e o aviso de SUBSTITUIR);
4. **Que o relatório diga uma coisa e a execução faça outra.** O mesmo
   levantamento alimenta os dois;
5. **Que sobre carta de alguém.** Entregar um banco com a carta de um
   testador dentro é vazamento de dado pessoal, não conveniência.
"""

import datetime
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def rodar(*args, entrada=None, monkeypatch=None):
    """Roda o comando e devolve o que ele escreveu."""
    if entrada is not None:
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: entrada)
    saida = StringIO()
    call_command("preparar_para_producao", *args, stdout=saida, stderr=saida)
    return saida.getvalue()


@pytest.fixture
def mundo(db, modelos_oficiais_prontos, user, other_user):
    """
    Um banco de demonstração: cartas, gente, parceiros, cópias, imagens,
    contato e textos legais de demonstração -- e um superusuário.
    """
    from apps.content.models import (
        Asset,
        ContentBlock,
        ContentTranslation,
        Partner,
        SiteSettings,
    )
    from apps.core import mail
    from apps.doctemplates.models import DocumentTemplate
    from apps.doctemplates.services.duplicacao import duplicar_modelo
    from apps.letters import services as letras

    chefe = get_user_model().objects.create_superuser(
        email="chefe@exemplo.test", password="x" * 12, full_name="Chefe"
    )

    letras.start_draft(user, "fr")
    letras.start_draft(other_user, "fr")
    # Uma carta do SUPERUSUÁRIO: ele sobrevive à limpeza, então esta
    # carta só some se o comando a apagar de propósito. Sem ela, apagar
    # os usuários cascatearia todas e a exclusão explícita pareceria
    # redundante -- o teste passaria sem provar nada.
    letras.start_draft(chefe, "fr")

    Partner.objects.create(
        name="Global Travel Services", url="https://exemplo.test/global"
    )
    Partner.objects.create(name="Parceiro de verdade", url="https://parceiro.test/")

    oficial = DocumentTemplate.objects.filter(is_system=True).first()
    duplicar_modelo(oficial, "Minha cópia")

    solta = Asset.objects.create(key="solta", kind=Asset.Kind.OTHER, file=_gif())
    logo = Asset.objects.create(key="logo-real", kind=Asset.Kind.LOGO, file=_gif())

    config = SiteSettings.load()
    config.contact_email = "contato@exemplo.test"
    config.contact_address = "Endereço de demonstração"
    config.social_links = {"facebook": "https://exemplo.test/demo"}
    config.logo = logo
    config.save()

    mail.configuracao()

    bloco, _ = ContentBlock.objects.get_or_create(
        key="legal.terms_of_use", defaults={"kind": ContentBlock.Kind.TEXT}
    )
    ContentTranslation.objects.update_or_create(
        block=bloco, language="pt",
        defaults={"content": "AVISO: SUBSTITUIR ANTES DE PUBLICAR.\n\nTexto de exemplo."},
    )
    outro, _ = ContentBlock.objects.get_or_create(
        key="legal.privacy_policy", defaults={"kind": ContentBlock.Kind.TEXT}
    )
    ContentTranslation.objects.update_or_create(
        block=outro, language="pt",
        defaults={"content": "Política de Privacidade de verdade, escrita pelo cliente."},
    )

    return {"chefe": chefe, "solta": solta, "logo": logo, "config": config}


def _gif():
    return SimpleUploadedFile("x.gif", GIF, content_type="image/gif")


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


# ===========================================================================
# 1. Não apaga sem pedir
# ===========================================================================


class TestNaoApagaSemPedir:
    def test_sem_argumento_nenhum_so_relata(self, mundo):
        from apps.letters.models import Letter

        saida = rodar()

        assert Letter.objects.count() == 3  # duas de usuário, uma do chefe
        assert "Nada foi apagado" in saida
        assert "--confirmar" in saida

    def test_o_relatorio_conta_o_que_removeria(self, mundo):
        saida = rodar()

        assert "cartas" in saida
        assert "parceiros" in saida
        assert "modelos oficiais" in saida

    def test_o_relatorio_diz_o_que_fica_intacto(self, mundo):
        saida = rodar()

        assert "Fica intacto" in saida
        assert "superusuários" in saida
        assert "permissões" in saida

    def test_com_confirmar_ainda_pergunta(self, mundo, monkeypatch):
        from apps.letters.models import Letter

        with pytest.raises(CommandError, match="não confere"):
            rodar("--confirmar", entrada="sim", monkeypatch=monkeypatch)

        assert Letter.objects.count() == 3  # duas de usuário, uma do chefe

    def test_a_palavra_certa_executa(self, mundo, monkeypatch):
        from apps.letters.models import Letter

        rodar("--confirmar", entrada="PREPARAR", monkeypatch=monkeypatch)

        assert Letter.objects.count() == 0

    def test_nao_perguntar_dispensa_a_pergunta(self, mundo):
        """Para execução automatizada -- e só para isso."""
        from apps.letters.models import Letter

        rodar("--confirmar", "--nao-perguntar")

        assert Letter.objects.count() == 0


# ===========================================================================
# 2. O que ele remove
# ===========================================================================


class TestRemove:
    @pytest.fixture(autouse=True)
    def _executado(self, mundo):
        rodar("--confirmar", "--nao-perguntar")
        return mundo

    def test_todas_as_cartas(self):
        """
        Inclusive a do superusuário, que nenhum cascateamento alcança:
        ele fica, e a carta dele tem de sair mesmo assim. "Instalação
        nova" não tem histórico de ninguém.
        """
        from apps.letters.models import Letter

        assert Letter.objects.count() == 0

    def test_os_usuarios_que_nao_sao_superusuario(self):
        restantes = get_user_model().objects.all()

        assert restantes.count() == 1
        assert restantes.first().is_superuser

    def test_todos_os_parceiros(self):
        from apps.content.models import Partner

        assert Partner.objects.count() == 0

    def test_as_copias_de_modelos(self):
        from apps.doctemplates.models import DocumentTemplate

        assert DocumentTemplate.objects.filter(is_system=False).count() == 0

    def test_as_imagens_sem_uso(self, _executado):
        from apps.content.models import Asset

        assert not Asset.objects.filter(pk=_executado["solta"].pk).exists()

    def test_o_contato_de_demonstracao(self):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        assert config.contact_email == ""
        assert config.contact_address == ""
        assert config.social_links == {}

    def test_o_texto_legal_de_demonstracao(self):
        from apps.content.models import ContentTranslation

        assert not ContentTranslation.objects.filter(
            block__key="legal.terms_of_use"
        ).exists()


# ===========================================================================
# 3. O que ele NÃO pode tocar
# ===========================================================================


class TestPreserva:
    @pytest.fixture(autouse=True)
    def _executado(self, mundo):
        rodar("--confirmar", "--nao-perguntar")
        return mundo

    def test_os_quatro_modelos_oficiais(self):
        from apps.doctemplates.models import DocumentTemplate

        assert DocumentTemplate.objects.filter(is_system=True).count() == 4

    def test_os_modelos_oficiais_continuam_com_layout(self):
        """Modelo oficial sem layout não gera carta nenhuma."""
        from apps.doctemplates.models import DocumentTemplate

        for modelo in DocumentTemplate.objects.filter(is_system=True):
            assert modelo.layout.get("elements"), modelo.slug

    def test_as_imagens_dos_modelos_oficiais(self):
        """
        O banco recusaria apagá-las (PROTECT), mas o comando não pode
        sequer tentar: uma exceção no meio deixaria a limpeza pela
        metade.
        """
        from apps.content.models import Asset

        assert Asset.objects.filter(template_references__isnull=False).exists()

    def test_a_logomarca_do_site(self, _executado):
        """Logomarca de verdade não é dado de teste."""
        from apps.content.models import Asset, SiteSettings

        assert Asset.objects.filter(pk=_executado["logo"].pk).exists()
        assert SiteSettings.load().logo_id == _executado["logo"].pk

    def test_o_superusuario(self, _executado):
        assert get_user_model().objects.filter(pk=_executado["chefe"].pk).exists()

    def test_as_configuracoes_do_sistema(self):
        from apps.content.models import SiteSettings
        from apps.core.models import EmailSettings
        from apps.letters import lifecycle, services
        from apps.letters.models import DocumentLanguageSettings, LetterPolicy

        assert SiteSettings.objects.filter(pk=SiteSettings.SINGLETON_ID).exists()
        assert EmailSettings.objects.exists()
        # Cada singleton tem o seu ponto de entrada -- nenhum deles é
        # construído direto, e é por isso que se pergunta por ali.
        assert lifecycle.policy() is not None
        assert services.configuracao_de_idiomas() is not None
        assert LetterPolicy.objects.count() <= 1
        assert DocumentLanguageSettings.objects.count() <= 1

    def test_as_permissoes(self):
        from django.contrib.auth.models import Permission

        from apps.accounts import admin_permissions

        for permissao in admin_permissions.todas():
            assert Permission.objects.filter(
                content_type__app_label=permissao.app_label,
                codename=permissao.codename,
            ).exists(), permissao.chave

    def test_o_conteudo_da_pagina_inicial(self):
        """
        TODAS as partes declaradas continuam de pé.

        O número sai do schema, e não escrito aqui: sete era a
        quantidade do dia em que este teste nasceu, não a regra. A regra
        é que preparar para produção não apaga parte nenhuma da Home --
        e ela tem de continuar valendo na próxima parte que alguém
        acrescentar.
        """
        from apps.content import section_schema
        from apps.content.models import PageSection, PageSectionTranslation

        declaradas = set(section_schema.SECOES)
        no_banco = set(
            PageSection.objects.filter(page__key="home").values_list("key", flat=True)
        )

        assert no_banco == declaradas
        assert PageSectionTranslation.objects.exists()

    def test_os_itens_do_menu(self):
        from apps.content.models import MenuItem

        assert MenuItem.objects.count() == 2

    def test_o_texto_legal_de_VERDADE(self):
        """
        O que não carrega o aviso de SUBSTITUIR é texto do cliente.
        Apagá-lo seria apagar trabalho jurídico de alguém.
        """
        from apps.content.models import ContentTranslation

        privacidade = ContentTranslation.objects.filter(
            block__key="legal.privacy_policy"
        ).first()

        assert privacidade is not None
        assert "de verdade" in privacidade.content


class TestContatoDeVerdade:
    """Contato que não aponta para `exemplo.test` fica onde está."""

    def test_nao_e_apagado(self, mundo):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.contact_email = "contato@cliente-real.test"
        config.contact_phone = "+32 2 000 00 00"
        config.contact_address = "Rua de verdade, 10"
        config.social_links = {"facebook": "https://facebook.test/cliente"}
        config.save()

        rodar("--confirmar", "--nao-perguntar")

        config = SiteSettings.load()
        assert config.contact_email == "contato@cliente-real.test"
        assert config.contact_phone == "+32 2 000 00 00"
        assert config.social_links != {}

    def test_o_relatorio_diz_que_nao_ha_contato_de_demonstracao(self, mundo):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.contact_email = "contato@cliente-real.test"
        config.contact_address = "Rua de verdade, 10"
        config.social_links = {}
        config.save()

        saida = rodar()

        assert "não  contato/redes de demonstração" in saida.replace("  não", " não")


# ===========================================================================
# 4. O site continua de pé depois
# ===========================================================================


class TestOSiteContinuaDePe:
    @pytest.fixture(autouse=True)
    def _executado(self, mundo):
        rodar("--confirmar", "--nao-perguntar")

    def test_a_home_abre(self, client):
        from django.urls import reverse

        assert client.get(reverse("core:home")).status_code == 200

    def test_a_home_nao_mostra_parceiro_nenhum(self, client):
        from django.urls import reverse

        corpo = client.get(reverse("core:home")).content.decode()

        assert "Global Travel Services" not in corpo
        assert "Parceiro de verdade" not in corpo

    def test_o_superusuario_ainda_entra(self, client, mundo):
        from django.urls import reverse

        client.force_login(mundo["chefe"])

        assert client.get(reverse("core:dashboard")).status_code == 200

    def test_ainda_da_para_criar_carta(self, client, mundo):
        """
        A prova de que a limpeza não quebrou o produto: os modelos
        oficiais continuam inteiros e uma carta nova nasce.
        """
        from apps.letters import services as letras

        rascunho = letras.start_draft(mundo["chefe"], "fr")

        assert rascunho is not None
        assert rascunho.document_template.is_system

    def test_rodar_de_novo_nao_estoura(self, mundo):
        """Idempotente: um banco já limpo não tem o que limpar."""
        saida = rodar("--confirmar", "--nao-perguntar")

        assert "instalação nova" in saida


# ===========================================================================
# 5. O comando não roda sozinho
# ===========================================================================


class TestNaoRodaSozinho:
    def test_nao_ha_migration_que_apague_dado(self):
        """
        Apagar dado numa migration faria isso em TODA subida, para
        sempre -- e um dia num banco que ninguém quis limpar.
        """
        import pathlib

        suspeitas = []
        for arquivo in pathlib.Path("apps").glob("*/migrations/*.py"):
            texto = arquivo.read_text(encoding="utf-8")
            if ".objects.all().delete()" in texto and "remover" not in arquivo.name:
                # `RunPython(..., remover)` é a REVERSÃO de uma migration
                # de dados, e essa é legítima.
                corpo = texto.split("def remover")[0]
                if ".objects.all().delete()" in corpo:
                    suspeitas.append(str(arquivo))

        assert not suspeitas, f"migration apagando dado: {suspeitas}"

    def test_o_comando_se_declara_irreversivel(self):
        from apps.core.management.commands import preparar_para_producao

        texto = preparar_para_producao.__doc__

        assert "confirma" in texto.lower()
        assert "NUNCA TOCA" in texto


class TestDatasNaoInterferem:
    """O comando não depende de que horas são."""

    def test_apaga_carta_de_qualquer_data(self, mundo):
        from apps.letters.models import Letter

        Letter.objects.update(created_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC))

        rodar("--confirmar", "--nao-perguntar")

        assert Letter.objects.count() == 0

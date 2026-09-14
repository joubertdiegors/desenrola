"""Fixtures compartilhadas pelos testes do projeto."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import translation

SENHA = "senha-forte-123"


@pytest.fixture(autouse=True)
def idioma_padrao():
    """
    O LocaleMiddleware ativa o idioma da URL na thread e o cliente de teste
    nao desfaz isso. Sem esta limpeza, um teste em /fr/ faria o `reverse`
    dos testes seguintes gerar URLs em frances.
    """
    translation.activate("pt")
    yield
    translation.deactivate()


@pytest.fixture
def nacionalidade_do_perfil(db):
    """
    A nacionalidade do perfil da usuaria de teste -- a mesma do anfitriao
    do documento oficial ("de nationalité belge").
    """
    from apps.doctemplates.models import Nationality

    nacionalidade, _criada = Nationality.objects.get_or_create(
        code="belge",
        defaults={
            "name_pt": "Belga",
            "name_fr": "Belge",
            "name_nl": "Belgische",
            "name_en": "Belgian",
            "guest_form": "Belge",
            "host_form": "belge",
        },
    )
    return nacionalidade


@pytest.fixture
def user(db, nacionalidade_do_perfil):
    """
    Usuaria comum com senha conhecida (SENHA).

    Os dados de perfil sao os MESMOS do anfitriao do documento oficial
    (pdfengine/assets/fr/) de proposito: assim os testes que finalizam uma
    carta de ponta a ponta geram um PDF comparavel com o modelo real.
    A cidade fica num campo proprio (`city`), separada do endereco -- e de
    la que sai o "Fait à <cidade>" do fecho do documento. O numero do
    documento tambem vem do perfil, nao do assistente.
    """
    return get_user_model().objects.create_user(
        email="claire@exemplo.be",
        password=SENHA,
        full_name="Claire Dubois",
        phone="+32 470 00 00 00",
        document_number="00000000",
        birth_date=datetime.date(1985, 3, 14),
        nationality=nacionalidade_do_perfil,
        address_line1="Rue des Exemple 25",
        postal_code="1200",
        city="Woluwe-Saint-Lambert",
    )


@pytest.fixture
def other_user(db):
    """Segundo usuario, para testes de isolamento."""
    return get_user_model().objects.create_user(
        email="rafael@exemplo.com",
        password=SENHA,
        full_name="Rafael Costa",
    )


@pytest.fixture
def permissao_backoffice(db):
    """A permissao que abre o Backoffice, `core.access_backoffice`."""
    from django.contrib.auth.models import Permission

    return Permission.objects.get(
        content_type__app_label="core", codename="access_backoffice"
    )


@pytest.fixture
def staff_user(db, permissao_backoffice):
    """
    Uma administradora de verdade: `is_staff` E a permissao de entrar
    no Backoffice.

    As duas coisas, porque desde a etapa do ciclo de vida quem abre a
    porta e a PERMISSAO -- `is_staff` sozinho nao abre mais nada (ver
    `core.views.backoffice_required`). Para o caso oposto, use
    `staff_sem_backoffice`.
    """
    usuario = get_user_model().objects.create_user(
        email="ana@desenrola.be",
        password=SENHA,
        full_name="Ana Martins",
        is_staff=True,
    )
    usuario.user_permissions.add(permissao_backoffice)
    return get_user_model().objects.get(pk=usuario.pk)


@pytest.fixture
def staff_sem_backoffice(db):
    """
    Alguem com `is_staff` mas SEM `core.access_backoffice`.

    Existe para provar que a flag sozinha nao abre a area
    administrativa -- era assim antes, e deixou de ser.
    """
    return get_user_model().objects.create_user(
        email="bruno@desenrola.be",
        password=SENHA,
        full_name="Bruno Alves",
        is_staff=True,
    )


@pytest.fixture
def auth_client(client, user):
    """Cliente ja autenticado como `user`."""
    client.force_login(user)
    return client


@pytest.fixture
def modelos_oficiais_prontos(tmp_path, settings):
    """
    Os quatro modelos oficiais completos: layout (ja vem da migration) e
    o asset do logo materializado.

    `services.official_document_template()` so devolve um modelo quando o
    asset existe de verdade -- sem isto, `start_draft()` devolveria None
    e nenhuma carta nasceria. E o equivalente, no teste, ao passo de
    deploy `reconstruir_modelos_oficiais`.

    MEDIA_ROOT proprio: sem isso a suite gravaria um PNG no `media/` do
    repositorio a cada execucao.
    """
    from apps.content.models import Asset
    from apps.doctemplates.models import DocumentTemplate
    from apps.doctemplates.services import carta_convite

    settings.MEDIA_ROOT = tmp_path
    carta_convite.reconstruir_todos(DocumentTemplate, Asset)
    return tmp_path


@pytest.fixture
def letter(user, modelos_oficiais_prontos):
    """
    Um rascunho real de `user`, criado pelo mesmo caminho que o sistema
    usa (`services.start_draft`) -- ou seja, ligado ao `DocumentTemplate`
    oficial do idioma, com o field_schema de verdade. E o que as telas do
    usuario encontram na pratica.
    """
    from apps.letters import services

    return services.start_draft(user, "fr")


@pytest.fixture
def nacionalidade_factory(db):
    """
    Fábrica para criar `Nationality` de teste.

    Usada pelos arquivos de teste cujos payloads submetem o assistente
    real via HTTP (test_wizard.py, test_navegacao.py, test_dashboard.py,
    test_render_letter.py): desde a decisão final da Fase 5/Etapa 3, o
    campo de nacionalidade não aceita mais texto livre -- precisa de uma
    `Nationality` ativa cujo `code` bata com o valor enviado no POST.

    NÃO é uma lista oficial de nacionalidades (essa ainda não existe --
    ver apps/letters/tests/test_nacionalidade_e_documento.py, que testa o
    cadastro em si e o comportamento com a tabela vazia).
    """
    from apps.doctemplates.models import Nationality

    def _criar(code, *, name_pt=None, guest_form=None, host_form=None):
        nome = name_pt or code
        nacionalidade, _criada = Nationality.objects.get_or_create(
            code=code,
            defaults={
                "name_pt": nome,
                "name_fr": guest_form or nome,
                "name_nl": nome,
                "name_en": nome,
                "guest_form": guest_form or nome,
                "host_form": host_form or nome,
            },
        )
        return nacionalidade

    return _criar


@pytest.fixture
def permissao_ver_todas(db):
    """A permissao de supervisao `letters.view_all_letters`."""
    from django.contrib.auth.models import Permission

    return Permission.objects.get(
        content_type__app_label="letters", codename="view_all_letters"
    )

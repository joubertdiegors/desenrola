"""Fixtures compartilhadas pelos testes do projeto."""

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
def user(db):
    """Usuaria comum com senha conhecida (SENHA)."""
    return get_user_model().objects.create_user(
        email="claire@exemplo.be",
        password=SENHA,
        full_name="Claire Dubois",
        phone="+32 470 00 00 00",
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
def staff_user(db):
    return get_user_model().objects.create_user(
        email="ana@desenrola.be",
        password=SENHA,
        full_name="Ana Martins",
        is_staff=True,
    )


@pytest.fixture
def auth_client(client, user):
    """Cliente ja autenticado como `user`."""
    client.force_login(user)
    return client


@pytest.fixture
def letter_template(db):
    """Um LetterTemplate qualquer, para testes de doctemplates/letters."""
    from apps.doctemplates.models import LetterTemplate

    return LetterTemplate.objects.create(
        name="Carta Convite — curta duração",
        slug="carta-convite-curta-duracao-fr",
        description="Modelo oficial para visitas de curta duração.",
        language="fr",
    )


@pytest.fixture
def draft_version(letter_template):
    """Uma TemplateVersion em rascunho, ligada a `letter_template`."""
    from apps.doctemplates.models import TemplateVersion

    return TemplateVersion.objects.create(
        template=letter_template,
        version_number=1,
        field_schema={"fields": ["nome_convidado", "passaporte"]},
    )


@pytest.fixture
def published_version(draft_version):
    """Uma TemplateVersion publicada (imutável), a partir de `draft_version`."""
    draft_version.publish()
    return draft_version

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
    """
    Um LetterTemplate qualquer, para testes de doctemplates/letters.

    O slug e deliberadamente diferente dos modelos oficiais semeados por
    migracao (apps/doctemplates/official_templates.py): este e um modelo
    de teste generico, nao o documento oficial de nenhum idioma.
    """
    from apps.doctemplates.models import LetterTemplate

    return LetterTemplate.objects.create(
        name="Carta Convite — curta duração",
        slug="carta-convite-de-teste",
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


@pytest.fixture
def letter(user):
    """
    Um rascunho real de `user`, criado pelo mesmo caminho que o sistema
    usa (`services.start_draft`) -- ou seja, ligado ao modelo oficial
    publicado do idioma, com o field_schema de verdade. E o que as telas
    do usuario encontram na pratica.
    """
    from apps.letters import services

    return services.start_draft(user, "fr")


@pytest.fixture
def nacionalidade_factory(db):
    """
    Fábrica para criar `Nationality` de teste.

    Usada pelos arquivos de teste cujos payloads submetem o assistente
    real via HTTP (test_wizard.py, test_navegacao.py, test_dashboard.py,
    test_pdf_generation.py): desde a decisão final da Fase 5/Etapa 3, o
    campo de nacionalidade não aceita mais texto livre -- precisa de uma
    `Nationality` ativa cujo `code` bata com o valor enviado no POST.

    NÃO é uma lista oficial de nacionalidades (essa ainda não existe --
    ver apps/letters/tests/test_nacionalidade_e_documento.py, que testa o
    cadastro em si e o comportamento com a tabela vazia).
    """
    from apps.doctemplates.models import Nationality

    def _criar(code, *, name_pt=None, guest_form=None, host_form=None):
        nome = name_pt or code
        return Nationality.objects.create(
            code=code,
            name_pt=nome,
            name_fr=guest_form or nome,
            name_nl=nome,
            name_en=nome,
            guest_form=guest_form or nome,
            host_form=host_form or nome,
        )

    return _criar


@pytest.fixture
def permissao_ver_todas(db):
    """A permissao de supervisao `letters.view_all_letters`."""
    from django.contrib.auth.models import Permission

    return Permission.objects.get(
        content_type__app_label="letters", codename="view_all_letters"
    )

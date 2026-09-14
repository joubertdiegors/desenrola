"""
Testes das telas de carta pronta: o detalhe (`letters:detail`) e a
entrega do PDF (`letters:pdf`), ambos sempre pela UUID publica e sempre
so para o dono.

O assistente (`letters:new` -> `letters:step`) tem cobertura propria em
test_wizard.py; a ponte com o renderer estrutural, em
test_render_letter.py.
"""

import uuid as uuid_lib

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.letters.models import Letter

pytestmark = pytest.mark.django_db


@pytest.fixture
def letter_gerada(letter):
    """Uma carta com PDF guardado, como depois de uma geração real."""
    letter.pdf_file.save("teste.pdf", ContentFile(b"%PDF-1.4 conteudo de teste"), save=False)
    letter.pdf_sha256 = "0" * 64
    letter.status = Letter.Status.GENERATED
    letter.save()
    return letter


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_criar_carta_exige_login(client):
    url = reverse("letters:new")
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_detalhe_exige_login(client, letter):
    url = reverse("letters:detail", args=[letter.uuid])
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_pdf_exige_login(client, letter_gerada):
    url = reverse("letters:pdf", args=[letter_gerada.uuid])
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


# ---------------------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------------------


class TestDetalhe:
    def test_dono_ve_a_propria_carta(self, auth_client, letter):
        response = auth_client.get(reverse("letters:detail", args=[letter.uuid]))

        assert response.status_code == 200
        assert letter.reference in response.content.decode()

    def test_terceiro_recebe_404(self, client, other_user, letter):
        client.force_login(other_user)

        response = client.get(reverse("letters:detail", args=[letter.uuid]))

        assert response.status_code == 404

    def test_permissao_de_ver_todas_nao_abre_o_detalhe_alheio(
        self, client, other_user, letter, permissao_ver_todas
    ):
        """
        `letters.view_all_letters` é supervisão, e a tela de supervisão
        não existe ainda -- aqui continua valendo só a propriedade.
        """
        other_user.user_permissions.add(permissao_ver_todas)
        client.force_login(other_user)

        response = client.get(reverse("letters:detail", args=[letter.uuid]))

        assert response.status_code == 404

    def test_uuid_inexistente_da_404(self, auth_client):
        response = auth_client.get(reverse("letters:detail", args=[uuid_lib.uuid4()]))

        assert response.status_code == 404

    def test_mostra_convidado_e_periodo(self, auth_client, letter):
        letter.data = {
            "guest_name": "Maria Santos da Silva",
            "stay_arrival": "2026-10-10",
            "stay_departure": "2026-10-24",
        }
        letter.save(update_fields=["data"])

        corpo = auth_client.get(reverse("letters:detail", args=[letter.uuid])).content.decode()

        assert "Maria Santos da Silva" in corpo
        assert "10/10/2026" in corpo
        assert "24/10/2026" in corpo


# ---------------------------------------------------------------------------
# PDF privado
# ---------------------------------------------------------------------------


class TestPdfPrivado:
    def test_dono_baixa_o_proprio_pdf(self, auth_client, letter_gerada):
        response = auth_client.get(reverse("letters:pdf", args=[letter_gerada.uuid]))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert b"".join(response.streaming_content) == b"%PDF-1.4 conteudo de teste"

    def test_content_disposition_traz_a_referencia(self, auth_client, letter_gerada):
        response = auth_client.get(reverse("letters:pdf", args=[letter_gerada.uuid]))

        disposition = response["Content-Disposition"]
        assert f'filename="{letter_gerada.reference}.pdf"' in disposition
        # "Ver PDF" abre no navegador; não força download
        assert disposition.startswith("inline")

    def test_terceiro_recebe_404(self, client, other_user, letter_gerada):
        client.force_login(other_user)

        response = client.get(reverse("letters:pdf", args=[letter_gerada.uuid]))

        assert response.status_code == 404

    def test_permissao_de_ver_todas_nao_baixa_pdf_alheio(
        self, client, other_user, letter_gerada, permissao_ver_todas
    ):
        other_user.user_permissions.add(permissao_ver_todas)
        client.force_login(other_user)

        response = client.get(reverse("letters:pdf", args=[letter_gerada.uuid]))

        assert response.status_code == 404

    def test_carta_sem_pdf_da_404(self, auth_client, letter):
        assert not letter.pdf_file

        response = auth_client.get(reverse("letters:pdf", args=[letter.uuid]))

        assert response.status_code == 404

    def test_uuid_inexistente_da_404(self, auth_client):
        response = auth_client.get(reverse("letters:pdf", args=[uuid_lib.uuid4()]))

        assert response.status_code == 404

    def test_arquivo_sumido_do_disco_da_404(self, auth_client, letter_gerada):
        """
        O registro aponta para um arquivo que não está mais lá: para quem
        pede, é o mesmo que não existir -- nunca um erro 500.
        """
        letter_gerada.pdf_file.storage.delete(letter_gerada.pdf_file.name)

        response = auth_client.get(reverse("letters:pdf", args=[letter_gerada.uuid]))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# URLs públicas
# ---------------------------------------------------------------------------


class TestUrlsUsamUuid:
    def test_detalhe_e_pdf_nao_expoem_id_sequencial(self, letter):
        """
        Um id em sequência deixaria adivinhar quantas cartas existem e
        tentar as dos outros. A URL pública é sempre a UUID.
        """
        for nome in ("letters:detail", "letters:pdf"):
            url = reverse(nome, args=[letter.uuid])
            assert str(letter.uuid) in url
            assert f"/{letter.pk}/" not in url

    def test_nao_existe_mais_rota_de_conclusao_ficticia(self):
        from django.urls import NoReverseMatch

        for nome in ("letters:result", "letters:generate"):
            with pytest.raises(NoReverseMatch):
                reverse(nome, args=[1])

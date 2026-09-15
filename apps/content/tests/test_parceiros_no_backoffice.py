"""
A tela de Parceiros, depois do fechamento do bloco CMS.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a tela volte a mostrar dados de demonstração.** Até a Etapa I
   ela servia `demo.ADMIN_PARTNERS` -- quatro parceiros escritos no
   código, que não estavam no banco e que a Home nunca mostrou. Quem
   administrava via uma coisa; quem visitava via outra;
2. **Que existam botões que não fazem nada.** Havia três: "Novo
   parceiro", "Editar" e "Remover";
3. **Que a tela e a Home discordem.** As duas leem o mesmo modelo.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.content.models import Asset, Partner

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:partners")
HOME = reverse("core:home")


def _gif(nome="p.gif"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        nome,
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
        content_type="image/gif",
    )


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(TELA)

        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse("accounts:login"))

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(TELA).status_code == 403


class TestMostraARealidade:
    def test_sem_parceiros_diz_que_nao_ha(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "Nenhum parceiro cadastrado" in corpo

    def test_mostra_o_parceiro_do_banco(self, client, staff_user):
        Partner.objects.create(name="JD-Print", description="Impressões 3D.")
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "JD-Print" in corpo
        assert "Impressões 3D." in corpo

    def test_nao_mostra_parceiro_que_nao_esta_no_banco(self, client, staff_user):
        """
        Os quatro de `demo.ADMIN_PARTNERS` eram estes. Nenhum deles pode
        aparecer numa tela que lê o banco vazio.
        """
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "Confiar Viagens" not in corpo
        assert "Nome do parceiro" not in corpo

    def test_os_dados_de_demonstracao_sairam_do_projeto(self):
        from apps.core import demo

        assert not hasattr(demo, "ADMIN_PARTNERS")

    def test_diz_quando_falta_imagem(self, client, staff_user):
        Partner.objects.create(name="Sem imagem")
        logo = Asset.objects.create(key="p1", kind=Asset.Kind.PARTNER, file=_gif())
        Partner.objects.create(name="Com imagem", logo=logo)
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "Sem imagem" in corpo
        assert "Cadastrada" in corpo

    def test_diz_quem_aparece_e_quem_esta_oculto(self, client, staff_user):
        Partner.objects.create(name="Visível", is_active=True)
        Partner.objects.create(name="Escondido", is_active=False)
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "Aparece" in corpo
        assert "Oculto" in corpo

    def test_a_tela_e_a_home_leem_o_mesmo_modelo(self, client, staff_user):
        """
        O defeito que esta etapa corrigiu era exatamente a divergência:
        a tela lia o código, a Home lia o banco.
        """
        Partner.objects.create(name="JD-Print", is_active=True)

        publico = client.get(HOME).content.decode()
        client.force_login(staff_user)
        admin = client.get(TELA).content.decode()

        assert "JD-Print" in publico
        assert "JD-Print" in admin


class TestSemBotaoInerte:
    def test_nao_ha_botao_que_nao_faz_nada(self, client, staff_user):
        Partner.objects.create(name="JD-Print")
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()
        # O menu e a casca trazem botões de verdade; a pergunta é sobre
        # os três que havia NESTA tela.
        for inerte in ("Novo parceiro", "Aguardando imagem"):
            assert inerte not in corpo

    def test_aponta_para_onde_se_cadastra(self, client, staff_user):
        """Não há formulário aqui: quem cadastra é o Django Admin."""
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert reverse("admin:content_partner_changelist") in corpo
        assert '<form' not in corpo.split('id="main"')[-1].split("</main>")[0]


class TestCusto:
    def test_mais_parceiros_nao_custam_mais_consultas(self, client, staff_user):
        client.force_login(staff_user)

        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                client.get(TELA)
            # Parceiro E imagem: sem `select_related`, o custo extra cai
            # em `content_asset`, e nao em `content_partner` -- contar so
            # a primeira tabela nao mediria nada.
            return len(
                [
                    c
                    for c in capturadas
                    if "content_partner" in c["sql"] or "content_asset" in c["sql"]
                ]
            )

        Partner.objects.create(name="Um")
        com_um = consultas()

        for indice in range(5):
            logo = Asset.objects.create(
                key=f"p{indice}", kind=Asset.Kind.PARTNER, file=_gif(f"p{indice}.gif")
            )
            Partner.objects.create(name=f"Parceiro {indice}", logo=logo)

        assert consultas() == com_um

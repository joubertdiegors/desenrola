"""
Validação para gerar carta convite -- a política do Wizzard.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que instalar a novidade tranque alguém.** O padrão é "não exigir
   nenhuma confirmação", e com ele tudo continua exatamente como era --
   inclusive para quem nunca confirmou nada;
2. **Que telefone PREENCHIDO passe por telefone CONFIRMADO.** Digitar um
   número não prova posse nenhuma. Só `phone_verified_at` (posto pelo
   código do SMS) libera;
3. **Que o bloqueio dependa do botão.** Esconder o botão não protege a
   rota: o assistente é trancado no SERVIDOR, e a URL digitada à mão
   volta ao painel com a mesma frase;
4. **Que o botão suma.** Ele continua na tela, desabilitado, com o aviso
   vermelho ao lado dizendo exatamente o que falta -- some o destino,
   não o convite;
5. **Que a frase minta.** "E-mail", "telefone" ou "e-mail e telefone":
   a mensagem nomeia o que falta, e é a MESMA no servidor e na tela;
6. **Que a política seja mudada por quem não pode.** Ver a tela é uma
   coisa; salvar exige `letters.change_letterpolicy`, conferido no
   servidor;
7. **Que a regra se espalhe.** Uma função (`letters.requisitos`) responde
   para a view, para o template e para os testes -- e é a que muda
   quando a regra mudar.
"""

import datetime

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.letters import requisitos, services
from apps.letters.models import Letter, LetterPolicy

pytestmark = pytest.mark.django_db

REQUISITO = LetterPolicy.GenerationRequirement

FRASE_EMAIL = "Confirme seu e-mail para gerar a carta convite."
FRASE_TELEFONE = "Confirme seu telefone para gerar a carta convite."
FRASE_OS_DOIS = "Confirme seu e-mail e seu telefone para gerar a carta convite."

NOVA = reverse("letters:new")
PAINEL = reverse("core:dashboard")
TELA_DA_POLITICA = reverse("backoffice:letter_policy")

VALID_STEP_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "FA123456",
}


@pytest.fixture(autouse=True)
def _nacionalidades_de_teste(nacionalidade_factory):
    """As nacionalidades usadas pelo payload da etapa 1 deste arquivo."""
    nacionalidade_factory("Brasileira")
    nacionalidade_factory("Belga")


def politica(valor):
    """Grava a política vigente -- o que o Backoffice faria."""
    config, _criado = LetterPolicy.objects.get_or_create(pk=LetterPolicy.SINGLETON_ID)
    config.generation_requirement = valor
    config.save(update_fields=["generation_requirement"])
    return config


def confirmar_email(user):
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])


def confirmar_telefone(user):
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])


# ===========================================================================
# 1. A regra, sozinha
# ===========================================================================


class TestRegra:
    def test_sem_configuracao_nenhuma_o_padrao_e_nao_exigir(self, user):
        """Instalação nova, ninguém configurou: a política nasce liberada."""
        assert not LetterPolicy.objects.exists()

        pendentes = requisitos.requisitos_para_gerar(user)

        assert pendentes.politica == REQUISITO.NENHUMA
        assert pendentes.pode_gerar
        assert pendentes.mensagem == ""

    def test_politica_sem_validacao_libera_conta_sem_nada_confirmado(self, user):
        politica(REQUISITO.NENHUMA)

        assert requisitos.requisitos_para_gerar(user).pode_gerar

    def test_politica_de_email_bloqueia_quem_nao_confirmou(self, user):
        politica(REQUISITO.EMAIL)

        pendentes = requisitos.requisitos_para_gerar(user)

        assert not pendentes.pode_gerar
        assert pendentes.falta_email
        assert not pendentes.falta_telefone
        assert str(pendentes.mensagem) == FRASE_EMAIL

    def test_politica_de_email_libera_quem_confirmou(self, user):
        politica(REQUISITO.EMAIL)
        confirmar_email(user)

        assert requisitos.requisitos_para_gerar(user).pode_gerar

    def test_politica_de_email_ignora_o_telefone(self, user):
        """Telefone por confirmar não bloqueia numa política só de e-mail."""
        politica(REQUISITO.EMAIL)
        confirmar_email(user)
        assert user.phone and not user.telefone_confirmado

        assert requisitos.requisitos_para_gerar(user).pode_gerar

    def test_politica_dos_dois_sem_nada_confirmado(self, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)

        pendentes = requisitos.requisitos_para_gerar(user)

        assert not pendentes.pode_gerar
        assert pendentes.falta_email and pendentes.falta_telefone
        assert str(pendentes.mensagem) == FRASE_OS_DOIS

    def test_politica_dos_dois_com_email_confirmado(self, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)

        pendentes = requisitos.requisitos_para_gerar(user)

        assert not pendentes.pode_gerar
        assert str(pendentes.mensagem) == FRASE_TELEFONE

    def test_politica_dos_dois_com_telefone_confirmado(self, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_telefone(user)

        pendentes = requisitos.requisitos_para_gerar(user)

        assert not pendentes.pode_gerar
        assert str(pendentes.mensagem) == FRASE_EMAIL

    def test_politica_dos_dois_com_tudo_confirmado_libera(self, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)
        confirmar_telefone(user)

        assert requisitos.requisitos_para_gerar(user).pode_gerar

    def test_telefone_preenchido_nao_e_telefone_confirmado(self, user):
        """O ponto central: o campo cheio não prova posse do número."""
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)
        user.phone = "+32470123456"
        user.save(update_fields=["phone"])

        pendentes = requisitos.requisitos_para_gerar(user)

        assert not pendentes.pode_gerar
        assert pendentes.falta_telefone

    def test_anonimo_nao_e_assunto_desta_regra(self, client):
        """Quem tranca a porta para quem não entrou é o `login_required`."""
        politica(REQUISITO.EMAIL_E_TELEFONE)
        resposta = client.get(PAINEL)

        assert requisitos.requisitos_para_gerar(resposta.wsgi_request.user).pode_gerar


# ===========================================================================
# 2. O bloqueio no servidor -- a URL digitada à mão
# ===========================================================================


class TestServidor:
    def test_get_do_assistente_bloqueado_volta_ao_painel_com_a_frase(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        resposta = auth_client.get(NOVA, follow=True)

        assert resposta.redirect_chain[-1][0].endswith(PAINEL)
        assert FRASE_EMAIL in resposta.content.decode()

    def test_post_bloqueado_nao_cria_carta(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        resposta = auth_client.post(NOVA, VALID_STEP_1)

        assert resposta.status_code == 302
        assert not Letter.objects.exists()

    def test_etapa_do_assistente_tambem_e_trancada(self, auth_client, user, letter):
        """Um rascunho que já existia não vira porta dos fundos."""
        politica(REQUISITO.EMAIL)

        resposta = auth_client.get(reverse("letters:step", args=[letter.uuid, 1]))

        assert resposta.status_code == 302
        assert resposta.url == PAINEL

    def test_com_o_requisito_cumprido_o_assistente_abre(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        politica(REQUISITO.EMAIL)
        confirmar_email(user)

        assert auth_client.get(NOVA).status_code == 200

    def test_sem_politica_o_assistente_abre_como_sempre(
        self, auth_client, modelos_oficiais_prontos
    ):
        assert auth_client.get(NOVA).status_code == 200

    def test_a_politica_vale_tambem_para_superusuario(self, client, staff_user):
        """
        Regra de negócio sobre os dados da própria conta, e não
        permissão: quem administra vê a barreira que ligou.
        """
        staff_user.is_superuser = True
        staff_user.save(update_fields=["is_superuser"])
        politica(REQUISITO.EMAIL)
        client.force_login(staff_user)

        resposta = client.get(NOVA)

        assert resposta.status_code == 302
        assert resposta.url == PAINEL

    def test_o_que_ja_existe_continua_alcancavel(self, auth_client, user, letter):
        """A regra protege a GERAÇÃO -- não tranca histórico nem carta pronta."""
        politica(REQUISITO.EMAIL_E_TELEFONE)

        assert auth_client.get(reverse("letters:history")).status_code == 200
        assert auth_client.get(reverse("letters:detail", args=[letter.uuid])).status_code == 200

    def test_anonimo_continua_indo_para_o_login(self, client):
        politica(REQUISITO.EMAIL)

        resposta = client.get(NOVA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url


# ===========================================================================
# 3. O botão e o aviso na tela
# ===========================================================================


class TestInterface:
    def test_liberado_o_botao_e_um_link_para_o_assistente(self, auth_client):
        corpo = auth_client.get(PAINEL).content.decode()

        assert f'href="{NOVA}"' in corpo
        assert "<button type=\"button\" class=\"btn btn-primary\" disabled" not in corpo
        assert "notice notice-error" not in corpo

    def test_bloqueado_o_botao_continua_na_tela_desabilitado(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        corpo = auth_client.get(PAINEL).content.decode()

        # O convite continua visível...
        assert "Começar" in corpo
        # ...mas sem destino e desabilitado.
        assert f'href="{NOVA}"' not in corpo
        assert "<button type=\"button\" class=\"btn btn-primary\" disabled" in corpo

    def test_bloqueado_mostra_a_frase_em_vermelho(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        corpo = auth_client.get(PAINEL).content.decode()

        assert "notice notice-error" in corpo
        assert FRASE_EMAIL in corpo

    def test_falta_email_traz_o_reenvio_que_ja_existe(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        corpo = auth_client.get(PAINEL).content.decode()

        assert reverse("accounts:email_confirm_resend") in corpo

    def test_falta_telefone_traz_o_caminho_da_confirmacao(self, auth_client, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)

        corpo = auth_client.get(PAINEL).content.decode()

        assert FRASE_TELEFONE in corpo
        assert reverse("accounts:phone_confirm") in corpo

    def test_a_frase_muda_com_o_que_falta(self, auth_client, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)

        corpo = auth_client.get(PAINEL).content.decode()

        assert FRASE_OS_DOIS in corpo

    def test_o_historico_bloqueia_do_mesmo_jeito(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        corpo = auth_client.get(reverse("letters:history")).content.decode()

        assert "Gerar Carta Convite" in corpo
        assert f'href="{NOVA}"' not in corpo
        assert FRASE_EMAIL in corpo

    def test_a_carta_pronta_bloqueia_o_gerar_outra(self, auth_client, user, letter):
        politica(REQUISITO.EMAIL)

        corpo = auth_client.get(reverse("letters:detail", args=[letter.uuid])).content.decode()

        assert "Gerar outra carta" in corpo
        assert f'href="{NOVA}"' not in corpo
        assert FRASE_EMAIL in corpo

    def test_confirmar_libera_o_botao_sozinho(self, auth_client, user):
        """Sem nenhuma outra ação: confirmou, o botão volta a ser link."""
        politica(REQUISITO.EMAIL)
        assert f'href="{NOVA}"' not in auth_client.get(PAINEL).content.decode()

        confirmar_email(user)

        assert f'href="{NOVA}"' in auth_client.get(PAINEL).content.decode()


# ===========================================================================
# 4. Quem pode mudar a política
# ===========================================================================


class TestBackoffice:
    def test_a_tela_mostra_as_tres_opcoes(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(TELA_DA_POLITICA).content.decode()

        assert "Validação para gerar carta convite" in corpo
        assert "Não exigir nenhuma confirmação" in corpo
        assert "Exigir confirmação de e-mail" in corpo
        assert "Exigir confirmação de e-mail e telefone" in corpo

    def test_a_validacao_vem_antes_das_outras_configuracoes(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(TELA_DA_POLITICA).content.decode()

        assert corpo.index("Validação para gerar carta convite") < corpo.index(
            "Edição depois de finalizar"
        )

    def test_quem_tem_a_permissao_grava(self, client, staff_user):
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="letters", codename="change_letterpolicy"
            )
        )
        client.force_login(staff_user)

        client.post(
            TELA_DA_POLITICA,
            {
                "generation_requirement": REQUISITO.EMAIL_E_TELEFONE,
                "editability": LetterPolicy.Editability.NAO_EDITAVEL,
                "editability_amount": 0,
                "expiration": LetterPolicy.Expiration.NUNCA,
                "expiration_amount": 0,
            },
        )

        config = LetterPolicy.objects.get(pk=LetterPolicy.SINGLETON_ID)
        assert config.generation_requirement == REQUISITO.EMAIL_E_TELEFONE

    def test_sem_a_permissao_nao_grava(self, client, staff_user):
        """Entrar na tela é uma coisa; salvar exige a permissão."""
        politica(REQUISITO.NENHUMA)
        client.force_login(staff_user)

        resposta = client.post(
            TELA_DA_POLITICA,
            {
                "generation_requirement": REQUISITO.EMAIL,
                "editability": LetterPolicy.Editability.NAO_EDITAVEL,
                "editability_amount": 0,
                "expiration": LetterPolicy.Expiration.NUNCA,
                "expiration_amount": 0,
            },
        )

        assert resposta.status_code == 403
        config = LetterPolicy.objects.get(pk=LetterPolicy.SINGLETON_ID)
        assert config.generation_requirement == REQUISITO.NENHUMA

    def test_usuario_comum_nem_alcanca_a_tela(self, auth_client):
        politica(REQUISITO.NENHUMA)

        resposta = auth_client.post(
            TELA_DA_POLITICA, {"generation_requirement": REQUISITO.EMAIL}
        )

        assert resposta.status_code in (302, 403)
        assert (
            LetterPolicy.objects.get(pk=LetterPolicy.SINGLETON_ID).generation_requirement
            == REQUISITO.NENHUMA
        )

    def test_anonimo_nem_alcanca_a_tela(self, client):
        resposta = client.get(TELA_DA_POLITICA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url


# ===========================================================================
# 5. Quem já tinha conta
# ===========================================================================


class TestCompatibilidade:
    def test_o_valor_gravado_por_padrao_e_nao_exigir(self):
        config = LetterPolicy.objects.create(pk=LetterPolicy.SINGLETON_ID)

        assert config.generation_requirement == REQUISITO.NENHUMA

    def test_conta_antiga_sem_confirmacao_nenhuma_continua_gerando(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        """Enquanto ninguém ligar a barreira, nada muda para ninguém."""
        assert user.email_verified_at is None and user.phone_verified_at is None

        assert auth_client.get(NOVA).status_code == 200

    def test_ao_ligar_a_politica_quem_ja_confirmou_continua_gerando(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        confirmar_email(user)
        politica(REQUISITO.EMAIL)

        assert auth_client.get(NOVA).status_code == 200

    def test_ao_ligar_a_politica_quem_nao_confirmou_e_bloqueado(self, auth_client, user):
        politica(REQUISITO.EMAIL)

        assert auth_client.get(NOVA).status_code == 302

    def test_desligar_a_politica_destranca_na_hora(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        politica(REQUISITO.EMAIL)
        assert auth_client.get(NOVA).status_code == 302

        politica(REQUISITO.NENHUMA)

        assert auth_client.get(NOVA).status_code == 200

    def test_rascunho_de_antes_da_politica_fica_guardado(self, auth_client, user, letter):
        """
        Bloquear não apaga: a carta em rascunho continua existindo e
        volta a ser editável assim que a confirmação acontecer.
        """
        politica(REQUISITO.EMAIL)
        assert auth_client.get(reverse("letters:step", args=[letter.uuid, 1])).status_code == 302

        confirmar_email(user)

        assert auth_client.get(reverse("letters:step", args=[letter.uuid, 1])).status_code == 200
        assert Letter.objects.filter(pk=letter.pk).exists()


# ===========================================================================
# 6. A regra num lugar só
# ===========================================================================


class TestUmLugarSo:
    def test_as_views_do_assistente_usam_o_decorador(self):
        import pathlib

        fonte = pathlib.Path("apps/letters/views.py").read_text(encoding="utf-8")

        assert fonte.count("@requisitos.exige_requisitos_para_gerar") == 2

    def test_os_templates_nao_decidem_sozinhos(self):
        """
        Nenhuma tela pergunta `email_confirmado` para mostrar o botão --
        todas passam pela etiqueta, que passa pela regra.
        """
        import pathlib

        for caminho in (
            "templates/core/dashboard.html",
            "templates/letters/history.html",
            "templates/letters/detail.html",
        ):
            texto = pathlib.Path(caminho).read_text(encoding="utf-8")
            assert "botao_gerar_carta" in texto, caminho
            assert "email_confirmado" not in texto, caminho
            assert "telefone_confirmado" not in texto, caminho

    def test_a_mensagem_do_servidor_e_a_mesma_da_tela(self, auth_client, user):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)

        da_tela = auth_client.get(PAINEL).content.decode()
        do_servidor = auth_client.get(NOVA, follow=True).content.decode()

        assert FRASE_TELEFONE in da_tela
        assert FRASE_TELEFONE in do_servidor


# ===========================================================================
# 7. O assistente inteiro, com a barreira ligada
# ===========================================================================


class TestFluxoCompleto:
    def test_confirmar_no_meio_do_caminho_devolve_o_acesso(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        politica(REQUISITO.EMAIL_E_TELEFONE)
        confirmar_email(user)

        assert auth_client.get(NOVA).status_code == 302

        confirmar_telefone(user)

        resposta = auth_client.get(NOVA)
        assert resposta.status_code == 200

    def test_a_carta_nasce_depois_de_confirmar(self, auth_client, user, modelos_oficiais_prontos):
        politica(REQUISITO.EMAIL)
        auth_client.post(NOVA, VALID_STEP_1)
        assert not Letter.objects.exists()

        confirmar_email(user)
        auth_client.post(NOVA, VALID_STEP_1)

        carta = Letter.objects.get(user=user)
        assert carta.status == Letter.Status.DRAFT

    def test_o_servico_de_criacao_nao_e_o_guarda(self, user):
        """
        A regra vive na borda (view), e não em `services.start_draft`:
        um comando de manutenção ou uma migração que precise criar
        rascunho não deve esbarrar numa política de interface. O teste
        registra essa fronteira de propósito.
        """
        politica(REQUISITO.EMAIL)

        carta = services.start_draft(user, "pt")

        assert carta is None or isinstance(carta.created_at, datetime.datetime)

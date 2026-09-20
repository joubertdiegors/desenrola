"""
A confirmação de telefone -- o código que prova a posse do número.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que telefone preenchido vire telefone confirmado.** Só o código
   recebido no aparelho e digitado de volta grava
   `User.phone_verified_at`. Nada mais;
2. **Que o código fique legível no banco.** O que se guarda é o HASH.
   Quem lê a tabela não confirma o telefone de ninguém;
3. **Que um código curto seja adivinhável.** Cinco tentativas, dez
   minutos de validade e um minuto entre envios -- os três limites,
   testados no ponto exato em que passam a valer;
4. **Que o código sobreviva ao uso ou à troca de número.** Ele morre ao
   confirmar, ao expirar, ao esgotar tentativas e quando o telefone da
   conta muda -- aí ele provaria a posse do número ANTERIOR;
5. **Que a rota vire um disparador de SMS.** Pedir código é POST, e
   sempre para a própria conta;
6. **Que trocar o telefone no Perfil mantenha a marca de confirmado.**
   Trocar o número apaga a confirmação, como trocar o e-mail já fazia.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from apps.accounts import confirmacao_de_telefone as ct
from apps.accounts import sms
from apps.accounts.models import ConfirmacaoDeTelefone

pytestmark = pytest.mark.django_db

CONFIRMAR = reverse("accounts:phone_confirm")
ENVIAR = reverse("accounts:phone_confirm_send")

# O que o backend de teste recebeu: (numero, mensagem).
ENVIADOS = []


class BackendDeTeste(sms.BackendDeSms):
    """Guarda o que seria enviado, em vez de mandar para lugar nenhum."""

    def enviar(self, numero, mensagem):
        ENVIADOS.append((numero, mensagem))
        return True


class BackendQueFalha(sms.BackendDeSms):
    def enviar(self, numero, mensagem):
        raise RuntimeError("provedor fora do ar")


@pytest.fixture(autouse=True)
def backend_de_teste(settings):
    ENVIADOS.clear()
    settings.SMS_BACKEND = "apps.accounts.tests.test_confirmacao_de_telefone.BackendDeTeste"
    yield
    ENVIADOS.clear()


def codigo_enviado():
    """O código do último SMS -- os seis dígitos que estão na mensagem."""
    import re

    assert ENVIADOS, "nenhum SMS foi enviado"
    achado = re.search(r"\b(\d{6})\b", ENVIADOS[-1][1])
    assert achado, ENVIADOS[-1][1]
    return achado.group(1)


# ===========================================================================
# 1. Enviar o código
# ===========================================================================


class TestEnviar:
    def test_envia_e_guarda_um_registro(self, user):
        assert ct.enviar(user) == ct.ENVIADO

        registro = ConfirmacaoDeTelefone.objects.get(user=user)
        assert registro.phone == user.phone
        assert registro.attempts == 0
        assert len(ENVIADOS) == 1
        assert ENVIADOS[0][0] == user.phone

    def test_o_codigo_tem_seis_digitos(self, user):
        ct.enviar(user)

        assert len(codigo_enviado()) == 6

    def test_o_codigo_nao_fica_legivel_no_banco(self, user):
        ct.enviar(user)
        codigo = codigo_enviado()

        registro = ConfirmacaoDeTelefone.objects.get(user=user)
        assert codigo not in registro.code_hash
        assert registro.code_hash != codigo

    def test_sem_telefone_nao_ha_o_que_confirmar(self, user):
        user.phone = ""
        user.save(update_fields=["phone"])

        assert ct.enviar(user) == ct.SEM_TELEFONE
        assert not ConfirmacaoDeTelefone.objects.exists()

    def test_telefone_ja_confirmado_nao_recebe_codigo(self, user):
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])

        assert ct.enviar(user) == ct.JA_CONFIRMADO
        assert not ENVIADOS

    def test_dois_pedidos_seguidos_o_segundo_espera(self, user):
        assert ct.enviar(user) == ct.ENVIADO

        assert ct.enviar(user) == ct.MUITO_CEDO
        assert len(ENVIADOS) == 1

    def test_depois_da_espera_pode_pedir_de_novo(self, user):
        agora = timezone.now()
        with freeze_time(agora):
            ct.enviar(user)
        with freeze_time(agora + ct.ESPERA_ENTRE_ENVIOS):
            assert ct.enviar(user) == ct.ENVIADO
        assert len(ENVIADOS) == 2

    def test_o_codigo_novo_substitui_o_anterior(self, user):
        agora = timezone.now()
        with freeze_time(agora):
            ct.enviar(user)
        primeiro = codigo_enviado()
        with freeze_time(agora + ct.ESPERA_ENTRE_ENVIOS):
            ct.enviar(user)

        assert ConfirmacaoDeTelefone.objects.filter(user=user).count() == 1
        assert ct.conferir(user, primeiro) == ct.CODIGO_ERRADO
        assert ct.conferir(user, codigo_enviado()) == ct.CONFIRMADO

    def test_provedor_fora_do_ar_nao_levanta(self, user, settings):
        settings.SMS_BACKEND = "apps.accounts.tests.test_confirmacao_de_telefone.BackendQueFalha"

        assert ct.enviar(user) == ct.FALHA_NO_ENVIO


# ===========================================================================
# 2. Conferir o código
# ===========================================================================


class TestConferir:
    def test_codigo_certo_confirma(self, user):
        ct.enviar(user)

        assert ct.conferir(user, codigo_enviado()) == ct.CONFIRMADO

        user.refresh_from_db()
        assert user.telefone_confirmado
        assert user.phone_verified_at is not None

    def test_confirmar_apaga_o_registro(self, user):
        ct.enviar(user)
        ct.conferir(user, codigo_enviado())

        assert not ConfirmacaoDeTelefone.objects.filter(user=user).exists()

    def test_o_mesmo_codigo_nao_vale_duas_vezes(self, user):
        ct.enviar(user)
        codigo = codigo_enviado()
        ct.conferir(user, codigo)

        assert ct.conferir(user, codigo) == ct.JA_CONFIRMADO

    def test_codigo_errado_nao_confirma_e_conta_a_tentativa(self, user):
        ct.enviar(user)

        assert ct.conferir(user, "000000" if codigo_enviado() != "000000" else "111111") == (
            ct.CODIGO_ERRADO
        )

        user.refresh_from_db()
        assert not user.telefone_confirmado
        assert ConfirmacaoDeTelefone.objects.get(user=user).attempts == 1

    def test_cinco_erros_matam_o_codigo(self, user):
        ct.enviar(user)
        errado = "000000" if codigo_enviado() != "000000" else "111111"

        for _ in range(ct.MAX_TENTATIVAS - 1):
            assert ct.conferir(user, errado) == ct.CODIGO_ERRADO
        assert ct.conferir(user, errado) == ct.TENTATIVAS_ESGOTADAS

        assert not ConfirmacaoDeTelefone.objects.filter(user=user).exists()

    def test_depois_de_esgotar_o_codigo_certo_nao_vale_mais(self, user):
        ct.enviar(user)
        certo = codigo_enviado()
        errado = "000000" if certo != "000000" else "111111"
        for _ in range(ct.MAX_TENTATIVAS):
            ct.conferir(user, errado)

        assert ct.conferir(user, certo) == ct.SEM_CODIGO
        user.refresh_from_db()
        assert not user.telefone_confirmado

    def test_codigo_expirado_nao_vale(self, user):
        agora = timezone.now()
        with freeze_time(agora):
            ct.enviar(user)
            codigo = codigo_enviado()

        with freeze_time(agora + ct.VALIDADE):
            assert ct.conferir(user, codigo) == ct.EXPIRADO

        user.refresh_from_db()
        assert not user.telefone_confirmado

    def test_um_segundo_antes_de_expirar_ainda_vale(self, user):
        agora = timezone.now()
        with freeze_time(agora):
            ct.enviar(user)
            codigo = codigo_enviado()

        with freeze_time(agora + ct.VALIDADE - datetime.timedelta(seconds=1)):
            assert ct.conferir(user, codigo) == ct.CONFIRMADO

    def test_sem_codigo_pedido_nao_ha_o_que_conferir(self, user):
        assert ct.conferir(user, "123456") == ct.SEM_CODIGO

    def test_trocar_o_numero_invalida_o_codigo(self, user):
        ct.enviar(user)
        codigo = codigo_enviado()
        user.phone = "+32470999888"
        user.save(update_fields=["phone"])

        assert ct.conferir(user, codigo) == ct.TELEFONE_MUDOU

        user.refresh_from_db()
        assert not user.telefone_confirmado
        assert not ConfirmacaoDeTelefone.objects.filter(user=user).exists()


# ===========================================================================
# 3. Esquecer
# ===========================================================================


class TestEsquecer:
    def test_apaga_a_confirmacao_e_o_codigo_pendente(self, user):
        ct.enviar(user)
        ct.conferir(user, codigo_enviado())
        user.refresh_from_db()

        assert ct.esquecer(user) is True

        user.refresh_from_db()
        assert not user.telefone_confirmado
        assert not ConfirmacaoDeTelefone.objects.filter(user=user).exists()

    def test_quem_nunca_confirmou_nao_muda_nada(self, user):
        assert ct.esquecer(user) is False


# ===========================================================================
# 4. As telas
# ===========================================================================


class TestTelas:
    def test_a_tela_exige_sessao(self, client):
        resposta = client.get(CONFIRMAR)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_o_envio_exige_sessao(self, client):
        resposta = client.post(ENVIAR)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_o_envio_so_aceita_post(self, auth_client):
        assert auth_client.get(ENVIAR).status_code == 405

    def test_a_tela_abre_para_quem_tem_telefone(self, auth_client, user):
        resposta = auth_client.get(CONFIRMAR)

        assert resposta.status_code == 200
        assert user.phone in resposta.content.decode()

    def test_sem_telefone_a_tela_manda_ao_perfil(self, auth_client, user):
        user.phone = ""
        user.save(update_fields=["phone"])

        corpo = auth_client.get(CONFIRMAR).content.decode()

        assert reverse("accounts:profile") in corpo

    def test_pedir_e_confirmar_pela_tela(self, auth_client, user):
        auth_client.post(ENVIAR)

        resposta = auth_client.post(CONFIRMAR, {"codigo": codigo_enviado()}, follow=True)

        user.refresh_from_db()
        assert user.telefone_confirmado
        assert "Telefone confirmado" in resposta.content.decode()

    def test_codigo_errado_pela_tela_avisa_e_nao_confirma(self, auth_client, user):
        auth_client.post(ENVIAR)
        errado = "000000" if codigo_enviado() != "000000" else "111111"

        resposta = auth_client.post(CONFIRMAR, {"codigo": errado}, follow=True)

        user.refresh_from_db()
        assert not user.telefone_confirmado
        assert "Código incorreto" in resposta.content.decode()

    def test_o_codigo_sai_para_o_telefone_da_propria_conta(self, auth_client, user, other_user):
        auth_client.post(ENVIAR)

        assert ENVIADOS[-1][0] == user.phone
        assert not ConfirmacaoDeTelefone.objects.filter(user=other_user).exists()

    def test_a_tela_volta_para_onde_a_pessoa_estava(self, auth_client, user):
        auth_client.post(ENVIAR)

        resposta = auth_client.post(
            CONFIRMAR, {"codigo": codigo_enviado(), "next": reverse("core:dashboard")}
        )

        assert resposta.status_code == 302
        assert resposta.url == reverse("core:dashboard")


# ===========================================================================
# 5. O Perfil e a troca de número
# ===========================================================================


class TestPerfil:
    def test_trocar_o_telefone_apaga_a_confirmacao(self, auth_client, user):
        ct.enviar(user)
        ct.conferir(user, codigo_enviado())
        user.refresh_from_db()
        assert user.telefone_confirmado

        dados = {
            "action": "dados",
            "full_name": user.full_name,
            "email": user.email,
            "phone_0": "+32",
            "phone_1": "470 99 88 77",
            "birth_date": user.birth_date.strftime("%d/%m/%Y") if user.birth_date else "",
            "nationality": user.nationality_id or "",
            "document_number": user.document_number,
            "address_line1": user.address_line1,
            "postal_code": user.postal_code,
            "city": user.city,
            "country": user.country,
        }
        auth_client.post(reverse("accounts:profile"), dados)

        user.refresh_from_db()
        assert user.phone.endswith("470998877") or user.phone != ""
        assert not user.telefone_confirmado

    def test_salvar_o_perfil_sem_mexer_no_telefone_mantem_a_confirmacao(self, auth_client, user):
        ct.enviar(user)
        ct.conferir(user, codigo_enviado())
        user.refresh_from_db()
        confirmado_em = user.phone_verified_at

        from apps.accounts import telefone as telefone_util

        ddi, numero = telefone_util.separar(user.phone)
        dados = {
            "action": "dados",
            "full_name": user.full_name,
            "email": user.email,
            "phone_0": ddi,
            "phone_1": numero,
            "birth_date": user.birth_date.strftime("%d/%m/%Y") if user.birth_date else "",
            "nationality": user.nationality_id or "",
            "document_number": user.document_number,
            "address_line1": user.address_line1,
            "postal_code": user.postal_code,
            "city": user.city,
            "country": user.country,
        }
        auth_client.post(reverse("accounts:profile"), dados)

        user.refresh_from_db()
        assert user.telefone_confirmado
        assert user.phone_verified_at == confirmado_em


# ===========================================================================
# 6. O envio de SMS
# ===========================================================================


class TestSms:
    def test_o_backend_padrao_registra_no_log_e_nao_levanta(self, settings, caplog):
        import logging

        caplog.set_level(logging.INFO, logger="apps.accounts.sms")
        settings.SMS_BACKEND = sms.PADRAO

        assert sms.enviar("+32470111222", "teste") is True
        assert "+32470111222" in caplog.text

    def test_numero_vazio_nao_envia(self):
        assert sms.enviar("", "teste") is False

    def test_falha_do_provedor_vira_falso(self, settings):
        settings.SMS_BACKEND = "apps.accounts.tests.test_confirmacao_de_telefone.BackendQueFalha"

        assert sms.enviar("+32470111222", "teste") is False

"""
A cópia oculta de tudo o que o site envia (`EmailSettings.bcc_email`).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a regra fique presa a UM fluxo -- ela é do site, e um e-mail
   novo tem de nascer com ela sem ninguém lembrar;
2. que a cópia apareça para o destinatário, o que faria o BCC deixar
   de ser oculto e viraria um vazamento de endereço administrativo;
3. que acrescentar a cópia mexa em remetente, destinatário ou conteúdo;
4. que o endereço vire uma configuração que qualquer um altera;
5. que apagar o campo deixe a cópia continuar saindo.

TODO DADO AQUI É DE MENTIRA -- `mail@mail.com`, `smtp.exemplo.com`.
Nenhum endereço real entra em teste, código ou migration.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail as django_mail
from django.test import Client
from django.urls import reverse

from apps.core import mail
from apps.core.models import EmailSettings

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:email_settings")

# Nada disto existe. É o ponto.
COPIA = "copia@mail.com"
OUTRA_COPIA = "arquivo@mail.com"
DESTINO = "para@mail.com"
REMETENTE = "de@mail.com"
SERVIDOR_FALSO = "smtp.exemplo.com"
EMAIL_FALSO = "mail@mail.com"

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"

COMPLETO = {
    "host": SERVIDOR_FALSO,
    "port": 587,
    "security": EmailSettings.Security.TLS,
    "username": "",
    "password": "",
    "from_email": EMAIL_FALSO,
    "from_name": "Desenrola",
}


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def permissoes_de_email(db):
    """As duas permissões da tela: ver e alterar."""
    return {
        p.codename: p
        for p in Permission.objects.filter(
            content_type__app_label="core",
            codename__in=("view_emailsettings", "change_emailsettings"),
        )
    }


def _pessoa(email, nome, permissoes):
    User = get_user_model()
    usuario = User.objects.create_user(email=email, password="x", full_name=nome)
    usuario.user_permissions.add(*permissoes)
    return User.objects.get(pk=usuario.pk)


@pytest.fixture
def operador(permissao_backoffice, permissoes_de_email):
    """Quem pode ver E alterar a configuração de e-mail."""
    return _pessoa(
        "operadora@mail.com",
        "Clara Dias",
        [permissao_backoffice, *permissoes_de_email.values()],
    )


@pytest.fixture
def leitor(permissao_backoffice, permissoes_de_email):
    """Quem pode ver, mas não alterar."""
    return _pessoa(
        "leitor@mail.com",
        "Diego Ramos",
        [permissao_backoffice, permissoes_de_email["view_emailsettings"]],
    )


@pytest.fixture
def cliente(operador):
    c = Client()
    c.force_login(operador)
    return c


@pytest.fixture
def pela_reserva(settings):
    """
    Envio SEM SMTP cadastrado: o backend do projeto cai na reserva do
    ambiente, aqui a caixa de memória.

    É um dos DOIS caminhos de `send_messages`, e a cópia tem de valer
    nos dois -- ela não pode depender de o interruptor estar ligado.

    `EMAIL_BACKEND` DE VOLTA AO DO PROJETO
    --------------------------------------
    O pytest-django troca o backend de e-mail pela caixa de memória em
    TODO teste. Sem devolvê-lo aqui, um `send_mail()` não passaria pelo
    `ConfiguredEmailBackend` -- e o teste diria que a cópia não saiu
    quando, na aplicação de verdade, ela sai. A reserva é que recebe a
    mensagem no fim.
    """
    settings.EMAIL_BACKEND = "apps.core.mail.ConfiguredEmailBackend"
    settings.EMAIL_FALLBACK_BACKEND = LOCMEM
    return settings


@pytest.fixture
def pelo_smtp(settings, monkeypatch):
    """
    O outro caminho: configuração ATIVA, com o SMTP trocado pela caixa
    de memória.

    A reserva vira a `dummy`, que engole tudo: se a mensagem aparece na
    caixa, ela passou pelo caminho do servidor cadastrado.
    """
    settings.EMAIL_BACKEND = "apps.core.mail.ConfiguredEmailBackend"
    settings.EMAIL_FALLBACK_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
    configuracao = mail.configuracao()
    configuracao.host = SERVIDOR_FALSO
    configuracao.from_email = EMAIL_FALSO
    configuracao.is_active = True
    configuracao.save()
    monkeypatch.setattr(
        mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
    )
    return configuracao


def com_copia(endereco=COPIA):
    """Grava o endereço da cópia oculta na configuração."""
    configuracao = mail.configuracao()
    configuracao.bcc_email = endereco
    configuracao.save()
    return configuracao


def backend():
    return django_mail.get_connection("apps.core.mail.ConfiguredEmailBackend")


def enviar(**campos):
    """Um e-mail qualquer, pelo backend do projeto."""
    campos = {
        "subject": "Assunto",
        "body": "Corpo",
        "from_email": REMETENTE,
        "to": [DESTINO],
        **campos,
    }
    backend().send_messages([django_mail.EmailMessage(**campos)])
    return django_mail.outbox[-1]


# ===========================================================================
# 1. Em branco, não existe cópia
# ===========================================================================


class TestSemConfiguracao:
    def test_o_padrao_e_vazio(self):
        assert mail.configuracao().bcc_email == ""

    def test_sem_endereco_nao_ha_copia_oculta(self, pela_reserva):
        assert enviar().bcc == []

    def test_sem_endereco_nao_ha_copia_nem_pelo_smtp(self, pelo_smtp):
        assert enviar().bcc == []

    def test_a_copia_nao_entra_na_conta_de_estar_pronta(self):
        """
        Um e-mail sem cópia oculta é um e-mail perfeitamente válido: o
        campo não pode virar requisito para ligar o envio.
        """
        configuracao = mail.configuracao()
        configuracao.host = SERVIDOR_FALSO
        configuracao.from_email = EMAIL_FALSO
        configuracao.is_active = True

        assert configuracao.pronta_para_enviar() is True


# ===========================================================================
# 2. Preenchido, a cópia sai -- e só ela
# ===========================================================================


class TestComEndereco:
    def test_sai_exatamente_o_endereco_configurado(self, pela_reserva):
        com_copia()

        assert enviar().bcc == [COPIA]

    def test_sai_tambem_pelo_caminho_do_smtp(self, pelo_smtp):
        com_copia()

        assert enviar().bcc == [COPIA]

    def test_o_destinatario_original_fica_intacto(self, pela_reserva):
        com_copia()

        mensagem = enviar(to=[DESTINO, "outro@mail.com"])

        assert mensagem.to == [DESTINO, "outro@mail.com"]

    def test_o_remetente_fica_intacto(self, pela_reserva):
        com_copia()

        assert enviar().from_email == REMETENTE

    def test_o_conteudo_fica_intacto(self, pela_reserva):
        """
        A cópia é da MESMA mensagem: nem assunto nem corpo mudam, e o
        endereço da cópia não aparece escrito no texto.
        """
        com_copia()

        mensagem = enviar()

        assert mensagem.subject == "Assunto"
        assert mensagem.body == "Corpo"
        assert COPIA not in mensagem.body

    def test_nao_e_um_segundo_e_mail(self, pela_reserva):
        com_copia()
        enviar()

        assert len(django_mail.outbox) == 1

    def test_o_endereco_entra_no_envelope(self, pela_reserva):
        """`recipients()` é para quem o servidor entrega de fato."""
        com_copia()

        assert COPIA in enviar().recipients()

    def test_uma_copia_para_cada_mensagem_do_lote(self, pela_reserva):
        com_copia()

        backend().send_messages(
            [
                django_mail.EmailMessage("a", "b", REMETENTE, ["um@mail.com"]),
                django_mail.EmailMessage("c", "d", REMETENTE, ["dois@mail.com"]),
            ]
        )

        assert [m.bcc for m in django_mail.outbox] == [[COPIA], [COPIA]]

    def test_uma_copia_ja_existente_na_mensagem_e_preservada(self, pela_reserva):
        com_copia()

        mensagem = enviar(bcc=["ja@mail.com"])

        assert mensagem.bcc == ["ja@mail.com", COPIA]

    def test_nao_duplica_quem_ja_recebe(self, pela_reserva):
        """
        O endereço da cópia sendo o próprio destino, ele não entra de
        novo: duas entradas no mesmo envelope mandariam a mesma
        mensagem duas vezes para a mesma caixa.
        """
        com_copia()

        assert enviar(to=[COPIA]).bcc == []

    def test_nao_duplica_nem_com_nome_na_frente(self, pela_reserva):
        com_copia()

        assert enviar(to=[f"Arquivo <{COPIA}>"]).bcc == []


# ===========================================================================
# 3. Oculta de verdade: o destinatário não vê
# ===========================================================================


class TestNaoAparece:
    def test_nao_ha_cabecalho_bcc_na_mensagem(self, pela_reserva):
        """
        Quem garante isto é o Django -- `message()` escreve `To:` e
        `Cc:` e nunca `Bcc:`. O teste existe para que uma mudança nossa
        (mandar o endereço por cabeçalho, por exemplo) seja percebida.
        """
        com_copia()

        escrita = enviar().message()

        assert escrita["Bcc"] is None
        assert COPIA not in escrita.as_string()

    def test_o_destinatario_so_ve_a_si_mesmo(self, pela_reserva):
        com_copia()

        escrita = enviar().message()

        assert escrita["To"] == DESTINO
        assert escrita["Cc"] is None


# ===========================================================================
# 4. A regra é do site, não de um fluxo
# ===========================================================================


class TestTodosOsFluxos:
    def test_a_confirmacao_de_e_mail_leva_a_copia(self, pela_reserva, client, user):
        from apps.accounts import confirmacao

        com_copia()
        pedido = client.get(reverse("core:home")).wsgi_request

        confirmacao.enviar(pedido, user)

        assert django_mail.outbox[-1].to == [user.email]
        assert django_mail.outbox[-1].bcc == [COPIA]

    def test_a_recuperacao_de_senha_leva_a_copia(self, pela_reserva, client, user):
        com_copia()

        client.post(reverse("accounts:password_reset"), {"email": user.email})

        assert len(django_mail.outbox) == 1
        assert django_mail.outbox[0].to == [user.email]
        assert django_mail.outbox[0].bcc == [COPIA]

    def test_um_send_mail_qualquer_leva_a_copia(self, pela_reserva):
        """
        O e-mail que ainda não existe: quem o escrever amanhã não
        precisa saber que a cópia oculta existe.
        """
        com_copia()

        django_mail.send_mail("Novo", "Fluxo", REMETENTE, [DESTINO])

        assert django_mail.outbox[0].bcc == [COPIA]

    def test_o_teste_de_envio_do_backoffice_leva_a_copia(self, monkeypatch):
        """
        O único envio que NÃO passa pelo backend do projeto: ele abre a
        conexão na mão, para usar a configuração recém-salva mesmo
        desligada.
        """
        configuracao = com_copia()
        configuracao.host = SERVIDOR_FALSO
        configuracao.from_email = EMAIL_FALSO
        configuracao.save()
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        ok, motivo = mail.enviar_teste(configuracao, DESTINO)

        assert (ok, motivo) == (True, None)
        assert django_mail.outbox[0].to == [DESTINO]
        assert django_mail.outbox[0].bcc == [COPIA]


# ===========================================================================
# 5. Trocar e apagar valem na mensagem seguinte
# ===========================================================================


class TestMudarAConfiguracao:
    def test_trocar_o_endereco_vale_no_proximo_e_mail(self, pela_reserva):
        com_copia()
        enviar()

        com_copia(OUTRA_COPIA)
        enviar()

        assert [m.bcc for m in django_mail.outbox] == [[COPIA], [OUTRA_COPIA]]

    def test_apagar_o_endereco_interrompe_a_copia(self, pela_reserva):
        com_copia()
        enviar()

        com_copia("")
        enviar()

        assert [m.bcc for m in django_mail.outbox] == [[COPIA], []]


# ===========================================================================
# 6. A tela: quem altera, e o que ela aceita
# ===========================================================================


class TestTela:
    def test_o_campo_aparece_para_quem_pode_ver(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        assert "Enviar cópia oculta para" in corpo
        assert "bcc_email" in corpo

    def test_a_descricao_explica_o_que_acontece(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        assert "todos os e-mails enviados pelo site" in corpo
        assert "O destinatário original não verá este endereço." in corpo

    def test_salvar_grava_o_endereco(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "bcc_email": COPIA})

        assert resposta.status_code == 302
        assert mail.configuracao().bcc_email == COPIA

    def test_salvar_em_branco_apaga_o_endereco(self, cliente):
        com_copia()

        cliente.post(TELA, {**COMPLETO, "bcc_email": ""})

        assert mail.configuracao().bcc_email == ""

    def test_endereco_invalido_e_recusado(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "bcc_email": "nao-e-um-email"})

        assert resposta.status_code == 200
        assert "bcc_email" in resposta.context["form"].errors
        assert mail.configuracao().bcc_email == ""

    def test_o_campo_e_opcional(self, cliente):
        assert cliente.post(TELA, {**COMPLETO, "bcc_email": ""}).status_code == 302

    def test_quem_so_ve_nao_altera(self, client, leitor):
        client.force_login(leitor)

        resposta = client.post(TELA, {**COMPLETO, "bcc_email": COPIA})

        assert resposta.status_code == 403
        assert mail.configuracao().bcc_email == ""

    def test_usuario_comum_nao_ve_nem_altera(self, client, user):
        client.force_login(user)

        assert client.get(TELA).status_code == 403
        assert client.post(TELA, {**COMPLETO, "bcc_email": COPIA}).status_code == 403
        assert mail.configuracao().bcc_email == ""

    def test_anonimo_vai_para_o_login(self, client):
        com_copia()

        resposta = client.get(TELA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url


# ===========================================================================
# 7. O endereço não vaza para fora do Backoffice
# ===========================================================================


class TestNaoVaza:
    @pytest.mark.parametrize("rota", ["core:home", "core:dashboard", "accounts:profile"])
    def test_nao_aparece_em_pagina_do_site(self, auth_client, rota):
        com_copia()

        corpo = auth_client.get(reverse(rota)).content.decode()

        assert COPIA not in corpo

    def test_nao_aparece_para_quem_nao_administra_e_mail(self, client, staff_user):
        """
        Entrar no Backoffice não é poder ver a configuração de e-mail: o
        endereço da cópia mora atrás da mesma permissão do resto da
        tela.
        """
        com_copia()
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:system")).content.decode()

        assert COPIA not in corpo
        assert client.get(TELA).status_code == 403

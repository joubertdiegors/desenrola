"""
Configuração de envio de e-mail no Backoffice.

TODO DADO AQUI É DE MENTIRA
---------------------------
`mail@mail.com`, `smtp.exemplo.com`, `senha-de-mentira`. Nenhum
endereço, servidor ou senha de verdade entra em teste, código ou
migration -- a configuração real é cadastrada pela tela, em produção.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a senha guardada volte para alguma tela, log ou mensagem de
   erro -- é o motivo de metade dos testes daqui;
2. que a porta seja o botão escondido em vez da permissão no servidor;
3. que "ativo" fique ligado numa configuração incompleta, o que
   derrubaria a recuperação de senha de quem está trancado para fora;
4. que uma falha de SMTP vire um traceback na cara do administrador,
   com a resposta do servidor dentro.
"""

import smtplib
import ssl

import pytest
from django.contrib.auth.models import Permission
from django.core import mail as django_mail
from django.test import Client
from django.urls import reverse

from apps.core import crypto, mail
from apps.core.models import EmailSettings

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:email_settings")
TESTE = reverse("backoffice:email_settings_test")
SITUACAO = reverse("backoffice:email_settings_activation")

# Nada disto existe. É o ponto.
EMAIL_FALSO = "mail@mail.com"
SENHA_FALSA = "senha-de-mentira"
SERVIDOR_FALSO = "smtp.exemplo.com"

COMPLETO = {
    "host": SERVIDOR_FALSO,
    "port": 587,
    "security": EmailSettings.Security.TLS,
    "username": EMAIL_FALSO,
    "password": SENHA_FALSA,
    "from_email": EMAIL_FALSO,
    "from_name": "Desenrola",
}

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


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
    from django.contrib.auth import get_user_model

    User = get_user_model()
    usuario = User.objects.create_user(email=email, password="x", full_name=nome)
    usuario.user_permissions.add(*permissoes)
    return User.objects.get(pk=usuario.pk)


@pytest.fixture
def operador(permissao_backoffice, permissoes_de_email):
    """Quem pode ver E alterar."""
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
def so_backoffice(permissao_backoffice):
    """Entra no Backoffice e mais nada."""
    return _pessoa("so.backoffice@mail.com", "Elisa Prado", [permissao_backoffice])


@pytest.fixture
def cliente(operador):
    c = Client()
    c.force_login(operador)
    return c


def config():
    """
    A configuração recarregada do banco -- nunca um objeto de memória.

    Passa por `mail.configuracao()`, o mesmo acessor da aplicação: num
    teste que terminou em 403 a linha pode nem existir, e o que se quer
    afirmar ("nada foi gravado") é exatamente o registro em branco.
    """
    return mail.configuracao()


class ConexaoQueFalha:
    """Uma conexão SMTP que estoura ao abrir, como um servidor recusando."""

    def __init__(self, erro):
        self.erro = erro

    def __enter__(self):
        raise self.erro

    def __exit__(self, *args):
        return False


# ===========================================================================
# 1. A porta
# ===========================================================================


class TestAcesso:
    @pytest.mark.parametrize("url", [TELA, TESTE, SITUACAO])
    def test_anonimo_vai_para_o_login(self, client, url):
        resposta = client.get(url)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_sem_backoffice_leva_403(self, client, user):
        client.force_login(user)

        assert client.get(TELA).status_code == 403

    def test_backoffice_sozinho_nao_basta(self, client, so_backoffice):
        """
        Entrar na área administrativa é uma coisa; ver para onde o
        sistema manda e-mail é outra.
        """
        client.force_login(so_backoffice)

        assert client.get(TELA).status_code == 403

    def test_quem_pode_ver_entra(self, client, leitor):
        client.force_login(leitor)

        resposta = client.get(TELA)

        assert resposta.status_code == 200
        assert "Configuração de e-mail" in resposta.content.decode()

    def test_quem_so_ve_nao_salva(self, client, leitor):
        """A URL continua digitável -- a recusa é no servidor."""
        client.force_login(leitor)

        resposta = client.post(TELA, COMPLETO)

        assert resposta.status_code == 403
        assert config().host == ""

    def test_quem_so_ve_nao_dispara_teste(self, client, leitor):
        client.force_login(leitor)

        assert client.post(TESTE, {"destino": EMAIL_FALSO}).status_code == 403

    def test_quem_so_ve_nao_ativa(self, client, leitor):
        client.force_login(leitor)

        resposta = client.post(SITUACAO, {"ativo": "1"})

        assert resposta.status_code == 403
        assert config().is_active is False

    def test_o_menu_so_oferece_a_quem_pode_ver(self, client, leitor, so_backoffice):
        """Link que levaria a 403 é promessa quebrada -- não se oferece."""
        client.force_login(so_backoffice)
        sem = client.get(reverse("backoffice:overview")).content.decode()

        client.force_login(leitor)
        com = client.get(reverse("backoffice:overview")).content.decode()

        assert f'href="{TELA}"' not in sem
        assert f'href="{TELA}"' in com

    @pytest.mark.parametrize("url", [TESTE, SITUACAO])
    def test_get_nao_altera_nada(self, cliente, url):
        """As duas rotas de ação são POST: um GET não muda estado."""
        assert cliente.get(url).status_code == 405


# ===========================================================================
# 2. Criar e editar
# ===========================================================================


class TestCriacaoEEdicao:
    def test_a_primeira_visita_ja_cria_o_registro(self, cliente):
        assert EmailSettings.objects.count() == 0

        cliente.get(TELA)

        assert EmailSettings.objects.count() == 1

    def test_salvar_grava_os_campos(self, cliente):
        cliente.post(TELA, COMPLETO)

        salvo = config()
        assert salvo.host == SERVIDOR_FALSO
        assert salvo.port == 587
        assert salvo.security == EmailSettings.Security.TLS
        assert salvo.username == EMAIL_FALSO
        assert salvo.from_email == EMAIL_FALSO
        assert salvo.from_name == "Desenrola"

    def test_editar_nao_cria_um_segundo_registro(self, cliente):
        cliente.post(TELA, COMPLETO)
        cliente.post(TELA, {**COMPLETO, "host": "outro.exemplo.com", "password": ""})

        assert EmailSettings.objects.count() == 1
        assert config().host == "outro.exemplo.com"

    def test_registra_quem_alterou_e_quando(self, cliente, operador):
        cliente.post(TELA, COMPLETO)

        salvo = config()
        assert salvo.updated_by == operador
        assert salvo.updated_at is not None

    def test_a_tela_mostra_quem_alterou(self, cliente, operador):
        cliente.post(TELA, COMPLETO)

        corpo = cliente.get(TELA).content.decode()

        assert operador.full_name in corpo

    def test_salvar_nao_liga_o_envio(self, cliente):
        """
        Cadastrar e ativar são decisões diferentes: dá para configurar,
        testar e só então passar a valer.
        """
        cliente.post(TELA, COMPLETO)

        assert config().is_active is False

    def test_a_tela_mostra_o_que_esta_salvo(self, cliente):
        cliente.post(TELA, COMPLETO)

        corpo = cliente.get(TELA).content.decode()

        assert SERVIDOR_FALSO in corpo
        assert EMAIL_FALSO in corpo


# ===========================================================================
# 3. A senha -- o coração desta suíte
# ===========================================================================


class TestSenha:
    def test_nao_e_guardada_em_texto_puro(self, cliente):
        cliente.post(TELA, COMPLETO)

        guardado = config().password_encrypted

        assert guardado
        assert SENHA_FALSA not in guardado
        assert config().senha() == SENHA_FALSA

    def test_nao_aparece_na_pagina(self, cliente):
        cliente.post(TELA, COMPLETO)

        corpo = cliente.get(TELA).content.decode()

        assert SENHA_FALSA not in corpo
        assert config().password_encrypted not in corpo

    def test_o_campo_volta_sempre_vazio(self, cliente):
        cliente.post(TELA, COMPLETO)

        corpo = cliente.get(TELA).content.decode()

        assert 'name="password"' in corpo
        assert 'type="password"' in corpo
        # O widget não pode trazer `value` nenhum -- nem o cifrado.
        trecho = corpo[corpo.index('name="password"') - 200 : corpo.index('name="password"') + 200]
        assert "value=" not in trecho

    def test_a_tela_diz_apenas_se_existe(self, cliente):
        sem = cliente.get(TELA).content.decode()
        cliente.post(TELA, COMPLETO)
        com = cliente.get(TELA).content.decode()

        assert "Não cadastrada" in sem
        assert "Cadastrada" in com

    def test_em_branco_mantem_a_que_esta_guardada(self, cliente):
        cliente.post(TELA, COMPLETO)
        antes = config().password_encrypted

        cliente.post(TELA, {**COMPLETO, "password": "", "from_name": "Outro"})

        assert config().password_encrypted == antes
        assert config().senha() == SENHA_FALSA
        assert config().from_name == "Outro"

    def test_uma_nova_substitui_a_antiga(self, cliente):
        cliente.post(TELA, COMPLETO)

        cliente.post(TELA, {**COMPLETO, "password": "outra-de-mentira"})

        assert config().senha() == "outra-de-mentira"

    def test_a_caixa_de_apagar_apaga(self, cliente):
        cliente.post(TELA, COMPLETO)

        cliente.post(TELA, {**COMPLETO, "password": "", "username": "", "remover_senha": "on"})

        assert config().password_encrypted == ""
        assert config().tem_senha is False

    def test_apagar_e_cadastrar_ao_mesmo_tempo_e_recusado(self, cliente):
        cliente.post(TELA, COMPLETO)

        resposta = cliente.post(TELA, {**COMPLETO, "remover_senha": "on"})

        assert "Escolha uma coisa só" in resposta.content.decode()
        assert config().senha() == SENHA_FALSA

    def test_usuario_sem_senha_e_recusado(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "password": ""})

        assert resposta.status_code == 200
        assert "é preciso haver uma senha cadastrada" in resposta.content.decode()
        assert config().username == ""

    def test_formulario_invalido_nao_apaga_a_senha_da_tela(self, cliente):
        """
        Marcar "apagar" e errar outro campo não pode fazer a tela dizer
        que a senha sumiu -- ela continua no banco.
        """
        cliente.post(TELA, COMPLETO)

        resposta = cliente.post(
            TELA, {**COMPLETO, "password": "", "remover_senha": "on", "port": 0}
        )

        assert "Cadastrada" in resposta.content.decode()
        assert config().tem_senha is True

    def test_a_senha_nao_vaza_no_log_de_uma_falha(self, cliente, monkeypatch, caplog):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail,
            "conexao",
            lambda *a, **k: ConexaoQueFalha(smtplib.SMTPAuthenticationError(535, b"nope")),
        )

        with caplog.at_level("WARNING"):
            cliente.post(TESTE, {"destino": EMAIL_FALSO})

        assert caplog.text
        assert SENHA_FALSA not in caplog.text
        assert config().password_encrypted not in caplog.text


# ===========================================================================
# 4. Validação no servidor
# ===========================================================================


class TestValidacao:
    @pytest.mark.parametrize("porta", [0, 65536, -1])
    def test_porta_fora_da_faixa(self, cliente, porta):
        resposta = cliente.post(TELA, {**COMPLETO, "port": porta})

        assert resposta.status_code == 200
        assert config().host == ""

    def test_remetente_precisa_ser_um_endereco(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "from_email": "nao-e-email"})

        assert resposta.status_code == 200
        assert config().from_email == ""

    def test_seguranca_so_aceita_as_opcoes_conhecidas(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "security": "inventada"})

        assert resposta.status_code == 200
        assert config().host == ""

    def test_tls_e_ssl_nao_podem_coexistir(self):
        """
        Não por validação, e sim por CONSTRUÇÃO: é um campo de escolha,
        não duas caixas. O estado inválido não existe para ser rejeitado.
        """
        opcoes = {valor for valor, _rotulo in EmailSettings.Security.choices}

        assert opcoes == {"nenhuma", "tls", "ssl"}

    def test_o_erro_volta_na_propria_tela(self, cliente):
        resposta = cliente.post(TELA, {**COMPLETO, "from_email": "nao-e-email"})

        assert "backoffice/email_settings.html" in [t.name for t in resposta.templates]


# ===========================================================================
# 5. Ativar e desativar
# ===========================================================================


class TestAtivacao:
    def test_ativa(self, cliente):
        cliente.post(TELA, COMPLETO)

        cliente.post(SITUACAO, {"ativo": "1"})

        assert config().is_active is True

    def test_desativa(self, cliente):
        cliente.post(TELA, COMPLETO)
        cliente.post(SITUACAO, {"ativo": "1"})

        cliente.post(SITUACAO, {"ativo": "0"})

        assert config().is_active is False

    def test_nao_ativa_sem_servidor(self, cliente):
        """
        Uma configuração "ativa" e incompleta falharia em toda mensagem
        -- inclusive na recuperação de senha de quem não consegue entrar.
        """
        resposta = cliente.post(SITUACAO, {"ativo": "1"}, follow=True)

        assert config().is_active is False
        assert "antes de ativar" in resposta.content.decode()

    def test_nao_ativa_sem_remetente(self, cliente):
        cliente.post(TELA, {**COMPLETO, "from_email": "", "username": "", "password": ""})

        cliente.post(SITUACAO, {"ativo": "1"})

        assert config().is_active is False

    def test_registra_quem_ligou(self, cliente, operador):
        cliente.post(TELA, COMPLETO)

        cliente.post(SITUACAO, {"ativo": "1"})

        assert config().updated_by == operador

    def test_a_tela_mostra_a_situacao(self, cliente):
        cliente.post(TELA, COMPLETO)

        desligado = cliente.get(TELA).content.decode()
        cliente.post(SITUACAO, {"ativo": "1"})
        ligado = cliente.get(TELA).content.decode()

        assert "Desativado" in desligado
        assert "Ativar envio" in desligado
        assert "Ativo" in ligado
        assert "Desativar envio" in ligado


# ===========================================================================
# 6. O envio de teste
# ===========================================================================


class TestEnvioDeTeste:
    def test_manda_a_mensagem(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        resposta = cliente.post(TESTE, {"destino": EMAIL_FALSO}, follow=True)

        assert len(django_mail.outbox) == 1
        assert django_mail.outbox[0].to == [EMAIL_FALSO]
        assert "enviada" in resposta.content.decode()

    def test_usa_o_remetente_configurado(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        cliente.post(TESTE, {"destino": EMAIL_FALSO})

        assert django_mail.outbox[0].from_email == f"Desenrola <{EMAIL_FALSO}>"

    def test_funciona_com_o_envio_desativado(self, cliente, monkeypatch):
        """Testar ANTES de ligar é a ordem certa de fazer as coisas."""
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        cliente.post(TESTE, {"destino": EMAIL_FALSO})

        assert config().is_active is False
        assert len(django_mail.outbox) == 1

    def test_destino_invalido_nao_envia(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        resposta = cliente.post(TESTE, {"destino": "nao-e-email"}, follow=True)

        assert django_mail.outbox == []
        assert "endereço de e-mail válido" in resposta.content.decode()

    def test_sem_servidor_avisa_em_vez_de_tentar(self, cliente):
        resposta = cliente.post(TESTE, {"destino": EMAIL_FALSO}, follow=True)

        assert django_mail.outbox == []
        assert "Cadastre o servidor SMTP" in resposta.content.decode()

    def test_o_teste_nao_altera_a_configuracao(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        antes = config().updated_at
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        cliente.post(TESTE, {"destino": EMAIL_FALSO})

        assert config().updated_at == antes


# ===========================================================================
# 7. Quando o SMTP falha
# ===========================================================================


class TestFalhaDeSmtp:
    @pytest.mark.parametrize(
        "erro, esperado",
        [
            (smtplib.SMTPAuthenticationError(535, b"x"), "recusou o usuário ou a senha"),
            (smtplib.SMTPSenderRefused(550, b"x", "a@b.c"), "recusou o remetente"),
            (smtplib.SMTPRecipientsRefused({}), "recusou o endereço de destino"),
            (ssl.SSLError("x"), "Falha no TLS/SSL"),
            (TimeoutError(), "Não foi possível conectar"),
            (ConnectionRefusedError(), "Não foi possível conectar"),
            (smtplib.SMTPServerDisconnected(), "recusou a mensagem"),
            (RuntimeError("x"), "Falha inesperada"),
        ],
    )
    def test_cada_falha_vira_uma_frase(self, erro, esperado):
        assert esperado in str(mail._motivo(erro))

    def test_a_frase_chega_a_tela(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail,
            "conexao",
            lambda *a, **k: ConexaoQueFalha(smtplib.SMTPAuthenticationError(535, b"x")),
        )

        resposta = cliente.post(TESTE, {"destino": EMAIL_FALSO}, follow=True)

        assert "recusou o usuário ou a senha" in resposta.content.decode()

    def test_a_resposta_crua_do_servidor_nao_chega_a_tela(self, cliente, monkeypatch):
        """
        `str()` de um erro de `smtplib` traz a resposta do servidor, que
        costuma repetir o usuário. O que vai para a tela é a frase, não
        a exceção.
        """
        segredo = "535 5.7.8 Username and Password not accepted for mail@mail.com"
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail,
            "conexao",
            lambda *a, **k: ConexaoQueFalha(
                smtplib.SMTPAuthenticationError(535, segredo.encode())
            ),
        )

        resposta = cliente.post(TESTE, {"destino": EMAIL_FALSO}, follow=True)

        assert "Username and Password not accepted" not in resposta.content.decode()

    def test_a_falha_nao_derruba_a_pagina(self, cliente, monkeypatch):
        cliente.post(TELA, COMPLETO)
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: ConexaoQueFalha(TimeoutError())
        )

        resposta = cliente.post(TESTE, {"destino": EMAIL_FALSO}, follow=True)

        assert resposta.status_code == 200


# ===========================================================================
# 8. CSRF
# ===========================================================================


class TestCsrf:
    @pytest.fixture
    def sem_token(self, operador):
        c = Client(enforce_csrf_checks=True)
        c.force_login(operador)
        return c

    def test_salvar_sem_token_e_recusado(self, sem_token):
        resposta = sem_token.post(TELA, COMPLETO)

        assert resposta.status_code == 403
        assert config().host == ""

    def test_ativar_sem_token_e_recusado(self, sem_token, cliente):
        cliente.post(TELA, COMPLETO)

        resposta = sem_token.post(SITUACAO, {"ativo": "1"})

        assert resposta.status_code == 403
        assert config().is_active is False

    def test_testar_sem_token_e_recusado(self, sem_token, cliente):
        cliente.post(TELA, COMPLETO)

        resposta = sem_token.post(TESTE, {"destino": EMAIL_FALSO})

        assert resposta.status_code == 403
        assert django_mail.outbox == []


# ===========================================================================
# 9. A cifra
# ===========================================================================


class TestCrypto:
    def test_ida_e_volta(self):
        assert crypto.decifrar(crypto.cifrar(SENHA_FALSA)) == SENHA_FALSA

    def test_o_cifrado_nao_contem_o_texto(self):
        assert SENHA_FALSA not in crypto.cifrar(SENHA_FALSA)

    def test_cada_cifragem_e_diferente(self):
        """Fernet leva um nonce: dois cifrados da mesma senha não batem --
        e é o que impede deduzir que duas contas usam a mesma senha."""
        assert crypto.cifrar(SENHA_FALSA) != crypto.cifrar(SENHA_FALSA)

    def test_vazio_continua_vazio(self):
        assert crypto.cifrar("") == ""
        assert crypto.decifrar("") is None

    def test_chave_trocada_devolve_none_em_vez_de_estourar(self, settings):
        guardado = crypto.cifrar(SENHA_FALSA)

        settings.EMAIL_SECRET_KEY = "outra-chave-de-mentira"

        assert crypto.decifrar(guardado) is None

    def test_lixo_devolve_none(self):
        assert crypto.decifrar("isto-nao-e-um-token") is None

    def test_a_chave_propria_tem_precedencia_sobre_a_secret_key(self, settings):
        settings.EMAIL_SECRET_KEY = "chave-de-mentira-a"
        com_a = crypto.cifrar(SENHA_FALSA)

        settings.EMAIL_SECRET_KEY = "chave-de-mentira-b"

        assert crypto.decifrar(com_a) is None
        assert crypto.decifrar(crypto.cifrar(SENHA_FALSA)) == SENHA_FALSA


class TestSenhaIlegivel:
    def test_a_tela_pede_para_cadastrar_de_novo(self, cliente, settings):
        cliente.post(TELA, COMPLETO)

        settings.EMAIL_SECRET_KEY = "chave-trocada-de-mentira"

        corpo = cliente.get(TELA).content.decode()
        assert "não pode mais ser lida" in corpo

    def test_o_modelo_sabe_dizer(self, settings):
        configuracao = mail.configuracao()
        configuracao.definir_senha(SENHA_FALSA)
        configuracao.save()
        assert configuracao.senha_ilegivel is False

        settings.EMAIL_SECRET_KEY = "chave-trocada-de-mentira"

        assert config().senha_ilegivel is True


# ===========================================================================
# 10. O backend: o interruptor tem de significar alguma coisa
# ===========================================================================


class TestBackend:
    def _backend(self):
        return django_mail.get_connection("apps.core.mail.ConfiguredEmailBackend")

    def test_sem_configuracao_ativa_vai_para_a_reserva(self, settings):
        settings.EMAIL_FALLBACK_BACKEND = LOCMEM

        self._backend().send_messages(
            [django_mail.EmailMessage("a", "b", "de@mail.com", ["para@mail.com"])]
        )

        assert len(django_mail.outbox) == 1

    def test_com_configuracao_ativa_vai_para_o_smtp(self, settings, monkeypatch):
        settings.EMAIL_FALLBACK_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
        configuracao = mail.configuracao()
        configuracao.host = SERVIDOR_FALSO
        configuracao.from_email = EMAIL_FALSO
        configuracao.is_active = True
        configuracao.save()
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        self._backend().send_messages(
            [django_mail.EmailMessage("a", "b", "de@mail.com", ["para@mail.com"])]
        )

        # A reserva é a `dummy`, que engole tudo: se a mensagem está na
        # caixa, ela passou pelo caminho do SMTP.
        assert len(django_mail.outbox) == 1

    def test_o_remetente_padrao_e_trocado_pelo_configurado(self, settings, monkeypatch):
        settings.DEFAULT_FROM_EMAIL = "padrao@mail.com"
        configuracao = mail.configuracao()
        configuracao.host = SERVIDOR_FALSO
        configuracao.from_email = EMAIL_FALSO
        configuracao.from_name = "Desenrola"
        configuracao.is_active = True
        configuracao.save()
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        self._backend().send_messages(
            [django_mail.EmailMessage("a", "b", "padrao@mail.com", ["para@mail.com"])]
        )

        assert django_mail.outbox[0].from_email == f"Desenrola <{EMAIL_FALSO}>"

    def test_quem_escolheu_o_remetente_fica_com_o_dele(self, settings, monkeypatch):
        settings.DEFAULT_FROM_EMAIL = "padrao@mail.com"
        configuracao = mail.configuracao()
        configuracao.host = SERVIDOR_FALSO
        configuracao.from_email = EMAIL_FALSO
        configuracao.is_active = True
        configuracao.save()
        monkeypatch.setattr(
            mail, "conexao", lambda *a, **k: django_mail.get_connection(LOCMEM)
        )

        self._backend().send_messages(
            [django_mail.EmailMessage("a", "b", "escolhido@mail.com", ["para@mail.com"])]
        )

        assert django_mail.outbox[0].from_email == "escolhido@mail.com"

    def test_a_reserva_nao_pode_ser_ele_mesmo(self, settings):
        """Aponte a reserva para o próprio backend e ele se chamaria até
        estourar a pilha -- em produção, no meio de um envio."""
        settings.EMAIL_FALLBACK_BACKEND = "apps.core.mail.ConfiguredEmailBackend"

        with pytest.raises(ValueError):
            self._backend().send_messages(
                [django_mail.EmailMessage("a", "b", "de@mail.com", ["para@mail.com"])]
            )


class TestConexao:
    """O que `conexao()` monta a partir da configuração."""

    def _config(self, **campos):
        configuracao = mail.configuracao()
        for chave, valor in {"host": SERVIDOR_FALSO, "port": 587, **campos}.items():
            setattr(configuracao, chave, valor)
        return configuracao

    def test_tls(self):
        ligacao = mail.conexao(self._config(security=EmailSettings.Security.TLS))

        assert ligacao.use_tls is True
        assert ligacao.use_ssl is False

    def test_ssl(self):
        ligacao = mail.conexao(self._config(security=EmailSettings.Security.SSL, port=465))

        assert ligacao.use_ssl is True
        assert ligacao.use_tls is False

    def test_sem_criptografia(self):
        ligacao = mail.conexao(self._config(security=EmailSettings.Security.NENHUMA))

        assert ligacao.use_tls is False
        assert ligacao.use_ssl is False

    def test_sem_usuario_nao_autentica(self):
        """
        Vazio, e não `None`: no backend do Django `None` quer dizer
        "use `settings.EMAIL_HOST_USER`" -- em produção, a credencial
        da `EMAIL_URL` de reserva entraria aqui sem ninguém pedir.
        """
        ligacao = mail.conexao(self._config(username=""))

        assert ligacao.username == ""
        assert ligacao.password == ""

    def test_nao_herda_a_credencial_do_ambiente(self, settings):
        settings.EMAIL_HOST_USER = "do-ambiente@mail.com"
        settings.EMAIL_HOST_PASSWORD = "senha-do-ambiente-de-mentira"

        ligacao = mail.conexao(self._config(username=""))

        assert ligacao.username == ""
        assert ligacao.password == ""

    def test_leva_a_senha_decifrada(self):
        configuracao = self._config(username=EMAIL_FALSO)
        configuracao.definir_senha(SENHA_FALSA)

        ligacao = mail.conexao(configuracao)

        assert ligacao.password == SENHA_FALSA

    def test_tem_tempo_limite(self):
        """Sem isto, um host errado prende a requisição até o navegador
        desistir -- e o teste de envio roda dentro de uma requisição."""
        assert mail.conexao(self._config()).timeout == EmailSettings.TEMPO_LIMITE


# ===========================================================================
# 11. O modelo
# ===========================================================================


class TestModelo:
    def test_e_um_registro_so(self):
        """
        Construir um SEGUNDO objeto e salvá-lo não cria linha nova nem
        sobrescreve em silêncio: falha alto, como em `LetterPolicy`. O
        caminho certo é `mail.configuracao()` -- carregar, alterar,
        salvar.
        """
        from django.db import IntegrityError, transaction

        mail.configuracao()

        with pytest.raises(IntegrityError), transaction.atomic():
            EmailSettings(host="outro.exemplo.com").save()

        assert EmailSettings.objects.count() == 1
        assert config().host == ""

    def test_o_texto_do_objeto_nao_revela_nada(self):
        configuracao = mail.configuracao()
        configuracao.host = SERVIDOR_FALSO
        configuracao.username = EMAIL_FALSO
        configuracao.definir_senha(SENHA_FALSA)

        texto = f"{configuracao}{configuracao!r}"

        assert SENHA_FALSA not in texto
        assert EMAIL_FALSO not in texto
        assert SERVIDOR_FALSO not in texto

    def test_remetente_com_e_sem_nome(self):
        configuracao = EmailSettings(from_email=EMAIL_FALSO)
        assert configuracao.remetente() == EMAIL_FALSO

        configuracao.from_name = "Desenrola"
        assert configuracao.remetente() == f"Desenrola <{EMAIL_FALSO}>"

        configuracao.from_email = ""
        assert configuracao.remetente() == ""

    def test_pronta_para_enviar(self):
        configuracao = EmailSettings(host=SERVIDOR_FALSO, from_email=EMAIL_FALSO)
        assert configuracao.pronta_para_enviar() is False

        configuracao.is_active = True
        assert configuracao.pronta_para_enviar() is True

        configuracao.host = ""
        assert configuracao.pronta_para_enviar() is False

    def test_senha_nao_entra_na_conta_de_estar_pronta(self):
        """Há relays internos que não pedem autenticação; exigir senha
        impediria uma configuração legítima."""
        configuracao = EmailSettings(
            host=SERVIDOR_FALSO, from_email=EMAIL_FALSO, is_active=True
        )

        assert configuracao.tem_senha is False
        assert configuracao.pronta_para_enviar() is True

    def test_a_senha_nao_e_um_campo_de_formulario(self):
        """
        `editable=False`: não existe ModelForm que a exiba, porque não
        existe campo para exibir.
        """
        campo = EmailSettings._meta.get_field("password_encrypted")

        assert campo.editable is False

    def test_nao_ha_permissao_de_adicionar_nem_de_apagar(self):
        """É um registro só, que sempre existe."""
        codenames = {
            p.codename
            for p in Permission.objects.filter(content_type__app_label="core")
            if "emailsettings" in p.codename
        }

        assert codenames == {"view_emailsettings", "change_emailsettings"}


# ===========================================================================
# 12. O catálogo de permissões
# ===========================================================================


class TestCatalogo:
    def test_as_duas_permissoes_estao_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {p.chave for p in admin_permissions.todas()}

        assert "core.view_emailsettings" in chaves
        assert "core.change_emailsettings" in chaves

    def test_a_tela_de_usuarios_as_oferece(self, client, operador, permissao_backoffice):
        from django.contrib.auth import get_user_model

        gerencia = Permission.objects.get(
            content_type__app_label="accounts", codename="manage_users"
        )
        operador.user_permissions.add(gerencia)
        operador = get_user_model().objects.get(pk=operador.pk)
        client.force_login(operador)

        corpo = client.get(
            reverse("backoffice:user_detail", args=[operador.pk])
        ).content.decode()

        assert "Configurar o envio de e-mail" in corpo

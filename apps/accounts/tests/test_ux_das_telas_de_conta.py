"""
Criar conta e Perfil, depois da revisão final de UX.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que um campo volte a nascer sem exemplo.** Quem preenche precisa
   ver o FORMATO esperado, não adivinhá-lo;
2. **Que a senha volte a ser digitada às cegas.** As duas telas têm o
   botão do olho -- o mesmo do login, não uma segunda invenção;
3. **Que ler os Termos custe o formulário preenchido.** Eles abrem em
   outra aba, com `rel="noopener"`;
4. **Que um documento vire número.** Código postal, documento e
   passaporte podem ter zero à esquerda, letra ou formatação, e
   `type="number"` come tudo isso;
5. **Que a mensagem de senha parecida volte a sair sem artigo.** "A
   senha é muito parecida com e-mail" não é português;
6. **Que a barra lateral do Perfil volte.** Ela duplicava navegação: as
   três seções já aparecem todas na mesma página.
"""

import pathlib

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.accounts.forms import EXEMPLO_DE_EMAIL

pytestmark = pytest.mark.django_db

CADASTRO = reverse("accounts:signup")
PERFIL = reverse("accounts:profile")

RAIZ = pathlib.Path(__file__).resolve().parents[3]


def publico():
    """
    Um cliente NÃO autenticado.

    `auth_client` e `client` são o mesmo objeto no `conftest`: pedir os
    dois numa função autentica o cliente, e o cadastro passa a
    redirecionar -- a página vem vazia e o teste não mede nada.
    """
    return Client()


# ===========================================================================
# 1. Exemplos nos campos
# ===========================================================================


class TestExemplos:
    def test_o_email_do_cadastro_tem_exemplo(self):
        html = publico().get(CADASTRO).content.decode()

        assert f'placeholder="{EXEMPLO_DE_EMAIL}"' in html

    def test_o_email_do_perfil_tem_o_MESMO_exemplo(self, auth_client):
        """Duas telas sugerindo formatos diferentes seria pior do que nenhuma."""
        html = auth_client.get(PERFIL).content.decode()

        assert f'placeholder="{EXEMPLO_DE_EMAIL}"' in html

    def test_o_exemplo_e_um_endereco_que_nao_existe(self):
        """
        Nada de e-mail real em código versionado -- nem como exemplo.
        """
        assert EXEMPLO_DE_EMAIL == "seuemail@email.com"

    @pytest.mark.parametrize(
        "campo", ["id_full_name", "id_postal_code", "id_city", "id_address_line1"]
    )
    def test_os_campos_do_cadastro_tem_exemplo(self, campo):
        html = publico().get(CADASTRO).content.decode()
        onde = html.index(f'id="{campo}"')

        assert "placeholder=" in html[onde : onde + 400]

    @pytest.mark.parametrize(
        "campo", ["p_name", "p_document", "p_address", "p_postal_code", "p_city"]
    )
    def test_os_campos_do_perfil_tem_exemplo(self, auth_client, campo):
        html = auth_client.get(PERFIL).content.decode()
        onde = html.index(f'id="{campo}"')

        assert "placeholder=" in html[onde : onde + 400]


# ===========================================================================
# 2. O olho da senha
# ===========================================================================


class TestOlhoDaSenha:
    def test_as_duas_senhas_do_cadastro_tem_o_olho(self):
        html = publico().get(CADASTRO).content.decode()

        assert html.count("data-pw-toggle") == 2

    def test_as_tres_senhas_do_perfil_tem_o_olho(self, auth_client):
        html = auth_client.get(PERFIL).content.decode()

        assert html.count("data-pw-toggle") == 3

    def test_e_o_MESMO_componente_do_login(self):
        """`pw-wrap` + `pw-toggle` -- não uma segunda maneira de mostrar senha."""
        cadastro = publico().get(CADASTRO).content.decode()
        login = publico().get(reverse("accounts:login")).content.decode()

        for marca in ("pw-wrap", "pw-toggle", "data-pw-toggle"):
            assert marca in cadastro
            assert marca in login

    def test_o_botao_diz_o_seu_estado(self):
        """Quem lê a tela precisa saber se a senha está visível."""
        html = publico().get(CADASTRO).content.decode()

        assert 'aria-pressed="false"' in html

    def test_o_botao_tem_nome(self):
        html = publico().get(CADASTRO).content.decode()

        assert "aria-label" in html[html.index("data-pw-toggle") - 200 :]

    def test_o_botao_nao_envia_o_formulario(self):
        """Um `<button>` sem `type` dentro de um `<form>` envia."""
        html = publico().get(CADASTRO).content.decode()
        onde = html.index("data-pw-toggle")

        assert 'type="button"' in html[onde - 200 : onde]


# ===========================================================================
# 3. A confirmação de senha responde enquanto se digita
# ===========================================================================


class TestConfirmacaoViva:
    def test_o_cadastro_liga_a_confirmacao_a_senha(self):
        html = publico().get(CADASTRO).content.decode()

        assert 'data-pw-confirm="id_password1"' in html
        assert 'data-pw-confirm-aviso="id_password1"' in html

    def test_o_perfil_liga_a_confirmacao_a_nova_senha(self, auth_client):
        html = auth_client.get(PERFIL).content.decode()

        assert 'data-pw-confirm="p_pw1"' in html
        assert 'data-pw-confirm-aviso="p_pw1"' in html

    def test_o_aviso_e_anunciado_por_leitor_de_tela(self):
        html = publico().get(CADASTRO).content.decode()
        onde = html.index("data-pw-confirm-aviso")

        assert 'aria-live="polite"' in html[onde : onde + 400]

    def test_os_dois_textos_do_aviso_vem_da_pagina(self):
        """
        Traduzíveis, e não escritos dentro do JavaScript -- que não
        passa pelo catálogo de tradução.
        """
        html = publico().get(CADASTRO).content.decode()

        assert "data-igual=" in html
        assert "data-diferente=" in html

    def test_o_servidor_continua_recusando_senhas_diferentes(self, client):
        """
        O aviso na tela é conveniência. Quem DECIDE é o servidor -- e
        continua decidindo com o JavaScript desligado.
        """
        client.post(
            CADASTRO,
            {
                "full_name": "Rui Santos",
                "email": "rui@exemplo.test",
                "password1": "Correto-Cavalo-Bateria-7",
                "password2": "Outra-Senha-Diferente-9",
                "phone_0": "+32",
                "phone_1": "",
                "terms": "on",
            },
        )

        from apps.accounts.models import User

        assert not User.objects.filter(email="rui@exemplo.test").exists()


# ===========================================================================
# 4. Os documentos legais abrem noutra aba
# ===========================================================================


class TestTermosEmOutraAba:
    @pytest.fixture
    def com_documentos(self, db):
        """
        Os dois documentos, com texto publicado.

        Os BLOCOS já nascem com o banco (migration `0007_paginas_legais`)
        -- o que falta numa instalação nova é o TEXTO, e é ele que faz o
        link existir.
        """
        from apps.content.models import ContentBlock, ContentTranslation

        for chave in ("legal.terms_of_use", "legal.privacy_policy"):
            bloco, _criado = ContentBlock.objects.get_or_create(
                key=chave, defaults={"kind": ContentBlock.Kind.RICH_TEXT}
            )
            ContentTranslation.objects.update_or_create(
                block=bloco, language="pt", defaults={"content": "<p>Texto.</p>"}
            )

    def test_abrem_em_outra_aba(self, com_documentos):
        html = publico().get(CADASTRO).content.decode()
        onde = html.index(reverse("core:legal_termos"))

        assert 'target="_blank"' in html[onde : onde + 120]

    def test_com_noopener(self, com_documentos):
        """Sem ele, a página aberta recebe `window.opener` e pode mexer nesta."""
        html = publico().get(CADASTRO).content.decode()
        onde = html.index(reverse("core:legal_termos"))

        assert 'rel="noopener"' in html[onde : onde + 120]

    def test_os_dois_documentos(self, com_documentos):
        html = publico().get(CADASTRO).content.decode()

        assert html.count('target="_blank" rel="noopener"') >= 2

    def test_sem_texto_publicado_nao_ha_link_nenhum(self):
        """Era a regra da Etapa G, e continua: nada de `#` que não abre nada."""
        html = publico().get(CADASTRO).content.decode()

        assert "Li e aceito" in html
        assert 'href="#"' not in html


# ===========================================================================
# 5. Documento não é número
# ===========================================================================


class TestNadaDeTypeNumber:
    CAMPOS_DO_CADASTRO = ("id_postal_code", "id_full_name", "id_address_line1", "id_city")
    CAMPOS_DO_PERFIL = ("p_postal_code", "p_document", "p_address", "p_city")

    @pytest.mark.parametrize("campo", CAMPOS_DO_CADASTRO)
    def test_nenhum_campo_do_cadastro_e_numerico(self, campo):
        html = publico().get(CADASTRO).content.decode()
        onde = html.index(f'id="{campo}"')

        assert 'type="number"' not in html[onde - 120 : onde + 400]

    @pytest.mark.parametrize("campo", CAMPOS_DO_PERFIL)
    def test_nenhum_campo_do_perfil_e_numerico(self, auth_client, campo):
        html = auth_client.get(PERFIL).content.decode()
        onde = html.index(f'id="{campo}"')

        assert 'type="number"' not in html[onde - 120 : onde + 400]

    def test_o_codigo_postal_abre_o_teclado_numerico_mesmo_assim(self):
        """
        `inputmode` dá o teclado de números no celular sem nenhum dos
        efeitos de `type="number"`: zero à esquerda sobrevive.
        """
        html = publico().get(CADASTRO).content.decode()
        onde = html.index('id="id_postal_code"')

        assert 'inputmode="numeric"' in html[onde - 120 : onde + 400]

    def test_o_codigo_postal_guarda_zero_a_esquerda(self, auth_client, user):
        auth_client.post(
            PERFIL,
            {
                "action": "dados",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+32",
                "phone_1": "",
                "postal_code": "0123",
            },
        )

        user.refresh_from_db()
        assert user.postal_code == "0123"

    def test_o_documento_guarda_letras(self, auth_client, user):
        auth_client.post(
            PERFIL,
            {
                "action": "dados",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+32",
                "phone_1": "",
                "document_number": "BE0123456X",
            },
        )

        user.refresh_from_db()
        assert user.document_number == "BE0123456X"


# ===========================================================================
# 6. A mensagem de senha parecida
# ===========================================================================


class TestMensagemDeSenhaParecida:
    def _mensagens(self, senha, email="maria.souza@exemplo.test"):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        from apps.accounts.models import User

        with translation.override("pt"):
            try:
                validate_password(senha, User(email=email, full_name="Maria Souza"))
            except ValidationError as erro:
                return list(erro.messages)
        return []

    def test_a_mensagem_tem_artigo_e_ponto_final(self):
        mensagens = self._mensagens("maria.souza@exemplo.test")
        parecida = [m for m in mensagens if "parecida" in m]

        assert parecida, mensagens
        assert parecida[0] == "A senha é muito parecida com o seu e-mail."

    def test_nao_sai_mais_sem_artigo(self):
        mensagens = self._mensagens("maria.souza@exemplo.test")

        assert "A senha é muito parecida com e-mail" not in mensagens

    def test_a_correcao_esta_no_catalogo_do_projeto(self):
        """
        E o `.mo` foi gerado: sem ele o catálogo em texto não chega a
        lugar nenhum.
        """
        po = (RAIZ / "locale/pt/LC_MESSAGES/django.po").read_text(encoding="utf-8")
        mo = RAIZ / "locale/pt/LC_MESSAGES/django.mo"

        assert 'msgstr "A senha é muito parecida com o seu %(verbose_name)s."' in po
        assert mo.exists()
        assert mo.stat().st_mtime >= (RAIZ / "locale/pt/LC_MESSAGES/django.po").stat().st_mtime - 5

    def test_as_outras_mensagens_de_senha_nao_mudaram(self):
        mensagens = self._mensagens("12345678")

        assert "Esta senha é muito comum." in mensagens
        assert "Esta senha é inteiramente numérica." in mensagens


# ===========================================================================
# 7. O Perfil sem barra lateral
# ===========================================================================


class TestPerfilSemLateral:
    def test_a_lateral_saiu(self, auth_client):
        html = auth_client.get(PERFIL).content.decode()

        assert "profile-side" not in html

    def test_as_secoes_continuam_na_pagina(self, auth_client):
        html = auth_client.get(PERFIL).content.decode()

        for secao in ("dados", "senha", "comunicacoes"):
            assert f'id="{secao}"' in html

    def test_no_celular_tambem_e_uma_pagina_so(self, auth_client):
        """
        O índice do celular SAIU.

        Ele levava a `?secao=dados`, `?secao=senha` e afins -- cada toque
        recarregava a página mostrando um pedaço. Agora o Perfil é uma
        página só em qualquer largura: tudo está ali, basta rolar.
        """
        html = auth_client.get(PERFIL).content.decode()

        assert "profile-home" not in html
        assert "?secao=" not in html

    def test_uma_pagina_so_traz_tudo_o_que_o_indice_levava(self, auth_client):
        """
        Uma página só é inútil se metade dela continuar escondida.

        A lista abaixo é a do índice que saiu: cada destino dele tem de
        estar nesta mesma resposta.
        """
        html = auth_client.get(PERFIL).content.decode()

        for ancora in ("dados", "endereco", "senha", "comunicacoes", "conta"):
            assert f'id="{ancora}"' in html

        for campo in ("full_name", "email", "phone", "birth_date", "nationality"):
            assert f'name="{campo}"' in html or f'_{campo}' in html

    def test_o_cabecalho_novo_traz_quem_e_a_pessoa(self, auth_client, user):
        html = auth_client.get(PERFIL).content.decode()

        assert "profile-topo" in html
        assert user.full_name in html
        assert user.email in html

    def test_o_sair_continua_ao_alcance_no_celular(self, auth_client):
        """
        No desktop o "Sair" mora no menu das iniciais, que é `d-only`.
        No celular esse menu não existe -- sem a seção "Conta" a pessoa
        ficaria sem porta de saída nesta tela.
        """
        html = auth_client.get(PERFIL).content.decode()
        conta = html[html.index('id="conta"') :]

        assert reverse("accounts:logout") in conta

    def test_nada_ficou_duplicado_ao_empilhar_as_secoes(self, auth_client):
        """
        O índice do celular repetia rótulos que as seções já traziam.
        Empilhar tudo sem tirar o índice teria deixado cada título duas
        vezes na mesma página.
        """
        html = auth_client.get(PERFIL).content.decode()

        for titulo in ("Dados pessoais", "Alterar senha", "Comunicações"):
            assert html.count(f"<h2>{titulo}</h2>") <= 1

    def test_salvar_devolve_a_pessoa_ao_ponto_onde_estava(self, auth_client, user):
        """
        `?secao=` deixou de esconder o resto da página, mas continua
        sendo a âncora de volta depois de salvar.
        """
        resposta = auth_client.post(
            PERFIL,
            {
                "action": "dados",
                "secao": "dados",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+32",
                "phone_1": "",
            },
        )

        assert resposta.status_code == 302
        assert resposta.url.endswith("?secao=dados#dados")

    def test_uma_secao_inventada_nao_vira_ancora(self, auth_client, user):
        """O valor chega por POST, e POST é coisa do cliente."""
        resposta = auth_client.post(
            PERFIL,
            {
                "action": "dados",
                "secao": "javascript:alert(1)",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+32",
                "phone_1": "",
            },
        )

        assert resposta.status_code == 302
        assert resposta.url == PERFIL

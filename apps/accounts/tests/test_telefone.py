"""
O campo de telefone -- um só, em toda tela que o pede.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o código do país volte a ser fixo em +32.** Era um `<span>`
   desenhado ao lado do campo: quem mora na Bélgica com celular
   português, brasileiro ou francês não conseguia gravar o próprio
   número;
2. **Que o telefone vire `type="number"`.** Ele tem espaços,
   parênteses, hífens e zeros à esquerda -- um campo numérico come
   tudo isso. Vale igual para código postal, documento e passaporte;
3. **Que o número gravado se perca ao reabrir a tela.** Gravar e
   reabrir tem de mostrar o mesmo país e o mesmo número -- inclusive
   para o que foi gravado ANTES deste campo existir;
4. **Que um código do país sozinho seja gravado como telefone.**
   `"+351"` sem número não é o telefone de ninguém;
5. **Que as duas telas divirjam.** Cadastro e Perfil usam a MESMA
   classe. Uma solução de telefone no projeto, não uma por tela.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts import telefone
from apps.accounts.forms import ProfileForm, SignupForm
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


# ===========================================================================
# 1. Desmontar e remontar o número
# ===========================================================================


class TestSepararEJuntar:
    @pytest.mark.parametrize(
        "numero,ddi,resto",
        [
            ("+32 470 00 00 00", "+32", "470 00 00 00"),
            ("+351 912 345 678", "+351", "912 345 678"),
            ("+55 11 91234-5678", "+55", "11 91234-5678"),
            ("+1 201 555 0123", "+1", "201 555 0123"),
            ("+244 923 123 456", "+244", "923 123 456"),
        ],
    )
    def test_separa_o_codigo_do_pais(self, numero, ddi, resto):
        assert telefone.separar(numero) == (ddi, resto)

    def test_o_codigo_mais_longo_e_tentado_primeiro(self):
        """
        A INVARIANTE TEM DUAS METADES, E ESTA É A PRIMEIRA.

        Se `+35` e `+351` estivessem os dois na lista, casar `+35` antes
        deixaria todo número português com um "1" colado no começo. Por
        isso a busca vai do código mais longo para o mais curto.

        Nenhum número de exemplo prova isto, e é por isso que o teste
        olha a ORDEM: hoje não há colisão de prefixo na lista (ver o
        teste seguinte), então trocar a ordenação não mudaria resposta
        nenhuma -- e a proteção some em silêncio no dia em que alguém
        acrescentar o país que colide.
        """
        tamanhos = [len(pais.ddi) for pais in telefone._POR_TAMANHO]

        assert tamanhos == sorted(tamanhos, reverse=True)

    def test_nenhum_codigo_e_prefixo_de_outro(self):
        """
        A SEGUNDA METADE: a lista de hoje não tem colisão.

        Enquanto isto valer, a ordenação acima é cinto de segurança. No
        dia em que alguém acrescentar, digamos, `+1` e `+1242`, é ela
        que faz o número certo continuar saindo -- e este teste passa a
        falhar se a lista ganhar a colisão SEM a ordenação.
        """
        codigos = [pais.ddi for pais in telefone.PAISES]
        colisoes = [
            (curto, longo)
            for curto in codigos
            for longo in codigos
            if curto != longo and longo.startswith(curto)
        ]

        assert not colisoes, colisoes

    def test_um_codigo_longo_nao_e_confundido_com_um_curto(self):
        assert telefone.separar("+351 912 345 678")[0] == "+351"

    def test_numero_sem_mais_e_tratado_como_belga(self):
        """
        É o que está gravado de antes: quando o `+32` era desenho, só o
        resto ia para o banco.
        """
        assert telefone.separar("470 00 00 00") == ("+32", "470 00 00 00")

    def test_vazio_volta_no_padrao_sem_numero(self):
        assert telefone.separar("") == (telefone.DDI_PADRAO, "")
        assert telefone.separar(None) == (telefone.DDI_PADRAO, "")

    def test_codigo_desconhecido_nao_apaga_o_que_a_pessoa_digitou(self):
        _ddi, resto = telefone.separar("+999 12345678")

        assert "12345678" in resto

    def test_juntar_remonta(self):
        assert telefone.juntar("+351", "912 345 678") == "+351 912 345 678"

    def test_codigo_sozinho_nao_e_telefone(self):
        assert telefone.juntar("+351", "") == ""
        assert telefone.juntar("+32", "   ") == ""

    @pytest.mark.parametrize(
        "numero",
        ["+32 470 00 00 00", "+351 912 345 678", "+55 11 91234-5678", "+1 201 555 0123"],
    )
    def test_ida_e_volta_nao_muda_o_numero(self, numero):
        assert telefone.juntar(*telefone.separar(numero)) == numero


# ===========================================================================
# 2. A lista de países
# ===========================================================================


class TestPaises:
    def test_a_belgica_vem_primeiro(self):
        """É onde o serviço acontece -- e continua trocável, que é o ponto."""
        assert telefone.PAISES[0].ddi == "+32"
        assert telefone.DDI_PADRAO == "+32"

    def test_nao_ha_codigo_repetido(self):
        codigos = [pais.ddi for pais in telefone.PAISES]

        assert len(set(codigos)) == len(codigos)

    def test_todo_codigo_comeca_com_mais(self):
        for pais in telefone.PAISES:
            assert pais.ddi.startswith("+")

    def test_toda_mascara_declarada_cabe_no_exemplo(self):
        """
        Máscara com mais dígitos do que o exemplo significa que uma das
        duas está errada -- e a tela mostraria as duas.
        """
        for pais in telefone.PAISES:
            if not pais.mascara:
                continue
            assert pais.mascara.count("#") == sum(c.isdigit() for c in pais.exemplo), pais.ddi

    def test_ha_os_paises_de_lingua_portuguesa(self):
        """São de onde vem boa parte de quem usa o produto."""
        codigos = {pais.ddi for pais in telefone.PAISES}

        assert {"+351", "+55", "+244", "+258", "+238"} <= codigos


# ===========================================================================
# 3. O campo, no formulário
# ===========================================================================


class TestCampo:
    def test_o_cadastro_e_o_perfil_usam_a_mesma_classe(self):
        do_cadastro = type(SignupForm().fields["phone"])
        do_perfil = type(ProfileForm().fields["phone"])

        assert do_cadastro is telefone.CampoDeTelefone
        assert do_perfil is do_cadastro

    def test_grava_o_numero_internacional_inteiro(self):
        form = ProfileForm(
            {
                "full_name": "Ana Lima",
                "email": "ana@exemplo.test",
                "phone_0": "+351",
                "phone_1": "912 345 678",
            },
            instance=User(),
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone"] == "+351 912 345 678"

    def test_sem_numero_grava_vazio(self):
        form = ProfileForm(
            {
                "full_name": "Ana Lima",
                "email": "ana@exemplo.test",
                "phone_0": "+351",
                "phone_1": "",
            },
            instance=User(),
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone"] == ""

    def test_a_tela_reabre_com_o_pais_certo(self, user):
        user.phone = "+55 11 91234-5678"
        user.save(update_fields=["phone"])

        form = ProfileForm(instance=user)

        assert form["phone"].value() == "+55 11 91234-5678"
        assert 'value="+55" selected' in str(form["phone"])

    @pytest.mark.parametrize(
        "digitado",
        [
            # Dígitos suficientes E letras: só a regra dos caracteres o
            # recusa. Com "chame no zap" -- zero dígitos -- quem recusava
            # era a regra do comprimento, e a das letras não era medida.
            "470 00 00 00 ramal 9",
            "470 00 00 00 (celular)",
            "chame no zap",
        ],
    )
    def test_letras_sao_recusadas(self, digitado):
        form = ProfileForm(
            {
                "full_name": "Ana Lima",
                "email": "ana@exemplo.test",
                "phone_0": "+32",
                "phone_1": digitado,
            },
            instance=User(),
        )

        assert not form.is_valid()
        assert "phone" in form.errors

    def test_numero_curto_demais_e_recusado(self):
        form = ProfileForm(
            {
                "full_name": "Ana Lima",
                "email": "ana@exemplo.test",
                "phone_0": "+32",
                "phone_1": "470",
            },
            instance=User(),
        )

        assert not form.is_valid()

    @pytest.mark.parametrize(
        "digitado", ["470 00 00 00", "470.12.34.56", "(470) 12-34-56", "470123456"]
    )
    def test_aceita_a_formatacao_que_as_pessoas_usam(self, digitado):
        form = ProfileForm(
            {
                "full_name": "Ana Lima",
                "email": "ana@exemplo.test",
                "phone_0": "+32",
                "phone_1": digitado,
            },
            instance=User(),
        )

        assert form.is_valid(), form.errors


# ===========================================================================
# 4. Na tela
# ===========================================================================


class TestNaTela:
    """
    CUIDADO COM `auth_client` E `client` JUNTOS
    -------------------------------------------
    No `conftest` deste projeto `auth_client` É o mesmo objeto que
    `client` -- ele apenas faz `force_login`. Pedir os dois na mesma
    função autentica o cliente, e o cadastro passa a redirecionar para
    o painel: a página vem VAZIA, e um teste sobre marcação passaria a
    não medir nada. Por isso a tela pública usa um `Client()` novo.
    """

    def _html(self, client, url):
        return client.get(url).content.decode()

    def _do_cadastro(self):
        return Client().get(reverse("accounts:signup")).content.decode()

    def test_o_codigo_do_pais_e_um_seletor_de_verdade_no_cadastro(self):
        html = self._do_cadastro()

        assert 'name="phone_0"' in html
        assert 'name="phone_1"' in html
        assert "<select" in html

    def test_o_codigo_do_pais_e_um_seletor_de_verdade_no_perfil(self, auth_client):
        html = self._html(auth_client, reverse("accounts:profile"))

        assert 'name="phone_0"' in html
        assert 'name="phone_1"' in html
        assert "<select" in html

    def test_o_mais_32_nao_e_mais_texto_desenhado_no_cadastro(self):
        assert '<span class="input dial-code"' not in self._do_cadastro()

    def test_o_mais_32_nao_e_mais_texto_desenhado_no_perfil(self, auth_client):
        html = self._html(auth_client, reverse("accounts:profile"))

        assert '<span class="input dial-code"' not in html

    def test_o_seletor_oferece_varios_paises(self):
        html = self._do_cadastro()

        for ddi in ("+32", "+351", "+55", "+33"):
            assert f'value="{ddi}"' in html

    def test_a_mascara_de_cada_pais_viaja_no_proprio_option(self):
        """
        A lista de países fica em UM lugar (Python). O JavaScript a lê
        daqui -- não guarda uma cópia que envelheceria sozinha.
        """
        html = self._do_cadastro()

        assert 'data-mascara="### ## ## ##"' in html
        assert 'data-exemplo="470 00 00 00"' in html

    def _bloco_do_numero(self, html):
        onde = html.index('name="phone_1"')
        return html[onde - 200 : onde + 200]

    def test_o_campo_do_numero_nunca_e_type_number_no_cadastro(self):
        """Zeros à esquerda, espaços e parênteses não sobrevivem a `number`."""
        bloco = self._bloco_do_numero(self._do_cadastro())

        assert 'type="tel"' in bloco
        assert 'type="number"' not in bloco

    def test_o_campo_do_numero_nunca_e_type_number_no_perfil(self, auth_client):
        bloco = self._bloco_do_numero(
            self._html(auth_client, reverse("accounts:profile"))
        )

        assert 'type="tel"' in bloco
        assert 'type="number"' not in bloco

    def test_o_rotulo_aponta_para_o_campo_do_numero(self):
        """
        Clicar em "Telefone" leva ao NÚMERO, não ao seletor de país: é
        onde se digita.
        """
        html = self._do_cadastro()

        assert 'for="id_phone_1"' in html

    def test_o_seletor_tem_nome_para_quem_le_a_tela(self):
        html = self._do_cadastro()

        onde = html.index('name="phone_0"')

        assert "aria-label" in html[onde - 120 : onde + 120]


# ===========================================================================
# 5. Fim a fim
# ===========================================================================


class TestFimAFim:
    def test_cadastro_com_telefone_de_outro_pais(self, client):
        client.post(
            reverse("accounts:signup"),
            {
                "full_name": "Rui Santos",
                "email": "rui@exemplo.test",
                "password1": "Correto-Cavalo-Bateria-7",
                "password2": "Correto-Cavalo-Bateria-7",
                "phone_0": "+351",
                "phone_1": "912 345 678",
                "terms": "on",
            },
        )

        assert User.objects.get(email="rui@exemplo.test").phone == "+351 912 345 678"

    def test_o_perfil_troca_o_pais_do_telefone(self, auth_client, user):
        user.phone = "+32 470 00 00 00"
        user.save(update_fields=["phone"])

        auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+55",
                "phone_1": "11 91234-5678",
            },
        )

        user.refresh_from_db()
        assert user.phone == "+55 11 91234-5678"

    def test_apagar_o_telefone_funciona(self, auth_client, user):
        user.phone = "+32 470 00 00 00"
        user.save(update_fields=["phone"])

        auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "full_name": user.full_name,
                "email": user.email,
                "phone_0": "+32",
                "phone_1": "",
            },
        )

        user.refresh_from_db()
        assert user.phone == ""

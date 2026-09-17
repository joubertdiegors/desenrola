"""
O comando que monta uma demonstração do produto.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o comando apague trabalho de alguém.** Ele é opt-in e roda mais
   de uma vez; o que já tem conteúdo não pode ser sobrescrito sem
   `--forcar`;
2. **Que entre dado real.** Nenhum e-mail, telefone, endereço, empresa
   ou perfil de verdade -- o conteúdo existe para ser apagado pelo
   cliente;
3. **Que o contador vire número inventado.** Ele conta cartas
   finalizadas de verdade, e num banco de demonstração fica em zero;
4. **Que apareça texto jurídico com cara de definitivo.** As duas
   páginas legais recebem um aviso em letras maiúsculas, e nada mais.
"""

import re

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.content.models import ContentBlock, ContentTranslation, Partner, SiteSettings

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
TERMOS = reverse("core:legal_termos")


def rodar(*args):
    call_command("conteudo_demonstrativo", *args, verbosity=0)


class TestPreenche:
    def test_o_contato_e_as_redes(self):
        rodar()

        config = SiteSettings.load()
        assert config.contact_email
        assert config.contact_phone
        assert config.contact_address
        assert set(config.social_links) == {"facebook", "instagram"}

    def test_os_quatro_parceiros(self):
        rodar()

        nomes = set(Partner.objects.values_list("name", flat=True))
        assert nomes == {
            "Global Travel Services",
            "European Welcome",
            "Travel Support",
            "Visa Assistance",
        }

    def test_as_duas_paginas_legais(self):
        rodar()

        for chave in ("legal.terms_of_use", "legal.privacy_policy"):
            texto = ContentTranslation.objects.get(block__key=chave, language="pt").content
            assert "SUBSTITUIR PELO TEXTO JURÍDICO DEFINITIVO" in texto

    def test_o_conteudo_chega_ao_site(self, client):
        rodar()

        corpo = client.get(HOME).content.decode()

        assert "Global Travel Services" in corpo
        assert SiteSettings.load().contact_email in corpo
        assert reverse("core:legal_privacidade") in corpo

    def test_a_pagina_legal_abre_com_o_aviso(self, client):
        rodar()

        resposta = client.get(TERMOS)

        assert resposta.status_code == 200
        assert "SUBSTITUIR PELO TEXTO JURÍDICO DEFINITIVO" in resposta.content.decode()


class TestNaoDestroi:
    def test_rodar_de_novo_nao_duplica(self):
        rodar()
        rodar()

        assert Partner.objects.count() == 4
        assert ContentTranslation.objects.filter(block__key__startswith="legal.").count() == 2

    def test_nao_sobrescreve_o_que_ja_tem_conteudo(self):
        config = SiteSettings.load()
        config.contact_email = "meu@mail.com"
        config.save()

        rodar()

        assert SiteSettings.load().contact_email == "meu@mail.com"

    def test_nao_sobrescreve_texto_legal_ja_escrito(self):
        bloco = ContentBlock.objects.get(key="legal.terms_of_use")
        ContentTranslation.objects.create(
            block=bloco, language="pt", content="O texto de verdade do cliente."
        )

        rodar()

        texto = ContentTranslation.objects.get(block=bloco, language="pt").content
        assert texto == "O texto de verdade do cliente."

    def test_forcar_sobrescreve(self):
        config = SiteSettings.load()
        config.contact_email = "meu@mail.com"
        config.save()

        rodar("--forcar")

        assert SiteSettings.load().contact_email != "meu@mail.com"

    def test_nao_apaga_parceiro_de_fora(self):
        Partner.objects.create(name="Parceiro do cliente")

        rodar()

        assert Partner.objects.filter(name="Parceiro do cliente").exists()

    def test_nao_toca_na_home(self):
        """Ela já vem preenchida pela migration `content.0004`."""
        from apps.content.services import secoes_da_pagina

        antes = secoes_da_pagina("home")

        rodar()

        assert secoes_da_pagina("home") == antes


class TestNadaInventado:
    def test_o_contador_continua_real(self, client):
        """
        Zero cartas finalizadas, zero no selo. O número não é escrito por
        este comando nem por nenhum outro.
        """
        rodar()

        corpo = client.get(HOME).content.decode()
        numero = re.search(r'banner-contador-valor">([^<]*)<', corpo)

        assert numero.group(1) == "0"

    def test_nenhum_endereco_fora_do_dominio_reservado(self):
        """
        `exemplo.test` é reservado pela RFC 2606 e nunca resolve. Um
        endereço de verdade aqui viraria um link para um site que não é
        nosso, numa demonstração entregue ao cliente.
        """
        rodar()

        config = SiteSettings.load()
        enderecos = list(config.social_links.values()) + list(
            Partner.objects.exclude(url="").values_list("url", flat=True)
        )

        assert enderecos
        for endereco in enderecos:
            assert "exemplo.test" in endereco, endereco

    def test_o_contato_e_reconhecivel_como_demonstracao(self):
        rodar()

        config = SiteSettings.load()

        assert config.contact_email.endswith("@exemplo.test")
        assert "demonstração" in config.contact_address.lower()
        assert re.fullmatch(r"\+\d+(?: 0+)+", config.contact_phone), config.contact_phone

    def test_o_arquivo_do_comando_nao_traz_dado_real(self):
        """
        A pergunta é sobre a FONTE: o comando é versionado, e um endereço
        de verdade nele entraria no repositório.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        fonte = (
            raiz
            / "apps"
            / "content"
            / "management"
            / "commands"
            / "conteudo_demonstrativo.py"
        ).read_text(encoding="utf-8")

        for endereco in re.findall(r"https?://[^\s\"')]+", fonte):
            assert "exemplo.test" in endereco, endereco
        for email in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", fonte):
            assert email.endswith("@exemplo.test"), email

    def test_nao_ha_aparencia_nova(self):
        """
        O comando não mexe em cor, logo nem favicon: o padrão do produto
        já é neutro, e não há imagem de marca para cadastrar.
        """
        antes = SiteSettings.load()
        cores = (antes.theme_primary_color, antes.theme_success_color)

        rodar()

        depois = SiteSettings.load()
        assert (depois.theme_primary_color, depois.theme_success_color) == cores
        assert depois.logo is None
        assert depois.favicon is None

"""
Formulários do Backoffice.

Ficam aqui, e não no app de cada modelo, porque são telas
ADMINISTRATIVAS -- o app guarda o modelo e a regra; o backoffice guarda
a tela que os configura.
"""

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.content.models import REDES_SOCIAIS, Asset, SiteSettings
from apps.core.models import EmailSettings
from apps.letters.models import DocumentLanguageSettings, LetterNotice, LetterPolicy

# O que aparece esmaecido dentro dos campos. Endereço de exemplo,
# deliberadamente genérico: nada que se pareça com um endereço de
# verdade entra no código -- a configuração real é cadastrada pela
# tela, em produção.
EXEMPLO_DE_EMAIL = "mail@mail.com"


class LetterPolicyForm(forms.ModelForm):
    """
    As duas políticas do ciclo de vida, num formulário só.

    A validação de "esta política exige um número" mora em
    `LetterPolicy.clean()`, no modelo -- vale para qualquer caminho de
    código, não só para quem passa por esta tela. Aqui só ficam os
    widgets e a apresentação.
    """

    class Meta:
        model = LetterPolicy
        fields = ("editability", "editability_amount", "expiration", "expiration_amount")
        widgets = {
            "editability": forms.Select(attrs={"class": "input"}),
            "expiration": forms.Select(attrs={"class": "input"}),
            "editability_amount": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "expiration_amount": forms.NumberInput(attrs={"class": "input", "min": 0}),
        }
        labels = {
            "editability": _("Depois de finalizar, a carta pode ser editada"),
            "editability_amount": _("Quantidade"),
            "expiration": _("A carta expira"),
            "expiration_amount": _("Quantidade"),
        }
        help_texts = {
            "editability_amount": _(
                "Quantas horas ou dias, conforme a política escolhida ao lado. "
                "Ignorado nas políticas que não usam número."
            ),
            "expiration_amount": _(
                "Quantos dias, conforme a política escolhida ao lado. "
                "Ignorado nas políticas que não usam número."
            ),
        }


class LetterNoticeForm(forms.ModelForm):
    """
    Uma declaração da etapa 4 do assistente.

    `key` não entra aqui: é o nome com que a resposta fica gravada em
    `Letter.data`, e renomeá-lo numa tela de cadastro desligaria o
    histórico das cartas que já aceitaram aquela declaração. A chave é
    gerada na criação (ver `backoffice_letter_notice_new`) e não muda
    mais -- o mesmo tratamento que `content.Asset.key` recebe.

    O texto é TEXTO: nada de HTML. Quem o desenha é o `<label>` do
    checkbox, com autoescape ligado.
    """

    class Meta:
        model = LetterNotice
        fields = ("text", "is_active")
        widgets = {"text": forms.Textarea(attrs={"class": "input", "rows": 5})}
        labels = {"text": _("Texto da declaração"), "is_active": _("Ativa")}


# Prefixo dos campos de rede social no formulário: `social__facebook`.
# Separa o nome da rede do resto do formulário sem que uma rede chamada
# "site_name" pudesse colidir com um campo de verdade.
PREFIXO_DA_REDE = "social__"


class SiteSettingsForm(forms.ModelForm):
    """
    As configurações globais e institucionais do site.

    O QUE ESTE FORMULÁRIO NÃO TEM
    -----------------------------
    Cor, logo e favicon (são da Aparência), SMTP (é do E-mail) e idiomas
    do documento (são dos Idiomas). Cada um tem a sua tela; repetir o
    campo aqui criaria dois lugares para mudar a mesma coisa, e um dia
    eles discordariam.

    AS REDES SOCIAIS NÃO SÃO UM CAMPO DE JSON
    -----------------------------------------
    `SiteSettings.social_links` guarda `{"facebook": "https://..."}` --
    um campo só, em vez de uma coluna por rede. Aqui ele vira UM CAMPO
    POR REDE CONHECIDA (`REDES_SOCIAIS`), com rótulo e validação de URL.
    Quem administra digita um endereço, não um objeto.

    Rede deixada em branco SAI do dicionário em vez de virar `""`: o
    formato guardado continua sendo "as redes que existem", e o rodapé
    não precisa saber distinguir vazio de ausente.

    ONDE MORA CADA VALIDAÇÃO
    ------------------------
    O esquema da URL (`http`/`https`, nunca `javascript:`) é conferido em
    três lugares, de propósito: aqui, no `clean()` do modelo (que vale
    para qualquer caminho de código) e no processador de contexto (que
    protege a página mesmo com a linha já gravada torta). O valor termina
    dentro de um `href`, onde o autoescape do template não protege.
    """

    class Meta:
        model = SiteSettings
        fields = ("site_name", "contact_email", "contact_phone", "contact_address")
        widgets = {
            "site_name": forms.TextInput(attrs={"class": "input"}),
            "contact_email": forms.EmailInput(attrs={"class": "input"}),
            "contact_phone": forms.TextInput(attrs={"class": "input"}),
            "contact_address": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }
        labels = {
            "site_name": _("Nome do site"),
            "contact_email": _("E-mail de contato"),
            "contact_phone": _("Telefone"),
            "contact_address": _("Endereço"),
        }
        help_texts = {
            "site_name": _("Aparece no topo das páginas, no rodapé e no título das abas."),
            "contact_email": _(
                "Vira o link \"Contato\" no rodapé. Em branco, o link não aparece."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        guardadas = getattr(self.instance, "social_links", None) or {}
        for chave, nome, _icone in REDES_SOCIAIS:
            self.fields[f"{PREFIXO_DA_REDE}{chave}"] = forms.URLField(
                label=nome,
                required=False,
                assume_scheme="https",
                initial=guardadas.get(chave, "") if isinstance(guardadas, dict) else "",
                widget=forms.URLInput(
                    attrs={"class": "input", "placeholder": "https://"}
                ),
            )

    def campos_das_redes(self):
        """Os campos de rede social, na ordem declarada -- para o template."""
        return [self[f"{PREFIXO_DA_REDE}{chave}"] for chave, _nome, _icone in REDES_SOCIAIS]

    def campos_de_contato(self):
        return [self["contact_email"], self["contact_phone"], self["contact_address"]]

    def _post_clean(self):
        # As redes precisam estar na instância ANTES do `full_clean()` do
        # modelo -- é o que permite o modelo cobrar as suas próprias
        # regras contando o que acabou de ser digitado, em vez de conferir
        # o que estava gravado antes.
        redes = {}
        for chave, _nome, _icone in REDES_SOCIAIS:
            url = (self.cleaned_data.get(f"{PREFIXO_DA_REDE}{chave}") or "").strip()
            if url:
                redes[chave] = url
        self.instance.social_links = redes
        super()._post_clean()


class DocumentLanguagesForm(forms.ModelForm):
    """
    Os idiomas que o assistente oferece, e em qual a carta nasce.

    ATENÇÃO: é o idioma do DOCUMENTO, nunca o da interface. A interface
    é só portuguesa desde a Etapa 4.1 e continua sendo -- a tela diz isso
    em voz alta, porque os dois conceitos são fáceis de confundir.

    CAIXAS, NÃO JSON
    ----------------
    O campo guardado é uma lista de códigos; aqui ele vira quatro caixas
    de seleção, montadas a partir de `settings.LANGUAGES`. Quem administra
    marca "Português", não escreve `["pt"]`.

    ONDE MORA CADA VALIDAÇÃO
    ------------------------
    As regras do CONJUNTO -- sobrar pelo menos um idioma, e o padrão
    estar entre os disponíveis -- moram em
    `DocumentLanguageSettings.clean()`, no modelo: valem para qualquer
    caminho de código, não só para quem passa por esta tela (mesma
    decisão de `LetterPolicyForm`). Aqui fica o que é da tela: os
    widgets, os rótulos, e a normalização da ordem.

    `required=False` de propósito: desmarcar tudo não é um campo em
    branco, é um estado inválido -- e quem explica isso, com a frase
    certa, é o modelo.
    """

    available_document_languages = forms.MultipleChoiceField(
        label=_("Idiomas disponíveis para novas cartas"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_(
            "Desmarcar um idioma não apaga nada: as cartas já escritas nele "
            "continuam funcionando, e o modelo oficial continua guardado. "
            "Apenas as cartas novas deixam de poder escolhê-lo."
        ),
    )

    class Meta:
        model = DocumentLanguageSettings
        fields = ("available_document_languages", "default_letter_language")
        widgets = {"default_letter_language": forms.Select(attrs={"class": "input"})}
        labels = {"default_letter_language": _("Idioma padrão para novas cartas")}
        help_texts = {
            "default_letter_language": _(
                "Toda carta nova nasce neste idioma; a pessoa pode trocá-lo "
                "na etapa 5. Cartas já criadas não mudam."
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No `__init__`, e nao na classe: as opcoes sao lidas quando o
        # formulario e montado, nao quando o modulo e importado.
        self.fields["available_document_languages"].choices = list(settings.LANGUAGES)

    def clean_available_document_languages(self):
        """
        Na ordem oficial e sem repetidos -- o que chega e uma lista do
        cliente, e a ordem em que as caixas foram enviadas nao e a ordem
        em que os idiomas existem.
        """
        escolhidos = set(self.cleaned_data["available_document_languages"])
        return [code for code, _label in settings.LANGUAGES if code in escolhidos]


class EmailSettingsForm(forms.ModelForm):
    """
    Os dados do servidor SMTP. NÃO inclui `is_active`: ligar e desligar
    o envio é um botão próprio, como em modelos e usuários -- salvar um
    host não pode ser a mesma ação que colocar o sistema para mandar
    e-mail de verdade.

    A SENHA
    -------
    Campo de escrita, nunca de leitura. Sai em branco toda vez
    (`render_value=False` e nenhum `initial`), e branco significa
    "mantenha a que está guardada" -- não "apague". Para apagar existe
    uma caixa explícita.

    A senha digitada é aplicada à instância aqui no `clean()`, ANTES do
    `full_clean()` do modelo: é o que permite o modelo cobrar "usuário
    preenchido exige senha" contando a que acabou de ser digitada.
    """

    password = forms.CharField(
        label=_("Senha"),
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": "input", "autocomplete": "new-password"},
        ),
    )
    remover_senha = forms.BooleanField(
        label=_("Apagar a senha guardada"),
        required=False,
    )

    class Meta:
        model = EmailSettings
        fields = ("host", "port", "security", "username", "from_email", "from_name")
        widgets = {
            "host": forms.TextInput(
                attrs={"class": "input", "placeholder": "smtp.exemplo.com"}
            ),
            "port": forms.NumberInput(attrs={"class": "input", "min": 1, "max": 65535}),
            "security": forms.Select(attrs={"class": "input"}),
            "username": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": EXEMPLO_DE_EMAIL,
                    "autocomplete": "off",
                }
            ),
            "from_email": forms.EmailInput(
                attrs={"class": "input", "placeholder": EXEMPLO_DE_EMAIL}
            ),
            "from_name": forms.TextInput(
                attrs={"class": "input", "placeholder": "Desenrola"}
            ),
        }
        labels = {
            "host": _("Servidor SMTP"),
            "port": _("Porta"),
            "security": _("Segurança da conexão"),
            "username": _("Usuário"),
            "from_email": _("Remetente"),
            "from_name": _("Nome do remetente"),
        }
        help_texts = {
            "username": _("Em branco, o sistema conecta sem autenticar."),
            "from_email": _(
                "Endereço que aparece como remetente. Provedores como o Gmail só "
                "aceitam a própria conta autenticada ou um alias verificado nela — "
                "um endereço de outro domínio costuma ser reescrito ou recusado."
            ),
            "from_name": _("Nome exibido antes do endereço. Opcional."),
        }

    def clean(self):
        dados = super().clean()
        nova = dados.get("password") or ""
        remover = dados.get("remover_senha")

        if nova and remover:
            raise forms.ValidationError(
                _("Escolha uma coisa só: apagar a senha guardada ou cadastrar uma nova.")
            )

        if remover:
            self.instance.definir_senha("")
        elif nova:
            self.instance.definir_senha(nova)
        # Sem nenhum dos dois, a instância fica com a senha que já tinha.
        return dados


class EmailTestForm(forms.Form):
    """
    Para onde mandar a mensagem de teste.

    Formulário separado, e não um campo do outro: testar não altera
    nada, e misturar os dois faria um teste disparar um salvamento.
    """

    destino = forms.EmailField(
        label=_("Enviar um teste para"),
        widget=forms.EmailInput(
            attrs={"class": "input", "placeholder": EXEMPLO_DE_EMAIL}
        ),
    )


class AparenciaForm(forms.ModelForm):
    """
    A identidade visual do site: as duas cores, a logomarca e o favicon.

    POR QUE AQUI, E NAO EM `SiteSettingsForm`
    -----------------------------------------
    São telas diferentes, e a de Sistema diz isso por escrito. Juntar os
    campos num formulário só faria uma tela mostrar o que a outra
    promete administrar -- e os dois lugares divergiriam no primeiro
    ajuste.

    AS IMAGENS VÊM DA BIBLIOTECA
    ----------------------------
    `content.Asset`, a mesma de onde o banner e os parceiros se servem.
    Não há upload aqui: toda imagem administrável do projeto tem um lugar
    só, e é lá que está a proteção contra trocar arquivo do qual uma
    carta finalizada depende.

    A COR USA O SELETOR NATIVO DO NAVEGADOR
    ---------------------------------------
    `type="color"` devolve sempre `#rrggbb` -- exatamente o formato que
    `HEX_COLOR_VALIDATOR` cobra no modelo -- e não depende de JavaScript.
    """

    class Meta:
        model = SiteSettings
        fields = ("theme_primary_color", "theme_success_color", "logo", "favicon")
        widgets = {
            "theme_primary_color": forms.TextInput(
                attrs={"class": "input input-cor", "type": "color"}
            ),
            "theme_success_color": forms.TextInput(
                attrs={"class": "input input-cor", "type": "color"}
            ),
            "logo": forms.Select(attrs={"class": "input"}),
            "favicon": forms.Select(attrs={"class": "input"}),
        }
        labels = {
            "theme_primary_color": _("Cor principal"),
            "theme_success_color": _("Cor de sucesso"),
            "logo": _("Logomarca"),
            "favicon": _("Favicon"),
        }
        help_texts = {
            "theme_primary_color": _(
                "Títulos, botões e tintas claras são derivados dela."
            ),
            "theme_success_color": _("Usada em confirmações e estados concluídos."),
            "logo": _("Sem imagem, o site desenha a marca padrão."),
            "favicon": _("O ícone da aba do navegador."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("logo", "favicon"):
            self.fields[campo].queryset = Asset.objects.filter(is_active=True)
            self.fields[campo].empty_label = _("Nenhuma (usar o padrão)")

    def campos_das_cores(self):
        return [self["theme_primary_color"], self["theme_success_color"]]

    def campos_das_imagens(self):
        return [self["logo"], self["favicon"]]

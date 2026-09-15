"""
Formulários do Backoffice.

Ficam aqui, e não no app de cada modelo, porque são telas
ADMINISTRATIVAS -- o app guarda o modelo e a regra; o backoffice guarda
a tela que os configura.
"""

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.core.models import EmailSettings
from apps.letters.models import DocumentLanguageSettings, LetterPolicy

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

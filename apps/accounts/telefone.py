"""
O campo de telefone do projeto -- um só, usado em toda tela que o pede.

O PROBLEMA QUE ELE RESOLVE
--------------------------
O cadastro e o perfil tinham `+32` DESENHADO ao lado do campo, num
`<span>` que ninguém podia trocar. Quem mora na Bélgica com um celular
português, brasileiro ou francês não tinha como gravar o próprio
número: ou digitava o `+351` dentro do campo, e ficava com `+32 +351
...` na tela, ou deixava em branco.

COMO ELE GUARDA
---------------
UMA coluna, como sempre (`User.phone`): o número internacional inteiro,
`+32 470 00 00 00`. A separação entre código do país e resto é da TELA,
não do banco -- e é por isso que este módulo tem `separar()` e
`juntar()`: eles desmontam para editar e remontam para gravar. Uma
coluna nova para o país seria migração, sincronização e um estado a
mais para dar errado, tudo para guardar o que já está escrito ali.

POR QUE `MultiValueField`, E NÃO DOIS CAMPOS SOLTOS
---------------------------------------------------
Porque é isso que ele é: um valor, mostrado em duas caixas. O Django já
sabe compor, validar e recompor um campo assim -- inclusive quando o
formulário volta com erro, que é justamente quando dois campos soltos
se perdem um do outro.

E SEM JAVASCRIPT
----------------
O código do país é um `<select>` de verdade: escolher funciona com o
teclado, sem script. A máscara é enfeite por cima (`static/js/app.js`),
e o servidor aceita o número com ou sem ela.
"""

import re
from dataclasses import dataclass

from django import forms
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Pais:
    """
    Um país na lista do seletor.

    `mascara` usa `#` para dígito. Em branco quando não vale a pena: um
    formato errado atrapalha mais do que formato nenhum, e há países
    onde o comprimento varia demais para uma máscara só.
    """

    ddi: str
    nome: str
    exemplo: str = ""
    mascara: str = ""


# A Bélgica primeiro -- é onde o serviço acontece --, e depois os
# vizinhos e os países de língua portuguesa, que são de onde vem a maior
# parte de quem usa o produto. O resto em ordem de nome.
PAISES = (
    Pais("+32", _("Bélgica"), "470 00 00 00", "### ## ## ##"),
    Pais("+31", _("Países Baixos"), "6 12345678"),
    Pais("+33", _("França"), "6 12 34 56 78", "# ## ## ## ##"),
    Pais("+49", _("Alemanha"), "151 12345678"),
    Pais("+352", _("Luxemburgo"), "621 123 456"),
    Pais("+351", _("Portugal"), "912 345 678", "### ### ###"),
    Pais("+55", _("Brasil"), "11 91234-5678", "## #####-####"),
    Pais("+244", _("Angola"), "923 123 456", "### ### ###"),
    Pais("+258", _("Moçambique"), "82 123 4567"),
    Pais("+238", _("Cabo Verde"), "991 12 34"),
    Pais("+245", _("Guiné-Bissau"), "955 123 456"),
    Pais("+239", _("São Tomé e Príncipe"), "981 2345"),
    Pais("+34", _("Espanha"), "612 34 56 78", "### ## ## ##"),
    Pais("+39", _("Itália"), "312 345 6789"),
    Pais("+44", _("Reino Unido"), "7400 123456", "#### ######"),
    Pais("+353", _("Irlanda"), "85 123 4567"),
    Pais("+41", _("Suíça"), "78 123 45 67"),
    Pais("+43", _("Áustria"), "664 1234567"),
    Pais("+48", _("Polônia"), "512 345 678"),
    Pais("+40", _("Romênia"), "712 345 678"),
    Pais("+380", _("Ucrânia"), "50 123 4567"),
    Pais("+90", _("Turquia"), "532 123 45 67"),
    Pais("+212", _("Marrocos"), "650 123456"),
    Pais("+213", _("Argélia"), "551 23 45 67"),
    Pais("+216", _("Tunísia"), "20 123 456"),
    Pais("+221", _("Senegal"), "70 123 45 67"),
    Pais("+225", _("Costa do Marfim"), "01 23 45 67 89"),
    Pais("+233", _("Gana"), "24 123 4567"),
    Pais("+234", _("Nigéria"), "802 123 4567"),
    Pais("+237", _("Camarões"), "6 71 23 45 67"),
    # Nome curto de propósito: a caixa fechada do seletor corta o que
    # não couber, e "República Democrática do Congo" some inteira
    # depois do código.
    Pais("+243", _("Congo (RDC)"), "991 234 567"),
    Pais("+27", _("África do Sul"), "71 123 4567"),
    Pais("+1", _("EUA / Canadá"), "201 555 0123", "### ### ####"),
    Pais("+61", _("Austrália"), "412 345 678"),
    Pais("+86", _("China"), "131 2345 6789"),
    Pais("+91", _("Índia"), "81234 56789"),
    Pais("+81", _("Japão"), "90 1234 5678"),
)

# O que a tela oferece quando ninguém escolheu nada. É a Bélgica porque
# é onde quem usa o produto mora -- e continua trocável, que é o ponto.
DDI_PADRAO = "+32"

# Os códigos do mais longo para o mais curto: `separar()` precisa casar
# "+351" antes de "+35" e "+3", senão um número português viraria grego.
_POR_TAMANHO = sorted(PAISES, key=lambda pais: len(pais.ddi), reverse=True)

# O que sobra depois do código do país: dígitos e os separadores que as
# pessoas realmente digitam. Nada de letras -- um telefone não as tem --
# e nada de um segundo "+".
RESTO_ACEITO = re.compile(r"^[0-9 ().\-/]*$")

# Quantos dígitos, no mínimo, fazem um telefone. O mais curto do mundo
# tem seis; abaixo disso é engano de digitação, não número.
MINIMO_DE_DIGITOS = 6


def opcoes():
    """As opções do seletor: (código, rótulo)."""
    return [(pais.ddi, f"{pais.ddi} {pais.nome}") for pais in PAISES]


def pais_do_ddi(ddi):
    """O país de um código, ou None."""
    return next((pais for pais in PAISES if pais.ddi == ddi), None)


def separar(numero):
    """
    Desmonta o que está gravado em (código do país, resto).

    Número sem `+` -- gravado antes de este campo existir, quando o
    `+32` era desenho -- volta como belga, que é o que ele sempre foi
    na tela. Código desconhecido fica no resto, para ninguém perder o
    que digitou: a tela mostra o padrão e o número inteiro ao lado.
    """
    numero = (numero or "").strip()
    if not numero:
        return DDI_PADRAO, ""
    if not numero.startswith("+"):
        return DDI_PADRAO, numero

    for pais in _POR_TAMANHO:
        if numero.startswith(pais.ddi):
            return pais.ddi, numero[len(pais.ddi) :].strip()
    return DDI_PADRAO, numero


def juntar(ddi, resto):
    """
    Remonta o número internacional. Sem resto, não há telefone.

    Código do país sozinho não é número de ninguém: devolver `"+32"`
    encheria o banco de telefones que não ligam para lugar nenhum.
    """
    resto = (resto or "").strip()
    if not resto:
        return ""
    return f"{(ddi or DDI_PADRAO).strip()} {resto}"


class WidgetDeTelefone(forms.MultiWidget):
    """
    As duas caixas: o seletor de país e o número.

    POR QUE A MOLDURA VEM DO `render`, E NÃO DE UM TEMPLATE
    -------------------------------------------------------
    O template de um widget é procurado pelo RENDERIZADOR DE
    FORMULÁRIOS do Django, que por padrão só enxerga os templates do
    próprio Django -- não os do projeto. Apontar um arquivo de
    `templates/` aqui exigiria trocar o `FORM_RENDERER` global, e isso
    mudaria a marcação de TODOS os formulários do site de uma vez, para
    ganhar uma `<div>`. A `<div>` sai daqui.
    """

    def __init__(self, attrs=None):
        do_numero = {
            "class": "input",
            # `tel`, e NUNCA `number`: um telefone tem espaços, parênteses
            # e zeros à esquerda, e `number` os come. E o teclado do
            # celular abre no teclado de discagem do mesmo jeito.
            "type": "tel",
            "inputmode": "tel",
            "autocomplete": "tel-national",
            "maxlength": 24,
            **(attrs or {}),
        }
        super().__init__(
            widgets=(
                forms.Select(
                    choices=opcoes(),
                    attrs={"class": "input dial-code", "aria-label": _("Código do país")},
                ),
                forms.TextInput(attrs=do_numero),
            )
        )

    def decompress(self, value):
        ddi, resto = separar(value)
        return [ddi, resto]

    def render(self, name, value, attrs=None, renderer=None):
        """As duas caixas dentro da moldura que as põe lado a lado."""
        return format_html(
            '<div class="phone-field" data-telefone>{}</div>',
            super().render(name, value, attrs, renderer),
        )

    def get_context(self, name, value, attrs):
        """
        Acrescenta a cada opção a máscara e o exemplo do país.

        É daqui que o JavaScript os lê (`data-mascara`, `data-exemplo`):
        a lista de países fica em UM lugar, em Python, e não repetida
        num arquivo de script que envelheceria sozinho.
        """
        contexto = super().get_context(name, value, attrs)
        seletor = contexto["widget"]["subwidgets"][0]
        por_ddi = {pais.ddi: pais for pais in PAISES}
        for grupo in seletor["optgroups"]:
            for opcao in grupo[1]:
                pais = por_ddi.get(opcao["value"])
                if pais is None:
                    continue
                opcao["attrs"]["data-mascara"] = pais.mascara
                opcao["attrs"]["data-exemplo"] = pais.exemplo
        return contexto


class CampoDeTelefone(forms.MultiValueField):
    """
    Um telefone internacional, mostrado em duas caixas.

    Opcional por padrão: telefone em branco é um estado legítimo em
    todas as telas onde ele aparece hoje.
    """

    widget = WidgetDeTelefone

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(
            fields=(
                forms.ChoiceField(choices=opcoes(), required=False),
                forms.CharField(max_length=24, required=False),
            ),
            # Sem isto, escolher só o país (sem digitar número) faria o
            # Django cobrar o outro campo. Aqui país sozinho é "não
            # informei telefone", e é assim que a tela chega.
            require_all_fields=False,
            **kwargs,
        )

    def compress(self, valores):
        if not valores:
            return ""
        ddi, resto = (valores + ["", ""])[:2]
        return juntar(ddi, resto)

    def clean(self, value):
        numero = super().clean(value)
        if not numero:
            return ""

        _ddi, resto = separar(numero)
        if not RESTO_ACEITO.match(resto):
            raise forms.ValidationError(
                _(
                    "O telefone aceita apenas números, espaços e os sinais "
                    "( ) . - /. Escolha o país na lista ao lado."
                )
            )
        if len(re.sub(r"\D", "", resto)) < MINIMO_DE_DIGITOS:
            raise forms.ValidationError(
                _("Telefone curto demais. Confira o número.")
            )
        return numero

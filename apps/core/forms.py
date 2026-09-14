"""
Formulários do Backoffice.

Hoje só a política das cartas. Fica aqui, e não em `apps.letters`,
porque é uma tela ADMINISTRATIVA -- o app `letters` guarda o modelo e a
regra; o backoffice guarda a tela que os configura.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.letters.models import LetterPolicy


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

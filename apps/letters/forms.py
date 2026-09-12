"""
Formulario dinamico do assistente de Carta Convite.

Transforma o `field_schema` de uma `TemplateVersion` (contrato documentado
em `apps.doctemplates.schema`) em um `django.forms.Form` de verdade — este
e o unico lugar do projeto que interpreta o schema para gerar campos; a
view so agrupa os campos por etapa e o template so renderiza o que o
formulario ja resolveu (label, required, widget, erros). Isso e o que
permite a um administrador futuro mudar o field_schema no backoffice sem
tocar em HTML nem em views.

So os 10 tipos de `FIELD_TYPE_CHOICES` sao suportados; nenhum tipo novo e
inventado aqui.

Idioma: os textos do campo (rotulo, placeholder, ajuda e os rotulos das
opcoes) saem de `apps.doctemplates.schema.resolve_*`, no idioma da carta
(`Letter.language`), com fallback para o texto de origem quando aquele
idioma nao tem traducao. O VALOR de uma opcao nao muda com o idioma — so
o rotulo —, entao trocar o idioma da carta nunca invalida o que ja foi
preenchido.

Upload de arquivo (`type="file"`): o mapeamento existe para o schema
poder declarar o tipo sem quebrar o formulario, mas o modelo oficial
semeado nesta fase (`apps.doctemplates.official_templates`) nao usa esse
tipo — nao ha, portanto, fluxo de recebimento/armazenamento de arquivo
enviado pelo usuario implementado nesta fase (ver relatorio da Fase 3).
"""

import datetime

from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from apps.doctemplates.schema import resolve_field_text, resolve_label, resolve_options

PHONE_VALIDATOR = RegexValidator(
    regex=r"^[0-9+()\-.\s]{6,32}$",
    message=_("Informe um telefone válido."),
)


def _base_attrs(field_def, language, extra=None):
    attrs = {"class": "input"}
    placeholder = resolve_field_text(field_def, language, "placeholder")
    if placeholder:
        attrs["placeholder"] = placeholder
    if extra:
        attrs.update(extra)
    return attrs


def _build_field(field_def, language=None):
    """Constroi um `forms.Field` a partir de uma definicao do field_schema."""
    field_type = field_def["type"]
    required = bool(field_def.get("required", False))
    common = {
        "required": required,
        "label": resolve_label(field_def, language),
        "help_text": resolve_field_text(field_def, language, "help_text"),
    }

    if field_type == "text":
        return forms.CharField(
            **common, max_length=255, widget=forms.TextInput(attrs=_base_attrs(field_def, language))
        )

    if field_type == "textarea":
        return forms.CharField(
            **common, widget=forms.Textarea(attrs=_base_attrs(field_def, language))
        )

    if field_type == "date":
        # Dois formatos aceitos na entrada: "%d/%m/%Y" e o que o usuario
        # digita no campo (texto simples, sem <input type="date"> nativo,
        # para preservar o visual v2); "%Y-%m-%d" (ISO) e o formato em que
        # `serialize_cleaned_data` grava em Letter.data — precisa continuar
        # aceito para revalidar o conjunto completo no fechamento (Etapa 6).
        # `DateInput` (e nao um TextInput comum) e o que faz um valor
        # `date` ja salvo re-exibir formatado como "10/04/2025", em vez de
        # "2025-04-10", ao reabrir uma etapa ja preenchida.
        placeholder = resolve_field_text(field_def, language, "placeholder") or "DD/MM/AAAA"
        return forms.DateField(
            **common,
            input_formats=["%d/%m/%Y", "%Y-%m-%d"],
            widget=forms.DateInput(
                format="%d/%m/%Y",
                attrs=_base_attrs(field_def, language, {"placeholder": placeholder}),
            ),
        )

    if field_type == "number":
        return forms.IntegerField(
            **common, widget=forms.NumberInput(attrs=_base_attrs(field_def, language))
        )

    if field_type == "email":
        return forms.EmailField(
            **common, widget=forms.EmailInput(attrs=_base_attrs(field_def, language))
        )

    if field_type == "phone":
        return forms.CharField(
            **common,
            max_length=32,
            validators=[PHONE_VALIDATOR],
            widget=forms.TextInput(attrs=_base_attrs(field_def, language, {"type": "tel"})),
        )

    if field_type == "select":
        choices = [("", "---------")] + resolve_options(field_def, language)
        return forms.ChoiceField(
            **common, choices=choices, widget=forms.Select(attrs=_base_attrs(field_def, language))
        )

    if field_type == "checkbox":
        return forms.BooleanField(**common, widget=forms.CheckboxInput())

    if field_type == "radio":
        return forms.ChoiceField(
            **common, choices=resolve_options(field_def, language), widget=forms.RadioSelect()
        )

    if field_type == "file":
        return forms.FileField(**common)

    raise ValueError(f"Tipo de campo não suportado: {field_type!r}")


def _clean_stay_dates(form):
    """
    Validacao entre datas da etapa 'Viagem': partida deve ser posterior a
    chegada. Regra de negocio concreta deste modelo oficial (o aviso ja
    exibido no assistente), nao uma feature generica do schema.
    """
    cleaned = form.cleaned_data
    arrival = cleaned.get("stay_arrival")
    departure = cleaned.get("stay_departure")
    if arrival and departure and departure <= arrival:
        form.add_error(
            "stay_departure",
            _("A data de partida deve ser posterior à data de chegada."),
        )
    return cleaned


def build_dynamic_form(fields, data=None, initial=None, language=None):
    """
    Constroi e instancia um `forms.Form` para os `fields` (uma lista de
    definicoes do field_schema, ja filtrada para a etapa desejada), com os
    textos no idioma pedido (`language=None` usa o texto de origem).

    `data=None` produz um formulario nao vinculado (para exibicao/GET);
    `data=QueryDict` produz um formulario vinculado, pronto para validar.
    """
    attrs = {field_def["key"]: _build_field(field_def, language) for field_def in fields}
    keys = {field_def["key"] for field_def in fields}

    if {"stay_arrival", "stay_departure"} <= keys:
        attrs["clean"] = _clean_stay_dates

    form_class = type("DynamicStepForm", (forms.Form,), attrs)
    return form_class(data=data, initial=initial)


def serialize_cleaned_data(cleaned_data):
    """Converte valores nao serializaveis em JSON (ex.: `date`) para texto ISO."""
    serialized = {}
    for key, value in cleaned_data.items():
        if isinstance(value, (datetime.date, datetime.datetime)):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def deserialize_initial(fields, stored_data):
    """
    Converte de volta os valores gravados em `Letter.data` (texto ISO) para
    o tipo esperado por `initial=` de cada campo (ex.: `date` real, para o
    DateField re-exibir corretamente no formato "%d/%m/%Y").
    """
    initial = {}
    for field_def in fields:
        key = field_def["key"]
        if key not in stored_data:
            continue
        value = stored_data[key]
        if field_def["type"] == "date" and isinstance(value, str) and value:
            try:
                value = datetime.date.fromisoformat(value)
            except ValueError:
                pass
        initial[key] = value
    return initial

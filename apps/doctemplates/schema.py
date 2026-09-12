"""
Contrato de formato para `LetterTemplate.default_field_schema` e
`TemplateVersion.field_schema`.

O campo continua sendo um JSONField livre (e precisa continuar assim: a
imutabilidade de uma versao publicada depende de ser um unico bloco
gravado atomicamente, sem uma tabela relacional paralela para reproduzir).
Este modulo so documenta e valida a FORMA esperada, para que "nao fique
hardcoded no HTML" vire uma regra checavel, nao so uma convencao:

    {
        "fields": [
            {
                "key": "nome_convidado",       # obrigatorio, unico no schema
                "type": "text",                 # um de FIELD_TYPE_CHOICES
                "label": "Nome completo",
                "required": true,
                "order": 1,
                "placeholder": "Como no passaporte",
                "help_text": "Copie exatamente como está no documento.",
                "options": [...],                # obrigatorio para select/radio
                "section": "convidado"           # etapa/secao do formulario
            },
            ...
        ]
    }

A validacao roda em `clean()` (chamada por `full_clean()`/formularios),
nao em `save()` — assim, dados que ainda nao seguem este formato (ex.:
fixtures de teste com uma lista simples de nomes de campo) continuam
funcionando; so quem pedir validacao explicita e cobrado pelo contrato.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

FIELD_TYPE_CHOICES = (
    "text",
    "textarea",
    "date",
    "number",
    "email",
    "phone",
    "select",
    "checkbox",
    "radio",
    "file",
)

# Tipos cujo valor e escolhido entre opcoes pre-definidas.
OPTION_BASED_TYPES = ("select", "radio")


def validate_field_schema(schema):
    """
    Levanta ValidationError se `schema` nao seguir o formato documentado
    acima. Um dict vazio (`{}`) e valido — um modelo pode nao ter nenhum
    campo definido ainda.
    """
    if not isinstance(schema, dict):
        raise ValidationError(_("A configuração dos campos deve ser um objeto (JSON)."))

    if not schema:
        return

    fields = schema.get("fields")
    if fields is None:
        raise ValidationError(_("A configuração dos campos precisa ter a chave \"fields\"."))
    if not isinstance(fields, list):
        raise ValidationError(_("\"fields\" deve ser uma lista de campos."))

    seen_keys = set()
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise ValidationError(
                _("O campo na posição %(index)s deve ser um objeto.") % {"index": index}
            )

        key = field.get("key")
        if not key or not isinstance(key, str):
            raise ValidationError(
                _("O campo na posição %(index)s precisa de uma \"key\" (texto).")
                % {"index": index}
            )
        if key in seen_keys:
            raise ValidationError(
                _("Chave de campo duplicada: \"%(key)s\".") % {"key": key}
            )
        seen_keys.add(key)

        field_type = field.get("type")
        if field_type not in FIELD_TYPE_CHOICES:
            raise ValidationError(
                _("O campo \"%(key)s\" tem um tipo inválido: \"%(type)s\".")
                % {"key": key, "type": field_type}
            )

        if field_type in OPTION_BASED_TYPES and not field.get("options"):
            raise ValidationError(
                _("O campo \"%(key)s\" é do tipo \"%(type)s\" e precisa de \"options\".")
                % {"key": key, "type": field_type}
            )

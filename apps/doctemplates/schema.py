"""
Contrato de formato para `DocumentTemplate.field_schema`.

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
                "required": true,
                "order": 1,
                "section": "convidado",         # etapa/secao do formulario

                # Textos no idioma de origem (fallback). Continuam validos
                # sozinhos, sem "translations".
                "label": "Nome completo",
                "placeholder": "Como no passaporte",
                "help_text": "Copie exatamente como está no documento.",

                # Traducoes dos MESMOS textos. So texto entra aqui: a
                # configuracao tecnica (key/type/required/order/section)
                # nunca e duplicada por idioma.
                "translations": {
                    "fr": {"label": "Nom complet", "placeholder": "..."},
                    "nl": {"label": "Volledige naam"},
                    "en": {"label": "Full name"}
                },

                # Obrigatorio para select/radio. Duas formas aceitas:
                #   ["Brasileira", "Belga"]              -> valor = rotulo
                #   [{"value": "be",                      -> valor estavel,
                #     "label": "Belga",                      rotulo traduzivel
                #     "translations": {"fr": "Belge"}}]
                "options": [...]
            },
            ...
        ]
    }

O idioma dos textos e resolvido em `resolve_field_text()` /
`resolve_options()`, com fallback seguro: idioma pedido -> texto de origem
-> a propria chave. Um idioma sem traducao nunca quebra o formulario, so
volta ao texto original.

A validacao roda em `clean()` (chamada por `full_clean()`/formularios),
nao em `save()` — assim, dados que ainda nao seguem este formato (ex.:
fixtures de teste com uma lista simples de nomes de campo) continuam
funcionando; so quem pedir validacao explicita e cobrado pelo contrato.
"""

from django.conf import settings
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
    # Escolha vinda do cadastro de nacionalidades (models.Nationality), e
    # nao de `options` fixas no schema: a lista e administravel e o que
    # fica guardado na carta e o CODIGO, nunca o texto traduzido.
    "nationality",
)

# Tipos cujo valor e escolhido entre opcoes pre-definidas.
OPTION_BASED_TYPES = ("select", "radio")

# Os unicos textos de um campo que sao traduziveis.
TRANSLATABLE_TEXT_KEYS = ("label", "placeholder", "help_text")


def valid_language_codes():
    """Os codigos de idioma aceitos — sempre de settings.LANGUAGES."""
    return {code for code, _label in settings.LANGUAGES}


def _validate_text_translations(translations, key):
    """Valida `{"fr": {"label": "..."}, ...}` de um campo."""
    if not isinstance(translations, dict):
        raise ValidationError(
            _("O campo \"%(key)s\" tem \"translations\" que não é um objeto.") % {"key": key}
        )

    codes = valid_language_codes()
    for language, texts in translations.items():
        if language not in codes:
            raise ValidationError(
                _("O campo \"%(key)s\" tem tradução para um idioma desconhecido: \"%(lang)s\".")
                % {"key": key, "lang": language}
            )
        if not isinstance(texts, dict):
            raise ValidationError(
                _("A tradução \"%(lang)s\" do campo \"%(key)s\" deve ser um objeto.")
                % {"key": key, "lang": language}
            )
        for text_key, value in texts.items():
            if text_key not in TRANSLATABLE_TEXT_KEYS:
                raise ValidationError(
                    _("A tradução \"%(lang)s\" do campo \"%(key)s\" tem um texto inválido: "
                      "\"%(text_key)s\".")
                    % {"key": key, "lang": language, "text_key": text_key}
                )
            if not isinstance(value, str):
                raise ValidationError(
                    _("O texto \"%(text_key)s\" (%(lang)s) do campo \"%(key)s\" deve ser texto.")
                    % {"key": key, "lang": language, "text_key": text_key}
                )


def _validate_options(options, key):
    """Valida as opcoes de um select/radio, nas duas formas aceitas."""
    codes = valid_language_codes()
    for option in options:
        if isinstance(option, str):
            continue
        if not isinstance(option, dict):
            raise ValidationError(
                _("O campo \"%(key)s\" tem uma opção que não é texto nem objeto.") % {"key": key}
            )

        value = option.get("value")
        if not value or not isinstance(value, str):
            raise ValidationError(
                _("Cada opção do campo \"%(key)s\" precisa de um \"value\" (texto).")
                % {"key": key}
            )

        label = option.get("label")
        if label is not None and not isinstance(label, str):
            raise ValidationError(
                _("A opção \"%(value)s\" do campo \"%(key)s\" tem um rótulo inválido.")
                % {"key": key, "value": value}
            )

        translations = option.get("translations")
        if translations is None:
            continue
        if not isinstance(translations, dict):
            raise ValidationError(
                _("A opção \"%(value)s\" do campo \"%(key)s\" tem \"translations\" inválido.")
                % {"key": key, "value": value}
            )
        for language, translated in translations.items():
            if language not in codes:
                raise ValidationError(
                    _("A opção \"%(value)s\" do campo \"%(key)s\" traduz um idioma "
                      "desconhecido: \"%(lang)s\".")
                    % {"key": key, "value": value, "lang": language}
                )
            if not isinstance(translated, str):
                raise ValidationError(
                    _("A tradução \"%(lang)s\" da opção \"%(value)s\" (campo \"%(key)s\") "
                      "deve ser texto.")
                    % {"key": key, "value": value, "lang": language}
                )


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

        if field.get("options") is not None:
            if not isinstance(field["options"], list):
                raise ValidationError(
                    _("O campo \"%(key)s\" tem \"options\" que não é uma lista.") % {"key": key}
                )
            _validate_options(field["options"], key)

        if field.get("translations") is not None:
            _validate_text_translations(field["translations"], key)


def resolve_field_text(field_def, language, text_key):
    """
    O texto (`label`, `placeholder` ou `help_text`) de um campo no idioma
    pedido. Fallback seguro: tradução do idioma -> texto de origem -> "".
    """
    translations = field_def.get("translations") or {}
    translated = translations.get(language) or {}
    value = translated.get(text_key)
    if value:
        return value
    return field_def.get(text_key) or ""


def resolve_label(field_def, language):
    """O rótulo do campo no idioma pedido; cai na `key` se não houver nenhum."""
    return resolve_field_text(field_def, language, "label") or field_def.get("key", "")


def resolve_options(field_def, language):
    """
    As opções de um select/radio como `[(valor, rótulo)]`.

    O VALOR é sempre o mesmo em qualquer idioma — é ele que fica gravado
    em `Letter.data`, então trocar o idioma da carta nunca invalida o que
    já foi respondido. Só o rótulo exibido muda.
    """
    resolved = []
    for option in field_def.get("options") or []:
        if isinstance(option, dict):
            value = option.get("value", "")
            translations = option.get("translations") or {}
            label = translations.get(language) or option.get("label") or value
        else:
            value = label = option
        resolved.append((value, label))
    return resolved

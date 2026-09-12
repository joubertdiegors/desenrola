from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LettersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.letters"
    label = "letters"
    verbose_name = _("Cartas")

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DoctemplatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doctemplates"
    label = "doctemplates"
    verbose_name = _("Modelos de documento")

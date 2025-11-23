from django.apps import AppConfig
from django.db.models.signals import post_migrate


class WorkforceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workforce"

    def ready(self):
        """
        Safe AppConfig:
        - No model imports at module load
        - No scheduler start here (prevents random reload loops)
        - Only connects signals
        """

        # ---- Create default teams AFTER migrations ----
        def create_default_teams(sender, **kwargs):
            from accounts.models import CustomUser
            from .models import Team

            dept_names = [choice[0] for choice in CustomUser.DEPARTMENT_CHOICES]

            required = dept_names + [
                "Minister",
                "Magnet",
                "Service Production",
                "Security",
            ]

            for name in required:
                Team.objects.get_or_create(name=name)

        post_migrate.connect(create_default_teams, sender=self)

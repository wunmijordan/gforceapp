from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db import connections
from django.db.utils import OperationalError
import threading, time


class WorkforceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workforce"

    def ready(self):
        """
        Bootstraps the workforce module:
        - Ensures default teams exist after migration
        - Starts the scheduler safely after DB is ready
        """
        from .models import Team
        from accounts.models import CustomUser
        from . import scheduler  # ⬅️ scheduler is now part of workforce

        # ---- 1️⃣ Create default teams after migrations ----
        def create_default_teams(sender, **kwargs):
            dept_names = [choice[0] for choice in CustomUser.DEPARTMENT_CHOICES]
            for name in dept_names + ["Minister", "Magnet", "Service Production", "Security"]:
                Team.objects.get_or_create(name=name)

        post_migrate.connect(create_default_teams, sender=self)

        # Also run immediately if DB is ready and no teams exist yet
        try:
            from django.db import connections
            from django.db.utils import OperationalError
            connections['default'].ensure_connection()
            from workforce.models import Team
            if not Team.objects.exists():
                create_default_teams(None)
        except OperationalError:
            pass

        # ---- 2️⃣ Safe scheduler startup ----
        def safe_start_scheduler():
            """Wait until DB is ready before starting scheduler (esp. on cold boot)."""
            for _ in range(10):  # retry up to ~10 seconds
                try:
                    connections["default"].cursor()
                    break
                except OperationalError:
                    print("⏳ [Scheduler] Waiting for DB to be ready...")
                    time.sleep(1)
            else:
                print("❌ [Scheduler] DB not ready. Scheduler start aborted.")
                return

            if not getattr(scheduler, "_started", False):
                scheduler.start()
                scheduler._started = True

        # Delay scheduler boot slightly to avoid race with Django startup
        threading.Timer(1.0, safe_start_scheduler).start()

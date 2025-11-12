from django.apps import AppConfig


class WorkforceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workforce"

    def ready(self):
        from .models import Team
        from accounts.models import CustomUser
        from . import scheduler
        from django.db.utils import OperationalError
        from django.db import connections
        from django.db.models.signals import post_migrate
        import threading, time

        # ---- 1️⃣ Create default teams after migrations ----
        def create_default_teams(sender=None, **kwargs):
            dept_names = [choice[0] for choice in CustomUser.DEPARTMENT_CHOICES]
            for name in dept_names + ["Minister", "Magnet", "Service Production", "Security"]:
                Team.objects.get_or_create(name=name)

        post_migrate.connect(create_default_teams, sender=self)

        # ---- 2️⃣ Safe scheduler startup ----
        def start_scheduler_safely():
            """Wait until DB is ready, create default teams if missing, then start scheduler."""
            for _ in range(10):
                try:
                    connections["default"].cursor()  # just checks DB connection
                    break
                except OperationalError:
                    print("⏳ [Scheduler] Waiting for DB...")
                    time.sleep(1)
            else:
                print("❌ [Scheduler] DB not ready, aborting scheduler startup.")
                return

            # Ensure default teams exist
            if not Team.objects.exists():
                create_default_teams()

            # Start scheduler once
            if not getattr(scheduler, "_started", False):
                scheduler.start()
                scheduler._started = True

        # Run scheduler in a separate thread to avoid sync DB in async context
        threading.Thread(target=start_scheduler_safely, daemon=True).start()


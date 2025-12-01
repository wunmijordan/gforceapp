from django.core.management.base import BaseCommand
from workforce.scheduler import start  

class Command(BaseCommand):
    help = "Start the background APScheduler worker."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting APScheduler worker..."))

        try:
            start()
            self.stdout.write(self.style.SUCCESS("✅ APScheduler started successfully."))
        except RuntimeError as e:
            if "already running" in str(e).lower():
                self.stdout.write(self.style.WARNING("⚠️ Scheduler already running, skipping."))
            else:
                self.stderr.write(self.style.ERROR(f"❌ Scheduler runtime error: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Scheduler error: {e}"))

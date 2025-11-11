import subprocess
import sys
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Run Django dev server with auto-reload using uvicorn."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting Django dev server..."))

        try:
            subprocess.run([
                "uvicorn",
                "gforceapp.asgi:application",
                "--reload",
                "--host", "0.0.0.0",
                "--port", "8000",
            ])
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n🛑 Dev server stopped by user (Ctrl+C)"))
            sys.exit(0)

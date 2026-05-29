"""
Management command: run_all

Starts ALL backend services in a single process using threads:
  1. Django development server (runserver on port 8000)
  2. Outbox Projector (SQL → MongoDB sync)
  3. SMS Worker (async OTP delivery)

Usage:
    python manage.py run_all

Press Ctrl+C to stop all services gracefully.
"""
import os
import signal
import sys
import time
import threading
import logging

# Prevent UnicodeEncodeError on Windows consoles when printing emojis/arrows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from django.core.management.base import BaseCommand
from django.core.management import call_command

from otp.services.projector import project_pending_events
from otp.services.sms_worker import process_pending_otps

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run all backend services: Django server + Projector + SMS Worker"

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="Port for the Django dev server (default: 8000)",
        )
        parser.add_argument(
            "--projector-interval",
            type=float,
            default=2.0,
            help="Projector polling interval in seconds (default: 2)",
        )
        parser.add_argument(
            "--worker-interval",
            type=float,
            default=1.0,
            help="SMS Worker polling interval in seconds (default: 1)",
        )

    def handle(self, *args, **options):
        port = options["port"]
        projector_interval = options["projector_interval"]
        worker_interval = options["worker_interval"]

        self._running = True

        self.stdout.write(self.style.SUCCESS(
            "\n" + "=" * 60 + "\n"
            "  BANCO DHABI -- CORE SENTINEL\n"
            "  Starting all services...\n"
            "=" * 60 + "\n"
            f"  [WEB] Django Server     -> http://127.0.0.1:{port}/\n"
            f"  [PRJ] Outbox Projector  -> polling every {projector_interval}s\n"
            f"  [SMS] SMS Worker        -> polling every {worker_interval}s\n"
            "=" * 60 + "\n"
            "  Press Ctrl+C to stop all services\n"
            "=" * 60
        ))

        # ── Start background threads ─────────────────────────────────────────
        projector_thread = threading.Thread(
            target=self._run_projector,
            args=(projector_interval,),
            name="projector",
            daemon=True,
        )
        worker_thread = threading.Thread(
            target=self._run_sms_worker,
            args=(worker_interval,),
            name="sms-worker",
            daemon=True,
        )

        projector_thread.start()
        worker_thread.start()

        # ── Start Django dev server in the main thread ───────────────────────
        try:
            call_command("runserver", f"0.0.0.0:{port}", "--noreload")
        except KeyboardInterrupt:
            self._running = False
            self.stdout.write(self.style.WARNING("\n[!] Shutting down all services..."))

    def _run_projector(self, interval: float):
        """Projector polling loop."""
        self.stdout.write(self.style.SUCCESS("  [Projector] Started"))
        while self._running:
            try:
                count = project_pending_events()
                if count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f"  [Projector] Projected {count} event(s)")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [Projector] ERROR: {exc}")
                )
            time.sleep(interval)

    def _run_sms_worker(self, interval: float):
        """SMS Worker polling loop."""
        self.stdout.write(self.style.SUCCESS("  [SMS Worker] Started"))
        while self._running:
            try:
                count = process_pending_otps()
                if count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f"  [SMS Worker] Processed {count} OTP(s)")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [SMS Worker] ERROR: {exc}")
                )
            time.sleep(interval)

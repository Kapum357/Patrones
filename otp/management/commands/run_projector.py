"""
Management command: run_projector

Runs the Outbox Projector in a continuous polling loop.

Usage:
    python manage.py run_projector
    python manage.py run_projector --interval 5   # poll every 5 seconds

Press Ctrl+C to stop gracefully.
"""
import signal
import time
import logging

from django.core.management.base import BaseCommand

from otp.services.projector import project_pending_events

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Outbox Projector — polls for unprojected events and writes to MongoDB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Polling interval in seconds (default: 2)",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single projection cycle and exit",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        run_once = options["once"]

        self.stdout.write(self.style.SUCCESS(
            "=" * 60 + "\n"
            "  [Outbox Projector] Starting...\n"
            f"  Polling every {interval}s  |  Press Ctrl+C to stop\n"
            "=" * 60
        ))

        # Graceful shutdown
        self._running = True

        def _shutdown(signum, frame):
            self.stdout.write(self.style.WARNING("\n[!] Shutdown signal received -- stopping..."))
            self._running = False

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        cycle = 0
        total_projected = 0

        while self._running:
            cycle += 1
            try:
                count = project_pending_events()
                if count > 0:
                    total_projected += count
                    self.stdout.write(
                        self.style.SUCCESS(f"  [Cycle {cycle}] OK: Projected {count} event(s)")
                    )
                else:
                    self.stdout.write(
                        f"  [Cycle {cycle}] No pending events", ending="\r"
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [Cycle {cycle}] ERROR: {exc}")
                )

            if run_once:
                break

            time.sleep(interval)

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] Projector stopped. Total projected: {total_projected} events over {cycle} cycles."
        ))

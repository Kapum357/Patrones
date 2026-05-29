"""
Management command: run_sms_worker

Runs the SMS Worker in a continuous polling loop.

Usage:
    python manage.py run_sms_worker
    python manage.py run_sms_worker --interval 1   # poll every 1 second

Press Ctrl+C to stop gracefully.
"""
import signal
import time
import logging

from django.core.management.base import BaseCommand

from otp.services.sms_worker import process_pending_otps

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the SMS Worker — polls for PENDING OTP requests and sends them via SMS Gateway"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=1.0,
            help="Polling interval in seconds (default: 1)",
        )

    def handle(self, *args, **options):
        interval = options["interval"]

        self.stdout.write(self.style.SUCCESS(
            "=" * 60 + "\n"
            "  [SMS Worker] Starting...\n"
            f"  Polling every {interval}s  |  Press Ctrl+C to stop\n"
            "=" * 60
        ))

        self._running = True

        def _shutdown(signum, frame):
            self.stdout.write(self.style.WARNING("\n[!] Shutdown signal received -- stopping..."))
            self._running = False

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        cycle = 0
        total_processed = 0

        while self._running:
            cycle += 1
            try:
                count = process_pending_otps()
                if count > 0:
                    total_processed += count
                    self.stdout.write(
                        self.style.SUCCESS(f"  [Cycle {cycle}] OK: Processed {count} OTP(s)")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  [Cycle {cycle}] ERROR: {exc}")
                )

            time.sleep(interval)

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] SMS Worker stopped. Total processed: {total_processed} OTPs over {cycle} cycles."
        ))

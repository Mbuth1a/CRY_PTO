import time

from django.core.management.base import BaseCommand

from simulator.services import generate_market_tick


class Command(BaseCommand):
    help = "Continuously generate synthetic BTCUSDT market ticks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=1.0,
            help="Seconds between market ticks.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting synthetic market generator "
                f"(interval={interval}s)"
            )
        )

        try:
            while True:
                tick = generate_market_tick()

                self.stdout.write(
                    f"{tick.symbol}: {tick.price} "
                    f"{tick.created_at}"
                )

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING("Market generator stopped.")
            )
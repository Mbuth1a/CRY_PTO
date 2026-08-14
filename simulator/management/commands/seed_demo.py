from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from simulator.models import DemoProfile, DemoWallet, MarketTick
from simulator.services import audit


class Command(BaseCommand):
    help = "Create synthetic demonstration data."

    def handle(self, *args, **kwargs):
        username = "labuser"
        password = "LabOnly-ChangeMe-123!"

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.save()

        profile, _ = DemoProfile.objects.get_or_create(
            user=user,
            defaults={"display_name": "Synthetic Lab User"},
        )

        DemoWallet.objects.get_or_create(
            user=user,
            asset="USDT",
            defaults={
                "balance": Decimal("25000"),
                "address": "demo_usdt_wallet_001",
            },
        )

        DemoWallet.objects.get_or_create(
            user=user,
            asset="KES",
            defaults={
                "balance": Decimal("100000"),
                "address": "demo_kes_wallet_001",
            },
        )

        if not MarketTick.objects.exists():
            MarketTick.objects.create(
                symbol="BTCUSDT",
                price=Decimal("65000.00000000"),
            )

        audit(
            "DEMO_SEED",
            "Synthetic demo environment initialized.",
            user=user,
            metadata={"synthetic": True},
        )

        self.stdout.write(self.style.SUCCESS("Demo environment ready."))
        self.stdout.write(f"Username: {username}")
        self.stdout.write(f"Password: {password}")

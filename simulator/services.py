import logging
import random
import uuid
from decimal import Decimal

from django.db import transaction

from .models import AuditEvent, DemoWallet, MarketTick, Position, SyntheticPayment

logger = logging.getLogger("fraudlab")


def audit(event_type, message, user=None, severity="INFO", metadata=None, ip_address=None):
    event = AuditEvent.objects.create(
        event_type=event_type,
        message=message,
        user=user,
        severity=severity,
        metadata=metadata or {},
        ip_address=ip_address,
    )
    logger.info("%s | %s | %s", severity, event_type, message)
    return event


def generate_market_tick():
    latest = MarketTick.objects.filter(symbol="BTCUSDT").first()
    base = latest.price if latest else Decimal("65000")
    movement = Decimal(str(random.uniform(-0.012, 0.012)))
    price = (base * (Decimal("1") + movement)).quantize(Decimal("0.00000001"))
    return MarketTick.objects.create(symbol="BTCUSDT", price=price)


@transaction.atomic
def synthetic_deposit(user, provider, amount, asset):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Amount must be positive.")

    reference = f"SIM-{uuid.uuid4().hex[:14].upper()}"

    payment = SyntheticPayment.objects.create(
        user=user,
        provider=provider,
        direction="DEPOSIT",
        amount=amount,
        asset=asset,
        reference=reference,
        metadata={"synthetic": True},
    )

    wallet, _ = DemoWallet.objects.get_or_create(
        user=user,
        asset=asset,
        defaults={"address": f"demo_{uuid.uuid4().hex}"},
    )
    wallet.balance += amount
    wallet.save(update_fields=["balance"])

    audit(
        "SYNTHETIC_DEPOSIT",
        f"{provider} synthetic deposit credited: {amount} {asset}",
        user=user,
        metadata={"reference": reference, "synthetic": True},
    )
    return payment


@transaction.atomic
def synthetic_withdrawal(user, provider, amount, asset):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Amount must be positive.")

    wallet = DemoWallet.objects.filter(user=user, asset=asset).first()
    if not wallet or wallet.balance < amount:
        raise ValueError("Insufficient synthetic balance.")

    wallet.balance -= amount
    wallet.save(update_fields=["balance"])

    reference = f"SIM-WD-{uuid.uuid4().hex[:12].upper()}"

    payment = SyntheticPayment.objects.create(
        user=user,
        provider=provider,
        direction="WITHDRAWAL",
        amount=amount,
        asset=asset,
        reference=reference,
        metadata={"synthetic": True},
    )

    audit(
        "SYNTHETIC_WITHDRAWAL",
        f"{provider} synthetic withdrawal: {amount} {asset}",
        user=user,
        metadata={"reference": reference, "synthetic": True},
    )
    return payment


def open_position(user, quantity, side="LONG"):
    tick = MarketTick.objects.filter(symbol="BTCUSDT").first()
    if not tick:
        tick = generate_market_tick()

    position = Position.objects.create(
        user=user,
        quantity=Decimal(str(quantity)),
        entry_price=tick.price,
        side=side,
    )

    audit(
        "POSITION_OPENED",
        f"Synthetic {side} position opened at {tick.price}",
        user=user,
        metadata={"quantity": str(quantity), "price": str(tick.price)},
    )
    return position

def synthetic_convert_kes_to_usdt(user, kes_amount, rate=Decimal("130")):
    """Convert synthetic KES into synthetic USDT inside the lab only."""
    kes_amount = Decimal(str(kes_amount))
    rate = Decimal(str(rate))

    if kes_amount <= 0 or rate <= 0:
        raise ValueError("Amount and rate must be positive.")

    kes_wallet = DemoWallet.objects.filter(
        user=user,
        asset="KES"
    ).first()

    if not kes_wallet or kes_wallet.balance < kes_amount:
        raise ValueError("Insufficient synthetic KES balance.")

    usdt_amount = (
        kes_amount / rate
    ).quantize(Decimal("0.00000001"))

    from .models import SyntheticConversion
    import uuid

    with transaction.atomic():

        kes_wallet.balance -= kes_amount
        kes_wallet.save(update_fields=["balance"])

        usdt_wallet, _ = DemoWallet.objects.get_or_create(
            user=user,
            asset="USDT",
            defaults={
                "address": f"demo_usdt_wallet_{uuid.uuid4().hex[:12]}"
            },
        )

        usdt_wallet.balance += usdt_amount
        usdt_wallet.save(update_fields=["balance"])

        reference = (
            f"SIM-FX-{uuid.uuid4().hex[:12].upper()}"
        )

        conversion = SyntheticConversion.objects.create(
            user=user,
            from_asset="KES",
            to_asset="USDT",
            from_amount=kes_amount,
            to_amount=usdt_amount,
            rate=rate,
            reference=reference,
        )

        audit(
            "SYNTHETIC_CONVERSION",
            f"Converted {kes_amount} KES to "
            f"{usdt_amount} USDT at synthetic rate {rate}.",
            user=user,
            metadata={
                "reference": reference,
                "synthetic": True,
                "from_asset": "KES",
                "to_asset": "USDT",
                "rate": str(rate),
            },
        )

    return conversion
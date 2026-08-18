import logging
from datetime import timedelta
import random
import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Position, MarketTick

from .models import AuditEvent, DemoWallet, MarketTick, Position, SyntheticPayment, MarketCandle

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
    latest = (
        MarketTick.objects
        .filter(symbol="BTCUSDT")
        .first()
    )

    base = latest.price if latest else Decimal("5")

    movement = Decimal(
        str(random.uniform(-0.0013, 0.0013))
    )

    price = (
        base * (Decimal("1") + movement)
    ).quantize(
        Decimal("0.00000001")
    )

    tick = MarketTick.objects.create(
        symbol="BTCUSDT",
        price=price,
    )

    update_market_candle(tick)

    return tick


def update_market_candle(tick):
    """
    Add a MarketTick to its corresponding 1-minute candle.

    The candle is created when the first tick arrives.
    Subsequent ticks update high, low and close.
    """

    bucket_start = tick.created_at.replace(
        second=0,
        microsecond=0,
    )

    candle, created = MarketCandle.objects.get_or_create(
        symbol=tick.symbol,
        timeframe="1m",
        bucket_start=bucket_start,
        defaults={
            "open": tick.price,
            "high": tick.price,
            "low": tick.price,
            "close": tick.price,
            "tick_count": 1,
        },
    )

    if not created:
        candle.high = max(candle.high, tick.price)
        candle.low = min(candle.low, tick.price)
        candle.close = tick.price
        candle.tick_count += 1
        candle.save(
            update_fields=[
                "high",
                "low",
                "close",
                "tick_count",
                "updated_at",
            ]
        )

    return candle

def get_latest_market_tick(symbol="BTCUSDT"):
    """
    Return the most recent persisted market tick.

    This is the single source of truth for:
    - chart updates
    - opening trades
    - closing trades
    """

    return (
        MarketTick.objects
        .filter(symbol=symbol)
        .order_by("-created_at", "-id")
        .first()
    )


def get_latest_market_price(symbol="BTCUSDT"):
    """
    Return the latest persisted market price.
    """

    tick = get_latest_market_tick(symbol)

    if tick is None:
        raise ValueError(
            f"No market tick available for {symbol}"
        )

    return tick.price



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

def get_latest_market_tick(symbol="BTCUSDT"):
    """
    Single server-authoritative source for the latest market price.
    """

    return (
        MarketTick.objects
        .filter(symbol=symbol)
        .order_by("-created_at", "-id")
        .first()
    )


@transaction.atomic
def open_position(
    user,
    quantity,
    side,
    symbol="BTCUSDT"
):
    """
    Open a position using the latest persisted MarketTick.

    The browser NEVER supplies the entry price.
    """

    quantity = Decimal(str(quantity))

    side = side.upper()

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    if side not in ("LONG", "SHORT"):
        raise ValueError("Invalid trade side.")

    # Prevent multiple simultaneous open positions
    existing = (
        Position.objects
        .select_for_update()
        .filter(
            user=user,
            status="OPEN"
        )
        .first()
    )

    if existing:
        raise ValueError(
            "You already have an open position."
        )

    # SERVER AUTHORITATIVE PRICE
    tick = get_latest_market_tick(symbol)

    if tick is None:
        raise ValueError(
            f"No market price available for {symbol}."
        )

    position = Position.objects.create(
        user=user,
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=tick.price,
        status="OPEN"
    )

    return position, tick


@transaction.atomic
def close_position(
    user,
    symbol="BTCUSDT"
):
    """
    Close the user's active position using
    the latest persisted MarketTick.

    The browser NEVER supplies the exit price.
    """

    position = (
        Position.objects
        .select_for_update()
        .filter(
            user=user,
            symbol=symbol,
            status="OPEN"
        )
        .first()
    )

    if position is None:
        raise ValueError(
            "No open position found."
        )

    # SERVER AUTHORITATIVE EXIT PRICE
    tick = get_latest_market_tick(symbol)

    if tick is None:
        raise ValueError(
            f"No market price available for {symbol}."
        )

    position.exit_price = tick.price
    position.closed_at = tick.created_at
    position.status = "CLOSED"

    position.save(
        update_fields=[
            "exit_price",
            "closed_at",
            "status",
        ]
    )

    return position, tick
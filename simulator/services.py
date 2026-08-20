import logging
import hashlib
import json
import re
from datetime import timedelta
import random
import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db import IntegrityError
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from .models import  MarketTick

from .models import AuditEvent, Wallet, MarketTick, MarketCandle, WalletTransaction, IdempotencyRequest

logger = logging.getLogger("fraudlab")

IDEMPOTENCY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{16,64}$"
)


class IdempotencyError(Exception):
    pass


class IdempotencyConflict(IdempotencyError):
    pass


def validate_idempotency_key(key):

    if not key:
        raise IdempotencyError(
            "Idempotency-Key header is required."
        )

    if not isinstance(key, str):
        raise IdempotencyError(
            "Invalid idempotency key."
        )

    key = key.strip()

    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise IdempotencyError(
            "Invalid idempotency key format."
        )

    return key

def create_request_hash(payload):
    """
    Creates a deterministic SHA-256 hash of the
    financial request payload.
    """

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def get_existing_request(
    user,
    operation,
    key,
):

    return (
        IdempotencyRequest.objects
        .select_related("transaction")
        .filter(
            user=user,
            operation=operation,
            key=key,
        )
        .first()
    )

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
    str(
        random.gauss(0, 0.0001)
        + random.uniform(-0.0003, 0.0004)
    )
    )

    price = (
        base * (Decimal("1") + movement)
    ).quantize(
        Decimal("0.00001")
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


def withdraw_au(
    user,
    au_amount,
    idempotency_key,
):

    au_amount = Decimal(
        str(au_amount)
    )

    if au_amount <= Decimal("0"):

        raise ValueError(
            "Withdrawal amount must be greater than zero."
        )

    request_payload = {
        "au_amount": str(au_amount),
    }

    request_hash = create_request_hash(
        request_payload
    )

    # ----------------------------------------------
    # Existing request?
    # ----------------------------------------------

    existing = get_existing_request(
        user=user,
        operation="WITHDRAWAL",
        key=idempotency_key,
    )

    if existing:

        if existing.request_hash != request_hash:

            raise ValueError(
                "This idempotency key was already "
                "used with different request data."
            )

        if existing.transaction:

            return existing.transaction

        raise ValueError(
            "This request is currently being processed."
        )

    # ----------------------------------------------
    # Server-authoritative price
    # ----------------------------------------------

    price = get_latest_market_price()

    ksh_amount = (
        au_amount * price
    ).quantize(
        Decimal("0.01")
    )

    transaction_id = uuid.uuid4().hex.upper()

    # ----------------------------------------------
    # Atomic operation
    # ----------------------------------------------

    with transaction.atomic():

        try:

            idempotency = (
                IdempotencyRequest.objects
                .create(
                    user=user,
                    operation="WITHDRAWAL",
                    key=idempotency_key,
                    request_hash=request_hash,
                )
            )

        except IntegrityError:

            existing = (
                IdempotencyRequest.objects
                .select_related("transaction")
                .get(
                    user=user,
                    operation="WITHDRAWAL",
                    key=idempotency_key,
                )
            )

            if existing.request_hash != request_hash:

                raise ValueError(
                    "This idempotency key was already "
                    "used with different request data."
                )

            if existing.transaction:

                return existing.transaction

            raise ValueError(
                "This request is currently being processed."
            )

        # ------------------------------------------
        # Lock wallet
        # ------------------------------------------

        wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=user)
        )

        # ------------------------------------------
        # Balance validation
        # ------------------------------------------

        if wallet.au_balance < au_amount:

            raise ValueError(
                "Insufficient AU balance."
            )

        # ------------------------------------------
        # Debit wallet
        # ------------------------------------------

        wallet.au_balance -= au_amount

        wallet.save(
            update_fields=[
                "au_balance",
                "updated_at",
            ]
        )

        # ------------------------------------------
        # Create withdrawal transaction
        # ------------------------------------------

        ledger = WalletTransaction.objects.create(
            transaction_id=transaction_id,

            user=user,

            transaction_type="WITHDRAWAL",

            status="COMPLETED",

            au_amount=au_amount,

            ksh_amount=ksh_amount,

            price_per_au=price,

            reference=(
                f"MPESA-PAYOUT-"
                f"{uuid.uuid4().hex[:12].upper()}"
            ),
        )

        # ------------------------------------------
        # Link idempotency record
        # ------------------------------------------

        idempotency.transaction = ledger

        idempotency.save(
            update_fields=[
                "transaction",
            ]
        )

    return ledger




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



def purchase_au(
    user,
    ksh_amount,
    idempotency_key,
):

    ksh_amount = Decimal(str(ksh_amount))

    if ksh_amount <= Decimal("0"):
        raise ValueError(
            "Purchase amount must be greater than zero."
        )

    request_payload = {
        "amount": str(ksh_amount),
    }

    request_hash = create_request_hash(
        request_payload
    )

    # --------------------------------------------------
    # Check whether this request was already processed
    # --------------------------------------------------

    existing = get_existing_request(
        user=user,
        operation="PURCHASE",
        key=idempotency_key,
    )

    if existing:

        if existing.request_hash != request_hash:

            raise ValueError(
                "This idempotency key was already used "
                "with different request data."
            )

        if existing.transaction:

            return existing.transaction

        raise ValueError(
            "This request is currently being processed."
        )

    # --------------------------------------------------
    # Obtain server-authoritative market price
    # --------------------------------------------------

    price = get_latest_market_price()

    au_amount = (
        ksh_amount / price
    ).quantize(
        Decimal("0.00000001")
    )

    transaction_id = uuid.uuid4().hex.upper()

    # --------------------------------------------------
    # Atomic financial operation
    # --------------------------------------------------

    with transaction.atomic():

        try:

            idempotency = (
                IdempotencyRequest.objects
                .create(
                    user=user,
                    operation="PURCHASE",
                    key=idempotency_key,
                    request_hash=request_hash,
                )
            )

        except IntegrityError:

            # Another request with this key won
            # the race condition.

            existing = (
                IdempotencyRequest.objects
                .select_related("transaction")
                .get(
                    user=user,
                    operation="PURCHASE",
                    key=idempotency_key,
                )
            )

            if existing.request_hash != request_hash:

                raise ValueError(
                    "This idempotency key was already "
                    "used with different request data."
                )

            if existing.transaction:

                return existing.transaction

            raise ValueError(
                "This request is currently being processed."
            )

        # ----------------------------------------------
        # Lock the wallet
        # ----------------------------------------------

        wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=user)
        )

        # ----------------------------------------------
        # Create financial transaction
        # ----------------------------------------------

        ledger = WalletTransaction.objects.create(
            transaction_id=transaction_id,

            user=user,

            transaction_type="PURCHASE",

            status="COMPLETED",

            au_amount=au_amount,

            ksh_amount=ksh_amount,

            price_per_au=price,

            reference=(
                f"MPESA-"
                f"{uuid.uuid4().hex[:12].upper()}"
            ),
        )

        # ----------------------------------------------
        # Credit wallet
        # ----------------------------------------------

        wallet.au_balance += au_amount

        wallet.save(
            update_fields=[
                "au_balance",
                "updated_at",
            ]
        )

        # ----------------------------------------------
        # Link request to transaction
        # ----------------------------------------------

        idempotency.transaction = ledger

        idempotency.save(
            update_fields=[
                "transaction",
            ]
        )

    return ledger
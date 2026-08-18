from decimal import Decimal
from django.contrib.auth.models import User
from django.db import models


class DemoProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=120)
    risk_score = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.display_name


class DemoWallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallets")
    asset = models.CharField(max_length=20, default="USDT")
    balance = models.DecimalField(max_digits=24, decimal_places=8, default=Decimal("0"))
    address = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return f"{self.address} / {self.asset}"




class MarketTick(models.Model):
    symbol = models.CharField(max_length=20, default="BTCUSDT")
    price = models.DecimalField(max_digits=24, decimal_places=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MarketCandle(models.Model):
    symbol = models.CharField(max_length=20, default="BTCUSDT")
    timeframe = models.CharField(max_length=10, default="1m")

    bucket_start = models.DateTimeField()

    open = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    high = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    low = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    close = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    tick_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-bucket_start"]

        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "timeframe", "bucket_start"],
                name="unique_market_candle_bucket",
            )
        ]

        indexes = [
            models.Index(
                fields=["symbol", "timeframe", "bucket_start"]
            ),
        ]

    def __str__(self):
        return f"{self.symbol} {self.timeframe} {self.bucket_start}"

class Position(models.Model):
    SIDE_CHOICES = [
        ("LONG", "LONG"),
        ("SHORT", "SHORT"),
    ]

    STATUS_CHOICES = [
        ("OPEN", "OPEN"),
        ("CLOSED", "CLOSED"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    symbol = models.CharField(
        max_length=20,
        default="BTCUSDT"
    )

    side = models.CharField(
        max_length=5,
        choices=SIDE_CHOICES,
        default="LONG"
    )

    quantity = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    entry_price = models.DecimalField(
        max_digits=24,
        decimal_places=8
    )

    exit_price = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        null=True,
        blank=True
    )

    opened_at = models.DateTimeField(
        auto_now_add=True
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPEN"
    )

    @property
    def unrealized_pnl(self):
        """
        Calculate current P&L using the latest persisted MarketTick.
        """

        if self.status != "OPEN":
            return Decimal("0")

        latest = (
            MarketTick.objects
            .filter(symbol=self.symbol)
            .order_by("-created_at", "-id")
            .first()
        )

        if not latest:
            return Decimal("0")

        delta = latest.price - self.entry_price

        if self.side == "SHORT":
            delta = -delta

        return delta * self.quantity

    @property
    def realized_pnl(self):
        """
        Calculate P&L after the position has been closed.
        """

        if (
            self.status != "CLOSED"
            or self.exit_price is None
        ):
            return Decimal("0")

        delta = self.exit_price - self.entry_price

        if self.side == "SHORT":
            delta = -delta

        return delta * self.quantity

    @property
    def current_price(self):
        """
        Return the latest server-side market price.
        """

        latest = (
            MarketTick.objects
            .filter(symbol=self.symbol)
            .order_by("-created_at", "-id")
            .first()
        )

        return latest.price if latest else None

    @property
    def current_value(self):
        """
        Current notional value of the position.
        """

        price = self.current_price

        if price is None:
            return Decimal("0")

        return price * self.quantity


    
class SyntheticPayment(models.Model):
    PROVIDERS = [
        ("MPESA", "Synthetic M-Pesa"),
        ("BINANCE", "Synthetic Binance"),
    ]
    DIRECTIONS = [("DEPOSIT", "Deposit"), ("WITHDRAWAL", "Withdrawal")]
    STATUSES = [("PENDING", "Pending"), ("COMPLETED", "Completed"), ("BLOCKED", "Blocked")]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    direction = models.CharField(max_length=20, choices=DIRECTIONS)
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    asset = models.CharField(max_length=20, default="KES")
    reference = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=STATUSES, default="COMPLETED")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SyntheticConversion(models.Model):
    FROM_CHOICES = [
        ("KES", "KES"),
        ("USDT", "USDT"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    from_asset = models.CharField(max_length=20, choices=FROM_CHOICES)
    to_asset = models.CharField(max_length=20, choices=FROM_CHOICES)
    from_amount = models.DecimalField(max_digits=24, decimal_places=8)
    to_amount = models.DecimalField(max_digits=24, decimal_places=8)
    rate = models.DecimalField(max_digits=24, decimal_places=8)
    reference = models.CharField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AuditEvent(models.Model):
    SEVERITIES = [("INFO", "Info"), ("WARN", "Warning"), ("HIGH", "High")]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=80)
    severity = models.CharField(max_length=10, choices=SEVERITIES, default="INFO")
    message = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

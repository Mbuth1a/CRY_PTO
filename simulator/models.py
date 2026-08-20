from decimal import Decimal
from django.contrib.auth.models import User
from django.db import models


class DemoProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=120)
    risk_score = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.display_name


class Wallet(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="wallet",
    )

    au_balance = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        default=Decimal("0"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} Wallet"


class WalletTransaction(models.Model):

    TYPE_CHOICES = [
        ("PURCHASE", "Purchase"),
        ("WITHDRAWAL", "Withdrawal"),
        ("REFUND", "Refund"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    transaction_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="wallet_transactions",
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    au_amount = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        default=Decimal("0"),
    )

    ksh_amount = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        default=Decimal("0"),
    )

    price_per_au = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        default=Decimal("0"),
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id


class IdempotencyRequest(models.Model):

    OPERATION_CHOICES = [
        ("PURCHASE", "Purchase"),
        ("WITHDRAWAL", "Withdrawal"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="idempotency_requests",
    )

    key = models.CharField(
        max_length=64,
    )

    operation = models.CharField(
        max_length=20,
        choices=OPERATION_CHOICES,
    )

    request_hash = models.CharField(
        max_length=64,
    )

    transaction = models.OneToOneField(
        "WalletTransaction",
        on_delete=models.PROTECT,
        related_name="idempotency_request",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "operation",
                    "key",
                ],
                name="unique_user_operation_idempotency_key",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "operation",
                    "key",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.operation} - "
            f"{self.key}"
        )


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

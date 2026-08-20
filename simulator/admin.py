from django.contrib import admin
from .models import AuditEvent, DemoProfile, Wallet, MarketTick, Wallet, WalletTransaction, IdempotencyRequest

admin.site.register(DemoProfile)
admin.site.register(MarketTick)
admin.site.register(AuditEvent)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "au_balance",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__username",
        "user__email",
    )


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "user",
        "transaction_type",
        "au_amount",
        "ksh_amount",
        "price_per_au",
        "status",
        "created_at",
    )

    search_fields = (
        "transaction_id",
        "user__username",
        "reference",
    )

    list_filter = (
        "transaction_type",
        "status",
    )

@admin.register(IdempotencyRequest)
class IdempotencyRequestAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "operation",
        "key",
        "transaction",
        "created_at",
    )

    search_fields = (
        "user__username",
        "key",
        "transaction__transaction_id",
    )

    list_filter = (
        "operation",
        "created_at",
    )

    readonly_fields = (
        "user",
        "operation",
        "key",
        "request_hash",
        "transaction",
        "created_at",
    )
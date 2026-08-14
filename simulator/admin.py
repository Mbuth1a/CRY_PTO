from django.contrib import admin
from .models import AuditEvent, DemoProfile, DemoWallet, MarketTick, Position, SyntheticPayment

admin.site.register(DemoProfile)
admin.site.register(DemoWallet)
admin.site.register(MarketTick)
admin.site.register(Position)
admin.site.register(SyntheticPayment)
admin.site.register(AuditEvent)

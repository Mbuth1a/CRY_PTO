from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import AuditEvent, DemoWallet, MarketTick, Position, SyntheticPayment
from .services import (
    audit,
    generate_market_tick,
    open_position,
    synthetic_deposit,
    synthetic_withdrawal,
    synthetic_convert_kes_to_usdt,
)

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "login.html")


@require_POST
def login_view(request):
    username = request.POST.get("username", "")
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)

    if user is None:
        audit("LOGIN_FAILURE", f"Failed synthetic login for username={username}", severity="WARN")
        return render(request, "login.html", {"error": "Invalid demo credentials."})

    login(request, user)
    audit("LOGIN_SUCCESS", "Synthetic demo login", user=user)
    return redirect("dashboard")


def logout_view(request):
    if request.user.is_authenticated:
        audit("LOGOUT", "Synthetic demo logout", user=request.user)
    logout(request)
    return redirect("home")


@login_required
def dashboard(request):
    wallet = DemoWallet.objects.filter(user=request.user, asset="USDT").first()
    latest = MarketTick.objects.filter(symbol="BTCUSDT").first()
    positions = Position.objects.filter(user=request.user, status="OPEN")
    payments = SyntheticPayment.objects.filter(user=request.user)[:10]
    return render(request, "dashboard.html", {
        "wallet": wallet,
        "latest": latest,
        "positions": positions,
        "payments": payments,
    })


@login_required
@require_GET
def market_api(request):
    tick = generate_market_tick()
    history = list(
        MarketTick.objects.filter(symbol="BTCUSDT")
        .order_by("-created_at")
        .values("price", "created_at")[:30]
    )
    history.reverse()

    return JsonResponse({
        "synthetic": True,
        "symbol": tick.symbol,
        "price": str(tick.price),
        "history": [
            {"price": str(x["price"]), "time": x["created_at"].isoformat()}
            for x in history
        ],
    })


@login_required
@require_POST
def deposit_api(request):
    provider = request.POST.get("provider", "MPESA").upper()
    asset = "KES" if provider == "MPESA" else "USDT"

    try:
        amount = Decimal(request.POST.get("amount", "0"))
        payment = synthetic_deposit(request.user, provider, amount, asset)
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "synthetic": True,
        "reference": payment.reference,
        "provider": payment.provider,
        "amount": str(payment.amount),
        "asset": payment.asset,
    })


@login_required
@require_POST
def withdrawal_api(request):
    provider = request.POST.get("provider", "MPESA").upper()
    asset = "KES" if provider == "MPESA" else "USDT"

    try:
        amount = Decimal(request.POST.get("amount", "0"))
        payment = synthetic_withdrawal(request.user, provider, amount, asset)
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "synthetic": True,
        "reference": payment.reference,
        "provider": payment.provider,
        "amount": str(payment.amount),
        "asset": payment.asset,
    })

@login_required
@require_POST
def convert_api(request):
    try:
        amount = Decimal(
            request.POST.get("amount", "0")
        )

        conversion = synthetic_convert_kes_to_usdt(
            request.user,
            amount
        )

    except (InvalidOperation, ValueError) as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400
        )

    return JsonResponse({
        "synthetic": True,
        "reference": conversion.reference,
        "from_asset": conversion.from_asset,
        "to_asset": conversion.to_asset,
        "from_amount": str(conversion.from_amount),
        "to_amount": str(conversion.to_amount),
        "rate": str(conversion.rate),
    })
@login_required
@require_POST
def position_api(request):
    try:
        quantity = Decimal(request.POST.get("quantity", "0"))
        side = request.POST.get("side", "LONG").upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError("Invalid side.")
        position = open_position(request.user, quantity, side)
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "synthetic": True,
        "id": position.id,
        "side": position.side,
        "quantity": str(position.quantity),
        "entry_price": str(position.entry_price),
    })


@login_required
@require_GET
def events_api(request):
    events = AuditEvent.objects.filter(user=request.user)[:50]
    return JsonResponse({
        "events": [
            {
                "type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "time": e.created_at.isoformat(),
            }
            for e in events
        ]
    })

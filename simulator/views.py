from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import AuditEvent, DemoWallet, MarketTick, Position, SyntheticPayment, MarketCandle
from .services import (
    audit,
    generate_market_tick,
    open_position,
    synthetic_deposit,
    synthetic_withdrawal,
    synthetic_convert_kes_to_usdt,
)
from .services import (
    open_position, close_position, get_latest_market_tick,)
def market_candles(request):
    symbol = request.GET.get("symbol", "BTCUSDT")
    limit = min(
        int(request.GET.get("limit", 500)),
        5000,
    )

    candles = (
        MarketCandle.objects
        .filter(
            symbol=symbol,
            timeframe="1m",
        )
        .order_by("-bucket_start")[:limit]
    )

    candles = reversed(list(candles))

    data = [
        {
            "time": candle.bucket_start.isoformat(),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "tick_count": candle.tick_count,
        }
        for candle in candles
    ]

    return JsonResponse({
        "symbol": symbol,
        "timeframe": "1m",
        "data": data,
    })

def market_history(request):
    symbol = request.GET.get("symbol", "BTCUSDT")
    limit = int(request.GET.get("limit", 500))

    ticks = (
        MarketTick.objects
        .filter(symbol=symbol)
        .order_by("-created_at")[:limit]
    )

    data = [
        {
            "time": tick.created_at.isoformat(),
            "price": float(tick.price),
        }
        for tick in reversed(ticks)
    ]

    return JsonResponse({
        "symbol": symbol,
        "data": data,
    })
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
@require_http_methods(["GET", "POST", "DELETE"])
def position_api(request):

    # ==================================================
    # GET CURRENT POSITION
    # ==================================================

    if request.method == "GET":

        position = (
            Position.objects
            .filter(
                user=request.user,
                status="OPEN"
            )
            .first()
        )

        if position is None:
            return JsonResponse({
                "open": False,
                "position": None,
            })

        tick = get_latest_market_tick(
            position.symbol
        )

        current_price = (
            tick.price
            if tick
            else position.entry_price
        )

        delta = (
            current_price -
            position.entry_price
        )

        if position.side == "SHORT":
            delta = -delta

        pnl = delta * position.quantity

        pnl_percent = Decimal("0")

        if position.entry_price > 0:
            pnl_percent = (
                pnl /
                (
                    position.entry_price *
                    position.quantity
                )
            ) * Decimal("100")

        return JsonResponse({
            "open": True,

            "position": {
                "id": position.id,
                "symbol": position.symbol,
                "side": position.side,
                "quantity": str(position.quantity),

                "entry_price": str(
                    position.entry_price
                ),

                "current_price": str(
                    current_price
                ),

                "current_value": str(
                    current_price *
                    position.quantity
                ),

                "unrealized_pnl": str(
                    pnl
                ),

                "pnl_percent": str(
                    pnl_percent
                ),

                "opened_at": (
                    position.opened_at.isoformat()
                ),
            }
        })

    # ==================================================
    # OPEN POSITION
    # ==================================================

    if request.method == "POST":

        try:

            quantity = Decimal(
                request.POST.get(
                    "quantity",
                    "0"
                )
            )

            side = request.POST.get(
                "side",
                "LONG"
            ).upper()

            position, tick = open_position(
                user=request.user,
                quantity=quantity,
                side=side,
                symbol="BTCUSDT"
            )

        except (
            InvalidOperation,
            ValueError
        ) as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400
            )

        return JsonResponse({
            "success": True,
            "open": True,

            "position": {
                "id": position.id,
                "symbol": position.symbol,
                "side": position.side,
                "quantity": str(position.quantity),

                # SERVER PRICE
                "entry_price": str(
                    tick.price
                ),

                "opened_at": (
                    position.opened_at.isoformat()
                ),
            }
        })

    # ==================================================
    # CLOSE POSITION
    # ==================================================

    if request.method == "DELETE":

        try:

            position, tick = close_position(
                user=request.user,
                symbol="BTCUSDT"
            )

        except ValueError as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400
            )

        return JsonResponse({
            "success": True,
            "open": False,

            "position": {
                "id": position.id,
                "symbol": position.symbol,
                "side": position.side,
                "quantity": str(position.quantity),

                "entry_price": str(
                    position.entry_price
                ),

                # SERVER PRICE
                "exit_price": str(
                    position.exit_price
                ),

                "realized_pnl": str(
                    position.realized_pnl
                ),

                "closed_at": (
                    position.closed_at.isoformat()
                ),
            }
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

from decimal import Decimal, InvalidOperation
import json
import uuid
import hashlib
from django.db import transaction
from django.db import IntegrityError
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect
from .models import AuditEvent, Wallet, MarketTick, MarketCandle, WalletTransaction, IdempotencyRequest 
from .services import (
    audit,
    generate_market_tick,
    purchase_au,
    get_latest_market_price,
    withdraw_au,
    validate_idempotency_key,
    IdempotencyError,

)
from .services import (get_latest_market_price)

def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()

            # Automatically log the user in.
            login(request, user)

            return redirect("dashboard")

    else:
        form = UserCreationForm()

    return render(
        request,
        "register.html",
        {
            "form": form,
        },
    )
@login_required
@require_POST
def purchase_au(request):

    # ---------------------------------------------------------
    # 1. READ IDEMPOTENCY KEY
    # ---------------------------------------------------------

    idempotency_key = request.headers.get(
        "Idempotency-Key"
    )

    if not idempotency_key:
        return JsonResponse(
            {
                "success": False,
                "error": "Missing Idempotency-Key."
            },
            status=400,
        )

    idempotency_key = idempotency_key.strip()

    if not idempotency_key:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid Idempotency-Key."
            },
            status=400,
        )

    if len(idempotency_key) > 64:
        return JsonResponse(
            {
                "success": False,
                "error": "Idempotency-Key is too long."
            },
            status=400,
        )

    # ---------------------------------------------------------
    # 2. READ REQUEST
    # ---------------------------------------------------------

    amount_raw = request.POST.get("amount")

    if not amount_raw:
        return JsonResponse(
            {
                "success": False,
                "error": "Purchase amount is required."
            },
            status=400,
        )

    try:
        ksh_amount = Decimal(amount_raw)

    except InvalidOperation:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid purchase amount."
            },
            status=400,
        )

    if ksh_amount <= Decimal("0"):
        return JsonResponse(
            {
                "success": False,
                "error": "Purchase amount must be greater than zero."
            },
            status=400,
        )

    ksh_amount = ksh_amount.quantize(
        Decimal("0.01")
    )

    # ---------------------------------------------------------
    # 3. CREATE REQUEST HASH
    # ---------------------------------------------------------

    request_payload = {
        "amount": str(ksh_amount),
    }

    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    # ---------------------------------------------------------
    # 4. IDEMPOTENCY CHECK
    # ---------------------------------------------------------

    existing = (
        IdempotencyRequest.objects
        .select_related("transaction")
        .filter(
            user=request.user,
            operation="PURCHASE",
            key=idempotency_key,
        )
        .first()
    )

    if existing:

        # Same key + different request = reject.
        if existing.request_hash != request_hash:

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "This Idempotency-Key has already "
                        "been used with different request data."
                    ),
                },
                status=409,
            )

        # Same request being retried.
        if existing.transaction:

            tx = existing.transaction

            return JsonResponse(
                {
                    "success": True,
                    "idempotent_replay": True,

                    "execution_price": str(
                        tx.price_per_au
                    ),

                    "au_credited": str(
                        tx.au_amount
                    ),

                    "amount_paid": str(
                        tx.ksh_amount
                    ),

                    "payment_verified": (
                        tx.status == "COMPLETED"
                    ),

                    "transaction_reference": (
                        tx.transaction_id
                    ),

                    "wallet_balance": str(
                        request.user.wallet.au_balance
                    ),
                }
            )

    # ---------------------------------------------------------
    # 5. PROCESS PURCHASE ATOMICALLY
    # ---------------------------------------------------------

    try:

        with transaction.atomic():

            # Lock wallet so two purchases cannot
            # modify it simultaneously.

            wallet = (
                Wallet.objects
                .select_for_update()
                .get(user=request.user)
            )

            # -------------------------------------------------
            # AUTHORITATIVE MARKET PRICE
            # -------------------------------------------------

            execution_price = get_latest_market_price(
                "BTCUSDT"
            )

            execution_price = Decimal(
                execution_price
            )

            if execution_price <= Decimal("0"):
                raise ValueError(
                    "Invalid market price."
                )

            # -------------------------------------------------
            # SIMULATED M-PESA VERIFICATION
            # -------------------------------------------------

            payment_verified = True

            if not payment_verified:
                raise ValueError(
                    "M-Pesa payment could not be verified."
                )

            # -------------------------------------------------
            # CALCULATE AU
            # -------------------------------------------------

            au_amount = (
                ksh_amount / execution_price
            ).quantize(
                Decimal("0.00000001")
            )

            if au_amount <= Decimal("0"):
                raise ValueError(
                    "Calculated AU amount is invalid."
                )

            # -------------------------------------------------
            # TRANSACTION ID
            # -------------------------------------------------

            transaction_id = (
                f"AU-{uuid.uuid4().hex.upper()}"
            )

            # -------------------------------------------------
            # CREDIT WALLET
            # -------------------------------------------------

            wallet.au_balance += au_amount

            wallet.save(
                update_fields=[
                    "au_balance",
                    "updated_at",
                ]
            )

            # -------------------------------------------------
            # CREATE LEDGER TRANSACTION
            # -------------------------------------------------

            wallet_transaction = (
                WalletTransaction.objects.create(
                    transaction_id=transaction_id,

                    user=request.user,

                    transaction_type="PURCHASE",

                    status="COMPLETED",

                    au_amount=au_amount,

                    ksh_amount=ksh_amount,

                    price_per_au=execution_price,

                    reference=(
                        f"MPESA-{uuid.uuid4().hex[:12].upper()}"
                    ),
                )
            )

            # -------------------------------------------------
            # CREATE IDEMPOTENCY RECORD
            # -------------------------------------------------

            IdempotencyRequest.objects.create(
                user=request.user,

                operation="PURCHASE",

                key=idempotency_key,

                request_hash=request_hash,

                transaction=wallet_transaction,
            )

        # -----------------------------------------------------
        # 6. SUCCESS RESPONSE
        # -----------------------------------------------------

        return JsonResponse(
            {
                "success": True,

                "idempotent_replay": False,

                "execution_price": str(
                    execution_price
                ),

                "au_credited": str(
                    au_amount
                ),

                "amount_paid": str(
                    ksh_amount
                ),

                "payment_verified": True,

                "transaction_reference": (
                    wallet_transaction.transaction_id
                ),

                "payment_reference": (
                    wallet_transaction.reference
                ),

                "wallet_balance": str(
                    wallet.au_balance
                ),
            }
        )

    except Wallet.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Wallet not found."
            },
            status=400,
        )

    except IntegrityError:

        # Another request with the same key may have
        # committed first.

        existing = (
            IdempotencyRequest.objects
            .select_related("transaction")
            .filter(
                user=request.user,
                operation="PURCHASE",
                key=idempotency_key,
            )
            .first()
        )

        if existing and existing.transaction:

            tx = existing.transaction

            return JsonResponse(
                {
                    "success": True,
                    "idempotent_replay": True,

                    "execution_price": str(
                        tx.price_per_au
                    ),

                    "au_credited": str(
                        tx.au_amount
                    ),

                    "amount_paid": str(
                        tx.ksh_amount
                    ),

                    "payment_verified": (
                        tx.status == "COMPLETED"
                    ),

                    "transaction_reference": (
                        tx.transaction_id
                    ),

                    "wallet_balance": str(
                        request.user.wallet.au_balance
                    ),
                }
            )

        return JsonResponse(
            {
                "success": False,
                "error": "Purchase could not be completed."
            },
            status=409,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=400,
        )

@login_required
def portfolio_api(request):

    wallet = request.user.wallet

    price = get_latest_market_price()

    au_balance = wallet.au_balance

    current_value = (
        au_balance * price
    ).quantize(
        Decimal("0.01")
    )

    purchases = WalletTransaction.objects.filter(
        user=request.user,
        transaction_type="PURCHASE",
        status="COMPLETED",
    )

    invested = sum(
        (
            tx.ksh_amount
            for tx in purchases
        ),
        Decimal("0"),
    )

    gain_loss = (
        current_value - invested
    )

    if invested > 0:

        gain_loss_percent = (
            gain_loss / invested
        ) * Decimal("100")

    else:

        gain_loss_percent = Decimal("0")

    return JsonResponse(
        {
            "au_balance": format(
                au_balance,
                ".2f"
            ),

            "price": str(price),

            "current_value": str(
                current_value
            ),

            "invested": str(
                invested
            ),

            "gain_loss": str(
                gain_loss.quantize(
                    Decimal("0.01")
                )
            ),

            "gain_loss_percent": str(
                gain_loss_percent.quantize(
                    Decimal("0.01")
                )
            ),
        }
    )

@login_required
@require_POST
def withdrawal_api(request):

    raw_key = request.headers.get(
        "Idempotency-Key"
    )

    try:

        idempotency_key = (
            validate_idempotency_key(raw_key)
        )

    except IdempotencyError as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=400,
        )

    try:

        data = json.loads(
            request.body
        )

    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    au_amount = data.get(
        "au_amount"
    )

    if au_amount is None:

        return JsonResponse(
            {
                "success": False,
                "error": "AU amount is required.",
            },
            status=400,
        )

    try:

        ledger = withdraw_au(
            user=request.user,
            au_amount=au_amount,
            idempotency_key=idempotency_key,
        )

    except ValueError as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,

            "transaction_id":
                ledger.transaction_id,

            "au_amount":
                str(ledger.au_amount),

            "ksh_amount":
                str(ledger.ksh_amount),

            "price":
                str(ledger.price_per_au),

            "reference":
                ledger.reference,
        }
    )


@login_required
def withdrawal_estimate(request):
    latest_tick = (
        MarketTick.objects
        .filter(symbol="BTCUSDT")
        .order_by("-created_at", "-id")
        .first()
    )

    if not latest_tick:
        return JsonResponse({
            "price": "0.00",
            "payout": "0.00",
        })

    price = latest_tick.price

    amount = Decimal(
        request.GET.get("amount", "0")
    )

    payout = amount * price

    return JsonResponse({
        "price": str(price),
        "payout": str(
            payout.quantize(Decimal("0.01"))
        ),
    })
    
def register_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            return render(
                request,
                "register.html",
                {
                    "error": "Username and password are required."
                },
            )

        if User.objects.filter(username=username).exists():
            return render(
                request,
                "register.html",
                {
                    "error": "Username already exists."
                },
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        login(request, user)

        return redirect("dashboard")

    return render(request, "register.html")

def login_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:

            login(request, user)

            return redirect("dashboard")

        return render(
            request,
            "login.html",
            {
                "error": "Invalid username or password."
            },
        )

    return render(request, "login.html")


# @require_POST
# def login_view(request):
#     username = request.POST.get("username", "")
#     password = request.POST.get("password", "")
#     user = authenticate(request, username=username, password=password)

#     if user is None:
#         audit("LOGIN_FAILURE", f"Failed synthetic login for username={username}", severity="WARN")
#         return render(request, "login.html", {"error": "Invalid demo credentials."})

#     login(request, user)
#     audit("LOGIN_SUCCESS", "Synthetic demo login", user=user)
#     return redirect("dashboard")


@require_POST
def logout_view(request):

    logout(request)

    return redirect("login")

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


@login_required
def dashboard(request):

    wallet, created = Wallet.objects.get_or_create(
        user=request.user)

    return render(
        request,
        "dashboard.html",
        {
            "wallet": wallet,
        },
    )




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


@login_required
def transaction_history_api(request):

    transactions = (
        WalletTransaction.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    history = []

    for tx in transactions:
        history.append({
            "date": tx.created_at.strftime("%d %b %Y %H:%M"),
            "type": tx.get_transaction_type_display(),
            "amount": f"{tx.ksh_amount:.2f}",
            "au": f"{tx.au_amount:.8f}",
            "price": f"{tx.price_per_au:.8f}",
            "status": tx.status,
            "reference": tx.reference or tx.transaction_id,
        })

    return JsonResponse({
        "transactions": history
    })


def site_entry(request):

    if request.user.is_authenticated:
        logout(request)

    return redirect("login")

from decimal import Decimal, InvalidOperation
import json
import uuid
import hashlib
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db import IntegrityError
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from .models import AuditEvent, Wallet, MarketTick, MarketCandle, WalletTransaction, IdempotencyRequest 
from .services import (
    audit,
    generate_market_tick,
    purchase_au,
    get_latest_market_price,
    withdraw_au,
    validate_idempotency_key,
    IdempotencyError,
    get_mpesa_base_url,
    get_mpesa_access_token,
    normalize_phone,
    generate_password,
    initiate_daraja_stk_push,
    initiate_simulated_stk_push,
       
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
                "error": "Missing Idempotency-Key.",
            },
            status=400,
        )

    idempotency_key = idempotency_key.strip()

    if not idempotency_key:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid Idempotency-Key.",
            },
            status=400,
        )

    if len(idempotency_key) > 64:
        return JsonResponse(
            {
                "success": False,
                "error": "Idempotency-Key is too long.",
            },
            status=400,
        )

    # ---------------------------------------------------------
    # 2. READ PURCHASE DATA
    # ---------------------------------------------------------

    amount_raw = request.POST.get("amount")
    phone = request.POST.get("phone", "").strip()

    if not amount_raw:
        return JsonResponse(
            {
                "success": False,
                "error": "Purchase amount is required.",
            },
            status=400,
        )

    if not phone:
        return JsonResponse(
            {
                "success": False,
                "error": "M-PESA phone number is required.",
            },
            status=400,
        )

    try:
        ksh_amount = Decimal(amount_raw).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid purchase amount.",
            },
            status=400,
        )

    if ksh_amount <= Decimal("0"):
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Purchase amount must be greater than zero."
                ),
            },
            status=400,
        )

    # ---------------------------------------------------------
    # 3. REQUEST HASH
    # ---------------------------------------------------------

    request_payload = {
        "amount": str(ksh_amount),
        "phone": phone,
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

        if existing.transaction:

            tx = existing.transaction

            return JsonResponse(
                {
                    "success": True,
                    "idempotent_replay": True,
                    "payment_status": tx.status,
                    "execution_price": str(
                        tx.price_per_au
                    ),
                    "au_amount": str(
                        tx.au_amount
                    ),
                    "amount_paid": str(
                        tx.ksh_amount
                    ),
                    "transaction_reference": (
                        tx.transaction_id
                    ),
                    "checkout_request_id": (
                        tx.checkout_request_id
                    ),
                    "message": (
                        tx.result_description
                    ),
                }
            )

    # ---------------------------------------------------------
    # 5. CREATE PENDING TRANSACTION
    # ---------------------------------------------------------

    try:

        with transaction.atomic():

            execution_price = Decimal(
                get_latest_market_price("BTCUSDT")
            )

            if execution_price <= Decimal("0"):
                raise ValueError(
                    "Invalid market price."
                )

            transaction_id = (
                f"AU-{uuid.uuid4().hex.upper()}"
            )

            wallet_transaction = (
                WalletTransaction.objects.create(
                    transaction_id=transaction_id,

                    user=request.user,

                    transaction_type="PURCHASE",

                    status="PENDING",

                    au_amount=Decimal("0"),

                    ksh_amount=ksh_amount,

                    price_per_au=execution_price,

                    phone_number=phone,

                    reference=transaction_id,

                    result_description=(
                        "Simulated M-PESA payment "
                        "awaiting confirmation."
                    ),
                )
            )

            IdempotencyRequest.objects.create(
                user=request.user,

                operation="PURCHASE",

                key=idempotency_key,

                request_hash=request_hash,

                transaction=wallet_transaction,
            )

        # -----------------------------------------------------
        # 6. SIMULATED STK PUSH
        # -----------------------------------------------------

        mpesa_response = (
            initiate_simulated_stk_push(
                amount=ksh_amount,
                phone_number=phone,
                account_reference=transaction_id,
            )
        )

        if mpesa_response.get("ResponseCode") != "0":

            wallet_transaction.status = "FAILED"

            wallet_transaction.result_description = (
                mpesa_response.get(
                    "ResponseDescription",
                    "Simulated M-PESA payment failed.",
                )
            )

            wallet_transaction.save(
                update_fields=[
                    "status",
                    "result_description",
                ]
            )

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        wallet_transaction
                        .result_description
                    ),
                },
                status=400,
            )

        # -----------------------------------------------------
        # 7. SAVE SIMULATED CHECKOUT IDS
        # -----------------------------------------------------

        wallet_transaction.merchant_request_id = (
            mpesa_response.get(
                "MerchantRequestID",
                "",
            )
        )

        wallet_transaction.checkout_request_id = (
            mpesa_response.get(
                "CheckoutRequestID",
            )
        )

        wallet_transaction.result_description = (
            mpesa_response.get(
                "CustomerMessage",
                "Simulated STK Push sent.",
            )
        )

        wallet_transaction.save(
            update_fields=[
                "merchant_request_id",
                "checkout_request_id",
                "result_description",
            ]
        )

        # -----------------------------------------------------
        # 8. RETURN PENDING
        # -----------------------------------------------------

        return JsonResponse(
            {
                "success": True,

                "payment_status": "PENDING",

                "transaction_reference": (
                    wallet_transaction.transaction_id
                ),

                "checkout_request_id": (
                    wallet_transaction.checkout_request_id
                ),

                "execution_price": str(
                    execution_price
                ),

                "amount_paid": str(
                    ksh_amount
                ),

                "message": (
                    "SIMULATION: Payment request "
                    "created. Awaiting confirmation."
                ),
            }
        )

    except IntegrityError:

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
                    "payment_status": tx.status,
                    "transaction_reference": (
                        tx.transaction_id
                    ),
                    "checkout_request_id": (
                        tx.checkout_request_id
                    ),
                }
            )

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Purchase request could not "
                    "be created."
                ),
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
@require_POST
def simulate_mpesa_callback(
    request,
    transaction_id,
):
    """
    Simulates the callback that Safaricom would
    normally send after an STK payment.

    This endpoint is ONLY for local simulation.
    """

    try:

        wallet_transaction = (
            WalletTransaction.objects
            .select_related("user")
            .get(
                transaction_id=transaction_id,
                user=request.user,
            )
        )

    except WalletTransaction.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Transaction not found.",
            },
            status=404,
        )

    # ---------------------------------------------------------
    # PROCESS TRANSACTION ATOMICALLY
    # ---------------------------------------------------------

    with transaction.atomic():

        wallet_transaction = (
            WalletTransaction.objects
            .select_for_update()
            .select_related("user")
            .get(
                pk=wallet_transaction.pk
            )
        )

        # -----------------------------------------------------
        # ALREADY COMPLETED
        # -----------------------------------------------------

        if wallet_transaction.status == "COMPLETED":

            return JsonResponse(
                {
                    "success": True,
                    "status": "COMPLETED",
                    "message": (
                        "Transaction already completed."
                    ),
                }
            )

        # -----------------------------------------------------
        # ONLY PENDING TRANSACTIONS CAN BE COMPLETED
        # -----------------------------------------------------

        if wallet_transaction.status != "PENDING":

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Transaction is not pending."
                    ),
                    "status": (
                        wallet_transaction.status
                    ),
                },
                status=400,
            )

        # -----------------------------------------------------
        # SIMULATED PAYMENT VERIFICATION
        # -----------------------------------------------------

        simulated_amount = (
            wallet_transaction.ksh_amount
        )

        if (
            simulated_amount.quantize(
                Decimal("0.01")
            )
            != wallet_transaction.ksh_amount
        ):

            wallet_transaction.status = "FAILED"

            wallet_transaction.result_code = 1

            wallet_transaction.result_description = (
                "Simulated payment amount mismatch."
            )

            wallet_transaction.save(
                update_fields=[
                    "status",
                    "result_code",
                    "result_description",
                ]
            )

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Payment amount verification failed."
                    ),
                },
                status=400,
            )

        # -----------------------------------------------------
        # CALCULATE AU
        # -----------------------------------------------------

        if wallet_transaction.price_per_au <= 0:

            wallet_transaction.status = "FAILED"

            wallet_transaction.result_code = 1

            wallet_transaction.result_description = (
                "Invalid stored execution price."
            )

            wallet_transaction.save(
                update_fields=[
                    "status",
                    "result_code",
                    "result_description",
                ]
            )

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Invalid transaction price."
                    ),
                },
                status=400,
            )

        au_amount = (
            wallet_transaction.ksh_amount /
            wallet_transaction.price_per_au
        ).quantize(
            Decimal("0.00000001")
        )

        # -----------------------------------------------------
        # LOCK WALLET
        # -----------------------------------------------------

        wallet = (
            Wallet.objects
            .select_for_update()
            .get(
                user=wallet_transaction.user
            )
        )

        # -----------------------------------------------------
        # CREDIT AU
        # -----------------------------------------------------

        wallet.au_balance += au_amount

        wallet.save(
            update_fields=[
                "au_balance",
                "updated_at",
            ]
        )

        # -----------------------------------------------------
        # COMPLETE TRANSACTION
        # -----------------------------------------------------

        wallet_transaction.au_amount = (
            au_amount
        )

        wallet_transaction.status = (
            "COMPLETED"
        )

        wallet_transaction.result_code = 0

        wallet_transaction.result_description = (
            "SIMULATION: M-PESA payment confirmed."
        )

        wallet_transaction.mpesa_receipt_number = (
            f"SIM{uuid.uuid4().hex[:10].upper()}"
        )

        wallet_transaction.save(
            update_fields=[
                "au_amount",
                "status",
                "result_code",
                "result_description",
                "mpesa_receipt_number",
            ]
        )

    return JsonResponse(
        {
            "success": True,
            "status": "COMPLETED",
            "transaction_reference": (
                wallet_transaction.transaction_id
            ),
            "au_amount": str(
                wallet_transaction.au_amount
            ),
            "receipt": (
                wallet_transaction
                .mpesa_receipt_number
            ),
            "message": (
                "SIMULATION: Payment completed."
            ),
        }
    )

@csrf_exempt
@require_POST
def mpesa_callback(request):

    try:
        data = json.loads(request.body)

    except json.JSONDecodeError:

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Invalid JSON.",
            },
            status=400,
        )

    try:

        stk_callback = (
            data["Body"]["stkCallback"]
        )

        merchant_request_id = (
            stk_callback.get(
                "MerchantRequestID",
                "",
            )
        )

        checkout_request_id = (
            stk_callback.get(
                "CheckoutRequestID",
                "",
            )
        )

        result_code = int(
            stk_callback.get(
                "ResultCode",
                1,
            )
        )

        result_description = (
            stk_callback.get(
                "ResultDesc",
                "",
            )
        )

    except (KeyError, TypeError, ValueError):

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": (
                    "Invalid M-PESA callback structure."
                ),
            },
            status=400,
        )

    # ---------------------------------------------------------
    # FIND TRANSACTION
    # ---------------------------------------------------------

    wallet_transaction = (
        WalletTransaction.objects
        .filter(
            checkout_request_id=
                checkout_request_id
        )
        .first()
    )

    if not wallet_transaction:

        # Return 200 so M-PESA does not repeatedly
        # retry a callback we cannot associate.

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Accepted.",
            }
        )

    # ---------------------------------------------------------
    # IDEMPOTENT CALLBACK HANDLING
    # ---------------------------------------------------------

    if wallet_transaction.status == "COMPLETED":

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Already processed.",
            }
        )

    if wallet_transaction.status == "FAILED":

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Already processed.",
            }
        )

    # ---------------------------------------------------------
    # FAILED / CANCELLED M-PESA PAYMENT
    # ---------------------------------------------------------

    if result_code != 0:

        wallet_transaction.status = "FAILED"

        wallet_transaction.result_code = result_code

        wallet_transaction.result_description = (
            result_description
        )

        wallet_transaction.merchant_request_id = (
            merchant_request_id
        )

        wallet_transaction.save(
            update_fields=[
                "status",
                "result_code",
                "result_description",
                "merchant_request_id",
            ]
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback processed.",
            }
        )

    # ---------------------------------------------------------
    # SUCCESSFUL PAYMENT
    # ---------------------------------------------------------

    callback_metadata = (
        stk_callback.get(
            "CallbackMetadata",
            {}
        )
    )

    items = callback_metadata.get(
        "Item",
        []
    )

    metadata = {}

    for item in items:

        name = item.get("Name")

        if name:
            metadata[name] = item.get(
                "Value"
            )

    mpesa_receipt = metadata.get(
        "MpesaReceiptNumber"
    )

    callback_amount = metadata.get(
        "Amount"
    )

    callback_phone = metadata.get(
        "PhoneNumber"
    )

    # ---------------------------------------------------------
    # ATOMIC WALLET CREDIT
    # ---------------------------------------------------------

    try:

        with transaction.atomic():

            wallet_transaction = (
                WalletTransaction.objects
                .select_for_update()
                .get(
                    pk=wallet_transaction.pk
                )
            )

            # Another callback may have processed
            # the transaction while this request
            # was waiting for the database lock.

            if wallet_transaction.status == "COMPLETED":

                return JsonResponse(
                    {
                        "ResultCode": 0,
                        "ResultDesc":
                            "Already processed.",
                    }
                )

            if wallet_transaction.status == "FAILED":

                return JsonResponse(
                    {
                        "ResultCode": 0,
                        "ResultDesc":
                            "Already processed.",
                    }
                )

            # -------------------------------------------------
            # VERIFY AMOUNT
            # -------------------------------------------------

            if callback_amount is not None:

                callback_amount_decimal = Decimal(
                    str(callback_amount)
                ).quantize(
                    Decimal("0.01")
                )

                if (
                    callback_amount_decimal
                    != wallet_transaction.ksh_amount
                ):

                    wallet_transaction.status = "FAILED"

                    wallet_transaction.result_code = (
                        result_code
                    )

                    wallet_transaction.result_description = (
                        "M-PESA amount does not match "
                        "the purchase amount."
                    )

                    wallet_transaction.save(
                        update_fields=[
                            "status",
                            "result_code",
                            "result_description",
                        ]
                    )

                    return JsonResponse(
                        {
                            "ResultCode": 0,
                            "ResultDesc":
                                "Amount mismatch.",
                        }
                    )

            # -------------------------------------------------
            # AUTHORITATIVE EXECUTION PRICE
            # -------------------------------------------------

            execution_price = Decimal(
                wallet_transaction.price_per_au
            )

            if execution_price <= Decimal("0"):

                raise ValueError(
                    "Invalid transaction price."
                )

            # -------------------------------------------------
            # CALCULATE AU
            # -------------------------------------------------

            au_amount = (
                wallet_transaction.ksh_amount
                / execution_price
            ).quantize(
                Decimal("0.00000001")
            )

            if au_amount <= Decimal("0"):

                raise ValueError(
                    "Calculated AU amount is invalid."
                )

            # -------------------------------------------------
            # LOCK WALLET
            # -------------------------------------------------

            wallet = (
                Wallet.objects
                .select_for_update()
                .get(
                    user=wallet_transaction.user
                )
            )

            # -------------------------------------------------
            # CREDIT AU
            # -------------------------------------------------

            wallet.au_balance += au_amount

            wallet.save(
                update_fields=[
                    "au_balance",
                    "updated_at",
                ]
            )

            # -------------------------------------------------
            # COMPLETE TRANSACTION
            # -------------------------------------------------

            wallet_transaction.status = "COMPLETED"

            wallet_transaction.au_amount = (
                au_amount
            )

            wallet_transaction.result_code = (
                result_code
            )

            wallet_transaction.result_description = (
                result_description
            )

            wallet_transaction.merchant_request_id = (
                merchant_request_id
            )

            if mpesa_receipt:

                wallet_transaction.mpesa_receipt_number = (
                    str(mpesa_receipt)
                )

            if callback_phone:

                wallet_transaction.phone_number = (
                    str(callback_phone)
                )

            wallet_transaction.save(
                update_fields=[
                    "status",
                    "au_amount",
                    "result_code",
                    "result_description",
                    "merchant_request_id",
                    "mpesa_receipt_number",
                    "phone_number",
                ]
            )

    except Wallet.DoesNotExist:

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc":
                    "Wallet not found.",
            },
            status=500,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": str(exc),
            },
            status=500,
        )

    # ---------------------------------------------------------
    # ACKNOWLEDGE CALLBACK
    # ---------------------------------------------------------

    return JsonResponse(
        {
            "ResultCode": 0,
            "ResultDesc":
                "Callback processed successfully.",
        }
    )

@login_required
@require_GET
def payment_status(request):

    transaction_id = request.GET.get(
        "transaction_id"
    )

    if not transaction_id:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "transaction_id is required."
                ),
            },
            status=400,
        )

    wallet_transaction = (
        WalletTransaction.objects
        .filter(
            transaction_id=transaction_id,
            user=request.user,
            transaction_type="PURCHASE",
        )
        .first()
    )

    if not wallet_transaction:

        return JsonResponse(
            {
                "success": False,
                "error": "Transaction not found.",
            },
            status=404,
        )

    return JsonResponse(
        {
            "success": True,

            "payment_status":
                wallet_transaction.status,

            "transaction_reference":
                wallet_transaction.transaction_id,

            "checkout_request_id":
                wallet_transaction.checkout_request_id,

            "mpesa_receipt_number":
                wallet_transaction.mpesa_receipt_number,

            "result_code":
                wallet_transaction.result_code,

            "result_description":
                wallet_transaction.result_description,

            "amount_paid":
                str(wallet_transaction.ksh_amount),

            "au_credited":
                str(wallet_transaction.au_amount),

            "execution_price":
                str(wallet_transaction.price_per_au),
        }
    )

@login_required
@require_GET
def purchase_status(request, transaction_id):

    tx = get_object_or_404(
        WalletTransaction,
        transaction_id=transaction_id,
        user=request.user,
    )

    return JsonResponse({
        "success": True,
        "status": tx.status,
        "au_amount": str(
            tx.au_amount
        ),
        "ksh_amount": str(
            tx.ksh_amount
        ),
        "receipt": (
            tx.mpesa_receipt_number
        ),
        "message": (
            tx.result_description
        ),
    })
    

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

    raw_key = request.headers.get("Idempotency-Key")

    try:
        idempotency_key = validate_idempotency_key(raw_key)
    except IdempotencyError as exc:
        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=400,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid JSON.",
            },
            status=400,
        )

    au_amount = data.get("au_amount")
    phone = data.get("phone")

    if au_amount is None:
        return JsonResponse(
            {
                "success": False,
                "error": "AU amount is required.",
            },
            status=400,
        )

    if not phone:
        return JsonResponse(
            {
                "success": False,
                "error": "M-PESA phone is required.",
            },
            status=400,
        )

    try:
        au_amount = Decimal(str(au_amount)).quantize(
            Decimal("0.00000001")
        )

        if au_amount <= 0:
            raise ValueError

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid AU amount.",
            },
            status=400,
        )

    request_hash = hashlib.sha256(
        json.dumps(
            {
                "au_amount": str(au_amount),
                "phone": phone,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    existing = (
        IdempotencyRequest.objects
        .select_related("transaction")
        .filter(
            user=request.user,
            operation="WITHDRAWAL",
            key=idempotency_key,
        )
        .first()
    )

    if existing:

        if existing.request_hash != request_hash:
            return JsonResponse(
                {
                    "success": False,
                    "error": "This Idempotency-Key has already been used with different request data.",
                },
                status=409,
            )

        if existing.transaction:
            tx = existing.transaction

            return JsonResponse(
                {
                    "success": True,
                    "payment_status": tx.status,
                    "transaction_reference": tx.transaction_id,
                    "checkout_request_id": tx.checkout_request_id,
                }
            )

    with transaction.atomic():

        wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=request.user)
        )

        if wallet.au_balance < au_amount:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Insufficient AU balance.",
                },
                status=400,
            )

        price = Decimal(
            get_latest_market_price("BTCUSDT")
        )

        ksh_amount = (
            au_amount * price
        ).quantize(Decimal("0.01"))

        tx = WalletTransaction.objects.create(
            transaction_id=f"WDR-{uuid.uuid4().hex.upper()}",
            user=request.user,
            transaction_type="WITHDRAWAL",
            status="PENDING",
            au_amount=au_amount,
            ksh_amount=ksh_amount,
            price_per_au=price,
            phone_number=phone,
            reference="SIMULATED-WITHDRAWAL",
            checkout_request_id=f"SIM-W-{uuid.uuid4().hex[:16].upper()}",
            result_description="Awaiting simulated M-PESA payout.",
        )

        IdempotencyRequest.objects.create(
            user=request.user,
            operation="WITHDRAWAL",
            key=idempotency_key,
            request_hash=request_hash,
            transaction=tx,
        )

    return JsonResponse(
        {
            "success": True,
            "payment_status": "PENDING",
            "transaction_reference": tx.transaction_id,
            "checkout_request_id": tx.checkout_request_id,
            "au_amount": str(tx.au_amount),
            "ksh_amount": str(tx.ksh_amount),
            "price": str(tx.price_per_au),
            "message": "Withdrawal request created.",
        }
    )

@login_required
@require_POST
def simulate_withdrawal_callback(
    request,
    transaction_id,
):

    with transaction.atomic():

        try:
            tx = (
                WalletTransaction.objects
                .select_for_update()
                .select_related("user")
                .get(
                    transaction_id=transaction_id,
                    transaction_type="WITHDRAWAL",
                    user=request.user,
                )
            )

        except WalletTransaction.DoesNotExist:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Withdrawal transaction not found.",
                },
                status=404,
            )

        # Already completed
        if tx.status == "COMPLETED":

            return JsonResponse(
                {
                    "success": True,
                    "status": "COMPLETED",
                    "receipt": tx.mpesa_receipt_number,
                }
            )

        # Already failed
        if tx.status == "FAILED":

            return JsonResponse(
                {
                    "success": False,
                    "error": tx.result_description,
                },
                status=400,
            )

        wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=tx.user)
        )

        # Final balance verification
        if wallet.au_balance < tx.au_amount:

            tx.status = "FAILED"

            tx.result_code = 1

            tx.result_description = (
                "Insufficient AU balance during payout."
            )

            tx.save(
                update_fields=[
                    "status",
                    "result_code",
                    "result_description",
                ]
            )

            return JsonResponse(
                {
                    "success": False,
                    "error": tx.result_description,
                },
                status=400,
            )

        # Deduct AU only after payout succeeds
        wallet.au_balance -= tx.au_amount

        wallet.save(
            update_fields=[
                "au_balance",
                "updated_at",
            ]
        )

        tx.status = "COMPLETED"

        tx.result_code = 0

        tx.result_description = (
            "Simulated M-PESA withdrawal completed."
        )

        tx.mpesa_receipt_number = (
            f"SIM{uuid.uuid4().hex[:10].upper()}"
        )

        tx.save(
            update_fields=[
                "status",
                "result_code",
                "result_description",
                "mpesa_receipt_number",
            ]
        )

    return JsonResponse(
        {
            "success": True,
            "status": "COMPLETED",
            "transaction_reference": tx.transaction_id,
            "receipt": tx.mpesa_receipt_number,
            "au_amount": str(tx.au_amount),
            "ksh_amount": str(tx.ksh_amount),
        }
    )


@login_required
@require_GET
def withdrawal_status(
    request,
    transaction_id,
):

    tx = get_object_or_404(
        WalletTransaction,
        transaction_id=transaction_id,
        transaction_type="WITHDRAWAL",
        user=request.user,
    )

    return JsonResponse(
        {
            "success": True,
            "status": tx.status,
            "au_amount": str(tx.au_amount),
            "ksh_amount": str(tx.ksh_amount),
            "receipt": tx.mpesa_receipt_number,
            "message": tx.result_description,
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



@require_POST
def logout_view(request):

    logout(request)

    return redirect("login")

@login_required
def market_candles(request):

    symbol = request.GET.get(
        "symbol",
        "BTCUSDT"
    )

    timeframe = request.GET.get(
        "timeframe",
        "1m"
    ).lower()

    try:
        limit = min(
            int(
                request.GET.get(
                    "limit",
                    500
                )
            ),
            5000,
        )
    except ValueError:
        limit = 500

    allowed_timeframes = {
        "1m": 1,
        "5m": 5,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    if timeframe not in allowed_timeframes:
        return JsonResponse(
            {
                "error": "Invalid timeframe."
            },
            status=400,
        )

    minutes = allowed_timeframes[
        timeframe
    ]

    # --------------------------------------------------
    # 1-MINUTE CANDLES
    # --------------------------------------------------

    if timeframe == "1m":

        candles = (
            MarketCandle.objects
            .filter(
                symbol=symbol,
                timeframe="1m",
            )
            .order_by(
                "-bucket_start"
            )[:limit]
        )

        candles = reversed(
            list(candles)
        )

        data = [
            {
                "time":
                    candle.bucket_start.isoformat(),

                "open":
                    float(candle.open),

                "high":
                    float(candle.high),

                "low":
                    float(candle.low),

                "close":
                    float(candle.close),

                "tick_count":
                    candle.tick_count,
            }
            for candle in candles
        ]

        return JsonResponse({
            "symbol": symbol,
            "timeframe": timeframe,
            "data": data,
        })

    # --------------------------------------------------
    # HIGHER TIMEFRAMES
    # --------------------------------------------------

    required_1m = limit * minutes

    base_candles = list(
        MarketCandle.objects
        .filter(
            symbol=symbol,
            timeframe="1m",
        )
        .order_by(
            "-bucket_start"
        )[:required_1m]
    )

    base_candles.reverse()

    aggregated = []

    current_bucket = None
    current_candle = None

    for candle in base_candles:

        bucket_start = candle.bucket_start

        if timeframe == "5m":

            bucket_start = bucket_start.replace(
                minute=(bucket_start.minute // 5) * 5,
                second=0,
                microsecond=0,
            )

        elif timeframe == "1h":

            bucket_start = bucket_start.replace(
                minute=0,
                second=0,
                microsecond=0,
            )

        elif timeframe == "4h":

            bucket_start = bucket_start.replace(
                hour=(bucket_start.hour // 4) * 4,
                minute=0,
                second=0,
                microsecond=0,
            )

        elif timeframe == "1d":

            bucket_start = bucket_start.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

        # Start a new aggregated candle
        if (
            current_bucket is None
            or bucket_start != current_bucket
        ):

            if current_candle is not None:
                aggregated.append(
                    current_candle
                )

            current_bucket = bucket_start

            current_candle = {
                "time":
                    bucket_start.isoformat(),

                "open":
                    float(candle.open),

                "high":
                    float(candle.high),

                "low":
                    float(candle.low),

                "close":
                    float(candle.close),

                "tick_count":
                    candle.tick_count,
            }

        else:

            current_candle["high"] = max(
                current_candle["high"],
                float(candle.high),
            )

            current_candle["low"] = min(
                current_candle["low"],
                float(candle.low),
            )

            current_candle["close"] = (
                float(candle.close)
            )

            current_candle["tick_count"] += (
                candle.tick_count
            )

    if current_candle is not None:
        aggregated.append(
            current_candle
        )

    # Keep only the requested number
    aggregated = aggregated[-limit:]

    return JsonResponse({
        "symbol": symbol,
        "timeframe": timeframe,
        "data": aggregated,
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

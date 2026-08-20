function csrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}

const priceHistory = [];
const MAX_POINTS = 60;
let candleHistory = [];
let tickCount = 0;

let withdrawalAmountConfirmed = false;
let confirmedWithdrawalAmount = null;
let confirmedWithdrawalPrice = null;
let confirmedWithdrawalPayout = null;

function addPricePoint(price) {
    const now = new Date();

    priceHistory.push({
        time: now,
        price: Number(price)
    });

    // Keep only the latest 60 ticks
    if (priceHistory.length > MAX_POINTS) {
        priceHistory.shift();
    }

    tickCount++;

    document.getElementById("tickCount").textContent = tickCount;

    document.getElementById("lastUpdate").textContent =
        now.toLocaleTimeString();

    document.getElementById("price").textContent =
        Number(price).toFixed(2);

    drawMarketChart();
}

function drawMarketChart() {
    const canvas = document.getElementById("chart");
    const ctx = canvas.getContext("2d");

    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    if (candleHistory.length === 0) {
        ctx.fillStyle = "#666";
        ctx.font = "14px Arial";
        ctx.fillText("Waiting for market data...", 20, 30);
        return;
    }

    // --------------------------------------------------
    // PRICE RANGE
    // --------------------------------------------------

    const prices = [];

    candleHistory.forEach(candle => {
        prices.push(
            Number(candle.high),
            Number(candle.low)
        );
    });

    let minPrice = Math.min(...prices);
    let maxPrice = Math.max(...prices);

    // Prevent a completely flat chart
    if (minPrice === maxPrice) {
        minPrice -= 1;
        maxPrice += 1;
    }

    // Add a little visual breathing room
    const priceRange = maxPrice - minPrice;

    minPrice -= priceRange * 0.05;
    maxPrice += priceRange * 0.05;

    // --------------------------------------------------
    // CHART DIMENSIONS
    // --------------------------------------------------

    const paddingTop = 20;
    const paddingRight = 60;
    const paddingBottom = 30;
    const paddingLeft = 50;

    const chartWidth =
        width - paddingLeft - paddingRight;

    const chartHeight =
        height - paddingTop - paddingBottom;

    // --------------------------------------------------
    // PRICE → CANVAS Y
    // --------------------------------------------------

    function priceToY(price) {
        return (
            paddingTop +
            ((maxPrice - price) /
                (maxPrice - minPrice)) *
                chartHeight
        );
    }

    // --------------------------------------------------
    // GRID
    // --------------------------------------------------

    ctx.strokeStyle = "#dddddd";
    ctx.lineWidth = 1;

    ctx.fillStyle = "#666";
    ctx.font = "11px Arial";

    for (let i = 0; i <= 4; i++) {
        const y =
            paddingTop +
            (chartHeight / 4) * i;

        ctx.beginPath();
        ctx.moveTo(paddingLeft, y);
        ctx.lineTo(width - paddingRight, y);
        ctx.stroke();

        const value =
            maxPrice -
            ((maxPrice - minPrice) / 4) * i;

        ctx.fillText(
            value.toFixed(2),
            width - paddingRight + 5,
            y + 4
        );
    }

    // --------------------------------------------------
    // CANDLE WIDTH
    // --------------------------------------------------

    const candleSpacing =
        chartWidth /
        Math.max(candleHistory.length, 1);

    const candleWidth =
        Math.max(
            3,
            Math.min(
                16,
                candleSpacing * 0.65
            )
        );

    // --------------------------------------------------
    // DRAW CANDLES
    // --------------------------------------------------

    candleHistory.forEach((candle, index) => {

        const open = Number(candle.open);
        const high = Number(candle.high);
        const low = Number(candle.low);
        const close = Number(candle.close);

        const x =
            paddingLeft +
            candleSpacing * index +
            candleSpacing / 2;

        const highY = priceToY(high);
        const lowY = priceToY(low);
        const openY = priceToY(open);
        const closeY = priceToY(close);

        // ----------------------------------------------
        // Determine candle direction
        // ----------------------------------------------

        const bullish = close >= open;

        // ----------------------------------------------
        // Wick
        // ----------------------------------------------

        ctx.beginPath();

        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);

        ctx.strokeStyle =
            bullish
                ? "#2e8b57"
                : "#d9534f";

        ctx.lineWidth = 1;

        ctx.stroke();

        // ----------------------------------------------
        // Candle body
        // ----------------------------------------------

        let bodyTop = Math.min(
            openY,
            closeY
        );

        let bodyBottom = Math.max(
            openY,
            closeY
        );

        let bodyHeight =
            bodyBottom - bodyTop;

        // Ensure tiny candles remain visible
        if (bodyHeight < 2) {
            bodyHeight = 2;

            bodyTop =
                ((openY + closeY) / 2) -
                1;
        }

        ctx.fillStyle =
            bullish
                ? "#2e8b57"
                : "#d9534f";

        ctx.fillRect(
            x - candleWidth / 2,
            bodyTop,
            candleWidth,
            bodyHeight
        );
    });

    // --------------------------------------------------
    // LATEST PRICE
    // --------------------------------------------------

    const latest =
        candleHistory[
            candleHistory.length - 1
        ];

    const latestPrice =
        Number(latest.close);

    const latestY =
        priceToY(latestPrice);

    // Horizontal price line
    ctx.beginPath();

    ctx.moveTo(
        paddingLeft,
        latestY
    );

    ctx.lineTo(
        width - paddingRight,
        latestY
    );

    ctx.strokeStyle = "#ff8c00";
    ctx.lineWidth = 1;

    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Latest price label
    ctx.fillStyle = "#ff8c00";
    ctx.font = "bold 11px Arial";

    ctx.fillText(
        latestPrice.toFixed(2),
        width - paddingRight + 5,
        latestY + 4
    );
}

async function loadMarketCandles() {
    try {
        const response = await fetch(
            "/api/market/candles/?symbol=BTCUSDT&limit=100"
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result = await response.json();

        candleHistory = result.data || [];

        drawMarketChart();

    } catch (error) {
        console.error(
            "Failed to load market candles:",
            error
        );
    }
}
loadMarketCandles();

async function updateLatestCandle() {
    try {
        const response = await fetch(
            "/api/market/candles/?symbol=BTCUSDT&limit=1"
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result = await response.json();

        if (!result.data || result.data.length === 0) {
            return;
        }

        const latest =
            result.data[0];

        if (candleHistory.length === 0) {
            candleHistory.push(latest);
        } else {
            const last =
                candleHistory[
                    candleHistory.length - 1
                ];

            if (
                last.time === latest.time
            ) {
                // Same minute:
                // update the existing candle
                candleHistory[
                    candleHistory.length - 1
                ] = latest;

            } else {
                // New minute:
                // add a new candle
                candleHistory.push(latest);

                // Keep chart manageable
                if (
                    candleHistory.length > 100
                ) {
                    candleHistory.shift();
                }
            }
        }

        drawMarketChart();

        

    } catch (error) {
        console.error(
            "Failed to update candle:",
            error
        );
    }
}
setInterval(
    updateLatestCandle,
    1000
);
async function postForm(url, data) {
    const body = new URLSearchParams(data);
    body.append('csrfmiddlewaretoken', csrfToken());

    const response = await fetch(url, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken()},
        body
    });

    return response.json();
}




async function refreshEvents() {
    const response = await fetch('/api/events/');
    const data = await response.json();
    const container = document.getElementById('events');

    if (!container) return;

    container.innerHTML = data.events.map(event => `
        <div class="event">
            <strong>${event.severity}</strong>
            ${event.type} — ${event.message}
        </div>
    `).join('');
}

window.addEventListener(
    "load",
    async () => {

        await refreshMarket();

        await refreshEvents();

        await updatePosition();
    }
);


async function generateMarketTick() {
    try {
        const response = await fetch("/api/market/", {
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        });

        if (!response.ok) {
            throw new Error(
                `Market request failed: ${response.status}`
            );
        }

        const data = await response.json();

        console.log("Synthetic tick:", data);

        if (data.price !== undefined) {
            addPricePoint(data.price);
        }

        document.getElementById("marketStatus").textContent = "LIVE";

    } catch (error) {
        console.error("Market update failed:", error);

        document.getElementById("marketStatus").textContent = "OFFLINE";
    }
}
// Generate the first tick immediately
generateMarketTick();

// Generate another synthetic tick every 2 seconds
setInterval(generateMarketTick, 1000);

let selectedTradeSide = "LONG";





function getCookie(name) {

    const cookies = document.cookie.split(";");

    for (let cookie of cookies) {

        cookie = cookie.trim();

        if (cookie.startsWith(name + "=")) {

            return decodeURIComponent(
                cookie.substring(name.length + 1)
            );
        }
    }

    return null;
}

function getCsrfToken() {
    return getCookie("csrftoken");
}



document.addEventListener(
    "DOMContentLoaded",
    () => {
        updatePortfolio();
    }
);
async function updatePortfolio() {

    try {

        const response = await fetch("/api/portfolio/", {
            method: "GET",
            credentials: "same-origin",
            headers: {
                "Accept": "application/json"
            }
        });

        if (!response.ok) {
            throw new Error(
                `Portfolio request failed: ${response.status}`
            );
        }

        const data = await response.json();

        const auBalance =
            document.getElementById("auBalance");

        const auPrice =
            document.getElementById("auPrice");

        const portfolioValue =
            document.getElementById("portfolioValue");

        const invested =
            document.getElementById("invested");

        const profitLoss =
            document.getElementById("profitLoss");

        const profitLossPercent =
            document.getElementById("profitLossPercent");

        if (auBalance) {
            auBalance.textContent =
                `${data.au_balance} AU`;
        }

        if (auPrice) {
            auPrice.textContent =
                `KSh ${data.price}`;
        }

        if (portfolioValue) {
            portfolioValue.textContent =
                `KSh ${data.current_value}`;
        }

        if (invested) {
            invested.textContent =
                `KSh ${data.invested}`;
        }

        if (profitLoss) {
            profitLoss.textContent =
                `KSh ${data.gain_loss}`;
        }

        if (profitLossPercent) {
            profitLossPercent.textContent =
                `${data.gain_loss_percent}%`;
        }

    } catch (error) {

        console.error(
            "Portfolio update failed:",
            error
        );
    }
} setInterval(updatePortfolio, 1000);


function getCSRFToken() {

    const cookie = document.cookie
        .split("; ")
        .find(row =>
            row.startsWith("csrftoken=")
        );

    return cookie
        ? decodeURIComponent(
            cookie.split("=")[1]
        )
        : "";
}



function generateIdempotencyKey() {

    if (crypto.randomUUID) {
        return crypto.randomUUID()
            .replace(/-/g, "");
    }

    const array = new Uint8Array(32);

    crypto.getRandomValues(array);

    return Array.from(array)
        .map(byte =>
            byte.toString(16).padStart(2, "0")
        )
        .join("");
}

async function purchaseAU(amount) {

    if (!amount || Number(amount) <= 0) {
        throw new Error("Enter a valid purchase amount.");
    }

    const idempotencyKey = generateIdempotencyKey();

    const body = new URLSearchParams();

    body.append("amount", amount);

    const response = await fetch(
        "/api/wallet/purchase/",
        {
            method: "POST",

            headers: {
                "X-CSRFToken": getCSRFToken(),
                "Idempotency-Key": idempotencyKey,
            },

            body: body,
        }
    );

    const text = await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch (error) {
        throw new Error(
            `Purchase failed (${response.status}): ${text}`
        );
    }

    if (!response.ok || !data.success) {
        throw new Error(
            data.error ||
            `Purchase failed (${response.status})`
        );
    }

    return data;
}

async function sendPurchaseRequest(
    amount,
    idempotencyKey
) {

    const response = await fetch(
        "/api/wallet/purchase/",
        {
            method: "POST",

            credentials: "same-origin",

            headers: {
                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json",

                "X-CSRFToken":
                    getCSRFToken(),

                "Idempotency-Key":
                    idempotencyKey,
            },

            body: JSON.stringify({
                amount: String(amount)
            }),
        }
    );

    const data =
        await response.json();

    if (!response.ok) {

        throw new Error(
            data.error ||
            "Purchase failed."
        );
    }

    return data;
}

async function purchaseAUWithRetry(amount) {

    const key =
        generateIdempotencyKey();

    try {

        return await sendPurchaseRequest(
            amount,
            key
        );

    } catch (error) {

        console.warn(
            "Purchase request failed. Retrying...",
            error
        );

        // IMPORTANT:
        // Reuse the SAME key.

        return await sendPurchaseRequest(
            amount,
            key
        );
    }
}

async function withdrawAU(amount, phone, idempotencyKey) {

    const response = await fetch("/api/withdraw/", {
        method: "POST",

        credentials: "same-origin",

        headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": idempotencyKey,
            "X-CSRFToken": getCsrfToken()
        },

        body: JSON.stringify({
            au_amount: amount,
            phone: phone
        })
    });

    const contentType =
        response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {

        const text = await response.text();

        console.error(
            "Withdrawal returned non-JSON:",
            response.status,
            text
        );

        throw new Error(
            `Withdrawal request returned HTTP ${response.status} instead of JSON.`
        );
    }

    const data = await response.json();

    if (!response.ok) {
        throw new Error(
            data.error ||
            data.message ||
            "Withdrawal failed."
        );
    }

    return data;
}

async function sendWithdrawalRequest(
    auAmount,
    idempotencyKey
) {

    const response = await fetch(
        "/api/wallet/withdraw/",
        {
            method: "POST",

            credentials: "same-origin",

            headers: {
                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json",

                "X-CSRFToken":
                    getCSRFToken(),

                "Idempotency-Key":
                    idempotencyKey,
            },

            body: JSON.stringify({
                au_amount:
                    String(auAmount)
            }),
        }
    );

    const data =
        await response.json();

    if (!response.ok) {

        throw new Error(
            data.error ||
            "Withdrawal failed."
        );
    }

    return data;
}



let purchaseInProgress = false;

function openPurchaseModal(amount) {

    pendingPurchaseAmount = amount;

    pendingPurchaseIdempotencyKey =
        generateIdempotencyKey();

    document.getElementById(
        "confirmPurchaseAmount"
    ).textContent =
        Number(amount).toFixed(2);

    document.getElementById(
        "purchaseModal"
    ).style.display = "flex";

    
}

async function handlePurchase() {

    if (purchaseInProgress) {
        return;
    }

    const amountInput =
        document.getElementById("purchaseAmount");

    if (!amountInput) {
        alert("Purchase amount field is missing.");
        return;
    }

    const amount =
        amountInput.value.trim();

    if (!amount) {
        alert("Enter a purchase amount.");
        return;
    }

    const numericAmount =
        Number(amount);

    if (
        !Number.isFinite(numericAmount) ||
        numericAmount <= 0
    ) {
        alert("Enter a valid purchase amount.");
        return;
    }

    /*
     * Get the current market price displayed
     * by the dashboard.
     */
    const priceElement =
        document.getElementById("price");

    if (!priceElement) {
        alert("Market price is unavailable.");
        return;
    }

    const price =
        Number(priceElement.textContent.trim());

    if (
        !Number.isFinite(price) ||
        price <= 0
    ) {
        alert("Market price is unavailable.");
        return;
    }

    const auQuantity =
        numericAmount / price;


    /*
     * Populate modal
     */

    document.getElementById(
        "modalPurchaseAmount"
    ).textContent =
        numericAmount.toFixed(2);

    document.getElementById(
        "modalAuPrice"
    ).textContent =
        price.toFixed(8);

    document.getElementById(
        "modalAuQuantity"
    ).textContent =
        auQuantity.toFixed(8);


    /*
     * Open modal
     */

    document.getElementById(
        "purchaseModal"
    ).style.display = "flex";
}

function closePurchaseModal() {

    document.getElementById(
        "purchaseModal"
    ).style.display = "none";

    resetPurchaseModal();
}

function resetPurchaseModal() {

    document.getElementById(
        "paymentStep"
    ).style.display = "block";

    document.getElementById(
        "paymentProcessing"
    ).style.display = "none";

    document.getElementById(
        "paymentSuccess"
    ).style.display = "none";

    document.getElementById(
        "paymentError"
    ).style.display = "none";

    document.getElementById(
        "paymentErrorMessage"
    ).textContent =
        "The transaction could not be verified.";

    const button =
        document.getElementById(
            "confirmPurchaseButton"
        );

    if (button) {
        button.disabled = false;
    }
}

async function confirmPurchase() {

    if (purchaseInProgress) {
        return;
    }

    const amountInput =
        document.getElementById(
            "purchaseAmount"
        );

    const phoneInput =
        document.getElementById(
            "mpesaPhone"
        );

    const amount =
        amountInput.value.trim();

    const phone =
        phoneInput.value.trim();


    if (!amount || Number(amount) <= 0) {

        showPurchaseError(
            "Enter a valid purchase amount."
        );

        return;
    }


    if (!phone) {

        showPurchaseError(
            "Enter the M-Pesa phone number."
        );

        return;
    }


    purchaseInProgress = true;


    const button =
        document.getElementById(
            "confirmPurchaseButton"
        );

    button.disabled = true;


    /*
     * Show processing state
     */

    document.getElementById(
        "paymentStep"
    ).style.display = "none";

    document.getElementById(
        "paymentProcessing"
    ).style.display = "block";


    try {

        /*
         * This calls your existing purchaseAU()
         * function.
         *
         * Your existing purchaseAU() should be
         * responsible for:
         *
         * - generating idempotency key
         * - sending KES amount
         * - server-side price lookup
         * - simulated M-Pesa transaction
         * - wallet credit
         * - transaction ledger
         */

        const result =
            await purchaseAU(amount, phone);


        console.log(
            "Purchase verified:",
            result
        );


        /*
         * Show success
         */

        document.getElementById(
            "paymentProcessing"
        ).style.display = "none";

        document.getElementById(
            "paymentSuccess"
        ).style.display = "block";


        /*
         * Display amount actually credited
         */

        const auAmount =
            result.au_amount ??
            result.quantity ??
            result.amount_au ??
            0;

        document.getElementById(
            "successAuAmount"
        ).textContent =
            Number(auAmount).toFixed(8);


        /*
         * Refresh dashboard
         */

        await updatePortfolio();

        /*
         * Refresh any payment/event
         * sections if your app.js has them.
         */

        if (typeof loadPayments === "function") {
            await loadPayments();
        }

        if (typeof loadEvents === "function") {
            await loadEvents();
        }


    } catch (error) {

        console.error(
            "Purchase failed:",
            error
        );

        showPurchaseError(
            error.message ||
            "Payment verification failed."
        );

    } finally {

        purchaseInProgress = false;

        button.disabled = false;
    }
}

function showPurchaseError(message) {

    document.getElementById(
        "paymentStep"
    ).style.display = "none";

    document.getElementById(
        "paymentProcessing"
    ).style.display = "none";

    document.getElementById(
        "paymentSuccess"
    ).style.display = "none";

    document.getElementById(
        "paymentError"
    ).style.display = "block";

    document.getElementById(
        "paymentErrorMessage"
    ).textContent = message;
}

let withdrawalInProgress = false;

async function handleWithdrawal() {

    // Prevent another click while this withdrawal is processing
    if (withdrawalInProgress) {
        return;
    }

    const button =
        document.getElementById("withdrawButton");

    const amountInput =
        document.getElementById("withdrawAuAmount");

    const phoneInput =
        document.getElementById("withdrawPhone");

    const status =
        document.getElementById("withdrawalStatus");

    if (!button || !amountInput || !phoneInput) {
        console.error(
            "Withdrawal elements not found."
        );
        return;
    }

    const amount =
        amountInput.value.trim();

    const phone =
        phoneInput.value.trim();

    if (!amount || Number(amount) <= 0) {
        alert("Enter a valid AU amount.");
        return;
    }

    if (!phone) {
        alert("Enter an M-Pesa number.");
        return;
    }

    /*
     * Lock immediately BEFORE making the request.
     */
    withdrawalInProgress = true;

    button.disabled = true;
    button.textContent = "Processing...";

    if (status) {
        status.textContent =
            "Processing withdrawal...";
    }

    /*
     * One unique key for this withdrawal attempt.
     */
    const idempotencyKey =
        generateIdempotencyKey();

    try {

        const result =
            await withdrawAU(
                amount,
                phone,
                idempotencyKey
            );

        console.log(
            "Withdrawal completed:",
            result
        );

        if (status) {
            status.textContent =
                result.message ||
                "Withdrawal completed successfully.";
        }

        /*
         * Refresh account data after backend confirmation.
         */
        await updatePortfolio();

        /*
         * Refresh the withdrawal estimate using
         * the new AU balance/market state.
         */
        await updateWithdrawalEstimate();
        

    } catch (error) {

        console.error(
            "Withdrawal failed:",
            error
        );

        if (status) {
            status.textContent =
                error.message ||
                "Withdrawal failed.";
        }

        /*
         * The button becomes available again ONLY
         * because the backend request has completed
         * with an error.
         */

    } finally {

        withdrawalInProgress = false;

        button.disabled = false;
        button.textContent =
            "Withdraw to M-Pesa";
    }
}



async function updateWithdrawalEstimate() {

    const amountInput =
        document.getElementById("withdrawAuAmount");

    const priceElement =
        document.getElementById("withdrawMarketPrice");

    const payoutElement =
        document.getElementById("estimatedWithdrawal");

    if (!amountInput || !priceElement || !payoutElement) {
        console.error(
            "Withdrawal estimate elements not found"
        );
        return;
    }

    const amount = amountInput.value.trim();

    /*
     * Nothing entered yet.
     */
    if (!amount || Number(amount) <= 0) {
        priceElement.textContent = "--";
        payoutElement.textContent = "0.00";
        return;
    }

    try {

        const response = await fetch(
            `/api/withdrawal/estimate/?amount=${encodeURIComponent(amount)}`,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        console.log(
            "Withdrawal estimate HTTP:",
            response.status
        );

        if (!response.ok) {

            const errorText =
                await response.text();

            console.error(
                "Withdrawal estimate response:",
                errorText
            );

            throw new Error(
                `Withdrawal estimate failed: ${response.status}`
            );
        }

        const data =
            await response.json();

        console.log(
            "Withdrawal estimate data:",
            data
        );

        if (data.error) {
            throw new Error(data.error);
        }

        priceElement.textContent =
            data.price ?? "--";

        payoutElement.textContent =
            data.payout ?? "0.00";

    } catch (error) {

        console.error(
            "Withdrawal estimate failed:",
            error
        );
    }
}
const withdrawAuAmount =
    document.getElementById("withdrawAuAmount");

if (withdrawAuAmount) {
    withdrawAuAmount.addEventListener(
        "input",
        updateWithdrawalEstimate
    );
}

async function confirmWithdrawalAmount() {

    if (withdrawalAmountConfirmed) {
        return;
    }

    const amountInput =
        document.getElementById("withdrawAuAmount");

    const priceElement =
        document.getElementById("withdrawMarketPrice");

    const payoutElement =
        document.getElementById("estimatedWithdrawal");

    const confirmButton =
        document.getElementById(
            "confirmWithdrawalAmountButton"
        );

    const phoneInput =
        document.getElementById("withdrawPhone");

    const withdrawButton =
        document.getElementById("withdrawButton");

    const status =
        document.getElementById("withdrawalStatus");

    if (
        !amountInput ||
        !priceElement ||
        !payoutElement ||
        !confirmButton ||
        !phoneInput ||
        !withdrawButton
    ) {
        console.error(
            "Withdrawal confirmation elements not found."
        );
        return;
    }

    const amount =
        amountInput.value.trim();

    if (!amount || Number(amount) <= 0) {

        alert(
            "Enter a valid AU amount first."
        );

        return;
    }

    /*
     * Make sure the latest estimate has been obtained.
     */
    await updateWithdrawalEstimate();

    const price =
        priceElement.textContent.trim();

    const payout =
        payoutElement.textContent.trim();

    if (
        price === "--" ||
        payout === "0.00"
    ) {
        alert(
            "A valid withdrawal estimate is required."
        );

        return;
    }

    /*
     * Save the confirmed values.
     */
    confirmedWithdrawalAmount = amount;
    confirmedWithdrawalPrice = price;
    confirmedWithdrawalPayout = payout;

    withdrawalAmountConfirmed = true;

    /*
     * Lock the amount.
     */
    amountInput.disabled = true;

    /*
     * Lock confirmation button.
     */
    confirmButton.disabled = true;
    confirmButton.textContent =
        "Amount Confirmed";

    /*
     * Enable M-Pesa number.
     */
    phoneInput.disabled = false;

    /*
     * Enable actual withdrawal.
     */
    withdrawButton.disabled = false;

    if (status) {
        status.textContent =
            "Amount confirmed. Enter your M-Pesa number.";
    }

    console.log(
        "Withdrawal amount confirmed:",
        {
            amount: confirmedWithdrawalAmount,
            price: confirmedWithdrawalPrice,
            payout: confirmedWithdrawalPayout
        }
    );
}
window.confirmWithdrawalAmount =
    confirmWithdrawalAmount;


function toggleWithdrawalPanel() {

    const panel =
        document.getElementById(
            "withdrawalPanel"
        );

    const toggleButton =
        document.getElementById(
            "withdrawToggleButton"
        );

    if (!panel || !toggleButton) {
        return;
    }

    const isOpen =
        panel.style.display !== "none";

    if (isOpen) {

        cancelWithdrawal();

    } else {

        panel.style.display = "block";

        toggleButton.textContent =
            "Close Withdrawal";
    }
}

function cancelWithdrawal() {

    if (withdrawalInProgress) {
        return;
    }

    const panel =
        document.getElementById("withdrawalPanel");

    const toggleButton =
        document.getElementById("withdrawToggleButton");

    const amountInput =
        document.getElementById("withdrawAuAmount");

    const priceElement =
        document.getElementById("withdrawMarketPrice");

    const payoutElement =
        document.getElementById("estimatedWithdrawal");

    const phoneInput =
        document.getElementById("withdrawPhone");

    const confirmButton =
        document.getElementById(
            "confirmWithdrawalAmountButton"
        );

    const withdrawButton =
        document.getElementById("withdrawButton");

    const status =
        document.getElementById("withdrawalStatus");


    // Reset confirmation state

    withdrawalAmountConfirmed = false;

    confirmedWithdrawalAmount = null;
    confirmedWithdrawalPrice = null;
    confirmedWithdrawalPayout = null;


    // Reset amount

    if (amountInput) {
        amountInput.value = "";
        amountInput.disabled = false;
    }


    // Reset phone

    if (phoneInput) {
        phoneInput.value = "";
        phoneInput.disabled = true;
    }


    // Reset estimate

    if (priceElement) {
        priceElement.textContent = "--";
    }

    if (payoutElement) {
        payoutElement.textContent = "0.00";
    }


    // Reset confirm button

    if (confirmButton) {
        confirmButton.disabled = false;
        confirmButton.textContent =
            "Confirm Amount";
    }


    // Reset withdrawal button

    if (withdrawButton) {
        withdrawButton.disabled = true;
        withdrawButton.textContent =
            "Withdraw to M-Pesa";
    }


    // Clear status

    if (status) {
        status.textContent = "";
    }


    // Close panel

    if (panel) {
        panel.style.display = "none";
    }

    if (toggleButton) {
        toggleButton.textContent =
            "Withdraw AU";
    }
}

function togglePurchasePanel() {

    const panel =
        document.getElementById("purchasePanel");

    const toggleButton =
        document.getElementById("buyAuToggleButton");

    if (!panel || !toggleButton) {
        console.error(
            "Purchase panel elements not found."
        );
        return;
    }

    const isOpen =
        panel.style.display !== "none";

    if (isOpen) {

        cancelPurchase();

    } else {

        panel.style.display = "block";

        toggleButton.textContent =
            "Close Buy AU";
    }
}

function cancelPurchase() {

    const panel =
        document.getElementById(
            "purchasePanel"
        );

    const toggleButton =
        document.getElementById(
            "buyAuToggleButton"
        );

    const amountInput =
        document.getElementById(
            "purchaseAmount"
        );

    const phoneInput =
        document.getElementById(
            "mpesaPhone"
        );

    const status =
        document.getElementById(
            "purchaseStatus"
        );

    if (amountInput) {
        amountInput.value = "";
    }

    if (phoneInput) {
        phoneInput.value = "";
    }

    if (status) {
        status.textContent = "";
    }

    /*
     * Reset the modal.
     */

    closePurchaseModal();

    /*
     * Reset the purchase amount display.
     */

    const modalAmount =
        document.getElementById(
            "modalPurchaseAmount"
        );

    const modalPrice =
        document.getElementById(
            "modalAuPrice"
        );

    const modalQuantity =
        document.getElementById(
            "modalAuQuantity"
        );

    if (modalAmount) {
        modalAmount.textContent = "0.00";
    }

    if (modalPrice) {
        modalPrice.textContent = "0.00000000";
    }

    if (modalQuantity) {
        modalQuantity.textContent = "0.00000000";
    }


    /*
     * Close panel.
     */

    if (panel) {
        panel.style.display = "none";
    }

    if (toggleButton) {
        toggleButton.textContent =
            "Buy AU";
    }
}

async function updateTransactionHistory() {

    const tbody =
        document.getElementById("transactionHistory");

    if (!tbody) {
        console.error(
            "transactionHistory element not found."
        );
        return;
    }

    try {

        const response = await fetch(
            "/api/transactions/",
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        console.log(
            "Transaction history HTTP:",
            response.status
        );

        if (!response.ok) {
            throw new Error(
                `Transaction history failed: ${response.status}`
            );
        }

        const data =
            await response.json();

        console.log(
            "Transaction history data:",
            data
        );

        if (
            !data.transactions ||
            data.transactions.length === 0
        ) {

            tbody.innerHTML = `
                <tr>
                    <td colspan="7">
                        No transactions yet.
                    </td>
                </tr>
            `;

            return;
        }

        tbody.innerHTML =
            data.transactions.map(tx => {

                return `
                    <tr>

                        <td>
                            ${tx.date}
                        </td>

                        <td>
                            ${tx.type}
                        </td>

                        <td>
                            KSh ${tx.amount}
                        </td>

                        <td>
                            ${tx.au}
                        </td>

                        <td>
                            KSh ${tx.price}
                        </td>

                        <td>
                            ${tx.status}
                        </td>

                        <td>
                            ${tx.reference}
                        </td>

                    </tr>
                `;

            }).join("");

    } catch (error) {

        console.error(
            "Transaction history update failed:",
            error
        );

        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                    Failed to load transactions.
                </td>
            </tr>
        `;
    }
}
document.addEventListener(
    "DOMContentLoaded",
    function () {

        updateTransactionHistory();

    }
);
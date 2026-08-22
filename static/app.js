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
let currentTimeframe = "1m";
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


function resizeMarketChart() {
    const canvas = document.getElementById("chart");

    if (!canvas) {
        return;
    }

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    const displayWidth = Math.max(1, Math.round(rect.width));
    const displayHeight = Math.max(1, Math.round(rect.height));

    const requiredWidth =
        Math.round(displayWidth * dpr);

    const requiredHeight =
        Math.round(displayHeight * dpr);

    /*
     * Only resize the backing canvas when necessary.
     * This avoids unnecessary clearing/rescaling.
     */
    if (
        canvas.width !== requiredWidth ||
        canvas.height !== requiredHeight
    ) {
        canvas.width = requiredWidth;
        canvas.height = requiredHeight;
    }

    const ctx = canvas.getContext("2d");

    /*
     * Draw using CSS-pixel coordinates while the
     * backing canvas remains high-DPI.
     */
    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );
}


function drawMarketChart() {

    const canvas =
        document.getElementById("chart");

    if (!canvas) {
        return;
    }

    if (
        !candleHistory ||
        candleHistory.length === 0
    ) {
        resizeMarketChart();

        const ctx =
            canvas.getContext("2d");

        const width =
            canvas.clientWidth;

        const height =
            canvas.clientHeight;

        ctx.clearRect(
            0,
            0,
            width,
            height
        );

        ctx.fillStyle = "#666";
        ctx.font = "14px Arial";

        ctx.fillText(
            "Waiting for market data...",
            20,
            30
        );

        return;
    }

    resizeMarketChart();

    const ctx =
        canvas.getContext("2d");

    /*
     * IMPORTANT:
     * Use CSS dimensions, not canvas.width/canvas.height.
     */
    const width =
        canvas.clientWidth;

    const height =
        canvas.clientHeight;

    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    // --------------------------------------------------
    // VISIBLE CANDLES
    // --------------------------------------------------

    const visibleCount =
        currentTimeframe === "1m"
            ? 60
            : currentTimeframe === "5m"
                ? 60
                : currentTimeframe === "1h"
                    ? 48
                    : currentTimeframe === "4h"
                        ? 42
                        : 30;

    const visibleHistory =
        candleHistory.slice(-visibleCount);


    if (visibleHistory.length === 0) {
        return;
    }


            // --------------------------------------------------
        // PRICE RANGE
        // --------------------------------------------------

        const prices = [];

        visibleHistory.forEach(candle => {
            const high = Number(candle.high);
            const low = Number(candle.low);

            if (
                Number.isFinite(high) &&
                Number.isFinite(low)
            ) {
                prices.push(high, low);
            }
        });

        if (prices.length === 0) {
            return;
        }

        let minPrice = Math.min(...prices);
        let maxPrice = Math.max(...prices);

        const actualRange =
            maxPrice - minPrice;

        const averagePrice =
            (maxPrice + minPrice) / 2;

        /*
        * Keep the chart vertically responsive.
        *
        * Minimum visual range = 0.25% of price.
        * This prevents very small movements from
        * disappearing while avoiding a huge Y-axis range.
        */
        const minimumRange =
            Math.max(
                averagePrice * 0.000000025,
                0.000001
            );

        /*
        * Give the actual movement a little more
        * vertical space.
        */
        const displayRange =
            Math.max(
                actualRange * 1.20,
                minimumRange
            );

        const centerPrice =
            averagePrice;

        minPrice =
            centerPrice -
            displayRange / 2;

        maxPrice =
            centerPrice +
            displayRange / 2;

        /*
        * Small breathing room around the candles.
        */
        const padding =
            displayRange * 0.05;

        minPrice -= padding;
        maxPrice += padding;


    // --------------------------------------------------
    // CHART DIMENSIONS
    // --------------------------------------------------

    const paddingTop = 20;
    const paddingRight = 65;
    const paddingBottom = 30;
    const paddingLeft = 50;

    const chartWidth =
        Math.max(
            1,
            width -
                paddingLeft -
                paddingRight
        );

    const chartHeight =
        Math.max(
            1,
            height -
                paddingTop -
                paddingBottom
        );

    // Left vertical chart boundary
    ctx.beginPath();
    ctx.moveTo(paddingLeft, paddingTop);
    ctx.lineTo(paddingLeft, height - paddingBottom);
    ctx.strokeStyle = "#666";
    ctx.lineWidth = 1;
    ctx.stroke();

    // --------------------------------------------------
    // PRICE -> CANVAS Y
    // --------------------------------------------------

    function priceToY(price) {

        return (
            paddingTop +
            (
                (maxPrice - price) /
                (maxPrice - minPrice)
            ) *
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

        ctx.moveTo(
            paddingLeft,
            y
        );

        ctx.lineTo(
            width - paddingRight,
            y
        );

        ctx.stroke();

        const value =
            maxPrice -
            (
                (maxPrice - minPrice) / 4
            ) * i;

        ctx.fillText(
            value.toFixed(2),
            width - paddingRight + 5,
            y + 4
        );
    }


    // --------------------------------------------------
    // CANDLE SPACING
    // --------------------------------------------------

    const candleSpacing =
        chartWidth /
        visibleHistory.length;

    /*
     * Wider candles when fewer are visible.
     */
    const candleWidth =
        Math.max(
            5,
            Math.min(
                18,
                candleSpacing * 0.72
            )
        );


    // --------------------------------------------------
    // DRAW CANDLES
    // --------------------------------------------------

    visibleHistory.forEach(
        (candle, index) => {

            const open =
                Number(candle.open);

            const high =
                Number(candle.high);

            const low =
                Number(candle.low);

            const close =
                Number(candle.close);

            if (
                !Number.isFinite(open) ||
                !Number.isFinite(high) ||
                !Number.isFinite(low) ||
                !Number.isFinite(close)
            ) {
                return;
            }

            const x =
                paddingLeft +
                (
                    candleSpacing * index
                ) +
                candleSpacing / 2;

            const highY =
                priceToY(high);

            const lowY =
                priceToY(low);

            const openY =
                priceToY(open);

            const closeY =
                priceToY(close);

            const bullish =
                close >= open;


            // ------------------------------------------
            // WICK
            // ------------------------------------------

            ctx.beginPath();

            ctx.moveTo(
                x,
                highY
            );

            ctx.lineTo(
                x,
                lowY
            );

            ctx.strokeStyle =
                bullish
                    ? "#2e8b57"
                    : "#d9534f";

            ctx.lineWidth = 1;

            ctx.stroke();


            // ------------------------------------------
            // BODY
            // ------------------------------------------

            let bodyTop =
                Math.min(
                    openY,
                    closeY
                );

            let bodyBottom =
                Math.max(
                    openY,
                    closeY
                );

            let bodyHeight =
                bodyBottom -
                bodyTop;


            /*
             * Keep very small price movements visible.
             */
            if (bodyHeight < 3) {

                bodyHeight = 3;

                bodyTop =
                    (
                        openY +
                        closeY
                    ) / 2 -
                    bodyHeight / 2;
            }


            ctx.fillStyle =
                bullish
                    ? "#2e8b57"
                    : "#d9534f";

            ctx.fillRect(
                x -
                    candleWidth / 2,
                bodyTop,
                candleWidth,
                bodyHeight
            );
        }
    );


    // --------------------------------------------------
    // LATEST PRICE
    // --------------------------------------------------

    const latest =
        visibleHistory[
            visibleHistory.length - 1
        ];

    const latestPrice =
        Number(latest.close);

    if (!Number.isFinite(latestPrice)) {
        return;
    }

    const latestY =
        priceToY(latestPrice);


    // Price line

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

    ctx.setLineDash([
        5,
        5
    ]);

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
window.addEventListener(
    "resize",
    drawMarketChart
);






async function loadMarketCandles(
    timeframe = currentTimeframe
) {

    console.log(
        "Loading candles:",
        timeframe
    );

    console.trace(
        "loadMarketCandles CALL STACK"
    );

    try {
        console.log("Loading candles:", timeframe);

        const response = await fetch(
            `/api/market/candles/?symbol=BTCUSDT&timeframe=${encodeURIComponent(timeframe)}&limit=100`,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        console.log("Candle API response:", result);

        candleHistory = result.data || [];

        drawMarketChart();

    } catch (error) {
        console.error(
            "Failed to load market candles:",
            error
        );
    }
}


function initTimeframeButtons() {
    const buttons =
        document.querySelectorAll(".timeframe-btn");

    console.log(
        "Timeframe buttons found:",
        buttons.length
    );

    buttons.forEach(button => {
        button.onclick = async () => {

            const timeframe =
                button.dataset.timeframe;

            console.log(
                "Timeframe clicked:",
                timeframe
            );

            currentTimeframe = timeframe;

            buttons.forEach(btn => {
                btn.classList.remove("active");
            });

            button.classList.add("active");

            await loadMarketCandles(timeframe);
        };
    });
}


if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initTimeframeButtons,
        { once: true }
    );
} else {
    initTimeframeButtons();
}


/*
 * Initial chart load — exactly once.
 */
loadMarketCandles("1m");


/*
 * Update the current selected candle.
 */
setInterval(
    updateLatestCandle,
    1000
);


async function updateLatestCandle() {

    try {

        const response = await fetch(
            `/api/market/candles/?symbol=BTCUSDT&timeframe=${encodeURIComponent(currentTimeframe)}&limit=1`,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json"
                }
            }
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result =
            await response.json();

        if (
            !result.data ||
            result.data.length === 0
        ) {
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

            if (last.time === latest.time) {

                candleHistory[
                    candleHistory.length - 1
                ] = latest;

            } else {

                candleHistory.push(latest);

                if (candleHistory.length > 100) {
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







/*
 * Keep the current candle updated.
 */

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

        

        await refreshEvents();

       
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

async function purchaseAU(amount, phone) {

    if (!amount || Number(amount) <= 0) {
        throw new Error(
            "Enter a valid purchase amount."
        );
    }

    if (!phone) {
        throw new Error(
            "Enter your M-PESA phone number."
        );
    }

    const idempotencyKey =
        generateIdempotencyKey();

    const body =
        new URLSearchParams();

    body.append(
        "amount",
        amount
    );

    body.append(
        "phone",
        phone
    );

    const response = await fetch(
        "/api/wallet/purchase/",
        {
            method: "POST",

            credentials:
                "same-origin",

            headers: {
                "X-CSRFToken":
                    getCSRFToken(),

                "Idempotency-Key":
                    idempotencyKey,

                "Accept":
                    "application/json",

                "Content-Type":
                    "application/x-www-form-urlencoded;charset=UTF-8",
            },

            body: body,
        }
    );

    const text =
        await response.text();

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

async function waitForPurchaseCompletion(
    transactionId,
    maxAttempts = 30,
    interval = 2000
) {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {

        console.log(
            `Checking M-PESA payment status (${attempt + 1}/${maxAttempts})...`
        );

        const response = await fetch(
            `/api/wallet/purchase/status/${encodeURIComponent(transactionId)}/`,
            {
                method: "GET",

                credentials: "same-origin",

                headers: {
                    "Accept": "application/json",
                },
            }
        );

        const text = await response.text();

        let data;

        try {
            data = JSON.parse(text);
        } catch (error) {
            throw new Error(
                `Payment status returned invalid response (${response.status}).`
            );
        }

        if (!response.ok || !data.success) {
            throw new Error(
                data.error ||
                "Unable to check M-PESA payment status."
            );
        }

        console.log(
            "M-PESA status:",
            data.status
        );

        /*
         * PAYMENT COMPLETED
         */
        if (data.status === "COMPLETED") {

            return data;
        }

        /*
         * PAYMENT FAILED
         */
        if (data.status === "FAILED") {

            throw new Error(
                data.message ||
                "M-PESA payment failed or was cancelled."
            );
        }

        /*
         * PAYMENT STILL PENDING
         */
        if (data.status === "PENDING") {

            const processingMessage =
                document.getElementById(
                    "paymentProcessingMessage"
                );

            if (processingMessage) {

                processingMessage.textContent =
                    "Waiting for M-PESA payment confirmation...";
            }

            await new Promise(
                resolve =>
                    setTimeout(
                        resolve,
                        interval
                    )
            );

            continue;
        }

        /*
         * UNKNOWN STATUS
         */
        throw new Error(
            `Unknown payment status: ${data.status}`
        );
    }

    throw new Error(
        "Payment confirmation timed out. Please check your M-PESA messages."
    );
}
async function confirmPurchase() {

    if (purchaseInProgress) {
        return;
    }

    const amountInput =
        document.getElementById("purchaseAmount");

    const phoneInput =
        document.getElementById("mpesaPhone");

    if (!amountInput || !phoneInput) {

        showPurchaseError(
            "Purchase amount or M-PESA phone field is missing."
        );

        return;
    }

    const amount =
        amountInput.value.trim();

    const phone =
        phoneInput.value.trim();

    if (
        !amount ||
        Number(amount) <= 0
    ) {

        showPurchaseError(
            "Enter a valid purchase amount."
        );

        return;
    }

    if (!phone) {

        showPurchaseError(
            "Enter the M-PESA phone number."
        );

        return;
    }

    purchaseInProgress = true;

    const button =
        document.getElementById(
            "confirmPurchaseButton"
        );

    if (button) {
        button.disabled = true;
    }

    const paymentStep =
        document.getElementById(
            "paymentStep"
        );

    const paymentProcessing =
        document.getElementById(
            "paymentProcessing"
        );

    if (paymentStep) {
        paymentStep.style.display = "none";
    }

    if (paymentProcessing) {
        paymentProcessing.style.display = "block";
    }

    try {

        /*
         * ==================================================
         * STEP 1
         * CREATE PENDING PURCHASE
         * ==================================================
         */

        const pendingResult =
            await purchaseAU(
                amount,
                phone
            );

        console.log(
            "M-PESA STK Push response:",
            pendingResult
        );


        /*
         * ==================================================
         * STEP 2
         * GET TRANSACTION ID
         * ==================================================
         */

        const transactionId =
            pendingResult.transaction_reference;

        if (!transactionId) {

            throw new Error(
                "Payment transaction reference was not returned."
            );
        }

        console.log(
            "Transaction:",
            transactionId
        );


        /*
         * ==================================================
         * STEP 3
         * PAYMENT MUST BE PENDING
         * ==================================================
         */

        if (
            pendingResult.payment_status !==
            "PENDING"
        ) {

            throw new Error(
                pendingResult.message ||
                "Unexpected payment status."
            );
        }


        /*
         * ==================================================
         * STEP 4
         * SHOW PROCESSING MESSAGE
         * ==================================================
         */

        const processingMessage =
            document.getElementById(
                "paymentProcessingMessage"
            );

        if (processingMessage) {

            processingMessage.textContent =
                "SIMULATION: Payment request created. Confirming payment...";
        }


        /*
         * ==================================================
         * STEP 5
         * SIMULATE DARAJA CALLBACK
         * ==================================================
         *
         * This is ONLY for the sandbox simulation.
         *
         * It calls:
         *
         * /api/mpesa/simulate-callback/
         *
         * That endpoint then calls the same
         * mpesa_callback() logic used by real Daraja.
         */

        const callbackResponse =
        await fetch(
            `/api/wallet/purchase/${encodeURIComponent(
                pendingResult.transaction_reference
            )}/simulate-callback/`,
            {
                method: "POST",

                credentials: "same-origin",

                headers: {
                    "X-CSRFToken":
                        getCSRFToken(),

                    "Accept":
                        "application/json",
                },
            }
        );


        const callbackText =
            await callbackResponse.text();

        let callbackData;

        try {

            callbackData =
                JSON.parse(
                    callbackText
                );

        } catch (error) {

            throw new Error(
                `Callback failed (${callbackResponse.status}): ${callbackText}`
            );
        }


        if (
            !callbackResponse.ok ||
            !callbackData.success
        ) {

            throw new Error(
                callbackData.error ||
                "Simulated payment failed."
            );
        }


        console.log(
            "Simulated payment completed:",
            callbackData
        );


        /*
         * ==================================================
         * STEP 6
         * CHECK DATABASE STATUS
         * ==================================================
         *
         * The callback should now have changed:
         *
         * PENDING → COMPLETED
         */

        const statusResponse =
        await fetch(
            `/api/wallet/purchase/status/${encodeURIComponent(
                transactionId
            )}/`,
            {
                method: "GET",

                credentials: "same-origin",

                headers: {
                    "Accept": "application/json",
                },
            }
        );


        const statusText =
            await statusResponse.text();

        let statusData;

        try {

            statusData =
                JSON.parse(
                    statusText
                );

        } catch (error) {

            throw new Error(
                `Status check failed (${statusResponse.status}): ${statusText}`
            );
        }


        if (
            !statusResponse.ok ||
            !statusData.success
        ) {

            throw new Error(
                statusData.error ||
                "Unable to verify payment status."
            );
        }


        console.log(
            "Purchase status:",
            statusData
        );


        /*
         * ==================================================
         * STEP 7
         * VERIFY COMPLETED
         * ==================================================
         */

        if (
            statusData.status ===
            "COMPLETED"
        ) {

            showPurchaseSuccess({
                ...pendingResult,

                ...statusData,

                payment_status:
                    "COMPLETED",

                au_amount:
                    statusData.au_amount,
            });


            /*
             * Refresh wallet/portfolio
             */

            await updatePortfolio();


            /*
             * Refresh payments
             */

            if (
                typeof loadPayments ===
                "function"
            ) {

                await loadPayments();
            }


            /*
             * Refresh events
             */

            if (
                typeof loadEvents ===
                "function"
            ) {

                await loadEvents();
            }


            return;
        }


        /*
         * ==================================================
         * STEP 8
         * FAILED / UNEXPECTED STATUS
         * ==================================================
         */

        if (
            statusData.status ===
            "FAILED"
        ) {

            throw new Error(
                statusData.message ||
                "M-PESA payment failed."
            );
        }


        throw new Error(
            statusData.message ||
            `Payment is still ${statusData.status}.`
        );


    } catch (error) {

        console.error(
            "Purchase failed:",
            error
        );

        showPurchaseError(
            error.message ||
            "Payment could not be completed."
        );

    } finally {

        purchaseInProgress = false;

        if (button) {
            button.disabled = false;
        }
    }
}
function showPurchaseSuccess(result) {

    document.getElementById(
        "paymentProcessing"
    ).style.display = "none";

    document.getElementById(
        "paymentError"
    ).style.display = "none";

    document.getElementById(
        "paymentSuccess"
    ).style.display = "block";

    const auAmount =
        result.au_amount || "0";

    const successAuAmount =
        document.getElementById(
            "successAuAmount"
        );

    if (successAuAmount) {

        successAuAmount.textContent =
            Number(auAmount).toFixed(8);
    }

    console.log(
        "M-PESA receipt:",
        result.receipt
    );
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
async function withdrawAU(amount, phone, idempotencyKey) {

    const response = await fetch(
        "/api/withdraw/",
        {
            method: "POST",

            credentials: "same-origin",

            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",

                "Idempotency-Key":
                    idempotencyKey,

                "X-CSRFToken":
                    getCSRFToken()
            },

            body: JSON.stringify({
                au_amount: String(amount),
                phone: phone
            })
        }
    );

    const text = await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch (error) {

        throw new Error(
            `Withdrawal request returned HTTP ${response.status}: ${text}`
        );
    }

    if (!response.ok || !data.success) {

        throw new Error(
            data.error ||
            data.message ||
            "Withdrawal failed."
        );
    }

    return data;
}






async function handleWithdrawal() {

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

        alert(
            "Enter a valid AU amount."
        );

        return;
    }

    if (!phone) {

        alert(
            "Enter an M-Pesa number."
        );

        return;
    }

    /*
     * Only allow the confirmed amount
     * to be submitted.
     */

    if (!withdrawalAmountConfirmed) {

        alert(
            "Please confirm the withdrawal amount first."
        );

        return;
    }

    /*
     * Lock withdrawal.
     */

    withdrawalInProgress = true;

    button.disabled = true;
    button.textContent = "Processing...";

    if (status) {

        status.textContent =
            "Creating withdrawal request...";
    }

    const idempotencyKey =
        generateIdempotencyKey();

    try {

        /*
         * ==================================================
         * STEP 1
         * CREATE PENDING WITHDRAWAL
         * ==================================================
         */

        const pendingResult =
            await withdrawAU(
                confirmedWithdrawalAmount,
                phone,
                idempotencyKey
            );

        console.log(
            "Withdrawal created:",
            pendingResult
        );

        /*
         * Must be PENDING.
         */

        if (
            pendingResult.payment_status !==
            "PENDING"
        ) {

            throw new Error(
                pendingResult.message ||
                "Unexpected withdrawal status."
            );
        }

        const transactionId =
            pendingResult.transaction_reference;

        if (!transactionId) {

            throw new Error(
                "Withdrawal transaction reference was not returned."
            );
        }

        console.log(
            "Withdrawal transaction:",
            transactionId
        );

        /*
         * ==================================================
         * STEP 2
         * SHOW PROCESSING
         * ==================================================
         */

        if (status) {

            status.textContent =
                "Withdrawal request created. Processing simulated M-PESA payout...";
        }

        /*
         * ==================================================
         * STEP 3
         * SIMULATE M-PESA CALLBACK
         * ==================================================
         */

        const callbackResponse =
            await fetch(
                `/api/withdraw/${encodeURIComponent(
                    transactionId
                )}/simulate-callback/`,
                {
                    method: "POST",

                    credentials:
                        "same-origin",

                    headers: {
                        "X-CSRFToken":
                            getCSRFToken(),

                        "Accept":
                            "application/json",
                    },
                }
            );

        const callbackText =
            await callbackResponse.text();

        let callbackData;

        try {

            callbackData =
                JSON.parse(callbackText);

        } catch (error) {

            throw new Error(
                `Withdrawal callback failed (${callbackResponse.status}): ${callbackText}`
            );
        }

        if (
            !callbackResponse.ok ||
            !callbackData.success
        ) {

            throw new Error(
                callbackData.error ||
                "Simulated withdrawal failed."
            );
        }

        console.log(
            "Withdrawal callback completed:",
            callbackData
        );

        /*
         * ==================================================
         * STEP 4
         * CHECK FINAL DATABASE STATUS
         * ==================================================
         */

        const statusResponse =
            await fetch(
                `/api/withdraw/status/${encodeURIComponent(
                    transactionId
                )}/`,
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    headers: {
                        "Accept":
                            "application/json",
                    },
                }
            );

        const statusText =
            await statusResponse.text();

        let statusData;

        try {

            statusData =
                JSON.parse(statusText);

        } catch (error) {

            throw new Error(
                `Withdrawal status check failed (${statusResponse.status}): ${statusText}`
            );
        }

        if (
            !statusResponse.ok ||
            !statusData.success
        ) {

            throw new Error(
                statusData.error ||
                "Unable to verify withdrawal status."
            );
        }

        console.log(
            "Withdrawal status:",
            statusData
        );

        /*
         * ==================================================
         * STEP 5
         * VERIFY COMPLETED
         * ==================================================
         */

        if (
            statusData.status ===
            "COMPLETED"
        ) {

            if (status) {

                status.textContent =
                    "Withdrawal completed successfully.";
            }

            console.log(
                "Withdrawal completed:",
                statusData
            );

            /*
             * Refresh wallet.
             */

            await updatePortfolio();

            /*
             * Refresh withdrawal estimate.
             */

            await updateWithdrawalEstimate();

            /*
             * Refresh transaction history.
             */

            if (
                typeof loadPayments ===
                "function"
            ) {

                await loadPayments();
            }

            if (
                typeof loadEvents ===
                "function"
            ) {

                await loadEvents();
            }

            return;
        }

        /*
         * ==================================================
         * STEP 6
         * FAILED
         * ==================================================
         */

        if (
            statusData.status ===
            "FAILED"
        ) {

            throw new Error(
                statusData.message ||
                "Withdrawal failed."
            );
        }

        throw new Error(
            statusData.message ||
            `Withdrawal is still ${statusData.status}.`
        );

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

function closeWithdrawalModalAfterSuccess() {

    const panel =
        document.getElementById(
            "withdrawalPanel"
        );

    const toggleButton =
        document.getElementById(
            "withdrawToggleButton"
        );

    if (panel) {
        panel.style.display = "none";
    }

    if (toggleButton) {
        toggleButton.textContent =
            "Withdraw AU";
    }

    console.log(
        "Withdrawal panel closed after successful withdrawal."
    );
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
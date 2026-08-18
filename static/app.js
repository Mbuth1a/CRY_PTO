function csrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}

const priceHistory = [];
const MAX_POINTS = 60;
let candleHistory = [];
let tickCount = 0;

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

async function deposit(provider) {
    const amount = document.getElementById('depositAmount').value;
    const result = await postForm('/api/deposit/', {provider, amount});
    alert(JSON.stringify(result));
    location.reload();
}

async function withdraw(provider) {
    const amount = document.getElementById('withdrawAmount').value;
    const result = await postForm('/api/withdraw/', {provider, amount});
    alert(JSON.stringify(result));
    location.reload();
}


async function openTrade() {

    if (activePosition !== null) {
        alert("You already have an open position.");
        return;
    }

    if (!currentMarketPrice || currentMarketPrice <= 0) {
        alert("Market price is not available yet.");
        return;
    }

    const amount = Number(
        document.getElementById("tradeAmount").value
    );

    const side =
        document.getElementById("side").value;

    if (!amount || amount <= 0) {
        alert("Enter a valid trade amount.");
        return;
    }

    // Calculate BTC quantity from the current market price
    const quantity =
        amount / currentMarketPrice;

    activePosition = {
        side: side,
        amount: amount,
        quantity: quantity,
        entryPrice: currentMarketPrice,
        openedAt: new Date()
    };

    updatePositionDisplay();

    document.getElementById("positionStatus").textContent =
        `OPEN ${side}`;

    document.getElementById("positionStatus").style.backgroundColor =
        side === "LONG" ? "#198754" : "#dc3545";

    document.getElementById("orderPanel").style.opacity =
        "0.6";

    console.log("Synthetic position opened:", activePosition);
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

async function convertKes() {
    const amount =
        document.getElementById('convertAmount').value;

    const result = await postForm(
        '/api/convert/',
        { amount }
    );

    alert(JSON.stringify(result));

    location.reload();
}

async function closePosition() {
    const quantity = document.getElementById('quantity').value;
    const side = document.getElementById('side').value;

    // Send a POST request to your backend to settle the trade and update the balance
    const result = await postForm('/api/close-position/', {
        side: side,       // Needed to know if closing a buy or sell
        quantity: quantity
    });

    alert(JSON.stringify(result));
    location.reload();
}

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


function openTradeModal() {

    const modal =
        document.getElementById("tradeModal");

    modal.style.display = "flex";

    updateTradePreview();

    selectTradeSide(selectedTradeSide);
}


function closeTradeModal() {

    document.getElementById("tradeModal")
        .style.display = "none";
}

function selectTradeSide(side) {

    selectedTradeSide = side;

    const longButton =
        document.getElementById("longButton");

    const shortButton =
        document.getElementById("shortButton");

    longButton.classList.remove("selected");
    shortButton.classList.remove("selected");

    if (side === "LONG") {

        longButton.classList.add("selected");

    } else {

        shortButton.classList.add("selected");
    }

    document.getElementById("confirmTradeButton")
        .textContent =
        `Open ${side} Trade`;
}

function updateTradePreview() {

    const amount =
        Number(
            document.getElementById(
                "tradeAmount"
            ).value
        );

    const price =
        Number(currentMarketPrice);

    document.getElementById(
        "modalMarketPrice"
    ).textContent =
        price > 0
            ? price.toFixed(2)
            : "--";

    if (
        !price ||
        price <= 0 ||
        !amount ||
        amount <= 0
    ) {

        document.getElementById(
            "estimatedQuantity"
        ).textContent = "--";

        document.getElementById(
            "estimatedEntryPrice"
        ).textContent = "--";

        return;
    }

    const quantity =
        amount / price;

    document.getElementById(
        "estimatedQuantity"
    ).textContent =
        quantity.toFixed(8) +
        " BTC";

    document.getElementById(
        "estimatedEntryPrice"
    ).textContent =
        price.toFixed(2) +
        " USDT";
}

async function confirmOpenTrade() {

    if (activePosition !== null) {

        alert(
            "You already have an open position."
        );

        return;
    }

    const amount =
        Number(
            document.getElementById(
                "tradeAmount"
            ).value
        );

    if (!amount || amount <= 0) {

        alert(
            "Enter a valid USDT trade amount."
        );

        return;
    }

    if (
        !currentMarketPrice ||
        currentMarketPrice <= 0
    ) {

        alert(
            "The synthetic market is not available yet."
        );

        return;
    }

    /*
     * Quantity is calculated from the current
     * displayed market price ONLY for the order request.
     *
     * The server determines the authoritative
     * entry price.
     */

    const quantity =
        amount / currentMarketPrice;

    const button =
        document.getElementById(
            "confirmTradeButton"
        );

    button.disabled = true;

    button.textContent =
        "Opening...";

    try {

        const result =
            await positionRequest(
                "POST",
                {
                    quantity:
                        quantity.toFixed(8),

                    side:
                        selectedTradeSide
                }
            );

        /*
         * IMPORTANT:
         *
         * Use the price returned by Django.
         */

        const position =
            result.position;

        activePosition = {

            id: position.id,

            side: position.side,

            quantity:
                Number(position.quantity),

            entryPrice:
                Number(position.entry_price),

            amount:
                Number(position.quantity) *
                Number(position.entry_price),

            openedAt:
                new Date(position.opened_at)
        };

        closeTradeModal();

        displayActivePosition();

        await updatePosition();

    } catch (error) {

        console.error(
            "Failed to open trade:",
            error
        );

        alert(
            "Unable to open trade: " +
            error.message
        );

    } finally {

        button.disabled = false;

        button.textContent =
            `Open ${selectedTradeSide} Trade`;
    }
}
function displayActivePosition() {

    if (!activePosition) {

        document.getElementById(
            "activePosition"
        ).style.display = "none";

        return;
    }

    const position =
        activePosition;

    document.getElementById(
        "activePosition"
    ).style.display = "block";

    document.getElementById(
        "positionStatus"
    ).textContent =
        "OPEN " + position.side;

    document.getElementById(
        "activeSide"
    ).textContent =
        position.side;

    document.getElementById(
        "positionAmount"
    ).textContent =
        position.amount.toFixed(2) +
        " USDT";

    document.getElementById(
        "positionQuantity"
    ).textContent =
        position.quantity.toFixed(8) +
        " BTC";

    document.getElementById(
        "entryPrice"
    ).textContent =
        position.entryPrice.toFixed(2) +
        " USDT";

    document.getElementById(
        "positionOpenedAt"
    ).textContent =
        position.openedAt.toLocaleTimeString();
}

async function closeTrade() {

    if (!activePosition) {

        alert(
            "There is no open position."
        );

        return;
    }

    const button =
        document.getElementById(
            "closeTradeButton"
        );

    if (!confirm(
        "Are you sure you want to close this trade?"
    )) {

        return;
    }

    button.disabled = true;

    button.textContent =
        "Closing...";

    try {

        const result =
            await positionRequest(
                "DELETE"
            );

        const closed =
            result.position;

        /*
         * EXIT PRICE comes from Django.
         */

        const exitPrice =
            Number(
                closed.exit_price
            );

        const realizedPnl =
            Number(
                closed.realized_pnl
            );

        /*
         * Show final result before clearing.
         */

        alert(
            "Trade closed.\n\n" +
            "Exit Price: " +
            exitPrice.toFixed(2) +
            " USDT\n" +
            "Realized P&L: " +
            realizedPnl.toFixed(2) +
            " USDT"
        );

        activePosition = null;

        document.getElementById(
            "activePosition"
        ).style.display = "none";

        document.getElementById(
            "positionStatus"
        ).textContent =
            "NO POSITION";

        document.getElementById(
            "positionStatus"
        ).style.backgroundColor =
            "";

        await updatePosition();

    } catch (error) {

        console.error(
            "Failed to close trade:",
            error
        );

        alert(
            "Unable to close trade: " +
            error.message
        );

    } finally {

        button.disabled = false;

        button.textContent =
            "Close Trade";
    }
}

async function updatePosition() {

    try {

        const result =
            await positionRequest(
                "GET"
            );

        if (!result.open) {

            activePosition = null;

            document.getElementById(
                "activePosition"
            ).style.display = "none";

            document.getElementById(
                "positionStatus"
            ).textContent =
                "NO POSITION";

            return;
        }

        const position =
            result.position;

        /*
         * Synchronize the browser with
         * the server's position.
         */

        activePosition = {

            id: position.id,

            side: position.side,

            quantity:
                Number(position.quantity),

            entryPrice:
                Number(position.entry_price),

            amount:
                Number(position.quantity) *
                Number(position.entry_price),

            openedAt:
                new Date(position.opened_at)
        };

        displayActivePosition();

        /*
         * SERVER AUTHORITATIVE CURRENT PRICE
         */

        const currentPrice =
            Number(
                position.current_price
            );

        const pnl =
            Number(
                position.unrealized_pnl
            );

        const pnlPercent =
            Number(
                position.pnl_percent
            );

        document.getElementById(
            "currentPositionPrice"
        ).textContent =
            currentPrice.toFixed(2) +
            " USDT";

        document.getElementById(
            "currentValue"
        ).textContent =
            Number(
                position.current_value
            ).toFixed(2) +
            " USDT";

        document.getElementById(
            "unrealizedPnl"
        ).textContent =
            pnl.toFixed(2) +
            " USDT";

        document.getElementById(
            "pnlPercent"
        ).textContent =
            pnlPercent.toFixed(2) +
            "%";

        /*
         * Visual P&L state
         */

        const pnlElement =
            document.getElementById(
                "unrealizedPnl"
            );

        const percentElement =
            document.getElementById(
                "pnlPercent"
            );

        if (pnl > 0) {

            pnlElement.style.color =
                "#198754";

            percentElement.style.color =
                "#198754";

        } else if (pnl < 0) {

            pnlElement.style.color =
                "#dc3545";

            percentElement.style.color =
                "#dc3545";

        } else {

            pnlElement.style.color =
                "#666";

            percentElement.style.color =
                "#666";
        }

    } catch (error) {

        console.error(
            "Position update failed:",
            error
        );
    }
}

setInterval(
    updatePosition,
    1000
);

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

async function positionRequest(method, body = null) {

    const headers = {
        "Accept": "application/json",
        "X-CSRFToken": getCsrfToken()
    };

    const options = {
        method: method,
        headers: headers,
        credentials: "same-origin"
    };

    if (body) {

        options.body =
            new URLSearchParams(body);

        headers["Content-Type"] =
            "application/x-www-form-urlencoded";
    }

    const response =
        await fetch(
            "/api/position/",
            options
        );

    const data =
        await response.json();

    if (!response.ok) {

        throw new Error(
            data.error ||
            `HTTP ${response.status}`
        );
    }

    return data;
}
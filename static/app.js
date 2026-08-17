function csrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}

const priceHistory = [];
const MAX_POINTS = 60;

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

    if (priceHistory.length === 0) {
        ctx.fillText("Waiting for market data...", 20, 30);
        return;
    }

    const prices = priceHistory.map(point => point.price);

    let minPrice = Math.min(...prices);
    let maxPrice = Math.max(...prices);

    // Prevent a completely flat chart
    if (minPrice === maxPrice) {
        minPrice -= 1;
        maxPrice += 1;
    }

    const padding = 45;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Grid
    ctx.strokeStyle = "#dddddd";
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {
        const y = padding + (chartHeight / 4) * i;

        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(width - padding, y);
        ctx.stroke();

        const value =
            maxPrice -
            ((maxPrice - minPrice) / 4) * i;

        ctx.fillStyle = "#666";
        ctx.font = "11px Arial";

        ctx.fillText(
            value.toFixed(2),
            5,
            y + 4
        );
    }

    // Price line
    ctx.beginPath();

    priceHistory.forEach((point, index) => {
        const x =
            padding +
            (index / Math.max(priceHistory.length - 1, 1)) *
            chartWidth;

        const y =
            padding +
            ((maxPrice - point.price) /
                (maxPrice - minPrice)) *
            chartHeight;

        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });

    ctx.strokeStyle = "#ff8c00";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Latest price point
    const latest = priceHistory[priceHistory.length - 1];

    const latestX =
        padding +
        ((priceHistory.length - 1) /
            Math.max(priceHistory.length - 1, 1)) *
        chartWidth;

    const latestY =
        padding +
        ((maxPrice - latest.price) /
            (maxPrice - minPrice)) *
        chartHeight;

    ctx.beginPath();
    ctx.arc(latestX, latestY, 4, 0, Math.PI * 2);

    ctx.fillStyle = "#ff8c00";
    ctx.fill();
}
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

window.addEventListener('load', async () => {
    await refreshMarket();
    await refreshEvents();
});

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
            document.getElementById("tradeAmount").value
        );

    const price =
        Number(currentMarketPrice);

    document.getElementById("modalMarketPrice")
        .textContent =
        price > 0
            ? price.toFixed(2)
            : "--";

    if (!price || price <= 0 || !amount || amount <= 0) {

        document.getElementById("estimatedQuantity")
            .textContent = "--";

        document.getElementById("estimatedEntryPrice")
            .textContent = "--";

        return;
    }

    const quantity =
        amount / price;

    document.getElementById("estimatedQuantity")
        .textContent =
        quantity.toFixed(8) + " BTC";

    document.getElementById("estimatedEntryPrice")
        .textContent =
        price.toFixed(2) + " USDT";
}

function confirmOpenTrade() {

    if (!currentMarketPrice ||
        currentMarketPrice <= 0) {

        alert(
            "The synthetic market is not available yet."
        );

        return;
    }

    const amount =
        Number(
            document.getElementById("tradeAmount").value
        );

    if (!amount || amount <= 0) {

        alert(
            "Enter a valid USDT trade amount."
        );

        return;
    }

    if (activePosition !== null) {

        alert(
            "You already have an open position."
        );

        return;
    }

    const quantity =
        amount / currentMarketPrice;

    activePosition = {

        side: selectedTradeSide,

        amount: amount,

        quantity: quantity,

        entryPrice: currentMarketPrice,

        openedAt: new Date()
    };

    console.log(
        "Synthetic trade opened:",
        activePosition
    );

    closeTradeModal();

    displayActivePosition();

    updatePosition();
}

function displayActivePosition() {

    const position =
        activePosition;

    if (!position) {
        return;
    }

    document.getElementById("activePosition")
        .style.display = "block";

    document.getElementById("positionStatus")
        .textContent =
        "OPEN " + position.side;

    document.getElementById("activeSide")
        .textContent =
        position.side;

    document.getElementById("positionAmount")
        .textContent =
        position.amount.toFixed(2) +
        " USDT";

    document.getElementById("positionQuantity")
        .textContent =
        position.quantity.toFixed(8) +
        " BTC";

    document.getElementById("entryPrice")
        .textContent =
        position.entryPrice.toFixed(2) +
        " USDT";

    document.getElementById("positionOpenedAt")
        .textContent =
        position.openedAt.toLocaleTimeString();
}



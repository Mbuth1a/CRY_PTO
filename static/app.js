function csrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}

async function refreshMarket() {
    const response = await fetch('/api/market/');
    const data = await response.json();

    document.getElementById('price').textContent = data.price;
    drawChart(data.history);
    await refreshEvents();
}

function drawChart(history) {
    const canvas = document.getElementById('chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!history.length) return;

    const values = history.map(x => Number(x.price));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    ctx.beginPath();

    history.forEach((point, i) => {
        const x = 20 + i * ((canvas.width - 40) / Math.max(history.length - 1, 1));
        const y = canvas.height - 20 - ((Number(point.price) - min) / range) * (canvas.height - 40);

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    ctx.stroke();
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

async function openPosition() {
    const quantity = document.getElementById('quantity').value;
    const side = document.getElementById('side').value;

    const result = await postForm('/api/position/', {quantity, side});
    alert(JSON.stringify(result));
    await refreshEvents();
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
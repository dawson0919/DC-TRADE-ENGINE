/* ════════════════════════════════════════════════
   Dashboard Overview
════════════════════════════════════════════════ */
async function loadDashboard() {
    try {
        const resp = await authFetch('/api/bots');
        if (!resp.ok) return;  // Auth failed — keep existing display
        const bots = await resp.json();
        if (!Array.isArray(bots)) return;

        // Skip re-render if data unchanged (prevents flicker)
        const hash = JSON.stringify(bots.map(b => [b.bot_id, b.status, b.total_pnl, b.total_trades, b.win_rate, b.position]));
        if (hash === _dashLastHash) return;
        _dashLastHash = hash;

        // Calculate stats
        let totalAllocation = 0;
        let totalPnl = 0;
        let totalUnrealizedPnl = 0;
        let activeBots = 0;
        let totalTrades = 0;
        let totalWins = 0;
        let totalTradesForWR = 0;

        bots.forEach(b => {
            totalAllocation += b.capital;
            totalPnl += b.total_pnl;
            if (b.position && b.position.unrealized_pnl_usd != null) {
                totalUnrealizedPnl += b.position.unrealized_pnl_usd;
            }
            if (b.status === 'running') activeBots++;
            totalTrades += b.total_trades;
            if (b.total_trades > 0) {
                totalWins += Math.round(b.win_rate / 100 * b.total_trades);
                totalTradesForWR += b.total_trades;
            }
        });

        const avgWinRate = totalTradesForWR > 0 ? (totalWins / totalTradesForWR * 100) : 0;
        const combinedPnl = totalPnl + totalUnrealizedPnl;
        const pnlPct = totalAllocation > 0 ? (combinedPnl / totalAllocation * 100) : 0;

        // Update stat cards
        document.getElementById('dash-allocation').textContent = '$' + totalAllocation.toLocaleString();
        const pnlEl = document.getElementById('dash-pnl');
        pnlEl.textContent = (combinedPnl >= 0 ? '+' : '') + '$' + combinedPnl.toFixed(2);
        pnlEl.style.color = combinedPnl >= 0 ? '#00c853' : '#ff1744';

        // Breakdown: realized + unrealized
        const bkEl = document.getElementById('dash-pnl-breakdown');
        const rSign = totalPnl >= 0 ? '+' : '';
        const uSign = totalUnrealizedPnl >= 0 ? '+' : '';
        const rColor = totalPnl >= 0 ? '#00c853' : '#ff1744';
        const uColor = totalUnrealizedPnl >= 0 ? '#00c853' : totalUnrealizedPnl < 0 ? '#ff1744' : '#6b7280';
        bkEl.innerHTML = '<span style="color:' + rColor + ';">已實現 ' + rSign + '$' + totalPnl.toFixed(2) + '</span>' +
            ' | <span style="color:' + uColor + ';">未實現 ' + uSign + '$' + totalUnrealizedPnl.toFixed(2) + '</span>';

        document.getElementById('dash-active-bots').textContent = activeBots;
        document.getElementById('dash-winrate').textContent = avgWinRate.toFixed(1) + '%';

        // Summary bar
        document.getElementById('dash-total-trades').textContent = totalTrades;
        document.getElementById('dash-total-winrate').textContent = avgWinRate.toFixed(1) + '%';
        const totalPnlEl = document.getElementById('dash-total-pnl');
        totalPnlEl.textContent = (totalPnl >= 0 ? '+' : '') + '$' + totalPnl.toFixed(2);
        totalPnlEl.style.color = totalPnl >= 0 ? '#00c853' : '#ff1744';
        const uPnlEl = document.getElementById('dash-unrealized-pnl');
        uPnlEl.textContent = (totalUnrealizedPnl >= 0 ? '+' : '') + '$' + totalUnrealizedPnl.toFixed(2);
        uPnlEl.style.color = totalUnrealizedPnl >= 0 ? '#00c853' : totalUnrealizedPnl < 0 ? '#ff1744' : '#6b7280';

        // Render PnL chart (flat line if no data)
        renderDashPnlChart(combinedPnl, totalAllocation);

        // Render bot list (default: show all)
        _dashAllBots = bots;
        filterDashBots('all');

    } catch (err) {
        console.error('Dashboard load error:', err);
    }
}

function renderDashPnlChart(totalPnl, totalAllocation) {
    const ctx = document.getElementById('dashPnlChart').getContext('2d');
    if (dashChart) dashChart.destroy();
    // Simple flat equity line for now (will be real-time with trade history)
    const startVal = totalAllocation > 0 ? totalAllocation : 10000;
    const endVal = startVal + totalPnl;
    const points = [];
    const labels = [];
    for (let i = 0; i < 30; i++) {
        const val = startVal + (totalPnl / 29) * i;
        points.push(val);
        const d = new Date();
        d.setDate(d.getDate() - (29 - i));
        labels.push(d.toISOString().slice(5, 10));
    }
    const lineColor = totalPnl >= 0 ? '#00c853' : '#ff1744';
    const bgColor = totalPnl >= 0 ? 'rgba(0,200,83,0.1)' : 'rgba(255,23,68,0.1)';
    dashChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: points,
                borderColor: lineColor,
                backgroundColor: bgColor,
                fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: true, grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280', maxTicksLimit: 6, font: { size: 10 } } },
                y: { display: true, grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280', font: { size: 10 } } },
            },
            interaction: { intersect: false, mode: 'index' },
        },
    });
}

let _dashAllBots = [];
let _dashLastHash = '';
function filterDashBots(filter) {
    document.querySelectorAll('.dash-bot-tab').forEach(btn => btn.classList.remove('active'));
    const tabs = document.querySelectorAll('.dash-bot-tab');
    if (filter === 'running' && tabs[0]) tabs[0].classList.add('active');
    if (filter === 'all' && tabs[1]) tabs[1].classList.add('active');
    const filtered = filter === 'running' ? _dashAllBots.filter(b => b.status === 'running') : _dashAllBots;
    renderDashBotList(filtered);
}

function renderDashBotList(bots) {
    const container = document.getElementById('dash-bot-list');
    if (bots.length === 0) {
        container.innerHTML = '<div class="dash-empty">' +
            '<p style="font-size:1.1rem;font-weight:600;">尚無機器人</p>' +
            '<p>建立你的第一個自動交易機器人</p>' +
            '<button class="btn btn-sm btn-accent" style="margin-top:12px;" onclick="switchTab(\'bots\');showCreateBotModal();">建立機器人</button>' +
            '</div>';
        return;
    }
    let html = '';
    bots.forEach(bot => {
        const statusColor = bot.status === 'running' ? '#00c853' : bot.status === 'error' ? '#ff1744' : '#6b7280';
        const statusLabel = bot.status === 'running' ? '運行中' : bot.status === 'error' ? '錯誤' : '已停止';
        const pnlColor = bot.total_pnl > 0 ? '#00c853' : bot.total_pnl < 0 ? '#ff1744' : '#6b7280';
        const isWebhook = bot.signal_source === 'webhook';
        const sourceLabel = isWebhook ? 'Webhook' : bot.strategy;
        const pos = bot.position;
        let dashPosHtml = '';
        if (pos) {
            const sideL = pos.side === 'long' ? 'LONG' : 'SHORT';
            const sideC = pos.side === 'long' ? '#00c853' : '#ff1744';
            const uC = pos.unrealized_pnl_usd > 0 ? '#00c853' : pos.unrealized_pnl_usd < 0 ? '#ff1744' : '#6b7280';
            dashPosHtml = '<div style="margin-top:4px;font-size:0.8rem;">' +
                '<span style="color:' + sideC + ';font-weight:700;">' + sideL + '</span>' +
                ' @ $' + pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) +
                ' <span style="color:' + uC + ';font-weight:600;">' + (pos.unrealized_pnl_usd >= 0 ? '+' : '') + '$' + pos.unrealized_pnl_usd.toFixed(2) + '</span>' +
                '</div>';
        }
        html += '<div class="dash-bot-item">' +
            '<div class="dash-bot-item-header">' +
            '<div class="dash-bot-item-name">' +
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:8px;"></span>' +
            bot.name +
            '<span class="badge ' + (bot.paper_mode ? 'badge-paper' : 'badge-live') + '">' + (bot.paper_mode ? '模擬' : '即時') + '</span>' +
            (isWebhook ? '<span class="badge badge-webhook">WH</span>' : '') +
            '</div>' +
            '<span style="font-size:0.8rem;color:#6b7280;">' + sourceLabel + ' | ' + bot.symbol + '</span>' +
            '</div>' +
            '<div class="dash-bot-item-stats">' +
            '<div><span>損益: </span><strong style="color:' + pnlColor + ';">' + (bot.total_pnl >= 0 ? '+' : '') + '$' + bot.total_pnl.toFixed(2) + '</strong></div>' +
            '<div><span>交易: </span><strong>' + bot.total_trades + '</strong></div>' +
            '<div><span>勝率: </span><strong>' + bot.win_rate.toFixed(1) + '%</strong></div>' +
            '<div><span>狀態: </span><strong style="color:' + statusColor + ';">' + statusLabel + '</strong></div>' +
            '</div>' +
            dashPosHtml +
            '</div>';
    });
    container.innerHTML = html;
}

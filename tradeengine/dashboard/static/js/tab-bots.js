/* ════════════════════════════════════════════════
   Tab 3: Bots
════════════════════════════════════════════════ */
let _botsLastHash = '';
async function loadBots(force) {
    const container = document.getElementById('bots-list');
    try {
        const resp = await authFetch('/api/bots');
        if (!resp.ok) return;  // Auth failed — keep existing display
        const bots = await resp.json();
        // Sort: live bots first, then paper; within each group: running first
        bots.sort((a, b) => {
            if (a.paper_mode !== b.paper_mode) return a.paper_mode ? 1 : -1;
            if (a.status !== b.status) {
                if (a.status === 'running') return -1;
                if (b.status === 'running') return 1;
            }
            return 0;
        });
        // Skip re-render if data unchanged (prevents flicker on auto-refresh)
        if (!force) {
            const bHash = JSON.stringify(bots.map(b => [b.bot_id, b.status, b.total_pnl, b.total_trades, b.win_rate, b.position, b.leverage, b.missed_signal]));
            if (bHash === _botsLastHash) return;
            _botsLastHash = bHash;
        }
        if (bots.length === 0) {
            container.innerHTML = '<div class="loading">尚無機器人，點擊「+ 新增機器人」建立</div>';
            return;
        }
        let html = '<div style="display:grid;gap:16px;">';
        bots.forEach(bot => {
            const statusLabel = bot.status === 'running' ? '運行中' : bot.status === 'error' ? '錯誤' : '已停止';
            const statusClass = bot.status === 'running' ? 'badge-running' : bot.status === 'error' ? 'badge-error' : 'badge-stopped';
            const modeClass = bot.paper_mode ? 'badge-paper' : 'badge-live';
            const isWebhook = bot.signal_source === 'webhook';
            const pnlColor = bot.total_pnl > 0 ? '#00e676' : bot.total_pnl < 0 ? '#ff1744' : '#e7e9ea';
            const pnlSign = bot.total_pnl > 0 ? '+' : '';
            const infoLine = isWebhook
                ? 'Webhook | ' + bot.symbol + ' | $' + bot.capital.toLocaleString() + (bot.leverage > 1 ? ' | ' + bot.leverage + 'x' : '')
                : bot.strategy + ' | ' + bot.symbol + ' | ' + bot.timeframe + ' | $' + bot.capital.toLocaleString() + (bot.leverage > 1 ? ' | ' + bot.leverage + 'x' : '');
            // Missed signal info
            const ms = bot.missed_signal;
            let missedHtml = '';
            if (ms && !_dismissedSignals.has(bot.bot_id)) {
                const msLabel = ms.side === 'long' ? '做多 LONG' : '做空 SHORT';
                const msColor = ms.side === 'long' ? '#00e676' : '#ff1744';
                const msTime = new Date(ms.signal_time).toLocaleString('zh-TW');
                const msPrice = parseFloat(ms.signal_price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 });
                const msCurPrice = parseFloat(ms.current_price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 });
                missedHtml = '<div style="margin-top:8px;padding:12px;background:linear-gradient(135deg,#1a1200,#1e1800);border:1px solid #f7931a44;border-radius:8px;">' +
                    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">' +
                    '<span style="color:#f7931a;font-weight:700;">&#9888; 未執行信號</span>' +
                    '<span style="background:' + msColor + '22;color:' + msColor + ';padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.8rem;">' + msLabel + '</span>' +
                    '<span style="color:#6b7280;font-size:0.75rem;">' + ms.candles_ago + ' 根 K 線前</span>' +
                    '</div>' +
                    '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">信號時間</div><div style="font-size:0.85rem;">' + msTime + '</div></div>' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">信號價格</div><div style="font-size:0.85rem;">$' + msPrice + '</div></div>' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">目前價格</div><div style="font-size:0.85rem;">$' + msCurPrice + '</div></div>' +
                    '</div>' +
                    '<div style="display:flex;gap:8px;">' +
                    '<button class="btn btn-sm" style="background:#f7931a;color:#000;font-weight:700;" onclick="forceEntry(\'' + bot.bot_id + '\',\'' + ms.side + '\')">強制市價進場</button>' +
                    '<button class="btn btn-sm btn-secondary" onclick="dismissMissedSignal(\'' + bot.bot_id + '\')">略過</button>' +
                    '</div>' +
                    '</div>';
            }
            // Position info
            const pos = bot.position;
            let posHtml = '';
            if (pos) {
                const sideLabel = pos.side === 'long' ? 'LONG' : 'SHORT';
                const sideColor = pos.side === 'long' ? '#00e676' : '#ff1744';
                const upnlColor = pos.unrealized_pnl_usd > 0 ? '#00e676' : pos.unrealized_pnl_usd < 0 ? '#ff1744' : '#e7e9ea';
                const upnlSign = pos.unrealized_pnl_usd > 0 ? '+' : '';
                posHtml = '<div style="margin-top:8px;padding:10px 12px;background:linear-gradient(135deg,#0d1117,#161b22);border:1px solid ' + sideColor + '33;border-radius:8px;">' +
                    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">' +
                    '<span style="background:' + sideColor + '22;color:' + sideColor + ';padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.8rem;">' + sideLabel + '</span>' +
                    '<span style="color:#6b7280;font-size:0.8rem;">持倉中</span>' +
                    '</div>' +
                    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">進場價</div><div style="font-weight:600;font-size:0.95rem;">$' + pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }) + '</div></div>' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">現價</div><div style="font-weight:600;font-size:0.95rem;">' + (pos.current_price > 0 ? '$' + pos.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }) : '—') + '</div></div>' +
                    '<div><div style="color:#6b7280;font-size:0.7rem;">未實現損益</div><div style="font-weight:700;font-size:0.95rem;color:' + upnlColor + ';">' + upnlSign + '$' + pos.unrealized_pnl_usd.toFixed(2) + ' (' + (pos.unrealized_pnl >= 0 ? '+' : '') + pos.unrealized_pnl.toFixed(2) + '%)</div></div>' +
                    '</div>' +
                    '</div>';
            }
            html += '<div class="card" style="border-left:3px solid ' +
                (bot.status === 'running' ? '#00e676' : bot.status === 'error' ? '#ff1744' : '#6b7280') + ';">' +
                '<div style="display:flex;justify-content:space-between;align-items:start;flex-wrap:wrap;gap:12px;">' +
                '<div>' +
                '<strong style="font-size:1.15rem;">' + bot.name + '</strong> ' +
                '<span class="badge ' + statusClass + '">' + statusLabel + '</span> ' +
                '<span class="badge ' + modeClass + '">' + (bot.paper_mode ? '模擬' : '即時') + '</span>' +
                (isWebhook ? '<span class="badge badge-webhook">Webhook</span>' : '') +
                '<p style="color:#6b7280;font-size:0.85rem;margin-top:4px;">' + infoLine + '</p>' +
                (bot.error_msg ? '<p style="color:#ff1744;font-size:0.8rem;margin-top:2px;">' + bot.error_msg + '</p>' : '') +
                '</div>' +
                '</div>' +
                '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px;padding:12px;background:#0a0a0f;border-radius:8px;">' +
                '<div style="text-align:center;"><div style="color:#6b7280;font-size:0.75rem;">已實現損益</div>' +
                '<div style="font-size:1.2rem;font-weight:700;color:' + pnlColor + ';">' + pnlSign + '$' + bot.total_pnl.toFixed(2) + '</div></div>' +
                '<div style="text-align:center;"><div style="color:#6b7280;font-size:0.75rem;">交易數</div>' +
                '<div style="font-size:1.2rem;font-weight:700;">' + bot.total_trades + '</div></div>' +
                '<div style="text-align:center;"><div style="color:#6b7280;font-size:0.75rem;">勝率</div>' +
                '<div style="font-size:1.2rem;font-weight:700;">' + bot.win_rate.toFixed(1) + '%</div></div>' +
                '<div style="text-align:center;"><div style="color:#6b7280;font-size:0.75rem;">最後信號</div>' +
                '<div style="font-size:0.9rem;font-weight:600;">' + (bot.last_signal || '—') + '</div>' +
                (bot.last_signal_time ? '<div style="font-size:0.65rem;color:#6b7280;">' + bot.last_signal_time + '</div>' : '') +
                '</div>' +
                '</div>' +
                posHtml +
                missedHtml +
                (isWebhook ? '<div class="webhook-info-box" id="webhook-info-' + bot.bot_id + '"><div class="loading" style="padding:8px;font-size:0.8rem;">載入 Webhook 資訊...</div></div>' : '') +
                '<div style="display:flex;gap:8px;margin-top:12px;">' +
                (bot.status !== 'running'
                    ? '<button class="btn btn-sm btn-success" onclick="startBot(\'' + bot.bot_id + '\')">啟動</button>'
                    : '<button class="btn btn-sm btn-danger" onclick="stopBot(\'' + bot.bot_id + '\')">停止</button>') +
                (bot.status !== 'running' && !isWebhook
                    ? '<button class="btn btn-sm btn-secondary" onclick=\'editBot(' + JSON.stringify(JSON.stringify(bot)) + ')\'>編輯</button>'
                    : '') +
                (bot.status !== 'running'
                    ? '<button class="btn btn-sm btn-danger" onclick="deleteBot(\'' + bot.bot_id + '\',\'' + bot.name.replace(/'/g, "\\'") + '\')">刪除</button>'
                    : '') +
                '</div></div>';
        });
        // Load webhook info for webhook bots
        bots.filter(b => b.signal_source === 'webhook').forEach(b => loadWebhookInfo(b.bot_id));
        html += '</div>';
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<div class="loading" style="color:#ff1744;">載入失敗: ' + err.message + '</div>';
    }
}

let _editingBotId = null;

function showCreateBotModal() {
    _editingBotId = null;
    document.getElementById('createBotModal').classList.add('active');
    document.querySelector('#createBotModal h3').textContent = '新增交易機器人';
    document.getElementById('bot-submitBtn').textContent = '建立';
    document.getElementById('bot-submitBtn').onclick = createBot;
    document.getElementById('bot-signal-source').value = 'strategy';
    document.getElementById('bot-signal-source').disabled = false;
    document.getElementById('bot-name').value = '';
    document.getElementById('bot-capital').value = '1000';
    document.getElementById('bot-leverage').value = '1';
    document.getElementById('bot-mode').value = 'true';
    document.getElementById('bot-sl').value = '';
    document.getElementById('bot-tp').value = '';
    onSignalSourceChange();
    loadStrategyParams('bot');
}

function editBot(botJson) {
    const bot = JSON.parse(botJson);
    _editingBotId = bot.bot_id;
    document.getElementById('createBotModal').classList.add('active');
    document.querySelector('#createBotModal h3').textContent = '編輯機器人';
    document.getElementById('bot-submitBtn').textContent = '儲存';
    document.getElementById('bot-submitBtn').onclick = updateBot;
    document.getElementById('bot-signal-source').value = bot.signal_source || 'strategy';
    document.getElementById('bot-signal-source').disabled = true;
    onSignalSourceChange();
    document.getElementById('bot-name').value = bot.name;
    document.getElementById('bot-strategy').value = bot.strategy;
    document.getElementById('bot-symbol').value = bot.symbol;
    onBotSymbolChange();
    document.getElementById('bot-timeframe').value = bot.timeframe;
    document.getElementById('bot-capital').value = bot.capital;
    document.getElementById('bot-leverage').value = bot.leverage || '1';
    document.getElementById('bot-mode').value = bot.paper_mode ? 'true' : 'false';
    document.getElementById('bot-sl').value = bot.sl_pct || '';
    document.getElementById('bot-tp').value = bot.tp_pct || '';
    loadStrategyParams('bot').then(() => {
        if (bot.params) {
            Object.entries(bot.params).forEach(([k, v]) => {
                const input = document.getElementById('bot-param-' + k);
                if (input) input.value = v;
            });
        }
    });
}

async function updateBot() {
    if (!_editingBotId) return;
    const btn = document.getElementById('bot-submitBtn');
    btn.disabled = true;
    btn.textContent = '儲存中...';
    const params = collectParams('bot');
    const slVal = document.getElementById('bot-sl').value;
    const tpVal = document.getElementById('bot-tp').value;
    const body = {
        name: document.getElementById('bot-name').value || '機器人',
        strategy: document.getElementById('bot-strategy').value,
        symbol: document.getElementById('bot-symbol').value,
        timeframe: document.getElementById('bot-timeframe').value,
        capital: parseFloat(document.getElementById('bot-capital').value),
        leverage: parseFloat(document.getElementById('bot-leverage').value),
        paper_mode: document.getElementById('bot-mode').value === 'true',
        sl_pct: slVal ? parseFloat(slVal) : null,
        tp_pct: tpVal ? parseFloat(tpVal) : null,
        params: params,
    };
    try {
        const data = await safeFetch('/api/bots/' + _editingBotId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        closeCreateBotModal();
        loadBots(true);
    } catch (err) { alert('更新失敗: ' + err.message); }
    finally { btn.disabled = false; btn.textContent = '儲存'; }
}

function submitBotModal() {
    if (_editingBotId) updateBot();
    else createBot();
}

function closeCreateBotModal() {
    document.getElementById('createBotModal').classList.remove('active');
    document.getElementById('bot-signal-source').disabled = false;
    _editingBotId = null;
}

function onBotSymbolChange() {
    const sym = document.getElementById('bot-symbol').value;
    const isPerp = sym.includes('_PERP');
    const isYahoo = sym.includes('=F');
    document.getElementById('bot-symbol-hint').style.display = isPerp ? 'block' : 'none';
    document.getElementById('bot-yahoo-hint').style.display = isYahoo ? 'block' : 'none';
    const modeSelect = document.getElementById('bot-mode');
    const leverageSelect = document.getElementById('bot-leverage');

    if (isYahoo) {
        modeSelect.value = 'true';
        modeSelect.disabled = true;
        leverageSelect.value = '1';
        leverageSelect.disabled = true;
    } else {
        modeSelect.disabled = false;
        leverageSelect.disabled = false;
    }
    // Yahoo futures: update capital label to USD
    const capLabel = document.getElementById('bot-capital').previousElementSibling;
    if (capLabel) capLabel.textContent = isYahoo ? '資金 (USD)' : '資金 (USDT)';
}

async function createBot() {
    const btn = document.getElementById('bot-submitBtn');
    btn.disabled = true;
    btn.textContent = '建立中...';
    const signalSource = document.getElementById('bot-signal-source').value;
    const isWebhook = signalSource === 'webhook';
    const params = isWebhook ? {} : collectParams('bot');
    const slVal = document.getElementById('bot-sl').value;
    const tpVal = document.getElementById('bot-tp').value;
    const body = {
        name: document.getElementById('bot-name').value || (isWebhook ? 'Webhook Bot' : (document.getElementById('bot-strategy').selectedOptions[0]?.text || '策略') + ' ' + document.getElementById('bot-symbol').value.replace('_USDT', '').replace('_PERP', '')),
        strategy: isWebhook ? 'webhook' : document.getElementById('bot-strategy').value,
        symbol: document.getElementById('bot-symbol').value,
        timeframe: isWebhook ? '' : document.getElementById('bot-timeframe').value,
        capital: parseFloat(document.getElementById('bot-capital').value),
        leverage: parseFloat(document.getElementById('bot-leverage').value),
        paper_mode: document.getElementById('bot-mode').value === 'true',
        sl_pct: isWebhook ? null : (slVal ? parseFloat(slVal) : null),
        tp_pct: isWebhook ? null : (tpVal ? parseFloat(tpVal) : null),
        params: params,
        signal_source: signalSource,
    };
    try {
        const resp = await authFetch('/api/bots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            if (resp.status === 403 && currentUser && currentUser.role !== 'advanced' && currentUser.role !== 'admin') {
                if (confirm('已達機器人上限（' + currentUser.max_bots + '個）。\n\n透過合作夥伴註冊可升級為進階會員（5個機器人）。\n\n前往查看升級方式？')) {
                    closeCreateBotModal();
                    switchTab('account');
                    scrollToPartner();
                }
                return;
            }
            throw new Error(errData.error || errData.detail || '伺服器錯誤 (' + resp.status + ')');
        }
        const data = await resp.json();
        closeCreateBotModal();
        loadBots(true);
    } catch (err) { alert('建立失敗: ' + err.message); }
    finally { btn.disabled = false; btn.textContent = _editingBotId ? '儲存' : '建立'; }
}

async function startBot(botId) {
    try {
        await safeFetch('/api/bots/' + botId + '/start', { method: 'POST' });
        loadBots(true);
    } catch (err) { alert('啟動失敗: ' + err.message); }
}

async function stopBot(botId) {
    try {
        await safeFetch('/api/bots/' + botId + '/stop', { method: 'POST' });
        loadBots(true);
    } catch (err) { alert('停止失敗: ' + err.message); }
}

async function deleteBot(botId, name) {
    if (!confirm('確定要刪除機器人「' + name + '」嗎?')) return;
    try {
        await safeFetch('/api/bots/' + botId, { method: 'DELETE' });
        loadBots(true);
    } catch (err) { alert('刪除失敗: ' + err.message); }
}

/* ═══ Webhook UI functions ═══ */
function onSignalSourceChange() {
    const source = document.getElementById('bot-signal-source').value;
    const isWebhook = source === 'webhook';
    document.getElementById('bot-strategy-fields').style.display = isWebhook ? 'none' : '';
    document.getElementById('bot-timeframe-field').style.display = isWebhook ? 'none' : '';
    document.getElementById('bot-sl-tp-fields').style.display = isWebhook ? 'none' : '';
    document.getElementById('bot-params').style.display = isWebhook ? 'none' : '';
    document.getElementById('bot-webhook-hint').style.display = isWebhook ? '' : 'none';
}

async function loadWebhookInfo(botId) {
    const container = document.getElementById('webhook-info-' + botId);
    if (!container) return;
    try {
        const resp = await authFetch('/api/bots/' + botId + '/webhook-info');
        if (!resp.ok) { container.innerHTML = '<span style="color:#6b7280;font-size:0.8rem;">無法載入 Webhook 資訊</span>'; return; }
        const info = await resp.json();
        container.innerHTML =
            '<label>Webhook URL</label>' +
            '<div class="copy-row">' +
            '<input type="text" readonly value="' + info.webhook_url + '" id="wh-url-' + botId + '">' +
            '<button class="btn-copy" onclick="copyToClipboard(\'wh-url-' + botId + '\',this)">複製</button>' +
            '</div>' +
            '<label>TradingView Alert Message 模板</label>' +
            '<div class="copy-row">' +
            '<textarea readonly id="wh-tpl-' + botId + '">' + info.alert_message_template + '</textarea>' +
            '<button class="btn-copy" onclick="copyToClipboard(\'wh-tpl-' + botId + '\',this)">複製</button>' +
            '</div>' +
            '<p style="font-size:0.75rem;color:#6b7280;margin-top:4px;">在 TradingView 建立 Alert，Webhook URL 貼上方網址，Alert Message 貼上方模板。</p>';
    } catch (err) { container.innerHTML = '<span style="color:#ff1744;font-size:0.8rem;">載入失敗</span>'; }
}

function copyToClipboard(inputId, btn) {
    const el = document.getElementById(inputId);
    const text = el.value || el.textContent;
    navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = '已複製!';
        btn.style.color = '#00c853';
        setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
    }).catch(() => { el.select(); document.execCommand('copy'); });
}

/* ═══ Missed Signal — Inline Actions ═══ */
const _dismissedSignals = new Set();

async function forceEntry(botId, side) {
    try {
        await safeFetch('/api/bots/' + botId + '/force-entry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ side: side }),
        });
        loadBots(true);
    } catch (err) {
        if (err.message.includes('Already has')) {
            alert('機器人已自動進場，無需手動操作');
            loadBots(true);
        } else {
            alert('強制進場失敗: ' + err.message);
        }
    }
}

function dismissMissedSignal(botId) {
    _dismissedSignals.add(botId);
    loadBots(true);
}

setInterval(() => {
    if (document.getElementById('tab-bots').classList.contains('active')) loadBots();
    if (document.getElementById('tab-dashboard').classList.contains('active')) loadDashboard();
}, 10000);

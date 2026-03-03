/* ════════════════════════════════════════════════
   Tab 2: Optimize
════════════════════════════════════════════════ */
async function runOptimize() {
    const btn = document.getElementById('opt-runBtn');
    const content = document.getElementById('opt-content');
    btn.disabled = true; btn.textContent = '優化中...';
    content.innerHTML = '<div class="loading"><div class="spinner"></div><br>正在進行參數優化...</div>';

    const strategy = document.getElementById('opt-strategy').value;
    const optOos = document.getElementById('opt-oos').value;
    let url = '/api/optimize?strategy=' + strategy + '&sort_by=' + document.getElementById('opt-sort').value +
        '&top_n=' + document.getElementById('opt-topn').value +
        '&max_combos=' + document.getElementById('opt-maxcombos').value + buildDataUrl('opt');
    if (optOos > 0) url += '&oos_pct=' + optOos;

    try {
        const resp = await authFetch(url);
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.error || errData.detail || '伺服器錯誤 (' + resp.status + ')');
        }
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        renderOptResults(data);
        loadOptimizeHistory();
    } catch (err) {
        content.innerHTML = '<div class="loading" style="color:#ff1744;">錯誤: ' + err.message + '</div>';
    } finally {
        btn.disabled = false; btn.textContent = '開始優化';
    }
}

function renderOptResults(data) {
    const content = document.getElementById('opt-content');
    const hasOos = !!data.oos_pct;
    let html = '<p style="color:#6b7280;margin-bottom:12px;">策略: ' + data.strategy +
        ' | 測試: ' + data.tested + '/' + data.total_combinations;
    if (hasOos) html += ' | IS: ' + data.is_period + ' | OOS: ' + data.oos_period;
    html += '</p>';
    if (!data.results || data.results.length === 0) { content.innerHTML = html + '<p style="color:#ff1744;">無結果</p>'; return; }
    html += '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' +
        '<th>#</th><th>參數</th>';
    if (hasOos) {
        html += '<th>IS 報酬</th><th>IS 夏普</th><th>OOS 報酬</th><th>OOS 夏普</th><th>OOS 勝率</th><th>穩定度</th><th></th>';
    } else {
        html += '<th>報酬率</th><th>夏普</th><th>回撤</th><th>勝率</th><th>交易數</th><th>獲利因子</th><th></th>';
    }
    html += '</tr></thead><tbody>';
    data.results.forEach(r => {
        const m = r.metrics;
        const paramsStr = Object.entries(r.params).map(e => e[0] + '=' + e[1]).join(', ');
        html += '<tr><td>' + r.rank + '</td><td style="font-size:0.8rem;">' + paramsStr + '</td>';
        if (hasOos && r.is_metrics && r.oos_metrics) {
            const im = r.is_metrics;
            const om = r.oos_metrics;
            const stability = im.sharpe_ratio > 0 ? (om.sharpe_ratio / im.sharpe_ratio) : 0;
            const stabColor = stability >= 0.7 ? '#00c853' : stability >= 0.4 ? '#ffc107' : '#ff1744';
            const stabLabel = stability >= 0.7 ? '穩定' : stability >= 0.4 ? '一般' : '過擬合';
            html += '<td class="' + (im.total_return_pct >= 0 ? 'positive' : 'negative') + '">' + (im.total_return_pct >= 0 ? '+' : '') + im.total_return_pct.toFixed(1) + '%</td>' +
                '<td>' + im.sharpe_ratio.toFixed(2) + '</td>' +
                '<td class="' + (om.total_return_pct >= 0 ? 'positive' : 'negative') + '">' + (om.total_return_pct >= 0 ? '+' : '') + om.total_return_pct.toFixed(1) + '%</td>' +
                '<td>' + om.sharpe_ratio.toFixed(2) + '</td>' +
                '<td>' + om.win_rate.toFixed(0) + '%</td>' +
                '<td style="color:' + stabColor + ';font-weight:700;">' + (stability * 100).toFixed(0) + '% ' + stabLabel + '</td>';
        } else {
            html += '<td class="' + (m.total_return_pct >= 0 ? 'positive' : 'negative') + '">' + (m.total_return_pct >= 0 ? '+' : '') + m.total_return_pct.toFixed(1) + '%</td>' +
                '<td>' + m.sharpe_ratio.toFixed(2) + '</td><td class="negative">' + m.max_drawdown_pct.toFixed(1) + '%</td>' +
                '<td>' + m.win_rate.toFixed(0) + '%</td><td>' + m.total_trades + '</td><td>' + m.profit_factor.toFixed(2) + '</td>';
        }
        const optCtx = {
            params: r.params,
            strategy: document.getElementById('opt-strategy').value,
            symbol: document.getElementById('opt-symbol') ? document.getElementById('opt-symbol').value : 'BTC_USDT',
            timeframe: document.getElementById('opt-timeframe') ? document.getElementById('opt-timeframe').value : '1h',
        };
        html += '<td><button class="btn btn-sm btn-secondary" onclick=\'applyOptParams(' + JSON.stringify(JSON.stringify(optCtx)) + ')\'>套用回測</button> ' +
            '<button class="btn btn-sm" onclick=\'createBotFromOpt(' + JSON.stringify(JSON.stringify(optCtx)) + ')\' style="margin-left:4px;">建立機器人</button></td></tr>';
    });
    html += '</tbody></table></div>';
    content.innerHTML = html;
}

async function applyOptParams(ctxJson) {
    const ctx = JSON.parse(ctxJson);
    const params = ctx.params || ctx;  // backward compat: old format passes params directly
    const strategy = ctx.strategy || document.getElementById('opt-strategy').value;
    const symbol = ctx.symbol || 'BTC_USDT';
    const timeframe = ctx.timeframe || '1h';

    // Set backtest form fields
    document.getElementById('bt-strategy').value = strategy;
    const btSymbol = document.getElementById('bt-symbol');
    if (btSymbol) btSymbol.value = symbol;
    const btTimeframe = document.getElementById('bt-timeframe');
    if (btTimeframe) btTimeframe.value = timeframe;

    switchTab('backtest');
    await loadStrategyParams('bt');
    Object.entries(params).forEach(([k, v]) => {
        const input = document.getElementById('bt-param-' + k);
        if (input) input.value = v;
    });
}

async function createBotFromOpt(ctxJson) {
    const ctx = JSON.parse(ctxJson);
    const params = ctx.params || ctx;
    const strategy = ctx.strategy || document.getElementById('opt-strategy').value;
    const symbol = ctx.symbol || 'BTC_USDT';
    const timeframe = ctx.timeframe || '1h';

    switchTab('bots');
    document.getElementById('createBotModal').classList.add('active');
    document.getElementById('bot-signal-source').value = 'strategy';
    onSignalSourceChange();
    document.getElementById('bot-strategy').value = strategy;
    document.getElementById('bot-symbol').value = symbol;
    onBotSymbolChange();
    document.getElementById('bot-timeframe').value = timeframe;
    document.getElementById('bot-name').value = strategy + ' 優化';
    await loadStrategyParams('bot');
    Object.entries(params).forEach(([k, v]) => {
        const input = document.getElementById('bot-param-' + k);
        if (input) input.value = v;
    });
}

async function loadOptimizeHistory() {
    const el = document.getElementById('opt-historyContent');
    try {
        const resp = await authFetch('/api/optimize/history');
        if (resp.status === 401) { el.innerHTML = '<div class="loading" style="color:#6b7280;">登入後可查看優化歷史</div>'; return; }
        if (!resp.ok) throw new Error('載入失敗');
        const data = await resp.json();
        const results = data.results || [];
        if (results.length === 0) { el.innerHTML = '<div class="loading" style="color:#6b7280;">尚無優化紀錄</div>'; return; }
        el.innerHTML = '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' +
            '<th>策略</th><th>交易對</th><th>時間框架</th><th>排序</th><th>測試數</th><th>時間</th><th></th>' +
            '</tr></thead><tbody>' +
            results.map(r => {
                const ts = r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : '';
                return '<tr>' +
                    '<td>' + r.strategy + '</td>' +
                    '<td>' + (r.symbol || 'CSV') + '</td>' +
                    '<td>' + (r.timeframe || '-') + '</td>' +
                    '<td>' + r.sort_by + '</td>' +
                    '<td>' + r.tested + '/' + r.total_combinations + '</td>' +
                    '<td style="font-size:0.8rem;color:#6b7280;">' + ts + '</td>' +
                    '<td style="white-space:nowrap;">' +
                    '<button class="btn" style="font-size:0.7rem;padding:2px 8px;margin-right:4px;" onclick="viewOptimizeResult(' + r.id + ')">查看</button>' +
                    '<button class="btn" style="font-size:0.7rem;padding:2px 8px;background:#2a1a1a;color:#ff4444;" onclick="deleteOptimizeResult(' + r.id + ')">刪除</button>' +
                    '</td></tr>';
            }).join('') +
            '</tbody></table></div>';
    } catch (e) {
        el.innerHTML = '<div class="loading" style="color:#6b7280;">載入失敗</div>';
    }
}

async function viewOptimizeResult(id) {
    const content = document.getElementById('opt-content');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><br>載入優化結果...</div>';
    try {
        const data = await safeFetch('/api/optimize/history/' + id);
        renderOptResults(data);
        document.getElementById('opt-content').scrollIntoView({ behavior: 'smooth' });
    } catch (e) {
        content.innerHTML = '<div class="loading" style="color:#ff1744;">錯誤: ' + e.message + '</div>';
    }
}

async function deleteOptimizeResult(id) {
    if (!confirm('確定刪除此優化結果？')) return;
    try {
        await safeFetch('/api/optimize/history/' + id, { method: 'DELETE' });
        loadOptimizeHistory();
    } catch (e) { alert('刪除失敗: ' + e.message); }
}

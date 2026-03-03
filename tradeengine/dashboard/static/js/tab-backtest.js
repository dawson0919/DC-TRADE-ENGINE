/* ════════════════════════════════════════════════
   Tab 1: Backtest
════════════════════════════════════════════════ */
async function runBacktest() {
    const btn = document.getElementById('bt-runBtn');
    const content = document.getElementById('bt-metricsContent');
    btn.disabled = true; btn.textContent = '回測中...';
    content.innerHTML = '<div class="loading"><div class="spinner"></div><br>正在執行回測...</div>';

    const strategy = document.getElementById('bt-strategy').value;
    const capital = document.getElementById('bt-capital').value;
    const sl = document.getElementById('bt-sl').value;
    const tp = document.getElementById('bt-tp').value;
    const customParams = collectParams('bt');

    const oosPct = document.getElementById('bt-oos').value;
    let url = '/api/backtest?strategy=' + strategy + '&capital=' + capital + buildDataUrl('bt');
    if (sl) url += '&sl=' + sl;
    if (tp) url += '&tp=' + tp;
    if (oosPct > 0) url += '&oos_pct=' + oosPct;
    if (Object.keys(customParams).length > 0) url += '&params_json=' + encodeURIComponent(JSON.stringify(customParams));

    try {
        const resp = await authFetch(url);
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.error || errData.detail || '伺服器錯誤 (' + resp.status + ')');
        }
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        if (data.is_metrics) {
            renderSplitMetrics(data);
            renderSplitChart(data);
        } else {
            if (data.metrics) renderMetrics(data.metrics);
            if (data.equity_curve && data.equity_curve.length > 0) renderChart(data.equity_curve);
        }
        if (data.trades && data.trades.length > 0) { renderTrades(data.trades); }
        else { document.getElementById('bt-tradesCard').style.display = 'none'; }
        loadBacktestHistory();
    } catch (err) {
        content.innerHTML = '<div class="loading" style="color:#ff1744;">錯誤: ' + err.message + '</div>';
    } finally {
        btn.disabled = false; btn.textContent = '執行回測';
    }
}

function renderMetrics(m) {
    const retClass = m.total_return_pct >= 0 ? 'positive' : 'negative';
    const sharpeClass = m.sharpe_ratio >= 1 ? 'positive' : m.sharpe_ratio < 0 ? 'negative' : '';
    document.getElementById('bt-metricsContent').innerHTML = `
        <div class="metrics-grid">
            <div class="metric"><div class="value ${retClass}">${m.total_return_pct >= 0 ? '+' : ''}${m.total_return_pct.toFixed(1)}%</div><div class="label">總報酬率</div></div>
            <div class="metric"><div class="value ${sharpeClass}">${m.sharpe_ratio.toFixed(2)}</div><div class="label">夏普比率</div></div>
            <div class="metric"><div class="value negative">${m.max_drawdown_pct.toFixed(1)}%</div><div class="label">最大回撤</div></div>
            <div class="metric"><div class="value">${m.win_rate.toFixed(0)}%</div><div class="label">勝率</div></div>
            <div class="metric"><div class="value">${m.total_trades}</div><div class="label">交易次數</div></div>
            <div class="metric"><div class="value">${m.profit_factor.toFixed(2)}</div><div class="label">獲利因子</div></div>
            <div class="metric"><div class="value">${m.sortino_ratio.toFixed(2)}</div><div class="label">索提諾比率</div></div>
            <div class="metric"><div class="value positive">${m.best_trade_pct >= 0 ? '+' : ''}${m.best_trade_pct.toFixed(1)}%</div><div class="label">最佳交易</div></div>
        </div>`;
}

function renderChart(equityData) {
    const ctx = document.getElementById('equityChart').getContext('2d');
    if (chart) chart.destroy();
    let data = equityData;
    if (data.length > 300) { const step = Math.ceil(data.length / 300); data = data.filter((_, i) => i % step === 0); }
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.time.slice(0, 10)),
            datasets: [{
                label: '資金曲線', data: data.map(d => d.value),
                borderColor: '#f7931a', backgroundColor: 'rgba(247,147,26,0.1)',
                fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280', maxTicksLimit: 8 } },
                y: { grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280' } },
            },
            interaction: { intersect: false, mode: 'index' },
        },
    });
}

function renderTrades(trades) {
    document.getElementById('bt-tradesCard').style.display = '';
    document.getElementById('bt-tradeCount').textContent = '(最近 ' + trades.length + ' 筆)';
    document.getElementById('bt-tradesBody').innerHTML = trades.map(t => `<tr>
        <td>${t.entry_time.slice(0, 16)}</td><td>${t.exit_time.slice(0, 16)}</td>
        <td>${t.direction === 'Long' ? '做多' : '做空'}</td>
        <td>${t.entry_price.toLocaleString()}</td><td>${t.exit_price.toLocaleString()}</td>
        <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">$${t.pnl.toFixed(2)}</td>
        <td class="${t.return_pct >= 0 ? 'positive' : 'negative'}">${t.return_pct >= 0 ? '+' : ''}${t.return_pct.toFixed(2)}%</td>
    </tr>`).join('');
}

function _metricsBlock(label, m, period, color) {
    const retClass = m.total_return_pct >= 0 ? 'positive' : 'negative';
    const sharpeClass = m.sharpe_ratio >= 1 ? 'positive' : m.sharpe_ratio < 0 ? 'negative' : '';
    return '<div style="flex:1;min-width:260px;background:#0a0a0f;border-radius:8px;padding:16px;border-top:3px solid ' + color + ';">' +
        '<h4 style="margin:0 0 4px;color:' + color + ';font-size:0.95rem;">' + label + '</h4>' +
        (period ? '<p style="font-size:0.75rem;color:#6b7280;margin:0 0 10px;">' + period + '</p>' : '') +
        '<div class="metrics-grid">' +
        '<div class="metric"><div class="value ' + retClass + '">' + (m.total_return_pct >= 0 ? '+' : '') + m.total_return_pct.toFixed(1) + '%</div><div class="label">總報酬率</div></div>' +
        '<div class="metric"><div class="value ' + sharpeClass + '">' + m.sharpe_ratio.toFixed(2) + '</div><div class="label">夏普比率</div></div>' +
        '<div class="metric"><div class="value negative">' + m.max_drawdown_pct.toFixed(1) + '%</div><div class="label">最大回撤</div></div>' +
        '<div class="metric"><div class="value">' + m.win_rate.toFixed(0) + '%</div><div class="label">勝率</div></div>' +
        '<div class="metric"><div class="value">' + m.total_trades + '</div><div class="label">交易次數</div></div>' +
        '<div class="metric"><div class="value">' + m.profit_factor.toFixed(2) + '</div><div class="label">獲利因子</div></div>' +
        '</div></div>';
}

function renderSplitMetrics(data) {
    const oosPct = data.oos_pct || 30;
    const isPct = 100 - oosPct;
    let html = '<div style="display:flex;gap:16px;flex-wrap:wrap;">';
    html += _metricsBlock('In-Sample (' + isPct + '%)', data.is_metrics, data.is_period, '#f7931a');
    html += _metricsBlock('Out-of-Sample (' + oosPct + '%)', data.oos_metrics, data.oos_period, '#2196f3');
    html += '</div>';
    // Overfitting warning
    const isSharpe = data.is_metrics.sharpe_ratio;
    const oosSharpe = data.oos_metrics.sharpe_ratio;
    const oosReturn = data.oos_metrics.total_return_pct;
    if (oosReturn < 0 || (isSharpe > 0.5 && oosSharpe < isSharpe * 0.4)) {
        html += '<div style="margin-top:12px;padding:10px 14px;background:#2a1a0a;border:1px solid #f7931a55;border-radius:8px;color:#ffa726;font-size:0.9rem;">' +
            '⚠ OOS 表現明顯弱於 IS，可能存在過擬合 (overfitting)。建議增加資料量或簡化策略參數。</div>';
    } else if (isSharpe > 0.5 && oosSharpe >= isSharpe * 0.7) {
        html += '<div style="margin-top:12px;padding:10px 14px;background:#0a2a0a;border:1px solid #00c85355;border-radius:8px;color:#66bb6a;font-size:0.9rem;">' +
            '✓ OOS 表現穩定，策略具有較好的泛化能力。</div>';
    }
    document.getElementById('bt-metricsContent').innerHTML = html;
}

function renderSplitChart(data) {
    const ctx = document.getElementById('equityChart').getContext('2d');
    if (chart) chart.destroy();
    let isData = data.is_equity_curve || [];
    let oosData = data.oos_equity_curve || [];
    if (isData.length > 200) { const s = Math.ceil(isData.length / 200); isData = isData.filter((_, i) => i % s === 0); }
    if (oosData.length > 200) { const s = Math.ceil(oosData.length / 200); oosData = oosData.filter((_, i) => i % s === 0); }
    // Overlay: both start from index 0, same initial capital
    const maxLen = Math.max(isData.length, oosData.length);
    const labels = Array.from({ length: maxLen }, (_, i) => i + 1);
    const isValues = isData.map(d => d.value);
    const oosValues = oosData.map(d => d.value);
    while (isValues.length < maxLen) isValues.push(null);
    while (oosValues.length < maxLen) oosValues.push(null);
    // Dates for tooltips
    const isDates = isData.map(d => d.time.slice(0, 10));
    const oosDates = oosData.map(d => d.time.slice(0, 10));
    const isRange = isDates.length ? isDates[0] + ' ~ ' + isDates[isDates.length - 1] : '';
    const oosRange = oosDates.length ? oosDates[0] + ' ~ ' + oosDates[oosDates.length - 1] : '';
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'In-Sample (' + isRange + ')', data: isValues,
                    borderColor: '#f7931a', backgroundColor: 'rgba(247,147,26,0.08)',
                    fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2
                },
                {
                    label: 'Out-of-Sample (' + oosRange + ')', data: oosValues,
                    borderColor: '#2196f3', backgroundColor: 'rgba(33,150,243,0.08)',
                    fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2
                },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: true, labels: { color: '#e7e9ea', font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        title: function (items) {
                            const idx = items[0].dataIndex;
                            const parts = [];
                            if (idx < isDates.length) parts.push('IS: ' + isDates[idx]);
                            if (idx < oosDates.length) parts.push('OOS: ' + oosDates[idx]);
                            return parts.join('  |  ');
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280', maxTicksLimit: 8 },
                    title: { display: true, text: 'K線序號', color: '#4a5568', font: { size: 10 } }
                },
                y: { grid: { color: '#1e1e2e' }, ticks: { color: '#6b7280' } },
            },
            interaction: { intersect: false, mode: 'index' },
        },
    });
}

/* ════════════════════════════════════════════════
   Tab 1b: Backtest History
════════════════════════════════════════════════ */
async function loadBacktestHistory() {
    const el = document.getElementById('bt-historyContent');
    try {
        const resp = await authFetch('/api/backtest/history');
        if (resp.status === 401) { el.innerHTML = '<div class="loading" style="color:#6b7280;">登入後可查看回測歷史</div>'; return; }
        if (!resp.ok) throw new Error('載入失敗');
        const data = await resp.json();
        const results = data.results || [];
        if (results.length === 0) { el.innerHTML = '<div class="loading" style="color:#6b7280;">尚無回測紀錄</div>'; return; }
        el.innerHTML = '<div style="overflow-x:auto;"><table class="data-table"><thead><tr>' +
            '<th>策略</th><th>交易對</th><th>時間框架</th><th>總報酬</th><th>夏普</th><th>勝率</th><th>交易數</th><th>時間</th><th></th>' +
            '</tr></thead><tbody>' +
            results.map(r => {
                const m = r.metrics || {};
                const ret = m.total_return_pct || 0;
                const retClass = ret >= 0 ? 'positive' : 'negative';
                const ts = r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : '';
                return '<tr>' +
                    '<td>' + r.strategy + '</td>' +
                    '<td>' + r.symbol + '</td>' +
                    '<td>' + r.timeframe + '</td>' +
                    '<td class="' + retClass + '">' + (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%</td>' +
                    '<td>' + (m.sharpe_ratio || 0).toFixed(2) + '</td>' +
                    '<td>' + (m.win_rate || 0).toFixed(0) + '%</td>' +
                    '<td>' + (m.total_trades || 0) + '</td>' +
                    '<td style="font-size:0.8rem;color:#6b7280;">' + ts + '</td>' +
                    '<td style="white-space:nowrap;">' +
                    '<button class="btn" style="font-size:0.7rem;padding:2px 8px;margin-right:4px;" onclick="viewBacktestResult(' + r.id + ')">查看</button>' +
                    '<button class="btn" style="font-size:0.7rem;padding:2px 8px;background:#2a1a1a;color:#ff4444;" onclick="deleteBacktestResult(' + r.id + ')">刪除</button>' +
                    '</td></tr>';
            }).join('') +
            '</tbody></table></div>';
    } catch (e) {
        el.innerHTML = '<div class="loading" style="color:#6b7280;">載入失敗</div>';
    }
}

async function viewBacktestResult(id) {
    const content = document.getElementById('bt-metricsContent');
    content.innerHTML = '<div class="loading"><div class="spinner"></div><br>載入回測結果...</div>';
    try {
        const data = await safeFetch('/api/backtest/history/' + id);
        if (data.metrics) renderMetrics(data.metrics);
        if (data.equity_curve && data.equity_curve.length > 0) renderChart(data.equity_curve);
        if (data.trades && data.trades.length > 0) { renderTrades(data.trades); }
        else { document.getElementById('bt-tradesCard').style.display = 'none'; }
        // Scroll to top of results
        document.getElementById('bt-metricsContent').scrollIntoView({ behavior: 'smooth' });
    } catch (e) {
        content.innerHTML = '<div class="loading" style="color:#ff1744;">錯誤: ' + e.message + '</div>';
    }
}

async function deleteBacktestResult(id) {
    if (!confirm('確定刪除此回測結果？')) return;
    try {
        await safeFetch('/api/backtest/history/' + id, { method: 'DELETE' });
        loadBacktestHistory();
    } catch (e) { alert('刪除失敗: ' + e.message); }
}

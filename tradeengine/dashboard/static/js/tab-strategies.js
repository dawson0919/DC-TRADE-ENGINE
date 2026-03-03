/* ════════════════════════════════════════════════
   Tab 5: Strategies
════════════════════════════════════════════════ */
const _stratMeta = {
    ma_crossover: {
        category: '趨勢', catColor: '#00c853', icon: '📈',
        detail: '使用兩條不同週期的均線（快線與慢線），當快線從下方穿越慢線（黃金交叉）時做多，反之（死亡交叉）做空。支援 SMA 與 EMA 兩種均線類型。適合有明確趨勢的行情，震盪市容易產生假信號。'
    },
    rsi: {
        category: '震盪', catColor: '#29b6f6', icon: '🔄',
        detail: 'RSI（相對強弱指標）衡量價格動能。當 RSI 跌至超賣線以下，代表市場超跌可能反彈，進場做多；升至超買線以上則平倉。屬於均值回歸策略，適合盤整行情，趨勢行情中可能過早離場。'
    },
    macd: {
        category: '趨勢', catColor: '#00c853', icon: '📊',
        detail: 'MACD 由快慢兩條指數移動平均的差值與訊號線組成。當 MACD 線上穿訊號線為做多信號，下穿為做空信號。兼具趨勢追蹤與動能判斷，是最受歡迎的技術指標之一。反應較快但可能有雜訊。'
    },
    bollinger: {
        category: '震盪', catColor: '#29b6f6', icon: '📉',
        detail: '布林通道以移動平均為中軌，上下各加減 N 倍標準差構成通道。價格觸及下軌代表極端超跌，做多等待回歸中軌；觸及上軌則反向操作。適合區間震盪行情，突破趨勢中可能逆勢操作。'
    },
    donchian: {
        category: '趨勢', catColor: '#00c853', icon: '🚀',
        detail: '唐奇安通道為 N 週期最高價與最低價形成的通道。價格突破最高點做多，跌破最低點做空。經典的趨勢突破策略（海龜交易法原型），能捕捉大行情但在盤整期會頻繁止損。進場與出場使用不同週期可減少假突破。'
    },
    supertrend: {
        category: '趨勢', catColor: '#00c853', icon: '⚡',
        detail: 'SuperTrend 基於 ATR（平均真實範圍）計算動態止損線，價格在線上方為多頭趨勢，跌破翻空。自動適應市場波動度，趨勢明確時表現出色。只有兩個參數（ATR 週期與倍數），簡單且有效。'
    },
    combined: {
        category: '複合', catColor: '#ab47bc', icon: '🔗',
        detail: '結合三大指標：EMA 判斷趨勢方向、RSI 過濾超買超賣、MACD 確認動能。三者同時滿足才進場，大幅降低假信號。參數較多但穩定性高，適合追求低頻高品質信號的交易者。'
    },
    triple_ema: {
        category: '趨勢', catColor: '#00c853', icon: '🗡️',
        detail: '三刀流策略使用快、中、慢三條 EMA。當三線呈多頭排列（快>中>慢）進場做多，快線跌破中線出場。比雙均線交叉更嚴格，能過濾部分假信號，但可能錯過行情起始段。'
    },
    consecutive_breakout: {
        category: '動能', catColor: '#ff9800', icon: '🏀',
        detail: '根據均線劃分多頭區與空頭區，在不同區域使用不同的連續 K 線閾值判斷進出場。多頭區只需較少連漲即做多（順勢），但需較多連跌才做空（逆勢需更強確認）。支援 6 種均線類型，參數靈活。'
    },
    turtle_breakout: {
        category: '趨勢', catColor: '#00c853', icon: '🐢',
        detail: '偵測樞紐高低點（Pivot High/Low），當價格突破最近一個樞紐高點做多，跌破樞紐低點做空。與唐奇安通道類似但以樞紐點為基準，信號更精確。左右 K 棒數控制樞紐靈敏度。'
    },
    dc_turtle: {
        category: '趨勢', catColor: '#00c853', icon: '🐢',
        detail: '[DC] 海龜停利停損策略。樞紐突破進場 + 三重出場機制：(1) 固定停利 — 獲利達設定百分比平倉；(2) 固定停損 — 虧損達設定百分比止損；(3) 移動停利 — 當獲利超過啟動門檻後，回撤達設定比例平倉保護獲利。結合趨勢突破與嚴格風控，適合波動較大的標的。'
    },
    granville_pro: {
        category: '趨勢', catColor: '#00c853', icon: '👨‍🏫',
        detail: '葛蘭碧法則精華版，使用單一 EMA 的交叉判斷多空方向。價格從下方穿越 EMA 做多（黃金交叉），從上方穿越做空（死亡交叉）。內建停損偏離機制：當價格偏離 EMA 超過設定百分比自動平倉。預設參數為 4H 級別深度優化結果（BTC: EMA-178, ETH: EMA-203, SOL: EMA-156）。'
    },
    donchian_supertrend: {
        category: '複合', catColor: '#ab47bc', icon: '🔱',
        detail: '唐奇安通道突破 + SuperTrend 趨勢過濾的雙通道策略。進場條件：價格突破唐奇安上軌且 SuperTrend 為上升趨勢（做多），跌破唐奇安下軌且 SuperTrend 為下降趨勢（做空）。出場條件：價格跌破唐奇安出場軌或 SuperTrend 翻轉。雙重確認機制有效過濾假突破，提高勝率與獲利因子。適合波動性大、趨勢明確的標的（如 XAG 白銀、PAXG 黃金）。回測最佳表現：XAG 1H 夏普 3.14 / 報酬 +42%，PAXG 4H 夏普 1.27 / 報酬 +25%。'
    },
    ichimoku_cloud: {
        category: '複合', catColor: '#ab47bc', icon: '☁️',
        detail: '一目均衡表 (Ichimoku Kinko Hyo) 雲圖突破策略，結合 EMA 200 長期趨勢濾網。做多條件：價格在雲層（先行帶 A、B）上方 + 轉換線 (Tenkan) 大於基準線 (Kijun) + 價格高於 EMA 200。做空條件：價格在雲層下方 + 轉換線小於基準線 + 價格低於 EMA 200。三重確認機制（雲圖趨勢、均線交叉、長期趨勢）大幅降低假信號。EMA 週期設為 0 可關閉濾網。適合中長線趨勢交易，1H/4H 時間框架效果較佳。'
    },
    vwap_crossover: {
        category: '趨勢', catColor: '#00c853', icon: '📊',
        detail: 'VWAP 標準差帶交叉策略（基於 TradingView VWAP Stdev Bands v2）。Session VWAP 每日 00:00 UTC 重置，使用 HL2 作為典型價格。做多條件：價格突破 VWAP + N 倍標準差上軌；做空條件：價格跌破下軌。預設 1.28 倍標準差（對應常態分佈 80% 信賴區間）。可加 EMA 趨勢濾網（週期 > 0 啟用）只順勢交易。適合日內及短線交易，15M/1H 時間框架效果較佳。'
    },
};

async function loadStrategies() {
    const container = document.getElementById('strat-list');
    try {
        const strats = await safeFetch('/api/strategies');
        let html = '';
        strats.forEach(s => {
            const meta = _stratMeta[s.name] || { category: '其他', catColor: '#6b7280', icon: '📌', detail: '' };
            html += '<div class="strat-card">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">' +
                '<div style="display:flex;align-items:center;gap:8px;">' +
                '<span style="font-size:1.3rem;">' + meta.icon + '</span>' +
                '<div><strong style="color:#f7931a;font-size:1.05rem;">' + s.display_name + '</strong>' +
                '<span style="color:#6b7280;font-size:0.78rem;margin-left:8px;">' + s.name + '</span></div>' +
                '</div>' +
                '<div style="display:flex;gap:6px;align-items:center;">' +
                '<span style="background:' + meta.catColor + '22;color:' + meta.catColor + ';padding:2px 8px;border-radius:10px;font-size:0.7rem;font-weight:600;">' + meta.category + '</span>' +
                '<span style="color:#6b7280;font-size:0.78rem;">' + s.parameters.length + ' 個參數</span>' +
                '</div>' +
                '</div>' +
                '<p style="color:#9ca3af;margin:10px 0 6px;font-size:0.85rem;line-height:1.6;">' + (meta.detail || s.description) + '</p>';
            if (s.parameters.length > 0) {
                html += '<div class="strat-params">';
                s.parameters.forEach(p => {
                    html += '<div class="strat-param"><span style="color:#6b7280;">' + p.display_name + ':</span> ' +
                        '<strong style="color:#e7e9ea;">' + p.default + '</strong>' +
                        (p.min != null ? ' <span style="color:#555;font-size:0.7rem;">(' + p.min + '~' + p.max + ')</span>' : '') + '</div>';
                });
                html += '</div>';
            }
            html += '</div>';
        });
        container.innerHTML = html;
        strategiesLoaded = true;
    } catch (err) {
        container.innerHTML = '<div class="loading" style="color:#ff1744;">載入失敗: ' + err.message + '</div>';
    }
}

/* ════════════════════════════════════════════════
   Tab 4: Account
════════════════════════════════════════════════ */
async function loadAccount() { loadApiKeyStatus(); loadBalances(); loadAccountInfo(); updatePartnerSection(); }

async function loadApiKeyStatus() {
    const dot = document.getElementById('apiKeyDot');
    const text = document.getElementById('apiKeyStatusText');
    const delBtn = document.getElementById('apikey-deleteBtn');
    const form = document.getElementById('apikey-form');
    try {
        const resp = await authFetch('/api/api-keys');
        if (resp.ok) {
            const data = await resp.json();
            if (data.has_key) {
                dot.className = 'api-key-dot connected';
                text.innerHTML = '<span style="color:#00c853;">Pionex API 已設定</span>' +
                    (data.label ? ' (' + data.label + ')' : '') +
                    ' <span style="color:#6b7280;font-size:0.8rem;">Key: ' + data.key_preview + '</span>';
                if (data.source === 'config') {
                    // Local mode: keys from server config file
                    form.innerHTML = '<p style="color:#6b7280;font-size:0.85rem;margin-top:8px;">金鑰來源：伺服器設定檔 (config/default.yaml 或 .env)</p>';
                    delBtn.style.display = 'none';
                } else {
                    delBtn.style.display = '';
                }
            } else {
                dot.className = 'api-key-dot disconnected';
                text.innerHTML = '<span style="color:#ff1744;">尚未設定 API 金鑰</span>';
                delBtn.style.display = 'none';
            }
        }
    } catch (err) { text.innerHTML = '<span style="color:#6b7280;">無法檢查</span>'; }
}

async function saveApiKey() {
    const key = document.getElementById('apikey-key').value.trim();
    const secret = document.getElementById('apikey-secret').value.trim();
    if (!key || !secret) { alert('請輸入 API Key 和 API Secret'); return; }
    try {
        const resp = await authFetch('/api/api-keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: key, api_secret: secret }) });
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.error || errData.detail || '伺服器錯誤 (' + resp.status + ')');
        }
        const data = await resp.json();
        document.getElementById('apikey-key').value = '';
        document.getElementById('apikey-secret').value = '';
        alert('API 金鑰已儲存');
        loadApiKeyStatus(); loadBalances();
    } catch (err) { alert('儲存失敗: ' + err.message); }
}

async function deleteApiKey() {
    if (!confirm('確定要刪除 API 金鑰嗎？')) return;
    try {
        await safeFetch('/api/api-keys', { method: 'DELETE' });
        loadApiKeyStatus(); loadBalances();
    } catch (err) { alert('刪除失敗: ' + err.message); }
}

async function loadBalances() {
    const balEl = document.getElementById('acct-balances');
    try {
        const resp = await authFetch('/api/account/balance');
        if (!resp.ok) { const err = await resp.json(); balEl.innerHTML = '<p style="color:#6b7280;">' + (err.error || '無法取得餘額') + '</p>'; return; }
        const data = await resp.json();
        let html = '<div class="balance-grid">';
        data.balances.forEach(b => {
            const dec = b.asset === 'USDT' ? 2 : 6;
            html += '<div class="balance-card"><div class="asset">' + b.asset + '</div>' +
                '<div class="amount">' + parseFloat(b.free).toFixed(dec) + '</div>' +
                '<div class="locked">凍結: ' + parseFloat(b.frozen).toFixed(dec) + '</div></div>';
        });
        html += '</div>';
        balEl.innerHTML = html;
    } catch (err) { balEl.innerHTML = '<p style="color:#ff1744;">載入失敗: ' + err.message + '</p>'; }
}

function loadAccountInfo() {
    const el = document.getElementById('acct-info');
    if (!currentUser) {
        if (!AUTH_ENABLED) {
            el.innerHTML = '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:0.9rem;">' +
                '<span style="color:#6b7280;">模式:</span><span style="color:#00c853;">本機模式</span>' +
                '<span style="color:#6b7280;">認證:</span><span>未啟用（API 金鑰使用伺服器設定檔）</span>' +
                '<span style="color:#6b7280;">機器人上限:</span><span>無限制</span>' +
                '</div>';
        } else {
            el.innerHTML = '<p style="color:#6b7280;">未登入</p>';
        }
        return;
    }
    const nameVal = (currentUser.display_name || '').replace(/"/g, '&quot;');
    el.innerHTML = '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:0.9rem;align-items:center;">' +
        '<span style="color:#6b7280;">Email:</span><span>' + currentUser.email + '</span>' +
        '<span style="color:#6b7280;">顯示名稱:</span>' +
        '<div style="display:flex;align-items:center;gap:8px;">' +
        '<input id="acct-display-name" type="text" value="' + nameVal + '" placeholder="輸入你的名稱" ' +
        'style="flex:1;padding:4px 8px;background:#0a0a0f;border:1px solid #1e1e2e;border-radius:4px;color:#e7e9ea;font-size:0.9rem;">' +
        '<button class="btn btn-sm" onclick="saveDisplayName()" style="padding:4px 12px;font-size:0.78rem;">儲存</button>' +
        '</div>' +
        '<span style="color:#6b7280;">角色:</span><span>' + (roleMap[currentUser.role] || '普通會員') + '</span>' +
        '<span style="color:#6b7280;">機器人上限:</span><span>' + (currentUser.max_bots >= 999 ? '無限制' : currentUser.max_bots) + '</span>' +
        '</div>';
}

async function saveDisplayName() {
    const input = document.getElementById('acct-display-name');
    const name = input.value.trim();
    if (!name) { alert('名稱不能為空'); return; }
    try {
        const data = await safeFetch('/api/account/update', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name })
        });
        currentUser.display_name = data.display_name;
        document.getElementById('userName').textContent = data.display_name;
        input.style.borderColor = '#00c853';
        setTimeout(() => { input.style.borderColor = '#1e1e2e'; }, 1500);
    } catch (err) { alert('儲存失敗: ' + err.message); }
}

function updatePartnerSection() {
    const el = document.getElementById('partnerSection');
    if (!el) return;
    // Show for standard/user roles (not advanced/admin), and only when auth is enabled
    if (currentUser && (currentUser.role === 'standard' || currentUser.role === 'user')) {
        el.style.display = '';
    } else {
        el.style.display = 'none';
    }
}

function scrollToPartner() {
    setTimeout(() => {
        const el = document.getElementById('partnerSection');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 200);
}

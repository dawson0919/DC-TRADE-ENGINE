/* ════════════════════════════════════════════════
   Global State
════════════════════════════════════════════════ */
let chart = null;
let dashChart = null;
let strategiesLoaded = false;
let currentUser = null;
let clerkToken = null;
const roleMap = { admin: '管理員', advanced: '進階會員', standard: '普通會員', user: '普通會員' };
const roleClassMap = { admin: 'role-admin', advanced: 'role-advanced', standard: 'role-standard', user: 'role-standard' };

/* ════════════════════════════════════════════════
   Auth: Clerk Integration
════════════════════════════════════════════════ */
const AUTH_ENABLED = window.__CONFIG__.authEnabled;

async function initAuth() {
    if (!AUTH_ENABLED || !window.Clerk) {
        console.info('Auth not enabled, running in local mode');
        loadDashboard();
        loadBacktestHistory();
        loadOptimizeHistory();
        return;
    }
    try {
        await window.Clerk.load({
            appearance: { variables: { colorPrimary: '#f7931a' } },
        });
        if (!window.Clerk.user) {
            window.location.href = '/login';
            return;
        }
        const session = window.Clerk.session;
        clerkToken = await session.getToken();
        setInterval(async () => {
            try {
                const s = window.Clerk.session;
                if (s) clerkToken = await s.getToken();
            } catch (e) { }
        }, 50000);
        const resp = await authFetch('/api/account/me');
        if (resp.ok) {
            currentUser = await resp.json();
            renderUserBar();
            loadDashboard();
            loadBacktestHistory();
            loadOptimizeHistory();
        } else {
            window.location.href = '/login';
        }
    } catch (err) {
        console.warn('Auth unavailable, running in dev mode');
        loadDashboard();
        loadBacktestHistory();
        loadOptimizeHistory();
    }
}

function renderUserBar() {
    if (!currentUser) return;
    const bar = document.getElementById('userBar');
    document.getElementById('userName').textContent = currentUser.display_name || currentUser.email;
    const roleEl = document.getElementById('userRole');
    roleEl.textContent = roleMap[currentUser.role] || '普通會員';
    roleEl.className = 'user-role ' + (roleClassMap[currentUser.role] || 'role-standard');
    bar.style.display = 'flex';
    if (currentUser.role === 'admin') document.getElementById('adminTab').style.display = '';
    const limitEl = document.getElementById('botLimitInfo');
    if (currentUser.max_bots < 999) {
        const label = currentUser.role === 'advanced' ? '進階會員' : '普通會員';
        limitEl.innerHTML = label + ' · 上限 ' + currentUser.max_bots + ' 個' +
            (currentUser.role !== 'advanced' ? ' <a href="#" onclick="switchTab(\'account\');scrollToPartner();return false;" style="color:#ffd700;margin-left:4px;">升級</a>' : '');
    }
}

async function doLogout() {
    try { await window.Clerk.signOut(); } catch (e) { }
    window.location.href = '/login';
}

async function authFetch(url, options = {}) {
    if (clerkToken) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = 'Bearer ' + clerkToken;
    }
    return fetch(url, options);
}

async function safeFetch(url, options = {}) {
    const resp = await authFetch(url, options);
    if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || errData.detail || '伺服器錯誤 (' + resp.status + ')');
    }
    return resp.json();
}

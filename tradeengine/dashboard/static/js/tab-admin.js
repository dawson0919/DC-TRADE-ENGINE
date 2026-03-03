/* ════════════════════════════════════════════════
   Tab 7: Admin
════════════════════════════════════════════════ */
let _adminUsersData = [];

async function loadAdminUsers() {
    const container = document.getElementById('admin-users');
    try {
        const resp = await authFetch('/api/admin/users');
        if (!resp.ok) { container.innerHTML = '<p style="color:#ff1744;">權限不足</p>'; return; }
        _adminUsersData = await resp.json();
        renderAdminUsers(_adminUsersData);
    } catch (err) { container.innerHTML = '<div class="loading" style="color:#ff1744;">載入失敗</div>'; }
}

function filterAdminUsers() {
    const q = (document.getElementById('admin-search').value || '').toLowerCase();
    if (!q) { renderAdminUsers(_adminUsersData); return; }
    renderAdminUsers(_adminUsersData.filter(u =>
        (u.email || '').toLowerCase().includes(q) ||
        (u.display_name || '').toLowerCase().includes(q) ||
        (u.clerk_id || '').toLowerCase().includes(q)
    ));
}

function renderAdminUsers(users) {
    const container = document.getElementById('admin-users');
    if (!users.length) { container.innerHTML = '<div class="loading" style="color:#6b7280;">無符合結果</div>'; return; }
    const inputStyle = 'width:100%;padding:4px 6px;background:#0a0a0f;border:1px solid #1e1e2e;border-radius:4px;color:#e7e9ea;font-size:0.82rem;';
    let html = '<table class="data-table"><thead><tr>' +
        '<th>Email</th><th>顯示名稱</th><th>ID</th><th>角色</th><th>機器人上限</th><th>狀態</th><th>註冊時間</th><th>操作</th></tr></thead><tbody>';
    users.forEach(u => {
        const isActive = u.is_active !== false;
        const email = u.email || '';
        const name = u.display_name || '';
        const shortId = u.clerk_id ? u.clerk_id.slice(-8) : '';
        html += '<tr>' +
            '<td><input type="text" value="' + email.replace(/"/g, '&quot;') + '" placeholder="未設定" style="' + inputStyle + '" ' +
            'onchange="updateUserField(\'' + u.clerk_id + '\',\'email\',this.value)"></td>' +
            '<td><input type="text" value="' + name.replace(/"/g, '&quot;') + '" placeholder="未設定" style="' + inputStyle + '" ' +
            'onchange="updateUserField(\'' + u.clerk_id + '\',\'display_name\',this.value)"></td>' +
            '<td style="font-size:0.75rem;color:#4a5568;font-family:monospace;" title="' + u.clerk_id + '">...' + shortId + '</td>' +
            '<td><select style="padding:4px;background:#0a0a0f;border:1px solid #1e1e2e;border-radius:4px;color:#e7e9ea;font-size:0.82rem;" ' +
            'onchange="updateUserRole(\'' + u.clerk_id + '\',this.value,this)">' +
            '<option value="standard"' + ((!u.role || u.role === 'standard' || u.role === 'user') ? ' selected' : '') + '>普通會員</option>' +
            '<option value="advanced"' + (u.role === 'advanced' ? ' selected' : '') + '>進階會員</option>' +
            '<option value="admin"' + (u.role === 'admin' ? ' selected' : '') + '>管理員</option>' +
            '</select></td>' +
            '<td><input type="number" value="' + u.max_bots + '" min="0" max="999" style="width:60px;padding:4px;background:#0a0a0f;border:1px solid #1e1e2e;border-radius:4px;color:#e7e9ea;text-align:center;" ' +
            'onchange="updateMaxBots(\'' + u.clerk_id + '\',this.value)"></td>' +
            '<td><span class="badge ' + (isActive ? 'badge-running' : 'badge-error') + '">' + (isActive ? '啟用' : '停用') + '</span></td>' +
            '<td style="font-size:0.8rem;color:#6b7280;">' + (u.created_at || '').slice(0, 10) + '</td>' +
            '<td><button class="btn btn-sm ' + (isActive ? 'btn-danger' : 'btn-success') + '" ' +
            'onclick="toggleUserActive(\'' + u.clerk_id + '\')">' + (isActive ? '停用' : '啟用') + '</button></td></tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

async function toggleUserActive(clerkId) {
    try { const resp = await authFetch('/api/admin/users/' + clerkId + '/toggle', { method: 'POST' }); if (resp.ok) loadAdminUsers(); }
    catch (err) { alert('操作失敗'); }
}

async function updateUserRole(clerkId, role, selectEl) {
    try {
        const resp = await authFetch('/api/admin/users/' + clerkId + '/role', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: role })
        });
        if (resp.ok) {
            const data = await resp.json();
            // Update the max_bots input in the same row
            const row = selectEl.closest('tr');
            if (row) {
                const maxBotsInput = row.querySelector('input[type="number"]');
                if (maxBotsInput) maxBotsInput.value = data.max_bots;
            }
        } else { alert('更新失敗'); }
    } catch (err) { alert('操作失敗'); }
}

async function updateMaxBots(clerkId, maxBots) {
    try { await safeFetch('/api/admin/users/' + clerkId + '/max-bots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ max_bots: parseInt(maxBots) }) }); }
    catch (err) { alert('操作失敗: ' + err.message); }
}

async function updateUserField(clerkId, field, value) {
    try {
        const resp = await authFetch('/api/admin/users/' + clerkId + '/update', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: value })
        });
        if (!resp.ok) alert('更新失敗');
    } catch (err) { alert('更新失敗'); }
}

async function reloadBotsFromDB(btn) {
    btn.disabled = true; btn.textContent = '重載中...';
    try {
        const resp = await authFetch('/api/admin/reload-bots', { method: 'POST' });
        if (resp.ok) {
            const data = await resp.json();
            btn.textContent = '已重載 ' + data.count + ' 個';
            loadBots(true);
            setTimeout(() => { btn.textContent = '重載 Bots'; btn.disabled = false; }, 3000);
        } else {
            btn.textContent = '重載失敗'; btn.disabled = false;
        }
    } catch (err) { btn.textContent = '重載失敗'; btn.disabled = false; }
}

async function syncClerkEmails(btn) {
    btn.disabled = true; btn.textContent = '同步中...';
    try {
        const resp = await authFetch('/api/admin/sync-clerk', { method: 'POST' });
        if (resp.ok) {
            const data = await resp.json();
            btn.textContent = '已同步 ' + data.updated + ' 筆';
            if (data.updated > 0) loadAdminUsers();
            setTimeout(() => { btn.textContent = '同步 Email'; btn.disabled = false; }, 3000);
        } else {
            btn.textContent = '同步失敗'; btn.disabled = false;
        }
    } catch (err) { btn.textContent = '同步失敗'; btn.disabled = false; }
}

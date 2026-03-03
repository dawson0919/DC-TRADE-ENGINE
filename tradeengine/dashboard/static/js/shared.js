/* ════════════════════════════════════════════════
   Tab Navigation
════════════════════════════════════════════════ */
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-nav .tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tabName).classList.add('active');
    const tabBtn = document.querySelector(`.tab-nav .tab[data-tab="${tabName}"]`);
    if (tabBtn) tabBtn.classList.add('active');

    if (tabName === 'dashboard') loadDashboard();
    if (tabName === 'strategies' && !strategiesLoaded) loadStrategies();
    if (tabName === 'bots') loadBots(true);
    if (tabName === 'account') loadAccount();
    if (tabName === 'admin') loadAdminUsers();
}
document.querySelectorAll('.tab-nav .tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});
/* ════════════════════════════════════════════════
   Shared: Strategy Params & Data Source Toggle
════════════════════════════════════════════════ */
async function loadStrategyParams(prefix) {
    const stratName = document.getElementById(prefix + '-strategy').value;
    let data;
    try { data = await safeFetch('/api/strategy/' + stratName); } catch (e) { return; }
    const container = document.getElementById(prefix + '-params');
    container.innerHTML = '';
    if (!data.parameters || data.parameters.length === 0) return;
    container.innerHTML = '<label style="color:#f7931a;font-size:0.9rem;margin-bottom:8px;display:block;">策略參數</label>';
    data.parameters.forEach(p => {
        const div = document.createElement('div');
        div.className = 'form-group';
        if (p.type === 'select') {
            div.innerHTML = `<label>${p.display_name}</label>
                <select id="${prefix}-param-${p.name}" data-param="${p.name}">
                    ${p.options.map(o => `<option value="${o}" ${o == p.default ? 'selected' : ''}>${o}</option>`).join('')}
                </select>`;
        } else {
            div.innerHTML = `<label>${p.display_name} (預設: ${p.default})</label>
                <input type="number" id="${prefix}-param-${p.name}" data-param="${p.name}"
                       value="${p.default}" min="${p.min != null ? p.min : ''}" max="${p.max != null ? p.max : ''}" step="${p.step || 1}">`;
        }
        container.appendChild(div);
    });
}

function collectParams(prefix) {
    const params = {};
    document.querySelectorAll('#' + prefix + '-params [data-param]').forEach(el => {
        params[el.dataset.param] = el.tagName === 'SELECT' ? el.value :
            (el.type === 'number' ? parseFloat(el.value) : el.value);
    });
    return params;
}

function toggleSource(prefix) {
    const src = document.getElementById(prefix + '-source').value;
    document.getElementById(prefix + '-api-fields').style.display = src === 'api' ? '' : 'none';
    document.getElementById(prefix + '-csv-fields').style.display = src === 'csv' ? '' : 'none';
    if (src === 'csv') filterCsvByTimeframe(prefix);
}

function filterCsvByTimeframe(prefix) {
    const tf = document.getElementById(prefix + '-timeframe').value;
    const sel = document.getElementById(prefix + '-csv');
    if (!sel) return;
    const opts = sel.querySelectorAll('option');
    let firstVisible = null;
    opts.forEach(o => {
        const match = !o.dataset.tf || o.dataset.tf === tf || o.dataset.tf === 'unknown';
        o.style.display = match ? '' : 'none';
        o.disabled = !match;
        if (match && !firstVisible) firstVisible = o;
    });
    // Auto-select first matching option
    if (firstVisible && sel.selectedOptions[0] && sel.selectedOptions[0].disabled) {
        sel.value = firstVisible.value;
    }
}

function buildDataUrl(prefix) {
    const source = document.getElementById(prefix + '-source').value;
    const tf = document.getElementById(prefix + '-timeframe').value;
    if (source === 'csv') {
        const csvSel = document.getElementById(prefix + '-csv');
        const csvSym = csvSel.options[csvSel.selectedIndex].dataset.symbol || '';
        return '&csv_path=' + encodeURIComponent(csvSel.value) + '&timeframe=' + tf + (csvSym ? '&symbol=' + encodeURIComponent(csvSym) : '');
    }
    return '&symbol=' + document.getElementById(prefix + '-symbol').value +
        '&timeframe=' + tf +
        '&limit=' + document.getElementById(prefix + '-limit').value;
}

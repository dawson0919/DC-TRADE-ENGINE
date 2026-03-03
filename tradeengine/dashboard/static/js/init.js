/* ════════════════════════════════════════════════
   Init
════════════════════════════════════════════════ */
function detectInAppBrowser() {
    const ua = navigator.userAgent || '';
    if (/Line\/|LIFF|FBAN|FBAV|Instagram|MicroMessenger|Twitter/i.test(ua)) {
        const el = document.getElementById('inAppBrowserWarning');
        el.style.display = 'flex';
        document.getElementById('inAppUrl').textContent = location.href;
    }
}
function copyInAppUrl() {
    const url = location.href;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
            document.getElementById('inAppCopyBtn').textContent = '已複製!';
            setTimeout(() => { document.getElementById('inAppCopyBtn').textContent = '複製連結'; }, 2000);
        });
    } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        document.getElementById('inAppCopyBtn').textContent = '已複製!';
        setTimeout(() => { document.getElementById('inAppCopyBtn').textContent = '複製連結'; }, 2000);
    }
}

window.addEventListener('load', () => {
    detectInAppBrowser();
    initAuth();
    loadStrategyParams('bt');
    filterCsvByTimeframe('bt');
    filterCsvByTimeframe('opt');
    lucide.createIcons();
});

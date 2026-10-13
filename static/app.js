(() => {
'use strict';

const PAGE_SIZE = 20;
const UNSPECIFIED = 'Not specified';
const state = {
    data: null,
    fileName: '',
    selected: new Set(),
    removed: new Set(),
    excluded: new Set(),
    order: {},          // itemCode -> [suffix, ...] (user's custom ordering)
    collapsed: new Set(),
    visible: PAGE_SIZE,
    file: null,
    currentList: []
};

const $ = id => document.getElementById(id);
let me = null;

async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: 'same-origin', ...opts });
    if (res.status === 401) { window.location.href = '/login.html'; throw new Error('Please sign in to continue.'); }
    return res;
}
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString();

/* ------------------------------------------------------------ views & toasts */
function showView(name) {
    ['setupView', 'loadingView', 'resultsView'].forEach(v => $(v).classList.toggle('hidden', v !== name));
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toast(msg, type = '', action = null, ms = 5000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${esc(msg)}</span>`;
    if (action) {
        const b = document.createElement('button');
        b.textContent = action.label;
        b.onclick = () => { action.fn(); el.remove(); };
        el.appendChild(b);
    }
    $('toasts').appendChild(el);
    setTimeout(() => el.remove(), ms);
}

/* ------------------------------------------------------------ upload handling */
let inputMode = 'file';
function parseCodes() { return [...new Set(($('codesInput').value || '').split(/[\s,;]+/).map(s => s.trim()).filter(Boolean))]; }
function refreshRunState() {
    $('verifyBtn').disabled = inputMode === 'file' ? !state.file : parseCodes().length === 0;
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
    inputMode = t.dataset.tab;
    document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === t));
    $('filePane').classList.toggle('hidden', inputMode !== 'file');
    $('pastePane').classList.toggle('hidden', inputMode !== 'paste');
    refreshRunState();
}));
$('codesInput').addEventListener('input', () => {
    const n = parseCodes().length;
    $('codesCount').textContent = n ? `${fmt(n)} unique code${n === 1 ? '' : 's'} detected` : '';
    refreshRunState();
});

const dz = $('dropzone'), fileInput = $('fileInput');

function setFile(file) {
    if (!file) return;
    if (!/\.(csv|xlsx|xls)$/i.test(file.name)) {
        toast('Unsupported file type. Please upload a .csv or .xlsx file.', 'error');
        return;
    }
    state.file = file;
    $('fileName').textContent = file.name;
    $('fileSize').textContent = file.size > 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
    $('fileChip').classList.remove('hidden');
    dz.classList.add('hidden');
    refreshRunState();
}

function clearFile() {
    state.file = null;
    fileInput.value = '';
    $('fileChip').classList.add('hidden');
    dz.classList.remove('hidden');
    refreshRunState();
}

dz.addEventListener('click', () => fileInput.click());
dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', e => setFile(e.dataTransfer.files[0]));
fileInput.addEventListener('change', () => setFile(fileInput.files[0]));
$('fileClear').addEventListener('click', clearFile);

/* ------------------------------------------------------------ analysis */
function startLoading() {
    $('barFill').classList.remove('determinate');
    $('barFill').style.width = '';
    $('loadingText').textContent = 'Preparing analysis';
    $('loadingCount').textContent = '';
    $('loadingPct').textContent = '';
    showView('loadingView');
}
function stopLoading() {}

function onProgress(ev) {
    const bar = $('barFill');
    bar.classList.add('determinate');
    bar.style.width = `${Math.min(ev.percent, 100)}%`;
    $('loadingPct').textContent = `${Math.min(ev.percent, 100)}%`;
    $('loadingText').textContent = ev.message;
    $('loadingCount').textContent = ev.total ? `${fmt(ev.done)} of ${fmt(ev.total)} checked` : '';
}

async function runAnalysis() {
    const brand = document.querySelector('input[name="brand"]:checked').value;
    const fd = new FormData();
    fd.append('brand', brand);
    let sourceName;
    if (inputMode === 'file') {
        if (!state.file) { toast('Please upload a file first.', 'error'); return; }
        fd.append('file', state.file);
        sourceName = state.file.name;
    } else {
        const codes = parseCodes();
        if (!codes.length) { toast('Please paste at least one item code.', 'error'); return; }
        fd.append('codes', codes.join('\n'));
        sourceName = `${fmt(codes.length)} pasted item code${codes.length === 1 ? '' : 's'}`;
    }

    $('verifyBtn').disabled = true;
    startLoading();

    try {
        const res = await api('/api/v1/analyze', { method: 'POST', body: fd });
        if (!res.ok) {
            let msg = `We could not process this request (error ${res.status}). Please try again.`;
            try { const jr = await res.json(); if (jr.detail) msg = jr.detail; } catch (_) {}
            throw new Error(msg);
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '', result = null;
        const handle = line => {
            if (!line.trim()) return;
            const ev = JSON.parse(line);
            if (ev.type === 'progress') onProgress(ev);
            else if (ev.type === 'result') result = ev.data;
            else if (ev.type === 'error') throw new Error(ev.detail);
        };
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let i;
            while ((i = buf.indexOf('\n')) >= 0) { handle(buf.slice(0, i)); buf = buf.slice(i + 1); }
        }
        handle(buf);
        if (!result) throw new Error('The connection was interrupted before results were ready. Please try again.');
        state.data = result;
        state.fileName = sourceName;
        state.selected.clear(); state.removed.clear(); state.excluded.clear();
        state.order = {}; state.collapsed.clear(); state.visible = PAGE_SIZE;
        stopLoading();
        populateResults(brand);
        showView('resultsView');
        loadMe();
    } catch (err) {
        stopLoading();
        showView('setupView');
        toast(err.message || 'Something went wrong. Please try again.', 'error', null, 7000);
    } finally {
        refreshRunState();
    }
}

function populateResults(brand) {
    const s = state.data.summary;
    const missing = s.total_items - s.active_items;
    const pct = s.total_items ? (s.active_items / s.total_items) * 100 : 0;
    $('resultsBrand').textContent = brand.charAt(0).toUpperCase() + brand.slice(1);
    $('resultsFile').textContent = state.fileName;
    $('mTotal').textContent = fmt(s.total_items);
    $('mActive').textContent = fmt(s.active_items);
    $('mMissing').textContent = fmt(missing);
    $('mImages').textContent = fmt(s.total_images_found);
    $('coveragePct').textContent = `${pct.toFixed(1)}%`;
    $('meterFill').style.width = '0';
    requestAnimationFrame(() => requestAnimationFrame(() => { $('meterFill').style.width = `${pct}%`; }));

    const divisions = [...new Set(Object.values(state.data.items).map(v => v.division).filter(d => d !== UNSPECIFIED))].sort();
    $('divFilter').classList.toggle('hidden', divisions.length === 0);
    $('toolbarEl').classList.toggle('no-div', divisions.length === 0);
    $('divFilter').innerHTML = '<option value="All Divisions">All divisions</option>' + divisions.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
    $('searchInput').value = '';
    $('divFilter').value = 'All Divisions';
    $('statusFilter').value = 'All Products';
    updateSelectionBar();
    renderInspector();
}

/* ------------------------------------------------------------ data helpers */
function labelFor(suffix) {
    if (suffix.includes('~')) { const [s, region] = suffix.split('~'); return `${labelFor(s)} (${region})`; }
    if (suffix === '-HERO') return 'Hero View';
    if (suffix.startsWith('_')) return `View ${suffix}`;
    return `Alt ${suffix.replace('-ALT', '')}`;
}

function getActiveItems(code) {
    const info = state.data.items[code];
    let list = Object.entries(info.urls)
        .filter(([sfx, url]) => state.data.available[url] && !state.removed.has(`${code}|${sfx}`))
        .map(([sfx, url]) => ({ id: `${code}|${sfx}`, sfx, label: labelFor(sfx), url }));
    const custom = state.order[code];
    if (custom) {
        const rank = new Map(custom.map((s, i) => [s, i]));
        list.sort((a, b) => (rank.has(a.sfx) ? rank.get(a.sfx) : 1e6) - (rank.has(b.sfx) ? rank.get(b.sfx) : 1e6));
    }
    return list;
}

function hasAnyImage(code) {
    return Object.values(state.data.items[code].urls).some(u => state.data.available[u]);
}

function filteredCodes() {
    const tokens = $('searchInput').value.trim().toUpperCase().split(',').map(t => t.trim()).filter(Boolean);
    const div = $('divFilter').value, status = $('statusFilter').value;
    const out = [];
    for (const [code, info] of Object.entries(state.data.items)) {
        if (state.excluded.has(code)) continue;
        if (div !== 'All Divisions' && info.division !== div) continue;
        const active = hasAnyImage(code);
        if (status === 'Active Only' && !active) continue;
        if (status === 'Missing Only' && active) continue;
        if (tokens.length && !tokens.some(t => code.includes(t))) continue;
        out.push(code);
    }
    return out;
}

function buildRows(codes, onlySelected) {
    const rows = [];
    codes.forEach(code => {
        const info = state.data.items[code];
        let items = getActiveItems(code);
        if (onlySelected) items = items.filter(i => state.selected.has(i.id));
        items.forEach((item, idx) => rows.push({
            'Handle': code.toLowerCase(),
            'Item Code': code,
            'Image Position': idx + 1,
            'Image Src': item.url,
            'Image Alt Text': `${code} - ${item.label}`,
            'Division': info.division
        }));
    });
    return rows;
}

/* ------------------------------------------------------------ rendering */
function lookupHTML(info) {
    const sites = (state.data && state.data.lookups) || [];
    if (!sites.length) return '';
    const links = sites.map(s => {
        const url = s.template.replace('{root}', encodeURIComponent(info.root));
        return `<a class="chip" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)}${s.note ? ` <em>${esc(s.note)}</em>` : ''}</a>`;
    }).join('');
    return `<div class="lookup">
        <div class="lookup-title">Search regional storefronts</div>
        <div class="lookup-sub">Imagery may be published on another market. Open a storefront to look for style ${esc(info.root)}.</div>
        <div class="lookup-links">${links}</div>
    </div>`;
}

const CHEVRON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';

function productHTML(code) {
    const info = state.data.items[code];
    const items = getActiveItems(code);
    const allSel = items.length > 0 && items.every(i => state.selected.has(i.id));
    const collapsed = state.collapsed.has(code);
    const c = esc(code);
    return `
    <article class="product ${collapsed ? 'collapsed' : ''}" data-code="${c}">
        <div class="product-head">
            <button class="toggle" data-action="toggle" aria-label="Expand or collapse">${CHEVRON}</button>
            <input type="checkbox" data-action="partition" ${allSel ? 'checked' : ''} ${items.length ? '' : 'disabled'} aria-label="Select all images for ${c}">
            <span class="p-title">${c}</span>
            <span class="badge ${items.length ? 'ok' : 'bad'}">${items.length ? 'Active' : 'Missing'}</span>
            <div class="p-meta">
                <span>Root <b>${esc(info.root)}</b></span>
                ${info.division !== UNSPECIFIED ? `<span>Division <b>${esc(info.division)}</b></span>` : ''}
                <span>Images <b>${items.length}</b></span>
            </div>
            <div class="p-actions">
                ${items.length ? `<button class="btn-quiet" data-action="export-one">Export</button>` : ''}
                <button class="btn-danger-ghost" data-action="remove-product">Remove</button>
            </div>
        </div>
        <div class="product-body">
            ${items.length ? `<div class="grid-container" data-grid="${c}">
                ${items.map((item, idx) => `
                <div class="card ${state.selected.has(item.id) ? 'selected' : ''}" data-id="${esc(item.id)}" data-sfx="${esc(item.sfx)}">
                    <input type="checkbox" data-action="select" ${state.selected.has(item.id) ? 'checked' : ''} aria-label="Select ${esc(item.label)}">
                    <span class="pos-badge">${idx + 1}</span>
                    <button class="x" data-action="remove-image" title="Remove image" aria-label="Remove image">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
                    </button>
                    <div class="thumb"><img src="${esc(item.url)}" alt="${esc(item.label)}" loading="lazy" decoding="async"></div>
                    <div class="label">${esc(item.label)}</div>
                </div>`).join('')}
            </div>` : `<div class="empty-note">No imagery is currently available for this product.</div>${lookupHTML(info)}`}
        </div>
    </article>`;
}

function renderInspector() {
    if (!state.data) return;
    const codes = filteredCodes();
    state.currentList = codes;
    const shown = codes.slice(0, state.visible);
    const container = $('inspectorContainer');

    if (!codes.length) {
        container.innerHTML = '<div class="panel empty-note" style="text-align:center">No products match your current filters.</div>';
    } else {
        container.innerHTML = shown.map(productHTML).join('');
        container.querySelectorAll('img').forEach(img => {
            if (img.complete && img.naturalWidth) img.classList.add('loaded');
            else {
                img.addEventListener('load', () => img.classList.add('loaded'));
                img.addEventListener('error', () => { img.closest('.thumb').innerHTML = '<span class="muted" style="font-size:12px">Preview unavailable</span>'; });
            }
        });
        container.querySelectorAll('[data-grid]').forEach(initSortable);
    }

    const imgCount = codes.reduce((n, c) => n + getActiveItems(c).length, 0);
    $('listCount').textContent = `Showing ${fmt(Math.min(shown.length, codes.length))} of ${fmt(codes.length)} products  |  ${fmt(imgCount)} images`;
    $('loadMore').classList.toggle('hidden', codes.length <= shown.length);
    $('loadMore').textContent = `Show ${Math.min(PAGE_SIZE, codes.length - shown.length)} more products`;
    $('exportAllBtn').disabled = imgCount === 0;
    $('exportAllBtn').textContent = imgCount ? `Export displayed images (${fmt(imgCount)})` : 'Export displayed images';
}

function initSortable(grid) {
    const code = grid.dataset.grid;
    new Sortable(grid, {
        animation: 150,
        ghostClass: 'sortable-ghost',
        filter: 'input,button',
        preventOnFilter: false,
        onEnd() {
            const cards = [...grid.children];
            state.order[code] = cards.map(c => c.dataset.sfx);
            cards.forEach((c, i) => { c.querySelector('.pos-badge').textContent = i + 1; });
        }
    });
}

/* ------------------------------------------------------------ interactions */
$('inspectorContainer').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const productEl = btn.closest('.product');
    const code = productEl && productEl.dataset.code;
    const action = btn.dataset.action;

    if (action === 'toggle') {
        productEl.classList.toggle('collapsed');
        if (productEl.classList.contains('collapsed')) state.collapsed.add(code); else state.collapsed.delete(code);
    } else if (action === 'export-one') {
        const rows = buildRows([code], false);
        runDownload(btn, '/api/v1/reports/export', { rows, filename: `Image_Export_${code}` }, `Image_Export_${code}.xlsx`);
    } else if (action === 'remove-product') {
        state.excluded.add(code);
        getActiveItems(code).forEach(i => state.selected.delete(i.id));
        updateSelectionBar();
        renderInspector();
        toast(`${code} removed from this view`, '', { label: 'Undo', fn: () => { state.excluded.delete(code); renderInspector(); } });
    } else if (action === 'remove-image') {
        const id = btn.closest('.card').dataset.id;
        state.removed.add(id);
        state.selected.delete(id);
        updateSelectionBar();
        renderInspector();
        toast('Image removed', '', { label: 'Undo', fn: () => { state.removed.delete(id); renderInspector(); } });
    }
});

$('inspectorContainer').addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.action === 'select') {
        const card = t.closest('.card'), id = card.dataset.id;
        t.checked ? state.selected.add(id) : state.selected.delete(id);
        card.classList.toggle('selected', t.checked);
        const productEl = t.closest('.product');
        const items = getActiveItems(productEl.dataset.code);
        productEl.querySelector('[data-action="partition"]').checked = items.length > 0 && items.every(i => state.selected.has(i.id));
        updateSelectionBar();
    } else if (t.dataset.action === 'partition') {
        const productEl = t.closest('.product');
        getActiveItems(productEl.dataset.code).forEach(i => t.checked ? state.selected.add(i.id) : state.selected.delete(i.id));
        productEl.querySelectorAll('.card').forEach(c => {
            const on = state.selected.has(c.dataset.id);
            c.classList.toggle('selected', on);
            c.querySelector('[data-action="select"]').checked = on;
        });
        updateSelectionBar();
    }
});

function updateSelectionBar() {
    const n = state.selected.size;
    $('selectedCountText').textContent = `${fmt(n)} image${n === 1 ? '' : 's'} selected`;
    $('popoutBar').classList.toggle('visible', n > 0);
}

let searchTimer;
$('searchInput').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.visible = PAGE_SIZE; renderInspector(); }, 200); });
['divFilter', 'statusFilter'].forEach(id => $(id).addEventListener('change', () => { state.visible = PAGE_SIZE; renderInspector(); }));
$('loadMore').addEventListener('click', () => { state.visible += PAGE_SIZE; renderInspector(); });
$('expandAll').addEventListener('click', () => { state.collapsed.clear(); renderInspector(); });
$('collapseAll').addEventListener('click', () => { state.currentList.forEach(c => state.collapsed.add(c)); renderInspector(); });
$('clearSelection').addEventListener('click', () => { state.selected.clear(); updateSelectionBar(); renderInspector(); });
$('verifyBtn').addEventListener('click', runAnalysis);
$('newAnalysisBtn').addEventListener('click', () => {
    if (state.selected.size || state.removed.size || state.excluded.size || Object.keys(state.order).length) {
        if (!confirm('Start a new analysis? Your current edits will be cleared.')) return;
    }
    state.data = null; state.selected.clear(); updateSelectionBar();
    $('codesInput').value = ''; $('codesCount').textContent = '';
    clearFile();
    showView('setupView');
});

/* ------------------------------------------------------------ downloads */
async function runDownload(btn, url, payload, filename) {
    if (btn.classList.contains('busy')) return;
    const original = btn.textContent;
    btn.classList.add('busy');
    btn.textContent = 'Preparing...';
    try {
        const res = await api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) {
            let msg = `The export could not be generated (error ${res.status}).`;
            try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }
        const blob = await res.blob();
        if (!blob.size) throw new Error('The export came back empty. Please try again.');
        triggerDownload(blob, filename);
        toast('Download started', 'success', null, 2500);
    } catch (err) {
        toast(err.message || 'Download failed. Please try again.', 'error', null, 6000);
    } finally {
        btn.classList.remove('busy');
        btn.textContent = original;
    }
}

function triggerDownload(blob, filename) {
    const typed = new Blob([blob], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(typed);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
}

$('coverageBtn').addEventListener('click', e => runDownload(e.currentTarget, '/api/v1/reports/coverage',
    { brand: state.data.brand, items: state.data.items, available: state.data.available }, 'Catalog_Coverage_Report.xlsx'));

$('exportAllBtn').addEventListener('click', e => {
    const rows = buildRows(state.currentList, false);
    if (!rows.length) { toast('There are no images to export.', 'error'); return; }
    runDownload(e.currentTarget, '/api/v1/reports/export', { rows, filename: 'Image_Export_All' }, 'Image_Export_All.xlsx');
});

$('exportSelectedBtn').addEventListener('click', e => {
    const rows = buildRows(Object.keys(state.data.items), true);
    if (!rows.length) { toast('Select at least one image to export.', 'error'); return; }
    runDownload(e.currentTarget, '/api/v1/reports/export', { rows, filename: 'Image_Export_Selected' }, 'Image_Export_Selected.xlsx');
});

/* ------------------------------------------------------------ account */
function renderUser() {
    if (!me || !me.usage) return;
    $('userName').textContent = me.name || me.email;
    $('userBox').classList.remove('hidden');
    $('adminLink').classList.toggle('hidden', me.role !== 'admin');
    const { used, limit } = me.usage;
    $('usageBox').classList.remove('hidden');
    if (limit === null) {
        $('usageText').textContent = `${fmt(used)} products this month`;
        $('usageFill').style.width = '0%';
    } else {
        $('usageText').textContent = `${fmt(used)} of ${fmt(limit)} products`;
        const pct = limit ? Math.min(100, (used / limit) * 100) : 100;
        $('usageFill').style.width = `${pct}%`;
        $('usageFill').classList.toggle('warn', pct >= 85);
    }
}
async function loadMe() {
    try {
        const r = await api('/api/v1/auth/me');
        if (!r.ok) { toast(`We could not load your account details (error ${r.status}).`, 'error', null, 8000); return; }
        me = await r.json();
        renderUser();
    } catch (_) {}
}
$('logoutBtn').addEventListener('click', async () => {
    try { await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) {}
    window.location.href = '/login.html';
});
loadMe().then(() => document.body.classList.remove('booting'));

/* ------------------------------------------------------------ theme */
$('themeToggle').addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (_) {}
});

$('year').textContent = new Date().getFullYear();
})();

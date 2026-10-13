(() => {
'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString();
const when = iso => iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Never';
let users = [], editingId = null;

async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: 'same-origin', ...opts });
    if (res.status === 401) { window.location.href = '/login.html'; throw new Error('Please sign in.'); }
    if (res.status === 403) { window.location.href = '/'; throw new Error('Administrator access is required.'); }
    return res;
}
function toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = `toast ${type}`; el.textContent = msg;
    $('toasts').appendChild(el); setTimeout(() => el.remove(), 4000);
}

async function loadAll() {
    const [s, u, a] = await Promise.all([
        api('/api/v1/admin/stats').then(r => r.json()),
        api('/api/v1/admin/users').then(r => r.json()),
        api('/api/v1/admin/activity?limit=100').then(r => r.json()),
    ]);
    users = u;
    $('kpis').innerHTML = [
        ['Customers', s.users, ''], ['Active accounts', s.active_users, 'ok'],
        ['Products this month', s.products_this_month, 'info'], ['Runs this month', s.runs_this_month, ''],
    ].map(([l, v, c]) => `<div class="kpi ${c}"><span>${l}</span><strong>${fmt(v)}</strong></div>`).join('');

    $('usersTable').querySelector('tbody').innerHTML = u.map(x => {
        const lim = x.monthly_limit === null ? 'Unlimited' : fmt(x.monthly_limit);
        return `<tr>
            <td><div class="cell-main">${esc(x.name || x.email)}</div><div class="cell-sub">${esc(x.email)}${x.company ? ' | ' + esc(x.company) : ''}</div></td>
            <td>${x.role === 'admin' ? 'Administrator' : 'Customer'}</td>
            <td><span class="badge ${x.is_active ? 'ok' : 'bad'}">${x.is_active ? 'Active' : 'Disabled'}</span></td>
            <td>${fmt(x.used_this_month)} <span class="muted">/ ${lim}</span></td>
            <td>${fmt(x.used_total)}</td>
            <td>${esc(when(x.last_login_at))}</td>
            <td class="right"><button class="btn-quiet" data-edit="${x.id}">Manage</button></td></tr>`;
    }).join('') || '<tr><td colspan="7" class="muted">No customers yet.</td></tr>';

    $('activityTable').querySelector('tbody').innerHTML = a.map(x => `<tr>
        <td>${esc(when(x.at))}</td><td>${esc(x.email)}</td><td>${esc(x.brand)}</td>
        <td class="trunc">${esc(x.source)}</td><td>${fmt(x.items)}</td><td>${fmt(x.images_found)}</td></tr>`).join('')
        || '<tr><td colspan="6" class="muted">No activity yet.</td></tr>';
}

const dlg = $('userDialog');
function openDialog(user) {
    editingId = user ? user.id : null;
    $('dialogTitle').textContent = user ? 'Manage customer' : 'Add customer';
    $('fEmail').value = user ? user.email : ''; $('fEmail').disabled = !!user;
    $('fName').value = user ? user.name : ''; $('fCompany').value = user ? user.company : '';
    $('fLimit').value = user && user.monthly_limit !== null ? user.monthly_limit : (user ? '' : '5000');
    $('fRole').value = user ? user.role : 'user';
    $('fPassword').value = ''; $('pwLabel').textContent = user ? 'New password (leave blank to keep)' : 'Password';
    $('activeRow').classList.toggle('hidden', !user); $('fActive').checked = user ? user.is_active : true;
    $('dialogError').classList.add('hidden');
    dlg.showModal();
}
$('addUserBtn').addEventListener('click', () => openDialog(null));
$('cancelDialog').addEventListener('click', () => dlg.close());
$('usersTable').addEventListener('click', e => {
    const b = e.target.closest('[data-edit]'); if (!b) return;
    openDialog(users.find(u => u.id === Number(b.dataset.edit)));
});

$('userForm').addEventListener('submit', async e => {
    e.preventDefault();
    const err = $('dialogError'); err.classList.add('hidden');
    const limitRaw = $('fLimit').value.trim();
    const limit = limitRaw === '' ? null : Number(limitRaw);
    const body = { name: $('fName').value, company: $('fCompany').value, role: $('fRole').value, monthly_limit: limit };
    let url, method;
    if (editingId) {
        url = `/api/v1/admin/users/${editingId}`; method = 'PATCH';
        body.is_active = $('fActive').checked;
        if ($('fPassword').value) body.password = $('fPassword').value;
    } else {
        url = '/api/v1/admin/users'; method = 'POST';
        body.email = $('fEmail').value; body.password = $('fPassword').value;
    }
    $('saveUser').disabled = true;
    try {
        const res = await api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the details and try again.');
        dlg.close(); toast(editingId ? 'Customer updated' : 'Customer created', 'success');
        await loadAll();
    } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
    finally { $('saveUser').disabled = false; }
});

$('logoutBtn').addEventListener('click', async () => {
    try { await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) {}
    window.location.href = '/login.html';
});
$('themeToggle').addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (_) {}
});
$('year').textContent = new Date().getFullYear();
loadAll().then(() => document.body.classList.remove('booting')).catch(() => {});
})();

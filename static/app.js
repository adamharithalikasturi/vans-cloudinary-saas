let globalData = null;
let selectedImageIds = new Set();
let excludedVans = new Set();
let removedImageIds = new Set();

// Automatically update default CDN input when brand changes
function updateDefaultCdn() {
    const brand = document.getElementById('brandSelect').value;
    const cdnInput = document.getElementById('baseCdn');
    if (brand === 'vans') {
        cdnInput.value = 'https://img.vans.com/image/upload/';
    } else if (brand === 'timberland') {
        cdnInput.value = 'https://assets.timberland.com/';
    } else if (brand === 'columbia') {
        cdnInput.value = 'https://www.columbia.com/dw/image/v2/AABW_PRD/on/demandware.static/-/Sites-columbia-master/default/';
    }
}

async function runVerification() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files[0]) { alert('Please upload a catalog file first.'); return; }

    const formData = new FormData();
    formData.append('brand', document.getElementById('brandSelect').value);
    formData.append('file', fileInput.files[0]);
    formData.append('base_cdn_url', document.getElementById('baseCdn').value);
    formData.append('preset', document.getElementById('preset').value);
    formData.append('max_concurrent', document.getElementById('maxConcurrent').value);
    formData.append('timeout', document.getElementById('timeout').value);

    document.getElementById('statusContainer').classList.remove('hidden');
    document.getElementById('verifyBtn').disabled = true;

    try {
        const response = await fetch('/api/verify-catalog', { method: 'POST', body: formData });
        if (!response.ok) {
            const errJson = await response.json();
            throw new Error(errJson.detail || 'Verification failed.');
        }
        
        globalData = await response.json();
        excludedVans.clear();
        removedImageIds.clear();
        selectedImageIds.clear();
        
        document.getElementById('mTotal').innerText = globalData.summary.total_items.toLocaleString();
        document.getElementById('mActive').innerText = globalData.summary.active_items.toLocaleString();
        document.getElementById('mMissing').innerText = (globalData.summary.total_items - globalData.summary.active_items).toLocaleString();
        document.getElementById('mImages').innerText = globalData.summary.total_images_found.toLocaleString();

        const divisions = [...new Set(Object.values(globalData.van_url_map).map(v => v.division))];
        const divSelect = document.getElementById('divFilter');
        divSelect.innerHTML = '<option value="All Divisions">All Divisions</option>' + divisions.map(d => `<option value="${d}">${d}</option>`).join('');

        document.getElementById('statusContainer').classList.add('hidden');
        document.getElementById('resultsArea').classList.remove('hidden');
        renderInspector();
    } catch (err) {
        alert('Error: ' + err.message);
        document.getElementById('statusContainer').classList.add('hidden');
    } finally {
        document.getElementById('verifyBtn').disabled = false;
    }
}

function renderInspector() {
    if (!globalData) return;
    const searchVal = document.getElementById('searchInput').value.trim().toUpperCase();
    const selectedDiv = document.getElementById('divFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;

    const container = document.getElementById('inspectorContainer');
    container.innerHTML = '';

    let displayItems = [];
    const searchTokens = searchVal ? searchVal.split(',').map(v => v.trim()).filter(Boolean) : [];

    for (let [itemCode, info] of Object.entries(globalData.van_url_map)) {
        if (excludedVans.has(itemCode)) continue;
        if (selectedDiv !== 'All Divisions' && info.division !== selectedDiv) continue;
        
        const hasActive = Object.values(info.urls).some(u => globalData.valid_url_map[u]);
        if (statusFilter === 'Active Only' && !hasActive) continue;
        if (statusFilter === 'Missing Only' && hasActive) continue;

        if (searchTokens.length > 0 && !searchTokens.includes(itemCode)) continue;
        displayItems.push(itemCode);
    }

    let globalShopifyRows = [];
    displayItems.forEach(itemCode => {
        let info = globalData.van_url_map[itemCode];
        let items = getActiveItems(itemCode);
        items.forEach((item, idx) => {
            globalShopifyRows.push({
                "Handle": itemCode.toLowerCase(),
                "Item Code": itemCode,
                "Image Position": idx + 1,
                "Image Src": item.url,
                "Image Alt Text": `${itemCode} - ${item.label}`,
                "Division": info.division
            });
        });
    });

    const exportContainer = document.getElementById('globalExportContainer');
    if (displayItems.length > 0 && globalShopifyRows.length > 0) {
        exportContainer.innerHTML = `<button onclick='downloadShopifyBatch(${JSON.stringify(globalShopifyRows)}, "Shopify_All_Displayed_Images_Export.xlsx")' class="bg-red-600 hover:bg-red-700 font-bold px-4 py-2 rounded text-sm cursor-pointer shadow">📥 Export All Displayed Images (${globalShopifyRows.length} total across ${displayItems.length} products) for Shopify (Excel)</button>`;
    } else {
        exportContainer.innerHTML = '';
    }

    if (displayItems.length === 0) {
        container.innerHTML = '<div class="text-slate-400 text-sm italic py-8 text-center">No matching catalog items found or selected.</div>';
        return;
    }

    displayItems.forEach(itemCode => {
        let info = globalData.van_url_map[itemCode];
        let items = getActiveItems(itemCode);
        let allSelected = items.length > 0 && items.every(i => selectedImageIds.has(i.id));

        const section = document.createElement('div');
        section.className = 'bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4 shadow-md';
        section.innerHTML = `
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-4">
                    <label class="flex items-center gap-2 text-xs font-semibold cursor-pointer text-slate-300">
                        <input type="checkbox" ${allSelected ? 'checked' : ''} onchange="togglePartition('${itemCode}', this.checked)" class="cursor-pointer w-4 h-4 rounded"> Select Partition
                    </label>
                    <h3 class="font-bold text-base text-blue-400 font-mono">Product Partition: ${itemCode}</h3>
                </div>
                <button onclick="removeProduct('${itemCode}')" class="bg-rose-600/20 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white px-3 py-1 rounded text-xs font-bold transition cursor-pointer">🗑️ Remove Product</button>
            </div>
            <div class="grid grid-cols-4 gap-4 text-xs text-slate-400 bg-slate-950/40 p-3 rounded">
                <div>Root Code: <span class="text-white font-mono">${info.root}</span></div>
                <div>Division: <span class="text-white">${info.division}</span></div>
                <div>Status: <span class="${items.length > 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}">${items.length > 0 ? '🟢 Active' : '🔴 Missing'}</span></div>
                <div>Images Active: <span class="text-white font-semibold">${items.length}</span></div>
            </div>
            <hr class="border-slate-800">
            <div class="grid-container" id="grid_${itemCode}">
                ${items.map((item, idx) => `
                    <div class="card bg-white text-slate-900 border border-slate-200 rounded-lg p-3 shadow relative flex flex-col items-center select-none cursor-grab active:cursor-grabbing transition transform hover:-translate-y-0.5 ${selectedImageIds.has(item.id) ? 'ring-2 ring-blue-500 bg-blue-50/50' : ''}" data-id="${item.id}">
                        <input type="checkbox" class="absolute top-2.5 left-2.5 cursor-pointer z-10 w-4 h-4" ${selectedImageIds.has(item.id) ? 'checked' : ''} onclick="toggleSelect('${item.id}')">
                        <span class="absolute top-2 left-9 bg-black/80 text-white text-[10px] px-2 py-0.5 rounded font-mono pos-badge">Pos ${idx + 1}</span>
                        <button onclick="removeCard('${item.id}')" class="absolute top-2 right-2 bg-rose-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold hover:scale-110 transition cursor-pointer z-10" title="Remove image">✕</button>
                        <img src="${item.url}" alt="${item.label}" class="w-full h-36 object-contain rounded mt-4 pointer-events-none">
                        <div class="mt-2 text-xs font-semibold text-center text-slate-800">${item.label}</div>
                        <a href="${item.url}" target="_blank" class="text-[11px] text-blue-600 mt-1 hover:underline font-medium" onclick="event.stopPropagation()">🔗 Direct URL</a>
                    </div>
                `).join('')}
            </div>
            ${items.length > 0 ? `<button onclick="downloadSinglePartition('${itemCode}')" class="bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold px-3 py-1.5 rounded text-xs cursor-pointer transition">📥 Download Shopify Excel for \`${itemCode}\` (${items.length} images)</button>` : ''}
        `;
        container.appendChild(section);

        // --- SORTABLEJS DRAG-AND-DROP REORDER BINDING ---
        if (items.length > 0) {
            const gridEl = document.getElementById(`grid_${itemCode}`);
            new Sortable(gridEl, {
                animation: 150,
                ghostClass: 'opacity-30',
                dragClass: 'scale-105 shadow-2xl',
                onEnd: function() {
                    const children = gridEl.children;
                    for (let i = 0; i < children.length; i++) {
                        const badge = children[i].querySelector('.pos-badge');
                        if (badge) badge.innerText = `Pos ${i + 1}`;
                    }
                }
            });
        }
    });
}

function getActiveItems(itemCode) {
    let info = globalData.van_url_map[itemCode];
    return Object.entries(info.urls)
        .filter(([suffix, url]) => globalData.valid_url_map[url] && !removedImageIds.has(`${itemCode}_${suffix}`))
        .map(([suffix, url]) => ({
            id: `${itemCode}_${suffix}`,
            label: suffix === '-HERO' ? 'Hero View' : (suffix.startsWith('_') ? `View ${suffix}` : `Alt ${suffix.replace('-ALT', '')}`),
            url: url
        }));
}

function toggleSelect(id) {
    if (selectedImageIds.has(id)) selectedImageIds.delete(id);
    else selectedImageIds.add(id);
    updatePopoutBar();
    
    const cardEl = document.querySelector(`.card[data-id="${id}"]`);
    if (cardEl) {
        if (selectedImageIds.has(id)) cardEl.classList.add('ring-2', 'ring-blue-500', 'bg-blue-50/50');
        else cardEl.classList.remove('ring-2', 'ring-blue-500', 'bg-blue-50/50');
    }
}

function togglePartition(itemCode, select) {
    let items = getActiveItems(itemCode);
    items.forEach(i => {
        if (select) selectedImageIds.add(i.id);
        else selectedImageIds.delete(i.id);
    });
    updatePopoutBar();
    renderInspector();
}

function removeCard(id) {
    removedImageIds.add(id);
    selectedImageIds.delete(id);
    updatePopoutBar();
    renderInspector();
}

function removeProduct(itemCode) {
    excludedVans.add(itemCode);
    getActiveItems(itemCode).forEach(i => selectedImageIds.delete(i.id));
    updatePopoutBar();
    renderInspector();
}

function updatePopoutBar() {
    const bar = document.getElementById('popoutBar');
    document.getElementById('selectedCountText').innerText = `${selectedImageIds.size} selected`;
    if (selectedImageIds.size > 0) bar.classList.add('visible');
    else bar.classList.remove('visible');
}

async function downloadMasterReport() {
    const response = await fetch('/api/download-master-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand: globalData.brand, van_url_map: globalData.van_url_map, valid_url_map: globalData.valid_url_map })
    });
    triggerDownload(await response.blob(), 'Cloudinary_Verified_Master.xlsx');
}

async function downloadSinglePartition(itemCode) {
    let info = globalData.van_url_map[itemCode];
    let items = getActiveItems(itemCode);
    let rows = items.map((item, idx) => ({
        "Handle": itemCode.toLowerCase(),
        "Item Code": itemCode,
        "Image Position": idx + 1,
        "Image Src": item.url,
        "Image Alt Text": `${itemCode} - ${item.label}`,
        "Division": info.division
    }));
    downloadShopifyBatch(rows, `Shopify_Export_${itemCode}.xlsx`);
}

async function downloadSelectedBundle() {
    let rows = [];
    for (let [itemCode, info] of Object.entries(globalData.van_url_map)) {
        let items = getActiveItems(itemCode);
        items.forEach((item, idx) => {
            if (selectedImageIds.has(item.id)) {
                rows.push({
                    "Handle": itemCode.toLowerCase(),
                    "Item Code": itemCode,
                    "Image Position": rows.length + 1,
                    "Image Src": item.url,
                    "Image Alt Text": `${itemCode} - ${item.label}`,
                    "Division": info.division
                });
            }
        });
    }
    downloadShopifyBatch(rows, 'Shopify_Multi_Product_Selected_Export.xlsx');
}

async function downloadShopifyBatch(rows, filename) {
    const response = await fetch('/api/download-shopify-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows })
    });
    triggerDownload(await response.blob(), filename);
}

function triggerDownload(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
}

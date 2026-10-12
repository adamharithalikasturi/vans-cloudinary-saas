let globalData = null;
let selectedImageIds = new Set();
let excludedVans = new Set();
let removedImageIds = new Set();

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
        if (!response.ok) throw new Error('Verification failed.');
        
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
        alert('Error processing file.');
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
        exportContainer.innerHTML = `<button onclick='downloadShopifyBatch(${JSON.stringify(globalShopifyRows)}, "Shopify_All_Displayed_Images_Export.xlsx")' class="bg-red-600 hover:bg-red-700 font-bold px-4 py-2 rounded text-sm cursor-pointer">📥 Export All Displayed Images (${globalShopifyRows.length} total across ${displayItems.length} products) for Shopify (Excel)</button>`;
    } else {
        exportContainer.innerHTML = '';
    }

    if (displayItems.length === 0) {
        container.innerHTML = '<div class="text-slate-400 text-sm italic">No matching catalog items found or selected.</div>';
        return;
    }

    displayItems.forEach(itemCode => {
        let info = globalData.van_url_map[itemCode];
        let items = getActiveItems(itemCode);
        let allSelected = items.length > 0 && items.every(i => selectedImageIds.has(i.id));

        const section = document.createElement('div');
        section.className = 'bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4';
        section.innerHTML = `
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-4">
                    <label class="flex items-center gap-2 text-xs font-semibold cursor-pointer text-slate-300">
                        <input type="checkbox" ${allSelected ? 'checked' : ''} onchange="togglePartition('${itemCode}', this.checked)" class="cursor-pointer"> Select Partition
                    </label>
                    <h3 class="font-bold text-base text-blue-400">Product Partition: ${itemCode}</h3>
                </div>
                <button onclick="removeProduct('${itemCode}')" class="bg-rose-600/20 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white px-3 py-1 rounded text-xs font-bold transition cursor-pointer">🗑️ Remove Product</button>
            </div>
            <div class="grid grid-cols-4 gap-4 text-xs text-slate-400">
                <div>Root Code: <span class="text-white font-mono">${info.root}</span></div>
                <div>Division: <span class="text-white">${info.division}</span></div>
                <div>Status: <span class="${items.length > 0 ? 'text-emerald-400' : 'text-rose-400'}">${items.length > 0 ? '🟢 Active' : '🔴 Missing'}</span></div>
                <div>Images Active: <span class="text-white">${items.length}</span></div>
            </div>
            <hr class="border-slate-800">
            <div class="grid-container" id="grid_${itemCode}">
                ${items.map((item, idx) => `
                    <div class="card ${selectedImageIds.has(item.id) ? 'selected' : ''}" data-id="${item.id}">
                        <input type="checkbox" class="absolute top-2 left-2 cursor-pointer z-10" ${selectedImageIds.has(item.id) ? 'checked' : ''} onclick="toggleSelect('${item.id}')">
                        <span class="absolute top-2 left-10 bg-black/70 text-[10px] px-2 py-0.5 rounded font-mono pos-badge">Pos ${idx + 1}</span>
                        <button onclick="removeCard('${item.id}')" class="absolute top-2 right-2 bg-rose-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold hover:scale-110 transition cursor-pointer z-10" title="Remove image">✕</button>
                        <img src="${item.url}" alt="${item.label}">
                        <div class="mt-2 text-xs font-bold text-center">${item.label}</div>
                        <a href="${item.url}" target="_blank" class="text-[10px] text-blue-400 mt-1 hover:underline" onclick="event.stopPropagation()">🔗 Direct URL</a>
                    </div>
                `).join('')}
            </div>
            ${items.length > 0 ? `<button onclick="downloadSinglePartition('${itemCode}')" class="bg-slate-800 hover:bg-slate-700 font-bold px-3 py-1.5 rounded text-xs cursor-pointer">📥 Download Shopify Excel for \`${itemCode}\` (${items.length} images)</button>` : ''}
        `;
        container.appendChild(section);

        // --- RESTORED SORTABLEJS DRAG-AND-DROP INITIALIZATION ---
        if (items.length > 0) {
            const gridEl = document.getElementById(`grid_${itemCode}`);
            new Sortable(gridEl, {
                animation: 150,
                ghostClass: 'opacity-30',
                dragClass: 'scale-105',
                onEnd: function() {
                    // Update position badges dynamically on drag completion
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
    
    // Toggle card visual selection state immediately without full re-render
    const cardEl = document.querySelector(`.card[data-id="${id}"]`);
    if (cardEl) {
        if (selectedImageIds.has(id)) cardEl.classList.add('selected');
        else cardEl.classList.remove('selected');
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
        body: JSON.stringify({ van_url_map: globalData.van_url_map, valid_url_map: globalData.valid_url_map })
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

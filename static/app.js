let globalData = null;
let selectedImageIds = new Set();
let excludedVans = new Set();
let removedImageIds = new Set();

async function runVerification() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files[0]) { alert('Please upload an SAP file first.'); return; }

    const formData = new FormData();
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
        
        document.getElementById('mTotal').innerText = globalData.summary.total_vans.toLocaleString();
        document.getElementById('mActive').innerText = globalData.summary.active_vans.toLocaleString();
        document.getElementById('mMissing').innerText = (globalData.summary.total_vans - globalData.summary.active_vans).toLocaleString();
        document.getElementById('mImages').innerText = globalData.summary.total_images_found.toLocaleString();

        // Populate Division filter
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

    let displayVans = [];
    const searchTokens = searchVal ? searchVal.split(',').map(v => v.trim()).filter(Boolean) : [];

    for (let [vanCode, info] of Object.entries(globalData.van_url_map)) {
        if (excludedVans.has(vanCode)) continue;
        if (selectedDiv !== 'All Divisions' && info.division !== selectedDiv) continue;
        
        const hasActive = Object.values(info.urls).some(u => globalData.valid_url_map[u]);
        if (statusFilter === 'Active Only' && !hasActive) continue;
        if (statusFilter === 'Missing Only' && hasActive) continue;

        if (searchTokens.length > 0 && !searchTokens.includes(vanCode)) continue;
        displayVans.push(vanCode);
    }

    // Global Export Rows for Top Button
    let globalShopifyRows = [];
    displayVans.forEach(vanCode => {
        let info = globalData.van_url_map[vanCode];
        let items = getActiveItems(vanCode);
        items.forEach((item, idx) => {
            globalShopifyRows.push({
                "Handle": vanCode.toLowerCase(),
                "SAP VAN": vanCode,
                "Image Position": idx + 1,
                "Image Src": item.url,
                "Image Alt Text": `${vanCode} - ${item.label}`,
                "MH3 Division": info.division
            });
        });
    });

    const exportContainer = document.getElementById('globalExportContainer');
    if (displayVans.length > 0 && globalShopifyRows.length > 0) {
        exportContainer.innerHTML = `<button onclick='downloadShopifyBatch(${JSON.stringify(globalShopifyRows)}, "Shopify_All_Displayed_Images_Export.xlsx")' class="bg-red-600 hover:bg-red-700 font-bold px-4 py-2 rounded text-sm cursor-pointer">📥 Export All Displayed Images (${globalShopifyRows.length} total across ${displayVans.length} products) for Shopify (Excel)</button>`;
    } else {
        exportContainer.innerHTML = '';
    }

    if (displayVans.length === 0) {
        container.innerHTML = '<div class="text-slate-400 text-sm italic">No matching SAP VANs found or selected.</div>';
        return;
    }

    displayVans.forEach(vanCode => {
        let info = globalData.van_url_map[vanCode];
        let items = getActiveItems(vanCode);
        let allSelected = items.length > 0 && items.every(i => selectedImageIds.has(i.id));

        const section = document.createElement('div');
        section.className = 'bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4';
        section.innerHTML = `
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-4">
                    <label class="flex items-center gap-2 text-xs font-semibold cursor-pointer text-slate-300">
                        <input type="checkbox" ${allSelected ? 'checked' : ''} onchange="togglePartition('${vanCode}', this.checked)" class="cursor-pointer"> Select Partition
                    </label>
                    <h3 class="font-bold text-base text-blue-400">Product Partition: ${vanCode}</h3>
                </div>
                <button onclick="removeProduct('${vanCode}')" class="bg-rose-600/20 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white px-3 py-1 rounded text-xs font-bold transition cursor-pointer">🗑️ Remove Product</button>
            </div>
            <div class="grid grid-cols-4 gap-4 text-xs text-slate-400">
                <div>Root VAN: <span class="text-white font-mono">${info.root}</span></div>
                <div>Division: <span class="text-white">${info.division}</span></div>
                <div>Status: <span class="${items.length > 0 ? 'text-emerald-400' : 'text-rose-400'}">${items.length > 0 ? '🟢 Active' : '🔴 Missing'}</span></div>
                <div>Images Active: <span class="text-white">${items.length}</span></div>
            </div>
            <hr class="border-slate-800">
            <div class="grid-container" id="grid_${vanCode}">
                ${items.map((item, idx) => `
                    <div class="card ${selectedImageIds.has(item.id) ? 'selected' : ''}" data-id="${item.id}">
                        <input type="checkbox" class="absolute top-2 left-2 cursor-pointer z-10" ${selectedImageIds.has(item.id) ? 'checked' : ''} onclick="toggleSelect('${item.id}')">
                        <span class="absolute top-2 left-10 bg-black/70 text-[10px] px-2 py-0.5 rounded font-mono">Pos ${idx + 1}</span>
                        <button onclick="removeCard('${item.id}')" class="absolute top-2 right-2 bg-rose-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold hover:scale-110 transition cursor-pointer z-10" title="Remove image">✕</button>
                        <img src="${item.url}" alt="${item.label}">
                        <div class="mt-2 text-xs font-bold text-center">${item.label}</div>
                        <a href="${item.url}" target="_blank" class="text-[10px] text-blue-400 mt-1 hover:underline" onclick="event.stopPropagation()">🔗 Direct URL</a>
                    </div>
                `).join('')}
            </div>
            ${items.length > 0 ? `<button onclick="downloadSinglePartition('${vanCode}')" class="bg-slate-800 hover:bg-slate-700 font-bold px-3 py-1.5 rounded text-xs cursor-pointer">📥 Download Shopify Excel for \`${vanCode}\` (${items.length} images)</button>` : ''}
        `;
        container.appendChild(section);

        if (items.length > 0) {
            new Sortable(document.getElementById(`grid_${vanCode}`), {
                animation: 150,
                ghostClass: 'opacity-30',
                onEnd: function() { renderInspector(); }
            });
        }
    });
}

function getActiveItems(vanCode) {
    let info = globalData.van_url_map[vanCode];
    return Object.entries(info.urls)
        .filter(([suffix, url]) => globalData.valid_url_map[url] && !removedImageIds.has(`${vanCode}_${suffix}`))
        .map(([suffix, url]) => ({
            id: `${vanCode}_${suffix}`,
            label: suffix === '-HERO' ? 'Hero View' : `Alt ${suffix.replace('-ALT', '')}`,
            url: url
        }));
}

function toggleSelect(id) {
    if (selectedImageIds.has(id)) selectedImageIds.delete(id);
    else selectedImageIds.add(id);
    updatePopoutBar();
    renderInspector();
}

function togglePartition(vanCode, select) {
    let items = getActiveItems(vanCode);
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

function removeProduct(vanCode) {
    excludedVans.add(vanCode);
    getActiveItems(vanCode).forEach(i => selectedImageIds.delete(i.id));
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
    triggerDownload(await response.blob(), 'SAP_VAN_Cloudinary_Verified_Master.xlsx');
}

async function downloadSinglePartition(vanCode) {
    let info = globalData.van_url_map[vanCode];
    let items = getActiveItems(vanCode);
    let rows = items.map((item, idx) => ({
        "Handle": vanCode.toLowerCase(),
        "SAP VAN": vanCode,
        "Image Position": idx + 1,
        "Image Src": item.url,
        "Image Alt Text": `${vanCode} - ${item.label}`,
        "MH3 Division": info.division
    }));
    downloadShopifyBatch(rows, `Shopify_Export_${vanCode}.xlsx`);
}

async function downloadSelectedBundle() {
    let rows = [];
    for (let [vanCode, info] of Object.entries(globalData.van_url_map)) {
        let items = getActiveItems(vanCode);
        items.forEach((item, idx) => {
            if (selectedImageIds.has(item.id)) {
                rows.push({
                    "Handle": vanCode.toLowerCase(),
                    "SAP VAN": vanCode,
                    "Image Position": rows.length + 1,
                    "Image Src": item.url,
                    "Image Alt Text": `${vanCode} - ${item.label}`,
                    "MH3 Division": info.division
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

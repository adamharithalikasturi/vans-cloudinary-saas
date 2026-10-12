let globalData = null;
let selectedImageIds = new Set();

async function runVerification() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files[0]) {
        alert('Please upload an SAP file first.');
        return;
    }

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
        
        // Update Metrics
        document.getElementById('mTotal').innerText = globalData.summary.total_vans.toLocaleString();
        document.getElementById('mActive').innerText = globalData.summary.active_vans.toLocaleString();
        document.getElementById('mMissing').innerText = (globalData.summary.total_vans - globalData.summary.active_vans).toLocaleString();
        document.getElementById('mImages').innerText = globalData.summary.total_images_found.toLocaleString();

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
    const targetVans = searchVal ? searchVal.split(',').map(v => v.trim()).filter(Boolean) : Object.keys(globalData.van_url_map).slice(0, 10);
    
    const container = document.getElementById('inspectorContainer');
    container.innerHTML = '';

    targetVans.forEach(vanCode => {
        if (!globalData.van_url_map[vanCode]) return;
        const info = globalData.van_url_map[vanCode];
        
        const activeItems = Object.entries(info.urls)
            .filter(([suffix, url]) => globalData.valid_url_map[url])
            .map(([suffix, url]) => ({
                id: `${vanCode}_${suffix}`,
                label: suffix === '-HERO' ? 'Hero View' : `Alt ${suffix.replace('-ALT', '')}`,
                url: url
            }));

        const cardHtml = activeItems.map((item, idx) => `
            <div class="card ${selectedImageIds.has(item.id) ? 'selected' : ''}" data-id="${item.id}" onclick="toggleSelect('${item.id}')">
                <input type="checkbox" class="absolute top-2 left-2 cursor-pointer" ${selectedImageIds.has(item.id) ? 'checked' : ''} onclick="event.stopPropagation(); toggleSelect('${item.id}')">
                <span class="absolute top-2 right-2 bg-black/70 text-xs px-2 py-0.5 rounded font-mono">Pos ${idx + 1}</span>
                <img src="${item.url}" alt="${item.label}">
                <div class="mt-2 text-xs font-bold text-center">${item.label}</div>
                <a href="${item.url}" target="_blank" class="text-[10px] text-blue-400 mt-1 hover:underline" onclick="event.stopPropagation()">🔗 Direct URL</a>
            </div>
        `).join('');

        const section = document.createElement('div');
        section.className = 'bg-slate-900 border border-slate-800 rounded-lg p-6';
        section.innerHTML = `
            <div class="flex justify-between items-center mb-4">
                <h3 class="font-bold text-base">Product Partition: <span class="text-blue-400">${vanCode}</span></h3>
                <span class="text-xs bg-slate-800 px-3 py-1 rounded text-slate-300">Division: ${info.division} | Active Images: ${activeItems.length}</span>
            </div>
            <div class="grid-container" id="grid_${vanCode}">${cardHtml}</div>
        `;
        container.appendChild(section);

        // Initialize SortableJS for drag-and-drop ordering
        new Sortable(document.getElementById(`grid_${vanCode}`), {
            animation: 150,
            ghostClass: 'opacity-30'
        });
    });
}

function toggleSelect(id) {
    if (selectedImageIds.has(id)) {
        selectedImageIds.delete(id);
    } else {
        selectedImageIds.add(id);
    }
    updatePopoutBar();
    renderInspector();
}

function updatePopoutBar() {
    const bar = document.getElementById('popoutBar');
    document.getElementById('selectedCountText').innerText = `${selectedImageIds.size} selected`;
    if (selectedImageIds.size > 0) {
        bar.classList.add('visible');
    } else {
        bar.classList.remove('visible');
    }
}

async function downloadMasterReport() {
    const response = await fetch('/api/download-master-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ van_url_map: globalData.van_url_map, valid_url_map: globalData.valid_url_map })
    });
    const blob = await response.blob();
    triggerDownload(blob, 'SAP_VAN_Cloudinary_Verified_Master.xlsx');
}

async function downloadSelectedBundle() {
    let rows = [];
    for (let [vanCode, info] of Object.entries(globalData.van_url_map)) {
        let pos = 1;
        for (let [suffix, url] of Object.entries(info.urls)) {
            let id = `${vanCode}_${suffix}`;
            if (selectedImageIds.has(id) && globalData.valid_url_map[url]) {
                rows.push({
                    "Handle": vanCode.toLowerCase(),
                    "SAP VAN": vanCode,
                    "Image Position": pos++,
                    "Image Src": url,
                    "Image Alt Text": `${vanCode} - ${suffix}`,
                    "MH3 Division": info.division
                });
            }
        }
    }

    const response = await fetch('/api/download-shopify-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows })
    });
    const blob = await response.blob();
    triggerDownload(blob, 'Shopify_Selected_Images_Export.xlsx');
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
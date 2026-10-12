import asyncio
import io
import os
import aiohttp
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Vans Enterprise Catalog & Cloudinary SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==============================================================================
# SUFFIX SPECTRUM DEFINITIONS
# ==============================================================================
FOOTWEAR_SUFFIXES = [("-HERO", "Hero View")] + \
                    [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                    [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)]

APPAREL_SUFFIXES = [("-HERO", "Hero View")] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(60, 76)]

ACCESSORY_SUFFIXES = [("-HERO", "Hero View")] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(1, 11)]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys(
    [s[0] for s in FOOTWEAR_SUFFIXES + APPAREL_SUFFIXES + ACCESSORY_SUFFIXES]
))

# ==============================================================================
# ASYNC PROBER ENGINE
# ==============================================================================
async def check_url(session, semaphore, url, timeout):
    async with semaphore:
        try:
            async with session.head(url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status == 200 and 'x-cld-error' not in resp.headers:
                    return url, True
                return url, False
        except Exception:
            return url, False

async def validate_urls(url_list, max_concurrent, timeout):
    semaphore = asyncio.Semaphore(max_concurrent)
    connector = aiohttp.TCPConnector(limit=max_concurrent, ttl_dns_cache=600, ssl=False)
    results = {}
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
        tasks = [check_url(session, semaphore, url, timeout) for url in url_list]
        for future in asyncio.as_completed(tasks):
            url, status = await future
            results[url] = status
    return results

# ==============================================================================
# EXCEL GENERATORS
# ==============================================================================
def create_excel_report(van_url_map, valid_url_map):
    rows = []
    for van, data in van_url_map.items():
        valid_count = sum(1 for u in data['urls'].values() if valid_url_map.get(u, False))
        row_data = {
            "SAP VAN": van,
            "Root VAN": data['root'],
            "MH3 Division": data['division'],
            "Status": "Active" if valid_count > 0 else "Missing",
            "Available Images": valid_count
        }
        for suffix in ALL_UNIQUE_SUFFIXES:
            header_title = "Hero View" if suffix == "-HERO" else f"Alt {suffix.replace('-ALT', '')}"
            if suffix in data['urls']:
                url = data['urls'][suffix]
                row_data[header_title] = f'=HYPERLINK("{url}", "{url}")' if valid_url_map.get(url, False) else ""
            else:
                row_data[header_title] = ""
        rows.append(row_data)

    df_report = pd.DataFrame(rows)
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_report.to_excel(writer, sheet_name="Cloudinary Master Tracker", index=False)
    output_buffer.seek(0)
    return output_buffer.getvalue()

def create_shopify_excel_report(shopify_export_rows):
    df_shopify = pd.DataFrame(shopify_export_rows)
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_shopify.to_excel(writer, sheet_name="Shopify Image Import", index=False)
    output_buffer.seek(0)
    return output_buffer.getvalue()

# ==============================================================================
# API ENDPOINTS
# ==============================================================================
@app.post("/api/verify-catalog")
async def verify_catalog(
    file: UploadFile = File(...),
    base_cdn_url: str = Form("https://img.vans.com/image/upload/"),
    preset: str = Form(""),
    max_concurrent: int = Form(400),
    timeout: int = Form(5)
):
    contents = await file.read()
    file_name = file.filename.lower()
    
    if file_name.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(contents), low_memory=False)
    elif file_name.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(io.BytesIO(contents))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    required_cols = {'VENDOR ARTICLE NO.', 'MH3 DIVISION', 'AH1 SILLOUTE'}
    if not required_cols.issubset(df.columns):
        raise HTTPException(status_code=400, detail=f"Missing columns: {list(required_cols)}")

    df_unique = df.drop_duplicates(subset=['VENDOR ARTICLE NO.']).copy()
    van_url_map = {}
    all_urls_to_check = set()
    preset_prefix = f"{preset.strip()}/" if preset.strip() else ""

    for _, row in df_unique.iterrows():
        van = str(row['VENDOR ARTICLE NO.']).strip()
        if not van or van == 'nan':
            continue
            
        division = str(row['MH3 DIVISION']).upper()
        silhouette = str(row['AH1 SILLOUTE']).upper()
        root_van = van[:-1] if van.endswith('1') else van
        
        if 'FOOTWEAR' in division or 'SHOES' in silhouette:
            active_suffixes = [s[0] for s in FOOTWEAR_SUFFIXES]
        elif 'APPAREL' in division or silhouette in ['TOPS', 'BOTTOMS']:
            active_suffixes = [s[0] for s in APPAREL_SUFFIXES]
        else:
            active_suffixes = [s[0] for s in ACCESSORY_SUFFIXES]
            
        van_url_map[van] = {
            'root': root_van,
            'division': division if division != '#' else 'FOOTWEAR',
            'urls': {}
        }
        
        for suffix in active_suffixes:
            url = f"{base_cdn_url}{preset_prefix}{root_van}{suffix}.jpg"
            van_url_map[van]['urls'][suffix] = url
            all_urls_to_check.add(url)

    url_list = list(all_urls_to_check)
    valid_url_map = await validate_urls(url_list, max_concurrent, timeout)
    
    return {
        "van_url_map": van_url_map,
        "valid_url_map": valid_url_map,
        "summary": {
            "total_vans": len(van_url_map),
            "active_vans": sum(1 for v in van_url_map.values() if any(valid_url_map.get(u, False) for u in v['urls'].values())),
            "total_images_found": sum(1 for res in valid_url_map.values() if res)
        }
    }

@app.post("/api/download-master-report")
async def download_master_report(payload: dict):
    excel_bytes = create_excel_report(payload.get("van_url_map", {}), payload.get("valid_url_map", {}))
    return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=SAP_VAN_Cloudinary_Verified_Master.xlsx"})

@app.post("/api/download-shopify-report")
async def download_shopify_report(payload: dict):
    excel_bytes = create_shopify_excel_report(payload.get("rows", []))
    return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=Shopify_Image_Import.xlsx"})

# Static mount
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

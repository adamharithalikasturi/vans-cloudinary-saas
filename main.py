import asyncio
import io
import os
import aiohttp
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from brands.vans import parse_vans_catalog, ALL_UNIQUE_SUFFIXES as VANS_SUFFIXES
from brands.timberland import parse_timberland_catalog, ALL_UNIQUE_SUFFIXES as TIMBERLAND_SUFFIXES

app = FastAPI(title="Multi-Brand Enterprise Cloudinary SaaS API")

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

@app.post("/api/verify-catalog")
async def verify_catalog(
    brand: str = Form("vans"),
    file: UploadFile = File(...),
    base_cdn_url: str = Form("https://assets.timberland.com/images/t_img/f_auto/"),
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

    brand_lower = brand.lower().strip()
    if brand_lower == "vans":
        item_url_map, all_urls, unique_suffixes = parse_vans_catalog(df, base_cdn_url, preset)
    elif brand_lower == "timberland":
        item_url_map, all_urls, unique_suffixes = parse_timberland_catalog(df, base_cdn_url, preset)
    else:
        raise HTTPException(status_code=400, detail="Unsupported brand selection.")

    valid_url_map = await validate_urls(list(all_urls), max_concurrent, timeout)
    
    return {
        "brand": brand_lower,
        "van_url_map": item_url_map,
        "valid_url_map": valid_url_map,
        "summary": {
            "total_items": len(item_url_map),
            "active_items": sum(1 for v in item_url_map.values() if any(valid_url_map.get(u, False) for u in v['urls'].values())),
            "total_images_found": sum(1 for res in valid_url_map.values() if res)
        }
    }

@app.post("/api/download-master-report")
async def download_master_report(payload: dict):
    brand = payload.get("brand", "vans").lower()
    item_url_map = payload.get("van_url_map", {})
    valid_url_map = payload.get("valid_url_map", {})
    
    active_suffixes = TIMBERLAND_SUFFIXES if brand == "timberland" else VANS_SUFFIXES
    
    rows = []
    for item_code, data in item_url_map.items():
        valid_count = sum(1 for u in data['urls'].values() if valid_url_map.get(u, False))
        row_data = {
            "Item Code": item_code,
            "Root Code": data['root'],
            "Division": data['division'],
            "Status": "Active" if valid_count > 0 else "Missing",
            "Available Images": valid_count
        }
        for suffix in active_suffixes:
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
        df_report.to_excel(writer, sheet_name="Master Tracker", index=False)
    output_buffer.seek(0)
    
    return StreamingResponse(
        output_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Cloudinary_Verified_Master.xlsx"}
    )

@app.post("/api/download-shopify-report")
async def download_shopify_report(payload: dict):
    df_shopify = pd.DataFrame(payload.get("rows", []))
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_shopify.to_excel(writer, sheet_name="Shopify Image Import", index=False)
    output_buffer.seek(0)
    return StreamingResponse(
        output_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Shopify_Image_Import.xlsx"}
    )

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

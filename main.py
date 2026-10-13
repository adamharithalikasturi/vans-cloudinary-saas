import asyncio
import io
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import aiohttp
import pandas as pd
from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import models
from admin import router as admin_router
from auth import current_user, router as auth_router, usage_for
from db import Base, SessionLocal, engine, get_db
from models import UsageLog, User
from security import hash_password
from sqlalchemy import text
from sqlalchemy.orm import Session

from brands.vans import parse_vans_catalog, ALL_UNIQUE_SUFFIXES as VANS_SUFFIXES
from brands.timberland import (
    scrape_timberland_catalog,
    ALL_UNIQUE_SUFFIXES as TIMBERLAND_SUFFIXES,
    PROBE_GROUPS as TIMBERLAND_PROBE_GROUPS,
    REGIONAL_SOURCES as TIMBERLAND_REGIONAL,
)

def seed_admin():
    """Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD (if set)."""
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    db = SessionLocal()
    try:
        if email and password and not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, name="Administrator", role="admin", password_hash=hash_password(password), monthly_limit=None))
            db.commit()
            print(f"[setup] Administrator account created: {email}")
        elif not db.query(User).filter(User.role == "admin").first():
            print("[setup] WARNING: no administrator exists. Set ADMIN_EMAIL and ADMIN_PASSWORD and restart.")
        db.query(models.SessionToken).filter(models.SessionToken.expires_at < models.utcnow()).delete()
        db.commit()
    finally:
        db.close()


def init_database():
    """Idempotent. Also runs at import time so it works on hosts that skip lifespan events."""
    try:
        Base.metadata.create_all(engine)
        seed_admin()
    except Exception:
        logging.getLogger("uvicorn.error").exception("Database initialisation failed. Check DATABASE_URL.")


@asynccontextmanager
async def lifespan(_app):
    init_database()
    yield


init_database()

app = FastAPI(title="Catalog Asset Intelligence API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
log = logging.getLogger("uvicorn.error")


@app.exception_handler(Exception)
async def unhandled_error(request, exc):
    """Never leak internals to customers; log the full traceback with a short reference."""
    ref = uuid.uuid4().hex[:8]
    log.error("Unhandled error [%s] %s %s", ref, request.method, request.url.path, exc_info=exc)
    return JSONResponse({"detail": f"Something went wrong on our side. Reference: {ref}"}, status_code=500)


@app.get("/api/v1/health")
def health():
    """Safe diagnostics: no secrets, only what is needed to see why sign-in might fail."""
    info = {"database": engine.dialect.name}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        info["connection"] = "ok"
    except Exception as exc:
        log.exception("Health check: database unreachable")
        return JSONResponse({**info, "status": "degraded", "connection": "failed", "error": type(exc).__name__}, status_code=503)
    db = SessionLocal()
    try:
        info["admin_exists"] = db.query(User).filter(User.role == "admin").first() is not None
        info["status"] = "ok"
        return info
    except Exception as exc:
        log.exception("Health check: tables missing or unreadable")
        return JSONResponse({**info, "status": "degraded", "tables": "missing", "error": type(exc).__name__}, status_code=503)
    finally:
        db.close()


app.include_router(auth_router)
app.include_router(admin_router)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Everything customers should not need to see or tune lives here, server-side.
def _site_lookup(name, domain, note=""):
    # Search-engine site lookup: works for any regional storefront without
    # depending on that site's own (changing) search URL format.
    return {"name": name, "note": note, "template": f"https://www.google.com/search?q=site%3A{domain}+{{root}}"}


BRAND_CONFIG = {
    "vans": {"base": "https://img.vans.com/image/upload/", "preset": "", "lookups": []},
    "timberland": {
        "base": "https://assets.timberland.com/",
        "preset": "",
        "lookups": [
            _site_lookup("Taiwan", "timberland.com.tw", "Often has it"),
            _site_lookup("Japan", "timberland.co.jp"),
            _site_lookup("Korea", "timberland.co.kr"),
            _site_lookup("UK", "timberland.co.uk"),
            _site_lookup("Global", "timberland.com"),
        ],
    },
}
MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "20000"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "400"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "5"))

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ------------------------------------------------------------------ validation
async def check_url(session, semaphore, url, timeout):
    async with semaphore:
        t = aiohttp.ClientTimeout(total=timeout)
        for attempt in range(3):
            try:
                async with session.head(url, timeout=t, allow_redirects=True) as resp:
                    if resp.status == 200 and "x-cld-error" not in resp.headers:
                        ctype = resp.headers.get("Content-Type", "image").lower()
                        return url, ctype.startswith("image")
                    if resp.status in (404, 410):
                        return url, False
            except Exception:
                pass
            await asyncio.sleep(0.5 * (attempt + 1))
        return url, False


async def validate_urls(url_list, max_concurrent, timeout, on_progress=None):
    url_list = list(url_list)
    total = len(url_list)
    semaphore = asyncio.Semaphore(max_concurrent)
    connector = aiohttp.TCPConnector(limit=max_concurrent, ttl_dns_cache=600, ssl=False)
    results = {}
    if not total:
        return results
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
        tasks = [check_url(session, semaphore, url, timeout) for url in url_list]
        done = 0
        for future in asyncio.as_completed(tasks):
            url, status = await future
            results[url] = status
            done += 1
            if on_progress:
                on_progress(done, total)
    return results


async def regional_pass(item_url_map, valid, sources, mc, timeout, on_progress=None):
    """Second chance for products with no imagery: look on other market image servers.
    Sources come from brands/<brand>.py -> REGIONAL_SOURCES (empty until configured)."""
    for src in sources:
        missing = [c for c, d in item_url_map.items() if not any(valid.get(u) for u in d["urls"].values())]
        if not missing:
            return
        sfxs = src.get("suffixes") or ["-HERO"]
        key = src["key"]

        def build(code, sfx):
            return src["template"].format(root=item_url_map[code]["root"], suffix=sfx)

        probe = {c: build(c, sfxs[0]) for c in missing}
        res = await validate_urls(list(probe.values()), mc, timeout, on_progress)
        hits = [c for c, u in probe.items() if res.get(u)]
        for c in hits:
            item_url_map[c]["urls"][f"{sfxs[0]}~{key}"] = probe[c]
            valid[probe[c]] = True

        rest = {(c, s_): build(c, s_) for c in hits for s_ in sfxs[1:]}
        res = await validate_urls(list(rest.values()), mc, timeout, on_progress)
        for (c, s_), u in rest.items():
            if res.get(u):
                item_url_map[c]["urls"][f"{s_}~{key}"] = u
                valid[u] = True


# ------------------------------------------------------------------ excel helpers
HEADER_FILL = PatternFill("solid", fgColor="0F172A")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Calibri", size=10)
LINK_FONT = Font(name="Calibri", size=10, color="1D4ED8", underline="single")
THIN = Side(style="thin", color="E2E8F0")
BORDER = Border(bottom=THIN)
ACTIVE_FILL = PatternFill("solid", fgColor="DCFCE7")
MISSING_FILL = PatternFill("solid", fgColor="FEE2E2")


def style_sheet(ws, headers, link_cols=(), widths=None):
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center", horizontal="left")
    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, max(14, len(h) + 4))


def finish_sheet(ws, link_cols=()):
    last_col = get_column_letter(ws.max_column)
    ws.auto_filter.ref = f"A1:{last_col}{ws.max_row}"
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = BODY_FONT
            c.border = BORDER
            c.alignment = Alignment(vertical="center")
    for col in link_cols:
        for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            for c in row:
                if c.value:
                    c.hyperlink = str(c.value)
                    c.font = LINK_FONT


def workbook_response(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def safe_filename(name, default):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "")).strip("._")
    if not name:
        name = default
    return name if name.lower().endswith(".xlsx") else name + ".xlsx"


# ------------------------------------------------------------------ catalog intake
CODE_LIKE = re.compile(r"^[A-Z0-9]{8,14}(-[A-Z0-9]+)?$")


def looks_like_code(v):
    v = str(v).strip().upper()
    return bool(CODE_LIKE.match(v)) and any(c.isdigit() for c in v) and any(c.isalpha() for c in v)


def _norm(c):
    return re.sub(r"[^A-Z0-9]", "", str(c).upper())


def normalize_catalog(df):
    """Accept anything from a single column of codes to a full SAP export.
    Returns a frame with at least 'VENDOR ARTICLE NO.'; other columns are optional."""
    df = df.copy()
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].copy()
    cols = list(df.columns)

    # Headerless single-column file: the first code was read as the header
    if len(cols) == 1 and looks_like_code(cols[0]):
        df = pd.concat([pd.DataFrame({cols[0]: [cols[0]]}), df], ignore_index=True)
        df.columns = ["VENDOR ARTICLE NO."]
        cols = list(df.columns)

    code_col = None
    keys = ["VENDORARTICLENO", "VENDORARTICLE", "ARTICLENO", "ARTICLE", "STYLE", "SKU", "ITEMCODE", "ITEM", "PRODUCTCODE", "CODE", "VAN"]
    for key in keys:
        code_col = next((c for c in cols if _norm(c) == key), None)
        if code_col:
            break
    if not code_col:
        for key in keys[:5]:
            code_col = next((c for c in cols if key in _norm(c)), None)
            if code_col:
                break
    if not code_col:
        for c in cols:
            sample = df[c].dropna().astype(str).head(200)
            if len(sample) and sample.map(looks_like_code).mean() > 0.6:
                code_col = c
                break
    if not code_col and len(cols) == 1:
        code_col = cols[0]
    if not code_col:
        raise HTTPException(status_code=400, detail="No item codes were found. Include a column of item codes (for example 'VENDOR ARTICLE NO.').")

    if code_col != "VENDOR ARTICLE NO.":
        df = df.drop(columns=[c for c in ["VENDOR ARTICLE NO."] if c in df.columns])
        df = df.rename(columns={code_col: "VENDOR ARTICLE NO."})

    df["VENDOR ARTICLE NO."] = df["VENDOR ARTICLE NO."].astype(str).str.strip().str.upper()
    df = df[~df["VENDOR ARTICLE NO."].isin(["", "NAN", "NONE"])]

    if "MH3 DIVISION" not in df.columns:
        df["MH3 DIVISION"] = df["DIVISION"] if "DIVISION" in df.columns else ""
    if "AH1 SILLOUTE" not in df.columns:
        df["AH1 SILLOUTE"] = ""
    return df


def codes_to_frame(text):
    codes = [c for c in re.split(r"[\s,;]+", text or "") if c]
    return pd.DataFrame({"VENDOR ARTICLE NO.": list(dict.fromkeys(codes))})


# ------------------------------------------------------------------ endpoints
@app.post("/api/v1/analyze")
async def analyze_catalog(
    brand: str = Form("vans"),
    file: UploadFile = File(None),
    codes: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if file is not None and file.filename:
        contents = await file.read()
        file_name = file.filename.lower()
        try:
            if file_name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(contents), low_memory=False)
            elif file_name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(contents))
            else:
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a .csv or .xlsx file.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="The file could not be read. Please check that it is a valid spreadsheet.")
    elif codes.strip():
        df = codes_to_frame(codes)
    else:
        raise HTTPException(status_code=400, detail="Please upload a file or paste item codes.")

    df = normalize_catalog(df)

    brand_lower = brand.lower().strip()
    cfg = BRAND_CONFIG.get(brand_lower)
    if not cfg:
        raise HTTPException(status_code=400, detail="Unsupported brand selection.")

    if brand_lower == "vans":
        item_url_map, all_urls, _ = parse_vans_catalog(df, cfg["base"], cfg["preset"])
    else:
        item_url_map, all_urls, _ = scrape_timberland_catalog(df, cfg["base"], cfg["preset"])

    if not item_url_map:
        raise HTTPException(status_code=400, detail="No valid products were found in the file.")
    if len(item_url_map) > MAX_ITEMS_PER_RUN:
        raise HTTPException(status_code=400, detail=f"Please submit no more than {MAX_ITEMS_PER_RUN:,} products at a time.")

    used, limit = usage_for(db, user)
    n_items = len(item_url_map)
    if limit is not None and used + n_items > limit:
        remaining = max(limit - used, 0)
        raise HTTPException(
            status_code=403,
            detail=f"This request ({n_items:,} products) exceeds your monthly allowance. "
                   f"You have {remaining:,} of {limit:,} products remaining this month. Contact support to increase your limit.",
        )

    user_id = user.id
    source = (file.filename if file is not None and file.filename else f"{n_items} pasted codes")[:250]
    regional = TIMBERLAND_REGIONAL if brand_lower == "timberland" else []

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def stage(label, lo, hi):
            last = {"pct": -1, "done": -1}

            def cb(done, total):
                pct = int(lo + (hi - lo) * (done / total)) if total else hi
                if pct != last["pct"] or done == total:
                    last["pct"] = pct
                    queue.put_nowait({"type": "progress", "percent": pct, "done": done, "total": total, "message": label})

            return cb

        async def worker():
            try:
                queue.put_nowait({"type": "progress", "percent": 1, "done": 0, "total": 0, "message": "Preparing analysis"})
                if brand_lower == "timberland":
                    probes = {p for p, _ in TIMBERLAND_PROBE_GROUPS}
                    probe_urls = {d["urls"][p] for d in item_url_map.values() for p in probes if p in d["urls"]}
                    valid = await validate_urls(probe_urls, MAX_CONCURRENT, REQUEST_TIMEOUT, stage("Validating asset availability", 2, 30))
                    rest = set()
                    for probe, group in TIMBERLAND_PROBE_GROUPS:
                        for d in item_url_map.values():
                            if valid.get(d["urls"].get(probe), False):
                                rest.update(d["urls"][s_] for s_ in group if s_ in d["urls"])
                    rest -= set(valid)
                    valid.update(await validate_urls(rest, MAX_CONCURRENT, REQUEST_TIMEOUT, stage("Completing coverage checks", 30, 90 if regional else 96)))
                    for u in all_urls:
                        valid.setdefault(u, False)
                else:
                    valid = await validate_urls(all_urls, MAX_CONCURRENT, REQUEST_TIMEOUT, stage("Validating asset availability", 2, 96))

                if regional:
                    await regional_pass(item_url_map, valid, regional, MAX_CONCURRENT, REQUEST_TIMEOUT, stage("Checking additional markets", 90, 97))

                queue.put_nowait({"type": "progress", "percent": 98, "done": 0, "total": 0, "message": "Compiling results"})
                active = sum(1 for v in item_url_map.values() if any(valid.get(u, False) for u in v["urls"].values()))
                images = sum(1 for ok in valid.values() if ok)

                log_db = SessionLocal()
                try:
                    log_db.add(UsageLog(user_id=user_id, brand=brand_lower, source=source, items_count=n_items, images_found=images))
                    log_db.commit()
                finally:
                    log_db.close()

                queue.put_nowait({"type": "result", "data": {
                    "brand": brand_lower,
                    "lookups": cfg["lookups"],
                    "items": item_url_map,
                    "available": valid,
                    "summary": {"total_items": n_items, "active_items": active, "total_images_found": images},
                }})
            except Exception:
                queue.put_nowait({"type": "error", "detail": "The analysis could not be completed. Please try again."})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield json.dumps(ev) + "\n"
        finally:
            task.cancel()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/v1/reports/coverage")
async def coverage_report(payload: dict, _user: User = Depends(current_user)):
    brand = str(payload.get("brand", "vans")).lower()
    items = payload.get("items", {})
    available = payload.get("available", {})
    suffixes = TIMBERLAND_SUFFIXES if brand == "timberland" else VANS_SUFFIXES

    def title(sfx):
        return "Hero View" if sfx == "-HERO" else f"Alt {sfx.replace('-ALT', '')}"

    wb = Workbook()
    ws = wb.active
    ws.title = "Coverage Report"
    headers = ["Item Code", "Root Code", "Division", "Status", "Available Images"] + [title(s) for s in suffixes]
    widths = {"Item Code": 18, "Root Code": 18, "Division": 14, "Status": 12, "Available Images": 17}
    style_sheet(ws, headers, widths=widths)

    active = 0
    for code, data in items.items():
        urls = data.get("urls", {})
        valid = sum(1 for u in urls.values() if available.get(u, False))
        active += 1 if valid else 0
        row = [code, data.get("root", ""), data.get("division", ""), "Active" if valid else "Missing", valid]
        for s in suffixes:
            u = urls.get(s)
            row.append(u if u and available.get(u, False) else "")
        ws.append(row)

    link_cols = range(6, len(headers) + 1)
    finish_sheet(ws, link_cols=link_cols)
    for r in range(2, ws.max_row + 1):
        c = ws.cell(row=r, column=4)
        c.fill = ACTIVE_FILL if c.value == "Active" else MISSING_FILL
        c.font = Font(name="Calibri", size=10, bold=True, color="166534" if c.value == "Active" else "991B1B")
    for i in range(6, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 22

    total = len(items)
    summ = wb.create_sheet("Summary", 0)
    summ.sheet_view.showGridLines = False
    summ["B2"] = "Catalog Coverage Summary"
    summ["B2"].font = Font(name="Calibri", size=16, bold=True, color="0F172A")
    summ["B3"] = f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}"
    summ["B3"].font = Font(name="Calibri", size=10, color="64748B")
    rows = [
        ("Total products", total),
        ("Products with imagery", active),
        ("Products without imagery", total - active),
        ("Coverage", (active / total) if total else 0),
        ("Verified images", sum(1 for v in available.values() if v)),
    ]
    for i, (k, v) in enumerate(rows, start=5):
        summ.cell(row=i, column=2, value=k).font = Font(name="Calibri", size=11, color="334155")
        c = summ.cell(row=i, column=3, value=v)
        c.font = Font(name="Calibri", size=11, bold=True, color="0F172A")
        c.alignment = Alignment(horizontal="right")
        if k == "Coverage":
            c.number_format = "0.0%"
        for col in (2, 3):
            summ.cell(row=i, column=col).border = BORDER
    summ.column_dimensions["A"].width = 3
    summ.column_dimensions["B"].width = 30
    summ.column_dimensions["C"].width = 16

    return workbook_response(wb, "Catalog_Coverage_Report.xlsx")


@app.post("/api/v1/reports/export")
async def export_report(payload: dict, _user: User = Depends(current_user)):
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="There are no images to export.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Image Export"
    headers = ["Handle", "Item Code", "Image Position", "Image Src", "Image Alt Text", "Division"]
    style_sheet(ws, headers, widths={"Handle": 20, "Item Code": 18, "Image Position": 16, "Image Src": 70, "Image Alt Text": 32, "Division": 14})
    for r in rows:
        ws.append([
            r.get("Handle", ""),
            r.get("Item Code", ""),
            r.get("Image Position", ""),
            r.get("Image Src", ""),
            r.get("Image Alt Text", ""),
            r.get("Division", ""),
        ])
    finish_sheet(ws, link_cols=(4,))
    return workbook_response(wb, safe_filename(payload.get("filename"), "Image_Export"))


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# brands/timberland.py
#
# Verified URL pattern (US asset server):
#   https://assets.timberland.com/<ROOT>-<ANGLE>
# ROOT = first 11 characters of the 12-character vendor article number
#   TB12731R0011 -> TB12731R001   (last digit = width digit, dropped)
# ANGLE = HERO, ALT2, ALT3, ALT4, ALTA ...

import re

DEFAULT_BASE = "https://assets.timberland.com/"

# The web form pre-fills the Vans base URL / preset, so Timberland ignores them.
# Set to True only if you want the form values to override.
USE_FRONTEND_VALUES = False

# main.py checks this angle first and only checks the others for products
# where it exists. This cuts the number of requests by roughly 70-90%.
PROBE_SUFFIX = "-HERO"

# Confirmed: HERO, ALT2, ALT3, ALT4, ALTA. The rest are guesses.
# After a big run, delete any angle that never returns an image.
SUFFIXES = (
    ["-HERO"]
    + [f"-ALT{i}" for i in range(1, 11)]   # ALT1 .. ALT10
    + [f"-ALT{c}" for c in "ABCDEFGH"]     # ALTA .. ALTH
)

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys(SUFFIXES))

# Clean vendor number: TB + 10 letters/digits (12 characters)
CODE_RE = re.compile(r"^TB[0-9A-Z]{10}$")


def clean_vendor_code(raw):
    """Return a clean 12-char code like TB0A2DHJ0151, or None if not a real product."""
    code = str(raw).strip().upper().replace(" ", "")
    if code in ("", "NAN", "#", "NOTASSIGNED", "NONE"):
        return None

    # Gifts / packaging rows (GWP_..., TIM_...)
    if code.startswith(("GWP", "TIM")):
        return None

    # SAP variants end with a trailing Z (0A17QX0651Z, TB0250772141Z)
    if code.endswith("Z") and len(code) in (11, 13):
        code = code[:-1]

    # Missing "TB" prefix (0A17QX0651 -> TB0A17QX0651)
    if len(code) == 10 and code[0] == "0":
        code = "TB" + code

    return code if CODE_RE.match(code) else None


def _division(row):
    for col in ("MH3 DIVISION", "DIVISION"):
        val = str(row.get(col, "")).upper().strip()
        if val not in ("", "#", "NAN"):
            return val
    return "FOOTWEAR"


def scrape_timberland_catalog(df, base_cdn_url, preset):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if USE_FRONTEND_VALUES:
        base = (base_cdn_url or "").strip() or DEFAULT_BASE
        prefix = f"{preset.strip()}/" if preset and preset.strip() else ""
    else:
        base, prefix = DEFAULT_BASE, ""
    if not base.endswith("/"):
        base += "/"

    item_url_map = {}
    all_urls = set()

    for _, row in df.drop_duplicates(subset=["VENDOR ARTICLE NO."]).iterrows():
        code = clean_vendor_code(row["VENDOR ARTICLE NO."])
        if not code or code in item_url_map:
            continue

        root = code[:-1]
        urls = {s: f"{base}{prefix}{root}{s}" for s in SUFFIXES}
        item_url_map[code] = {"root": root, "division": _division(row), "urls": urls}
        all_urls.update(urls.values())

    return item_url_map, all_urls, ALL_UNIQUE_SUFFIXES

# brands/timberland.py
#
# Verified URL pattern (US asset server):
#   https://assets.timberland.com/<ROOT>-<ANGLE>
# where ROOT = first 11 characters of the 12-character vendor article number
#   TB12731R0011 -> TB12731R001   (last digit = width digit, dropped)
# and ANGLE is HERO, ALT2, ALT3, ALT4, ALTA ...

import re

DEFAULT_BASE = "https://assets.timberland.com/"

# Controls whether frontend-provided base URL and preset are honored or ignored
USE_FRONTEND_VALUES = False

# Original Suffixes + Expanded Category Suffixes combined so nothing is omitted
FOOTWEAR_SUFFIXES = [("-HERO", "Hero View")] + \
                    [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                    [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)] + \
                    [(f"-ALT{c}", f"Alt {c}") for c in "ABCDEFGH"]

APPAREL_SUFFIXES = [("-HERO", "Hero View")] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)] + \
                   [(f"-ALT{i}", f"Alt {i}") for i in range(60, 76)] + \
                   [(f"-ALT{c}", f"Alt {c}") for c in "ABCDEFGH"]

ACCESSORY_SUFFIXES = [("-HERO", "Hero View")] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)] + \
                     [(f"-ALT{i}", f"Alt {i}") for i in range(1, 11)] + \
                     [(f"-ALT{c}", f"Alt {c}") for c in "ABCDEFGH"]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys(
    [s[0] for s in FOOTWEAR_SUFFIXES + APPAREL_SUFFIXES + ACCESSORY_SUFFIXES]
))

# A clean Timberland vendor number: TB + 10 letters/digits (12 chars total)
CODE_RE = re.compile(r"^TB[0-9A-Z]{10}$")

def clean_vendor_code(raw):
    """Return a clean 12-char code like TB0A2DHJ0151, or None if it isn't a real product."""
    code = str(raw).strip().upper().replace(" ", "")
    if not code or code in ("NAN", "#", "NOT ASSIGNED"):
        return None

    # Skip gifts / packaging rows (GWP_..., TIM_..., etc.)
    if code.startswith(("GWP", "TIM_", "TIM")):
        return None

    # SAP variants end with a trailing Z (e.g. 0A17QX0651Z, TB0250772141Z)
    if code.endswith("Z") and len(code) in (11, 13):
        code = code[:-1]

    # Some codes lost the "TB" prefix (e.g. 0A17QX0651 -> TB0A17QX0651)
    if len(code) == 10 and code[0] == "0":
        code = "TB" + code

    return code if CODE_RE.match(code) else None


def scrape_timberland_catalog(df, base_cdn_url, preset):
    if USE_FRONTEND_VALUES:
        base = (base_cdn_url or "").strip() or DEFAULT_BASE
        preset_prefix = f"{preset.strip()}/" if preset and preset.strip() else ""
    else:
        base = DEFAULT_BASE
        preset_prefix = ""
        
    if not base.endswith("/"):
        base += "/"

    df_unique = df.drop_duplicates(subset=["VENDOR ARTICLE NO."]).copy()
    item_url_map = {}
    all_urls_to_check = set()

    for _, row in df_unique.iterrows():
        code = clean_vendor_code(row["VENDOR ARTICLE NO."])
        if not code:
            continue

        root = code[:-1]  # drop the last (width) digit

        division = str(row.get("MH3 DIVISION", row.get("DIVISION", ""))).upper().strip()
        if division in ("", "#", "NAN"):
            division = str(row.get("DIVISION", "")).upper().strip()
        if division in ("", "#", "NAN"):
            division = "FOOTWEAR"

        silhouette = str(row.get("AH1 SILLOUTE", row.get("CATEGORY", ""))).upper().strip()

        # Division & category-aware suffix routing (keeping original logic intact)
        if 'FOOTWEAR' in division or 'SHOES' in silhouette:
            active_suffixes = [s[0] for s in FOOTWEAR_SUFFIXES]
        elif 'APPAREL' in division or silhouette in ['TOPS', 'BOTTOMS', 'SWEATSHIR', 'COMPLETES']:
            active_suffixes = [s[0] for s in APPAREL_SUFFIXES]
        else:
            active_suffixes = [s[0] for s in ACCESSORY_SUFFIXES]

        item_url_map[code] = {
            "root": root,
            "division": division,
            "urls": {},
        }

        for suffix in active_suffixes:
            url = f"{base}{preset_prefix}{root}{suffix}"
            item_url_map[code]["urls"][suffix] = url
            all_urls_to_check.add(url)

    return item_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

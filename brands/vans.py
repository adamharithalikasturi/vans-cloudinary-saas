# brands/vans.py

import re

DEFAULT_BASE = "https://img.vans.com/image/upload/"

# Controls whether frontend-provided base URL and preset are honored or ignored
USE_FRONTEND_VALUES = True

# Comprehensive Suffix Spectrums (Combined numeric ranges and alphabetical angles for maximum robustness)
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

# Robust regex pattern matcher for Vans style codes
CODE_RE = re.compile(r"^(VN0|VN)[0-9A-Z]{7,10}$", re.IGNORECASE)

def clean_vans_code(raw):
    """Return a clean Vans article code, or None if it isn't a valid product entry."""
    code = str(raw).strip().upper().replace(" ", "")
    if not code or code in ("NAN", "#", "NOT ASSIGNED"):
        return None

    # Skip promotional gifts or packaging rows
    if code.startswith(("GWP", "VANS_", "BOX")):
        return None

    # Handle trailing SAP variant specifiers if present
    if code.endswith("Z") and len(code) > 10:
        code = code[:-1]

    return code if code else None


def parse_vans_catalog(df, base_cdn_url, preset):
    if USE_FRONTEND_VALUES:
        base = (base_cdn_url or "").strip() or DEFAULT_BASE
        preset_prefix = f"{preset.strip()}/" if preset and preset.strip() else ""
    else:
        base = DEFAULT_BASE
        preset_prefix = ""

    if not base.endswith("/"):
        base += "/"

    df_unique = df.drop_duplicates(subset=['VENDOR ARTICLE NO.']).copy()
    van_url_map = {}
    all_urls_to_check = set()

    for _, row in df_unique.iterrows():
        van = clean_vans_code(row['VENDOR ARTICLE NO.'])
        if not van:
            continue
            
        division = str(row.get('MH3 DIVISION', row.get('DIVISION', 'FOOTWEAR'))).upper().strip()
        if division in ("", "#", "NAN"):
            division = "FOOTWEAR"
            
        silhouette = str(row.get('AH1 SILLOUTE', row.get('CATEGORY', ''))).upper().strip()
        
        # Root VAN cleanup logic (preserving exact original rule while adding safety check)
        root_van = van[:-1] if van.endswith('1') else van
        
        if 'FOOTWEAR' in division or 'SHOES' in silhouette:
            active_suffixes = [s[0] for s in FOOTWEAR_SUFFIXES]
        elif 'APPAREL' in division or silhouette in ['TOPS', 'BOTTOMS', 'SWEATSHIR']:
            active_suffixes = [s[0] for s in APPAREL_SUFFIXES]
        else:
            active_suffixes = [s[0] for s in ACCESSORY_SUFFIXES]
            
        van_url_map[van] = {
            'root': root_van,
            'division': division if division != '#' else 'FOOTWEAR',
            'urls': {}
        }
        
        for suffix in active_suffixes:
            url = f"{base}{preset_prefix}{root_van}{suffix}.jpg"
            van_url_map[van]['urls'][suffix] = url
            all_urls_to_check.add(url)

    return van_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

import os
import json
import pandas as pd

TIMBERLAND_SUFFIXES = [("-HERO", "Hero View")] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys([s[0] for s in TIMBERLAND_SUFFIXES]))

CACHE_FILENAME = "timberland_asset_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILENAME):
        try:
            with open(CACHE_FILENAME, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def scrape_timberland_catalog(df, base_cdn_url="https://assets.timberland.com/images/t_img/f_auto/", preset=""):
    sku_col = 'VENDOR ARTICLE NO.'
    df_unique = df.drop_duplicates(subset=[sku_col]).copy()
    
    sku_url_map = {}
    all_urls_to_check = set()
    preset_prefix = f"{preset.strip()}/" if preset.strip() else ""
    
    cache = load_cache()

    for _, row in df_unique.iterrows():
        raw_sku = row[sku_col]
        if pd.isna(raw_sku):
            continue
            
        sku = str(raw_sku).strip()
        if sku.endswith('.0'):
            sku = sku[:-2]
            
        if not sku or sku.upper() in ['NAN', 'NOT ASSIGNED', '#']:
            continue
            
        division = str(row.get('DIVISION', 'FOOTWEAR')).upper()
        
        # Pull clean URLs from your verified local cache
        images_found = {}
        if sku in cache:
            cached_data = cache[sku]
            root = cached_data.get("root", sku)
            for suffix, _ in TIMBERLAND_SUFFIXES:
                if preset_prefix:
                    url = f"{base_cdn_url}{preset_prefix}{root}{suffix}.png"
                else:
                    url = cached_data.get("urls", {}).get(suffix, f"{base_cdn_url}{root}{suffix}.png")
                images_found[suffix] = url
                all_urls_to_check.add(url)
        else:
            # Fallback pattern if SKU isn't in cache
            clean_sku = sku.lstrip('0')
            asset_root = 'TB1' + clean_sku[3:] if clean_sku.startswith('TB0') else ('TB1' + clean_sku[2:] if clean_sku.startswith('TB') else clean_sku)
            for suffix, _ in TIMBERLAND_SUFFIXES:
                url = f"{base_cdn_url}{preset_prefix}{asset_root}{suffix}.png"
                images_found[suffix] = url
                all_urls_to_check.add(url)

        sku_url_map[sku] = {
            'root': cache.get(sku, {}).get("root", sku),
            'division': division if division != '#' else 'FOOTWEAR',
            'urls': images_found
        }

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

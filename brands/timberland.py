# brands/timberland.py

TIMBERLAND_SUFFIXES = [("_01", "Primary View"), ("_02", "Side View"), ("_03", "Back View"), ("_04", "Detail View")]

ALL_UNIQUE_SUFFIXES = [s[0] for s in TIMBERLAND_SUFFIXES]

def parse_timberland_catalog(df, base_cdn_url, preset):
    # Expects Timberland-specific column headers (e.g., 'STYLE_CODE' or similar)
    sku_col = 'STYLE_CODE' if 'STYLE_CODE' in df.columns else df.columns[0]
    df_unique = df.drop_duplicates(subset=[sku_col]).copy()
    
    sku_url_map = {}
    all_urls_to_check = set()
    preset_prefix = f"{preset.strip()}/" if preset.strip() else ""

    for _, row in df_unique.iterrows():
        sku = str(row[sku_col]).strip()
        if not sku or sku == 'nan':
            continue
            
        sku_url_map[sku] = {
            'root': sku,
            'division': 'TIMBERLAND FOOTWEAR',
            'urls': {}
        }
        
        for suffix, label in TIMBERLAND_SUFFIXES:
            url = f"{base_cdn_url}{preset_prefix}{sku}{suffix}.jpg"
            sku_url_map[sku]['urls'][suffix] = url
            all_urls_to_check.add(url)

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

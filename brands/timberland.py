# brands/timberland.py

TIMBERLAND_FOOTWEAR_SUFFIXES = [("-HERO", "Hero View")] + \
                               [(f"-ALT{i}", f"Alt {i}") for i in range(1, 11)]

TIMBERLAND_APPAREL_SUFFIXES  = [("-HERO", "Hero View")] + \
                               [(f"-ALT{i}", f"Alt {i}") for i in range(1, 11)]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys(
    [s[0] for s in TIMBERLAND_FOOTWEAR_SUFFIXES + TIMBERLAND_APPAREL_SUFFIXES]
))

def parse_timberland_catalog(df, base_cdn_url, preset):
    sku_col = 'VENDOR ARTICLE NO.'
    df_unique = df.drop_duplicates(subset=[sku_col]).copy()
    
    sku_url_map = {}
    all_urls_to_check = set()
    preset_prefix = f"{preset.strip()}/" if preset.strip() else ""

    for _, row in df_unique.iterrows():
        sku = str(row[sku_col]).strip()
        if not sku or sku == 'nan' or sku.upper() == 'NOT ASSIGNED':
            continue
            
        division = str(row.get('DIVISION', 'FOOTWEAR')).upper()
        active_suffixes = TIMBERLAND_FOOTWEAR_SUFFIXES if 'FOOTWEAR' in division else TIMBERLAND_APPAREL_SUFFIXES
        
        sku_url_map[sku] = {
            'root': sku,
            'division': division,
            'urls': {}
        }
        
        for suffix, label in active_suffixes:
            # Format matches Timberland's Cloudinary pattern
            url = f"{base_cdn_url}{preset_prefix}{sku}{suffix}.jpg"
            sku_url_map[sku]['urls'][suffix] = url
            all_urls_to_check.add(url)

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

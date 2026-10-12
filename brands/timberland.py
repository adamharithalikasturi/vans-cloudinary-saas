# brands/timberland.py

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
        silhouette = str(row.get('AH1 SILLOUTE', '')).upper()
        
        # Optional root cleanup if Timberland style numbers follow a similar trim pattern
        root_sku = sku

        if 'FOOTWEAR' in division or 'SHOES' in silhouette:
            active_suffixes = [s[0] for s in FOOTWEAR_SUFFIXES]
        elif 'APPAREL' in division or silhouette in ['TOPS', 'BOTTOMS']:
            active_suffixes = [s[0] for s in APPAREL_SUFFIXES]
        else:
            active_suffixes = [s[0] for s in ACCESSORY_SUFFIXES]
            
        sku_url_map[sku] = {
            'root': root_sku,
            'division': division if division != '#' else 'FOOTWEAR',
            'urls': {}
        }
        
        for suffix in active_suffixes:
            url = f"{base_cdn_url}{preset_prefix}{root_sku}{suffix}.jpg"
            sku_url_map[sku]['urls'][suffix] = url
            all_urls_to_check.add(url)

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

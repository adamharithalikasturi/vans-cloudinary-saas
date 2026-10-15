# brands/vans.py

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

def parse_vans_catalog(df, base_cdn_url, preset):
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
        
        known = division not in ('', '#', 'NAN') or silhouette not in ('', '#', 'NAN')
        if not known:
            # Only the item code was supplied: check every angle we know about
            active_suffixes = ALL_UNIQUE_SUFFIXES
        elif 'FOOTWEAR' in division or 'SHOES' in silhouette:
            active_suffixes = [s[0] for s in FOOTWEAR_SUFFIXES]
        elif 'APPAREL' in division or silhouette in ['TOPS', 'BOTTOMS']:
            active_suffixes = [s[0] for s in APPAREL_SUFFIXES]
        else:
            active_suffixes = [s[0] for s in ACCESSORY_SUFFIXES]
            
        van_url_map[van] = {
            'root': root_van,
            'division': division if division not in ('', '#', 'NAN') else ('FOOTWEAR' if known else 'Not specified'),
            'urls': {}
        }
        
        for suffix in active_suffixes:
            # Construct the three regional/format variants for this suffix
            url_standard = f"{base_cdn_url}{preset_prefix}{root_van}{suffix}.jpg"
            url_us = f"https://img.vans.com/image/upload/{preset_prefix}{root_van}{suffix}.jpg"
            url_eu = f"https://assets.vans.eu/images/{preset_prefix}{root_van}{suffix}/.jpg"
            
            # Add all of them to the checker so the backend probes each source
            all_urls_to_check.add(url_standard)
            all_urls_to_check.add(url_us)
            all_urls_to_check.add(url_eu)
            
            # Fallback mapping order: Standard first, then US, then EU.
            # We map them under the clean suffix key using a priority structure or by checking 
            # (Note: Since the async checker resolves which URLs return 200 OK after this function runs, 
            # we can store them or let the app evaluate them. To prevent duplicate card rendering in the UI 
            # while keeping the clean label, we assign the primary fallback chain or keep them organized).
            # If your backend checks status codes later, mapping them under distinct fallback keys or 
            # storing the preference order allows your validator to pick the first working one.
            
            # For immediate clean labeling without cluttering the UI with '_standard/_us/_eu' tags:
            # We map standard as the primary key name (e.g., '-HERO' or '-ALT40'), 
            # and let your validation script resolve the fallback.
            
            # To ensure clean labels (e.g., 'Alt 40' instead of 'Alt 40_standard'):
            van_url_map[van]['urls'][suffix] = url_standard
            van_url_map[van]['urls'][f"{suffix}_us"] = url_us
            van_url_map[van]['urls'][f"{suffix}_eu"] = url_eu

    return van_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

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
            # Construct all three variations
            url_standard = f"{base_cdn_url}{preset_prefix}{root_van}{suffix}.jpg"
            url_us = f"https://assets.vans.com/images/{preset_prefix}{root_van}{suffix}/.jpg"
            url_eu = f"https://assets.vans.eu/images/{preset_prefix}{root_van}{suffix}/.jpg"
            
            # Add all to background checker
            all_urls_to_check.add(url_standard)
            all_urls_to_check.add(url_us)
            all_urls_to_check.add(url_eu)
            
            # Store them cleanly. To ensure EU images aren't lost for hero/early alts 
            # while keeping clean labels, we map the primary clean suffix to standard, 
            # but preserve US and EU as fallback keys so the validator can capture whichever server holds the asset.
            van_url_map[van]['urls'][suffix] = url_standard
            van_url_map[van]['urls'][f"{suffix}_us"] = url_us
            van_url_map[van]['urls'][f"{suffix}_eu"] = url_eu

    return van_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES


# ---------------------------------------------------------------------------
# Server fallback: standard first, then US, then EU.
#
# parse_vans_catalog() builds up to three addresses per image slot:
#     "<suffix>"      -> standard server   (shown as e.g. "Alt 40")
#     "<suffix>_us"   -> US server         (shown as e.g. "Alt 40_us")
#     "<suffix>_eu"   -> EU server         (shown as e.g. "Alt 40_eu")
# After the availability check, prune_fallbacks() keeps only ONE per slot:
#     standard found  -> use standard, ignore US and EU
#     else US found   -> use US, ignore EU
#     else EU found   -> use EU
# Nothing is deleted from the parsing logic above; this only removes duplicates afterwards.
# ---------------------------------------------------------------------------
FALLBACK_ORDER = ("_us", "_eu")      # standard is always tried first


def prune_fallbacks(van_url_map, valid):
    """Mutates van_url_map and valid (url -> bool) in place so each image slot has a single winner."""
    keep, discard = set(), set()

    for data in van_url_map.values():
        urls = data["urls"]
        slots = [k for k in urls if not k.endswith(FALLBACK_ORDER)]      # "-HERO", "-ALT1", ...

        for slot in slots:
            candidates = [(slot, urls.get(slot))] + [(slot + tag, urls.get(slot + tag)) for tag in FALLBACK_ORDER]
            candidates = [(k, u) for k, u in candidates if u]

            winner_key = next((k for k, u in candidates if valid.get(u, False)), None)
            for key, url in candidates:
                if key == winner_key:
                    keep.add(url)
                else:
                    discard.add(url)
                    if key != slot:               # keep the standard key (even when empty) so slots stay stable
                        urls.pop(key, None)       # drop losing fallbacks to keep results small

    # Never switch off an address that is also a winner (standard and US can be the same address)
    for url in discard - keep:
        if url in valid:
            valid[url] = False

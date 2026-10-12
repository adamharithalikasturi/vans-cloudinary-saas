import requests
from bs4 import BeautifulSoup

TIMBERLAND_SUFFIXES = [("-HERO", "Hero View")] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys([s[0] for s in TIMBERLAND_SUFFIXES]))

def scrape_timberland_catalog(df, base_cdn_url="https://assets.timberland.com/images/t_img/f_auto/", preset=""):
    sku_col = 'VENDOR ARTICLE NO.'
    df_unique = df.drop_duplicates(subset=[sku_col]).copy()
    
    sku_url_map = {}
    all_urls_to_check = set()
    preset_prefix = f"{preset.strip()}/" if preset.strip() else ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for _, row in df_unique.iterrows():
        sku = str(row[sku_col]).strip()
        if not sku or sku == 'nan' or sku.upper() == 'NOT ASSIGNED':
            continue
            
        division = str(row.get('DIVISION', 'FOOTWEAR')).upper()
        silhouette = str(row.get('AH1 SILLOUTE', '')).upper()
        
        search_query = sku.lstrip('0').rstrip('Z')
        search_url = f"https://www.timberland.com/en-us/search?q={search_query}"
        
        images_found = {}
        try:
            resp = requests.get(search_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for img in soup.find_all('img'):
                    src = img.get('src', '') or img.get('data-src', '')
                    if "assets.timberland.com/images" in src:
                        matched_suffix = "-HERO"
                        for suffix, _ in TIMBERLAND_SUFFIXES:
                            if suffix.lower() in src.lower():
                                matched_suffix = suffix
                                break
                        images_found[matched_suffix] = src
                        all_urls_to_check.add(src)
        except Exception:
            pass

        # Fallback to programmatic pattern mapping if direct search markup blocks requests
        if not images_found:
            clean_sku = sku.lstrip('0')
            asset_root = 'TB1' + clean_sku[3:] if clean_sku.startswith('TB0') else ('TB1' + clean_sku[2:] if clean_sku.startswith('TB') else clean_sku)
            for suffix, _ in TIMBERLAND_SUFFIXES:
                url = f"{base_cdn_url}{preset_prefix}{asset_root}{suffix}.png"
                images_found[suffix] = url
                all_urls_to_check.add(url)

        sku_url_map[sku] = {
            'root': search_query,
            'division': division if division != '#' else 'FOOTWEAR',
            'urls': images_found
        }

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

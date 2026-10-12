import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TIMBERLAND_SUFFIXES = [("-HERO", "Hero View")] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(1, 16)] + \
                      [(f"-ALT{i}", f"Alt {i}") for i in range(40, 56)]

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys([s[0] for s in TIMBERLAND_SUFFIXES]))

def scrape_timberland_catalog(df, base_cdn_url="", preset=""):
    sku_col = 'VENDOR ARTICLE NO.'
    df_unique = df.drop_duplicates(subset=[sku_col]).copy()
    
    sku_url_map = {}
    all_urls_to_check = set()

    # Setup Selenium options for headless execution
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)

    try:
        for _, row in df_unique.iterrows():
            sku = str(row[sku_col]).strip()
            if not sku or sku == 'nan' or sku.upper() == 'NOT ASSIGNED':
                continue
                
            division = str(row.get('DIVISION', 'FOOTWEAR')).upper()
            silhouette = str(row.get('AH1 SILLOUTE', '')).upper()
            
            # Clean SKU for searching on Timberland's site
            search_query = sku.lstrip('0').rstrip('Z')
            search_url = f"https://www.timberland.com/en-us/search?q={search_query}"
            
            driver.get(search_url)
            images_found = {}
            
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='assets.timberland.com']"))
                )
                img_elements = driver.find_elements(By.CSS_SELECTOR, "img")
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src and "assets.timberland.com/images" in src:
                        # Extract suffix type (e.g. -HERO, -ALT1) from URL if present
                        matched_suffix = "-HERO"
                        for suffix, _ in TIMBERLAND_SUFFIXES:
                            if suffix.lower() in src.lower():
                                matched_suffix = suffix
                                break
                        images_found[matched_suffix] = src
                        all_urls_to_check.add(src)
            except Exception:
                pass # Fallback or empty if not found via search grid

            sku_url_map[sku] = {
                'root': search_query,
                'division': division if division != '#' else 'FOOTWEAR',
                'urls': images_found
            }
            time.sleep(1) # Polite pause between queries

    finally:
        driver.quit()

    return sku_url_map, all_urls_to_check, ALL_UNIQUE_SUFFIXES

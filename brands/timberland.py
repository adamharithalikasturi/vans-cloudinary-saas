import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_timberland_images(excel_path, output_csv="timberland_scraped_links.csv"):
    # Load dataset
    df = pd.read_excel(excel_path)
    sku_col = 'VENDOR ARTICLE NO.'
    unique_skus = df[sku_col].dropna().unique()
    
    # Setup Selenium options (running headless or visible)
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Uncomment if you want it to run in the background
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    scraped_data = []

    try:
        for sku in unique_skus:
            sku_str = str(sku).strip()
            if not sku_str or sku_str == 'nan' or sku_str.upper() == 'NOT ASSIGNED':
                continue
                
            # Clean SKU for search if needed (e.g., removing leading zeros or trailing Z)
            search_query = sku_str.lstrip('0').rstrip('Z')
            
            # Timberland search URL structure
            search_url = f"https://www.timberland.com/en-us/search?q={search_query}"
            driver.get(search_url)
            
            images_found = set()
            try:
                # Wait for product grid or product images to load
                WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='assets.timberland.com']"))
                )
                
                # Extract all image elements pointing to Cloudinary CDN
                img_elements = driver.find_elements(By.CSS_SELECTOR, "img")
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src and "assets.timberland.com/images" in src:
                        images_found.add(src)
                        
            except Exception as e:
                print(f"Timeout or no images found for SKU: {sku_str}")

            # Save found links for this SKU
            for img_url in images_found:
                scraped_data.append({
                    'VENDOR ARTICLE NO.': sku_str,
                    'IMAGE_URL': img_url
                })
                
            print(f"Processed SKU {sku_str}: Found {len(images_found)} images.")
            time.sleep(2) # Polite delay between requests

    finally:
        driver.quit()
        
    # Save results to CSV
    result_df = pd.DataFrame(scraped_data)
    result_df.to_csv(output_csv, index=False)
    print(f"Scraping complete! Saved to {output_csv}")

if __name__ == "__main__":
    scrape_timberland_images("261012-timberland-list.xlsx")

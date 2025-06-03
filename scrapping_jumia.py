import os
import re
import time
import traceback
import tempfile
import logging
import pandas as pd
from datetime import datetime
from typing import List
from functools import lru_cache
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

import boto3
from botocore.config import Config

# === LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === CONFIG ===
BASE_URL = "https://www.jumia.ma"
MAX_PAGES = 1000
WAIT_TIME = 3
TIMEOUT = 20
SCROLL_ATTEMPTS = 3
SAVE_INTERVAL = 100
MAX_WORKERS = 5
MAX_RETRIES = 3
OUTPUT_DIR = "jumia_product_link"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === BOTO3 CONFIG ===
S3_CONFIG = Config(max_pool_connections=10)

@lru_cache(maxsize=1)
def get_chrome_options() -> Options:
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Décommenter si interface serveur
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
    temp_profile_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f'--user-data-dir={temp_profile_dir}')
    return chrome_options

def open_browser():
    service = Service("/usr/local/bin/chromedriver")
    return webdriver.Chrome(service=service, options=get_chrome_options())

def scroll_page(browser):
    try:
        last_height = browser.execute_script("return document.body.scrollHeight")
        for _ in range(SCROLL_ATTEMPTS):
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            new_height = browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    except Exception as e:
        logger.warning(f"⚠️ Scroll error: {e}")

def extract_product_links(soup: BeautifulSoup) -> List[str]:
    links = []
    try:
        for article in soup.find_all("article", class_="prd"):
            a = article.find("a", class_="core")
            if a and a.get("href"):
                links.append(urljoin(BASE_URL, a["href"]))
    except Exception as e:
        logger.error(f"❌ Extraction error: {e}")
    return links

def process_page(page_url: str, browser, retry_count=0):
    if retry_count >= MAX_RETRIES:
        logger.error(f"❌ Max retries reached for {page_url}")
        return []
    try:
        browser.get(page_url)
        time.sleep(WAIT_TIME)
        WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, "prd")))
        scroll_page(browser)
        return extract_product_links(BeautifulSoup(browser.page_source, "lxml"))
    except (TimeoutException, WebDriverException) as e:
        logger.warning(f"⚠️ Retry {retry_count + 1} for {page_url} due to: {e}")
        return process_page(page_url, browser, retry_count + 1)

def process_page_batch(batch, browser):
    all_links = []
    for page_url in batch:
        links = process_page(page_url, browser)
        all_links.extend(links)
    return all_links

def save_results(product_urls: List[str], filename: str):
    scores = [len(product_urls) - i for i in range(len(product_urls))]
    df = pd.DataFrame({"lien_du_produit": product_urls, "score": scores})
    output_path = os.path.join(OUTPUT_DIR, filename)
    df.to_excel(output_path, index=False, engine='openpyxl')
    logger.info(f"💾 Sauvegarde : {output_path}")
    upload_to_s3(output_path)

def save_intermediate(product_urls: List[str], page: int):
    if len(product_urls) % SAVE_INTERVAL == 0:
        filename = f"jumia_links_intermediate_page{page}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_results(product_urls, filename)
        logger.info(f"📥 Sauvegarde intermédiaire après {len(product_urls)} produits")

def upload_to_s3(file_path, bucket="msde-pfe-blobs", s3_key=None):
    s3 = boto3.client("s3", config=S3_CONFIG)
    if not s3_key:
        s3_key = f"jumia/links/{os.path.basename(file_path)}"
    try:
        s3.upload_file(file_path, bucket, s3_key)
        logger.info(f"✅ Upload S3 : s3://{bucket}/{s3_key}")
    except Exception as e:
        logger.error(f"❌ Upload échoué : {e}")

def get_product_links(category_url: str) -> List[str]:
    logger.info("🔍 Lancement de la collecte des liens produits...")
    browser = open_browser()
    if not browser:
        logger.error("❌ Impossible d'ouvrir le navigateur")
        return []
    
    all_links = []
    try:
        base_url = re.sub(r'\?page=\d+', '', category_url)
        page_urls = [f"{base_url}?page={i}" for i in range(1, MAX_PAGES + 1)]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for i in range(0, len(page_urls), MAX_WORKERS):
                batch = page_urls[i:i + MAX_WORKERS]
                futures.append(executor.submit(process_page_batch, batch, browser))

            for future in as_completed(futures):
                links = future.result()
                all_links.extend(links)
                logger.info(f"🔗 Liens cumulés : {len(all_links)}")
                save_intermediate(all_links, len(all_links) // SAVE_INTERVAL)
    except Exception as e:
        logger.error(traceback.format_exc())
    finally:
        browser.quit()

    return all_links

def main():
    logger.info("🚀 === DÉMARRAGE DU SCRAPING ===")
    category_url = "https://www.jumia.ma/beaute-hygiene-sante/"
    product_urls = get_product_links(category_url)

    if not product_urls:
        logger.error("❌ Aucun lien de produit trouvé.")
        return

    filename = f"jumia_products_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    save_results(product_urls, filename)
    logger.info("🏁 === FIN DU SCRAPING ===")

if __name__ == "__main__":
    main()

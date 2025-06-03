# Importation des bibliothèques nécessaires
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import traceback
from selenium.webdriver.chrome.options import Options
import re
import os
import tempfile
from typing import List
from functools import lru_cache
import logging
import boto3  # 🟢 Pour l'envoi vers AWS S3
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration du dossier de sortie
output_dir = "jumia_product_link"
os.makedirs(output_dir, exist_ok=True)

# Constantes
MAX_PAGES = 1000
SCROLL_ATTEMPTS = 3
WAIT_TIME = 3
BASE_URL = "https://www.jumia.ma"
SAVE_INTERVAL = 100
MAX_RETRIES = 3
TIMEOUT = 20
MAX_WORKERS = 5

@lru_cache(maxsize=1)
def get_chrome_options() -> Options:
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # ✅ Ajout d'un répertoire temporaire pour éviter le conflit
    temp_profile_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f'--user-data-dir={temp_profile_dir}')
    
    return chrome_options

def open_browser():
    chrome_options = get_chrome_options()
    service = Service("/usr/local/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

def scroll_page(browser: webdriver.Chrome) -> None:
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
        logger.warning(f"Error during page scroll: {e}")

def extract_product_links(soup: BeautifulSoup) -> List[str]:
    links = []
    try:
        for article in soup.find_all("article", class_="prd"):
            if link := article.find("a", class_="core"):
                href = link.get('href')
                if href:
                    full_url = urljoin(BASE_URL, href)
                    links.append(full_url)
    except Exception as e:
        logger.error(f"Error extracting product links: {e}")
    return links

def process_page(page_url: str, browser: webdriver.Chrome, retry_count: int = 0) -> List[str]:
    if retry_count >= MAX_RETRIES:
        logger.error(f"Max retries reached for page {page_url}")
        return []

    try:
        browser.get(page_url)
        time.sleep(WAIT_TIME)

        try:
            WebDriverWait(browser, TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, "prd"))
            )
        except TimeoutException:
            logger.warning(f"Timeout waiting for products on page {page_url}")
            return process_page(page_url, browser, retry_count + 1)

        scroll_page(browser)
        return extract_product_links(BeautifulSoup(browser.page_source, "lxml"))

    except WebDriverException as e:
        logger.error(f"WebDriver error on page {page_url}: {e}")
        return process_page(page_url, browser, retry_count + 1)
    except Exception as e:
        logger.error(f"Unexpected error processing page {page_url}: {e}")
        return []

def process_page_batch(page_urls: List[str], browser: webdriver.Chrome) -> List[str]:
    all_links = []
    for page_url in page_urls:
        if links := process_page(page_url, browser):
            all_links.extend(links)
    return all_links

def save_intermediate_results(product_urls: List[str], page: int) -> None:
    if len(product_urls) % SAVE_INTERVAL == 0:
        filename = f"jumia_products_links_intermediate_page{page}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_results(product_urls, filename)
        logger.info(f"Sauvegarde intermédiaire effectuée : {len(product_urls)} produits")

def get_product_links(category_url: str) -> List[str]:
    logger.info("Starting link collection...")
    browser = open_browser()
    if not browser:
        logger.error("Failed to initialize browser")
        return []

    all_links = []
    try:
        base_url = re.sub(r'\?page=\d+', '', category_url)
        page_urls = [f"{base_url}?page={page}" for page in range(1, MAX_PAGES + 1)]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for i in range(0, len(page_urls), MAX_WORKERS):
                batch = page_urls[i:i + MAX_WORKERS]
                future = executor.submit(process_page_batch, batch, browser)
                futures.append(future)

            for future in as_completed(futures):
                if batch_links := future.result():
                    all_links.extend(batch_links)
                    logger.info(f"Total links collected: {len(all_links)}")
                    save_intermediate_results(all_links, len(all_links) // SAVE_INTERVAL)

    except Exception as e:
        logger.error(f"Error during link collection: {e}")
        logger.error(traceback.format_exc())
    finally:
        browser.quit()

    return all_links

def save_results(product_urls: List[str], filename: str) -> None:
    scores = [len(product_urls) - i for i in range(len(product_urls))]
    df = pd.DataFrame({
        "lien_du_produit": product_urls,
        "score": scores
    })
    output_path = os.path.join(output_dir, filename)
    df.to_excel(output_path, index=False, engine='openpyxl')
    logger.info(f"{len(product_urls)} liens sauvegardés dans : {output_path}")
    upload_to_s3(output_path)

# 🟢 Fonction d'upload vers AWS S3
def upload_to_s3(file_path, bucket_name="msde-pfe-blobs", s3_key=None):
    s3 = boto3.client("s3")
    if not s3_key:
        s3_key = f"jumia/links/{os.path.basename(file_path)}"
    try:
        s3.upload_file(file_path, bucket_name, s3_key)
        logger.info(f"✅ Fichier uploadé sur S3 : s3://{bucket_name}/{s3_key}")
    except Exception as e:
        logger.error(f"❌ Échec de l'upload S3 : {e}")

def main():
    logger.info("=== DÉMARRAGE DU SCRAPING ===")
    category_url = "https://www.jumia.ma/beaute-hygiene-sante/"
    product_urls = get_product_links(category_url)

    if not product_urls:
        logger.error("Aucun lien de produit trouvé. Arrêt du script.")
        return

    filename = f"jumia_products_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    save_results(product_urls, filename)
    logger.info("=== FIN DU SCRIPT ===")

if __name__ == "__main__":
    main()

# Importation des bibliothèques nécessaires
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from urllib.parse import urljoin
import pandas as pd
import tempfile
import traceback
import logging
import boto3
import datetime
import re
import os
import time
from typing import List, Set
from queue import Queue
from threading import Lock

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
MAX_PAGES = 10000
SCROLL_ATTEMPTS = 3
WAIT_TIME = 2  # Réduit pour optimiser la vitesse
BASE_URL = "https://www.jumia.ma"
MAX_RETRIES = 3
TIMEOUT = 15  # Réduit pour optimiser la vitesse
MAX_WORKERS = 8  # Augmenté pour plus de parallélisme
BATCH_SIZE = 50  # Taille des lots pour le traitement

# Structure de données thread-safe pour stocker les liens
class ThreadSafeLinkStorage:
    def __init__(self):
        self._links: Set[str] = set()
        self._lock = Lock()
    
    def add_links(self, links: List[str]):
        with self._lock:
            self._links.update(links)
    
    def get_all_links(self) -> List[str]:
        with self._lock:
            return list(self._links)
    
    def get_count(self) -> int:
        with self._lock:
            return len(self._links)

link_storage = ThreadSafeLinkStorage()

@lru_cache(maxsize=1)
def get_chrome_options() -> Options:
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return chrome_options

def open_browser():
    service = Service("/usr/bin/chromedriver")
    chrome_options = get_chrome_options()
    return webdriver.Chrome(service=service, options=chrome_options)

def scroll_page(browser: webdriver.Chrome) -> None:
    try:
        last_height = browser.execute_script("return document.body.scrollHeight")
        for _ in range(SCROLL_ATTEMPTS):
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)  # Réduit pour optimiser la vitesse
            new_height = browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    except Exception as e:
        logger.warning(f"Erreur pendant le scroll : {e}")

def extract_product_links(soup: BeautifulSoup) -> List[str]:
    links = []
    try:
        for article in soup.find_all("article", class_="prd"):
            if link := article.find("a", class_="core"):
                href = link.get('href')
                if href:
                    links.append(urljoin(BASE_URL, href))
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des liens : {e}")
    return links

def process_page(page_url: str, browser: webdriver.Chrome, retry_count: int = 0) -> List[str]:
    if retry_count >= MAX_RETRIES:
        logger.error(f"Nombre max de tentatives atteint pour {page_url}")
        return []

    try:
        browser.get(page_url)
        time.sleep(WAIT_TIME)

        WebDriverWait(browser, TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "prd"))
        )

        scroll_page(browser)
        return extract_product_links(BeautifulSoup(browser.page_source, "lxml"))

    except (TimeoutException, WebDriverException) as e:
        logger.warning(f"Erreur sur {page_url} : {e}. Nouvelle tentative...")
        return process_page(page_url, browser, retry_count + 1)

    except Exception as e:
        logger.error(f"Erreur inattendue : {e}")
        return []

def process_page_batch(page_urls: List[str], browser: webdriver.Chrome) -> List[str]:
    all_links = []
    for url in page_urls:
        links = process_page(url, browser)
        if links:
            all_links.extend(links)
            link_storage.add_links(links)
            logger.info(f"📦 Total actuel : {link_storage.get_count()} liens collectés.")
    return all_links

def save_results(product_urls: List[str], filename: str) -> None:
    scores = [len(product_urls) - i for i in range(len(product_urls))]
    df = pd.DataFrame({
        "lien_du_produit": product_urls,
        "score": scores
    })
    output_path = os.path.join(output_dir, filename)
    df.to_excel(output_path, index=False, engine='openpyxl')
    logger.info(f"💾 {len(product_urls)} liens sauvegardés dans : {output_path}")
    upload_to_s3(output_path)

def upload_to_s3(file_path, bucket_name="msde-pfe-blobs", s3_key=None):
    s3 = boto3.client("s3")
    if not s3_key:
        s3_key = f"jumia/links/{os.path.basename(file_path)}"
    try:
        s3.upload_file(file_path, bucket_name, s3_key)
        logger.info(f"☁️ Fichier envoyé vers S3 : s3://{bucket_name}/{s3_key}")
    except Exception as e:
        logger.error(f"❌ Échec de l'envoi vers S3 : {e}")

def get_product_links(category_url: str) -> List[str]:
    logger.info("🔍 Lancement de la collecte des liens produits...")
    browser = open_browser()
    if not browser:
        logger.error("❌ Échec de l'initialisation du navigateur.")
        return []

    try:
        base_url = re.sub(r'\?page=\d+', '', category_url)
        page_urls = [f"{base_url}?page={page}" for page in range(1, MAX_PAGES + 1)]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for i in range(0, len(page_urls), BATCH_SIZE):
                batch = page_urls[i:i + BATCH_SIZE]
                futures.append(executor.submit(process_page_batch, batch, browser))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Erreur dans le traitement d'un lot : {e}")

    except Exception as e:
        logger.error(f"❌ Erreur pendant la collecte : {e}")
        logger.error(traceback.format_exc())
    finally:
        browser.quit()

    return link_storage.get_all_links()

def main():
    logger.info("🚀 === DÉMARRAGE DU SCRAPING ===")
    category_url = "https://www.jumia.ma/beaute-hygiene-sante/"
    product_urls = get_product_links(category_url)

    if not product_urls:
        logger.error("❌ Aucun produit trouvé. Fin du script.")
        return

    filename = f"jumia_products_links_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    save_results(product_urls, filename)
    logger.info("✅ === FIN DU SCRAPING ===")

if __name__ == "__main__":
    main()

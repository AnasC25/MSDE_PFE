from datetime import datetime
import logging
import os
import tempfile
import time
import traceback

import boto3
import pandas as pd
import psutil
from botocore.config import Config
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Logging config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Folders & S3
OUTPUT_DIR = "jumia_products"
os.makedirs(OUTPUT_DIR, exist_ok=True)

S3_CONFIG = Config(max_pool_connections=50)
s3_client = boto3.client("s3", config=S3_CONFIG)
BUCKET_NAME = "msde-pfe-blobs"

def open_browser():
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--user-agent=Mozilla/5.0')
        chrome_options.add_argument(f'--user-data-dir={tempfile.mkdtemp()}')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = Service("/usr/local/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.error(f"Erreur navigateur : {e}")
        raise

def get_product_links(browser, category_url):
    try:
        logger.info(f"Récupération des liens depuis : {category_url}")
        all_product_links = set()
        current_page = 1
        max_pages = 50

        while current_page <= max_pages:
            if psutil.virtual_memory().percent > 85:
                logger.warning("⚠️ Mémoire saturée, pause 30s...")
                time.sleep(30)

            page_url = f"{category_url}?page={current_page}" if current_page > 1 else category_url
            logger.info(f"Page {current_page} : {page_url}")
            try:
                browser.get(page_url)
                time.sleep(5)
            except Exception as e:
                logger.error(f"Crash du navigateur à {page_url} : {e}")
                continue

            try:
                WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.core[href*='.html']"))
                )
            except TimeoutException:
                logger.warning("⏳ Timeout, passage à la page suivante")
                current_page += 1
                continue

            soup = BeautifulSoup(browser.page_source, "lxml")
            links = set()
            for sel in ["article.prd._fb._spn.c-prd.col a.core", "article.prd a.core", "a.core[href*='.html']"]:
                elements = soup.select(sel)
                logger.info(f"{len(elements)} éléments avec {sel}")
                for el in elements:
                    href = el.get("href")
                    if href and not href.startswith("http"):
                        href = "https://www.jumia.ma" + href
                    links.add(href)

            if not links:
                logger.info("Fin de la pagination.")
                break

            all_product_links.update(links)
            logger.info(f"Total cumulé : {len(all_product_links)} liens")

            if current_page % 10 == 0:
                logger.info("♻️ Redémarrage du navigateur pour vider mémoire...")
                browser.quit()
                browser = open_browser()

            current_page += 1
            time.sleep(2)

        return list(sorted(all_product_links))
    except Exception as e:
        logger.error(f"Erreur dans get_product_links : {e}")
        logger.error(traceback.format_exc())
        return []

def get_product_details(url, browser):
    try:
        logger.info(f"Details produit : {url}")
        browser.get(url)
        time.sleep(2)
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "-fs20")))

        soup = BeautifulSoup(browser.page_source, "lxml")

        def extract(sel):
            el = soup.select_one(sel)
            return el.text.strip() if el else "Non disponible"

        img = soup.select_one("#imgs img")
        return {
            "designation": extract("h1.-fs20.-pts.-pbxs"),
            "marque": extract("#jm > main > div:nth-child(1) > section > div > div.col10 > div.-phs > div.-pvxs"),
            "prix_vente": extract("span.-b.-ubpt.-tal.-fs24.-prxs"),
            "prix_barre": extract("span.-tal.-gy5.-lthr.-fs16.-pvxs.-ubpt"),
            "image_url": img['src'] if img and 'src' in img.attrs else "Non disponible",
            "lien_produit": url,
            "date_extraction": datetime.now()
        }
    except Exception as e:
        logger.warning(f"Erreur produit : {e}")
        return None

def upload_to_s3(file_path):
    try:
        key = f"jumia/products/{os.path.basename(file_path)}"
        s3_client.upload_file(file_path, BUCKET_NAME, key)
        logger.info(f"✅ Upload S3 : s3://{BUCKET_NAME}/{key}")
    except Exception as e:
        logger.error(f"❌ Échec upload S3 : {e}")

def main():
    logger.info("🚀 SCRAPING JUMIA LANCÉ")
    browser = open_browser()

    try:
        all_products = []
        for cat_url in ["https://www.jumia.ma/beaute-hygiene-sante/"]:
            links = get_product_links(browser, cat_url)
            for idx, link in enumerate(links, 1):
                logger.info(f"[{idx}/{len(links)}] Scraping produit")
                data = get_product_details(link, browser)
                if data:
                    all_products.append(data)
                time.sleep(1.5)

        if all_products:
            df = pd.DataFrame(all_products)
            df["score"] = range(len(df), 0, -1)
            file = f"jumia_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            path = os.path.join(OUTPUT_DIR, file)
            df.to_excel(path, index=False, engine="openpyxl")
            logger.info(f"💾 Fichier généré : {path}")
            upload_to_s3(path)
        else:
            logger.warning("❌ Aucun produit trouvé")
    finally:
        browser.quit()

    logger.info("🏁 FIN DU SCRAPING")

if __name__ == "__main__":
    main()

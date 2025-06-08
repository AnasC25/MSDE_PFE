# Script complet fusionné et converti avec Playwright
import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import boto3
import io
from tenacity import retry, stop_after_attempt, wait_exponential

# === Configuration initiale ===
BASE_URL = "https://www.jumia.ma"
CATEGORY_URL = f"{BASE_URL}/beaute-hygiene-sante/"
WAIT_TIME = 3
MAX_RETRIES = 3

# Configuration AWS
AWS_REGION = 'us-east-1'
BUCKET_NAME = 'msde-pfe-blobs'
S3_PREFIX = 'jumia'

# Configuration AWS
s3_client = boto3.client('s3', region_name=AWS_REGION)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Récupération des liens de produits ===
async def fetch_product_links() -> List[str]:
    links = []
    current_page = 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        while True:
            url = f"{CATEGORY_URL}?page={current_page}"
            logger.info(f"🔄 Chargement : {url}")
            try:
                await page.goto(url, timeout=60000)
                await page.wait_for_selector("article.prd", timeout=30000)
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")
                articles = soup.find_all("article", class_="prd")

                for article in articles:
                    a_tag = article.find("a", class_="core")
                    if a_tag and a_tag.get("href"):
                        href = a_tag["href"]
                        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                        links.append(full_url)
                        logger.info(f"✅ Lien ajouté : {full_url}")
                if not articles:
                    logger.info("❌ Aucun article trouvé. Arrêt.")
                    break
                current_page += 1
                await asyncio.sleep(WAIT_TIME)
            except Exception as e:
                logger.warning(f"⚠️ Erreur sur page {current_page} : {e}")
                break
        await browser.close()

    return links

@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
async def fetch_single_product_detail(page, url: str) -> dict:
    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("body", timeout=30000)
        content = await page.content()
        soup = BeautifulSoup(content, "lxml")

        name = soup.find("h1", class_="-fs20 -pts -pbxs")
        price = soup.find("span", class_="-b -ltr -tal -fs24")

        return {
            "url": url,
            "nom_du_produit": name.get_text(strip=True) if name else "N/A",
            "prix": price.get_text(strip=True) if price else "N/A"
        }
    except Exception as e:
        logger.warning(f"⚠️ Échec de la récupération des détails pour {url}: {e}")
        raise

# === Récupération des détails de produits ===
async def fetch_product_details(links: List[str]):
    results = []
    failed_urls = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for idx, url in enumerate(links):
            logger.info(f"🔄 Détail produit {idx+1}/{len(links)} : {url}")
            try:
                product_detail = await fetch_single_product_detail(page, url)
                results.append(product_detail)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"❌ Échec après {MAX_RETRIES} tentatives pour {url}: {e}")
                failed_urls.append(url)
                continue

        await browser.close()

    if results:
        df = pd.DataFrame(results)
        df["score"] = range(len(results), 0, -1)
        
        # Sauvegarde en parquet et upload vers S3
        parquet_buffer = io.BytesIO()
        df.to_parquet(parquet_buffer, index=False)
        parquet_buffer.seek(0)
        
        s3_key = f"{S3_PREFIX}/details/jumia_product_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        s3_client.upload_fileobj(parquet_buffer, BUCKET_NAME, s3_key)
        logger.info(f"✅ Détails sauvegardés dans S3 : {s3_key}")
        
        if failed_urls:
            logger.warning(f"⚠️ {len(failed_urls)} URLs ont échoué après {MAX_RETRIES} tentatives")
    else:
        logger.warning("❌ Aucun détail récupéré.")

# === Fonction principale ===
async def main():
    logger.info("🚀 Démarrage du scraping Jumia")
    links = await fetch_product_links()
    if links:
        await fetch_product_details(links)
    logger.info("🏁 Script terminé")

# === Exécution ===
asyncio.run(main())

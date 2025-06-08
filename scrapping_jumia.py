# === IMPORTS ===
import os
import io
import re
import boto3
import asyncio
import logging
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List
from playwright.async_api import async_playwright, TimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential

# === CONFIGURATION ===
BASE_URL = "https://www.jumia.ma"
CATEGORY_URL = f"{BASE_URL}/beaute-hygiene-sante/"
WAIT_TIME = 2
MAX_RETRIES = 3
USE_PROXY = True

# ScraperAPI Configuration
SCRAPER_API_KEY = "8572c68867fd3e96ea4674da6db14638"
PROXY_SERVER = f"http://api.scraperapi.com:8001/?api_key={SCRAPER_API_KEY}&render=true"

# AWS S3
AWS_REGION = 'us-east-1'
BUCKET_NAME = 'msde-pfe-blobs'
S3_PREFIX = 'jumia'
s3_client = boto3.client('s3', region_name=AWS_REGION)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    "accept-language": "fr-FR,fr;q=0.9",
    "referer": "https://www.google.com/"
}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# === SCRAPING DES LIENS ===
async def fetch_product_links() -> List[str]:
    links = []
    current_page = 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": PROXY_SERVER} if USE_PROXY else None
        )
        context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=HEADERS)
        page = await context.new_page()

        while True:
            url = f"{CATEGORY_URL}?page={current_page}"
            logger.info(f"🔄 Chargement : {url}")
            try:
                await page.goto(url, timeout=60000)
                await page.wait_for_selector("article.prd", timeout=60000)
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

            except TimeoutError:
                logger.warning(f"⚠️ Timeout sur page {current_page}, arrêt.")
                break
            except Exception as e:
                logger.warning(f"⚠️ Erreur sur page {current_page} : {e}")
                break

        await browser.close()
    return links

# === SCRAPING DÉTAIL PRODUIT ===
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
        logger.warning(f"⚠️ Échec de récupération pour {url}: {e}")
        # Dump HTML en cas d'échec
        try:
            html_dump = await page.content()
            with open("debug_failed_page.html", "w", encoding="utf-8") as f:
                f.write(html_dump)
        except:
            pass
        raise

# === TRAITEMENT DES LIENS ===
async def fetch_product_details(links: List[str]):
    results = []
    failed_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": PROXY_SERVER} if USE_PROXY else None
        )
        context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=HEADERS)
        page = await context.new_page()

        for idx, url in enumerate(links):
            logger.info(f"🔄 Produit {idx+1}/{len(links)} : {url}")
            try:
                product_detail = await fetch_single_product_detail(page, url)
                results.append(product_detail)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"❌ Échec après {MAX_RETRIES} tentatives : {url}")
                failed_urls.append(url)

        await browser.close()

    # Enregistrement
    if results:
        df = pd.DataFrame(results)
        df["score"] = range(len(results), 0, -1)

        parquet_buffer = io.BytesIO()
        df.to_parquet(parquet_buffer, index=False)
        parquet_buffer.seek(0)

        s3_key = f"{S3_PREFIX}/details/jumia_product_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        s3_client.upload_fileobj(parquet_buffer, BUCKET_NAME, s3_key)
        logger.info(f"✅ Données envoyées vers S3 : {s3_key}")
    else:
        logger.warning("❌ Aucun détail produit récupéré.")

    if failed_urls:
        logger.warning(f"⚠️ URLs échouées : {len(failed_urls)}")

# === LANCEUR ===
async def main():
    logger.info("🚀 Démarrage du scraping Jumia")
    links = await fetch_product_links()
    if links:
        await fetch_product_details(links)
    logger.info("🏁 Script terminé")

if __name__ == "__main__":
    asyncio.run(main())

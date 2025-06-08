# Script complet fusionné et converti avec Playwright
import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
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

class JumiaScraper:
    def __init__(self):
        self.browser: Browser = None
        self.context = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        self.start_time = datetime.now()
        logger.info("🚀 Initialisation du scraper Jumia")

    async def init_browser(self):
        """Initialize the browser with Cloudflare bypass settings."""
        try:
            logger.info("🌐 Démarrage du navigateur...")
            playwright = await async_playwright().start()
            
            # Launch browser with additional arguments to bypass Cloudflare
            self.browser = await playwright.chromium.launch(
                headless=True,  # Set to True for headless mode
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--window-size=1920,1080',
                    '--start-maximized'
                ]
            )
            
            # Create a new context with specific settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.user_agent,
                ignore_https_errors=True,
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0'
                }
            )
            logger.info("✅ Navigateur démarré avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage du navigateur: {str(e)}")
            raise

    async def close_browser(self):
        """Close the browser and context."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
            logger.info("🔒 Navigateur fermé avec succès")

    async def handle_cloudflare_challenge(self, page: Page):
        """Handle Cloudflare challenge if present."""
        try:
            # Wait for Cloudflare challenge to appear
            challenge_present = await page.wait_for_selector('#challenge-running', timeout=5000)
            if challenge_present:
                logger.info("🛡️ Cloudflare challenge détecté, attente de la résolution...")
                # Wait for the challenge to be solved
                await page.wait_for_selector('#challenge-running', state='hidden', timeout=30000)
                logger.info("✅ Cloudflare challenge résolu")
        except TimeoutError:
            logger.info("✅ Pas de challenge Cloudflare détecté")

    async def fetch_product_links(self) -> List[str]:
        """Fetch all product links from the category pages."""
        links = []
        current_page = 1
        page = None

        try:
            page = await self.context.new_page()
            
            while True:
                url = f"{CATEGORY_URL}?page={current_page}"
                logger.info(f"🔄 Chargement : {url}")
                
                try:
                    response = await page.goto(url, timeout=60000)
                    await self.handle_cloudflare_challenge(page)
                    
                    if response.status != 200:
                        logger.warning(f"⚠️ Page {current_page} retourne le statut {response.status}")
                        break
                    
                    await page.wait_for_selector("article.prd", timeout=30000)
                    content = await page.content()
                    soup = BeautifulSoup(content, "lxml")
                    articles = soup.find_all("article", class_="prd")

                    if not articles:
                        logger.info("❌ Aucun article trouvé. Arrêt.")
                        break

                    for article in articles:
                        a_tag = article.find("a", class_="core")
                        if a_tag and a_tag.get("href"):
                            href = a_tag["href"]
                            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                            links.append(full_url)
                            logger.info(f"✅ Lien ajouté : {full_url}")

                    current_page += 1
                    await asyncio.sleep(WAIT_TIME)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Erreur sur page {current_page} : {e}")
                    break
                    
        finally:
            if page:
                await page.close()

        return links

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_single_product_detail(self, page: Page, url: str) -> Dict:
        """Fetch details for a single product with retry mechanism."""
        try:
            await page.goto(url, timeout=60000)
            await self.handle_cloudflare_challenge(page)
            await page.wait_for_selector("body", timeout=30000)
            content = await page.content()
            soup = BeautifulSoup(content, "lxml")

            # Extract product details
            name = soup.find("h1", class_="-fs20 -pts -pbxs")
            price = soup.find("span", class_="-b -ltr -tal -fs24")
            brand = soup.find("a", class_="-prxs")
            rating = soup.find("div", class_="stars")
            reviews_count = soup.find("a", class_="-plxs")
            description = soup.find("div", class_="markup -mhm -pvl -oxa -sc")

            return {
                "url": url,
                "nom_du_produit": name.get_text(strip=True) if name else "N/A",
                "prix": price.get_text(strip=True) if price else "N/A",
                "marque": brand.get_text(strip=True) if brand else "N/A",
                "note": rating.get_text(strip=True) if rating else "N/A",
                "nombre_avis": reviews_count.get_text(strip=True) if reviews_count else "0",
                "description": description.get_text(strip=True) if description else "N/A",
                "date_scraping": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.warning(f"⚠️ Échec de la récupération des détails pour {url}: {e}")
            raise

    async def fetch_product_details(self, links: List[str]):
        """Fetch details for all products and save to S3."""
        results = []
        failed_urls = []
        page = None

        try:
            page = await self.context.new_page()

            for idx, url in enumerate(links):
                logger.info(f"🔄 Détail produit {idx+1}/{len(links)} : {url}")
                try:
                    product_detail = await self.fetch_single_product_detail(page, url)
                    results.append(product_detail)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"❌ Échec après {MAX_RETRIES} tentatives pour {url}: {e}")
                    failed_urls.append(url)
                    continue

            if results:
                df = pd.DataFrame(results)
                df["score"] = range(len(results), 0, -1)
                
                # Save to parquet and upload to S3
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
                
        finally:
            if page:
                await page.close()

async def main():
    scraper = JumiaScraper()
    try:
        await scraper.init_browser()
        links = await scraper.fetch_product_links()
        if links:
            await scraper.fetch_product_details(links)
    finally:
        await scraper.close_browser()
    logger.info("🏁 Script terminé")

if __name__ == "__main__":
    asyncio.run(main())

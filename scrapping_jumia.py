import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import os
import time
from concurrent.futures import ThreadPoolExecutor
import io
import random

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration AWS
AWS_REGION = 'us-east-1'
BUCKET_NAME = 'msde-pfe-blobs'
S3_PREFIX = 'jumia'

# Configuration des timeouts
PAGE_TIMEOUT = 5000  # 5 secondes
NAVIGATION_TIMEOUT = 180000  # 180 secondes
SELECTOR_TIMEOUT = 120000  # 120 secondes

class JumiaScraper:
    def __init__(self):
        self.browser: Browser = None
        self.products: List[Dict] = []
        self.base_url = "https://www.jumia.ma/beaute-hygiene-sante/"
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.start_time = time.time()
        logger.info("🚀 Initialisation du scraper Jumia")

    def log_time(self, action: str):
        """Log the time taken for an action."""
        current_time = time.time()
        elapsed = current_time - self.start_time
        logger.info(f"⏱️ {action}: {elapsed:.2f} secondes")

    async def init_browser(self):
        """Initialize the browser."""
        try:
            logger.info("🌐 Démarrage du navigateur...")
            start = time.time()
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu'
                ]
            )
            elapsed = time.time() - start
            logger.info(f"✅ Navigateur démarré avec succès en {elapsed:.2f} secondes")
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage du navigateur: {str(e)}")
            raise

    async def close_browser(self):
        """Close the browser."""
        if self.browser:
            try:
                logger.info("🔒 Fermeture du navigateur...")
                start = time.time()
                await self.browser.close()
                elapsed = time.time() - start
                logger.info(f"✅ Navigateur fermé avec succès en {elapsed:.2f} secondes")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la fermeture du navigateur: {str(e)}")

    def upload_to_s3_buffer(self, buffer, filename: str, content_type: str = 'application/octet-stream') -> bool:
        """Upload a buffer to S3 bucket."""
        try:
            logger.info(f"📤 Début de l'upload vers S3 (buffer): {filename}")
            start = time.time()
            
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=BUCKET_NAME)
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    logger.error(f"❌ Le bucket S3 '{BUCKET_NAME}' n'existe pas")
                    return False
                elif error_code == '403':
                    logger.error(f"❌ Accès refusé au bucket S3 '{BUCKET_NAME}'")
                    return False
                else:
                    raise
            
            s3_key = f"{S3_PREFIX}/{filename}"
            buffer.seek(0)
            self.s3_client.upload_fileobj(
                buffer,
                BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": content_type}
            )
            elapsed = time.time() - start
            logger.info(f"✅ Upload S3 réussi: s3://{BUCKET_NAME}/{s3_key} en {elapsed:.2f} secondes")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'upload S3: {str(e)}")
            return False

    async def get_product_links(self, page: Page, max_pages: int = 50) -> List[str]:
        """Get all product links from the category pages."""
        all_links = set()
        current_page = 1
        
        while current_page <= max_pages:
            try:
                page_url = f"{self.base_url}?page={current_page}" if current_page > 1 else self.base_url
                logger.info(f"🌐 Navigation vers la page {current_page}: {page_url}")
                
                await page.goto(page_url, wait_until='networkidle')
                await page.wait_for_selector('a.core[href*=".html"]', timeout=SELECTOR_TIMEOUT)
                
                # Extract all product links
                links = await page.evaluate('''() => {
                    const links = new Set();
                    document.querySelectorAll('a.core[href*=".html"]').forEach(a => {
                        let href = a.href;
                        if (!href.startsWith('http')) {
                            href = 'https://www.jumia.ma' + href;
                        }
                        links.add(href);
                    });
                    return Array.from(links);
                }''')
                
                if not links:
                    logger.info("Fin de la pagination.")
                    break
                
                before = len(all_links)
                all_links.update(links)
                logger.info(f"📦 Liens trouvés cette page : {len(links)} | Total cumulé : {len(all_links)} (+{len(all_links)-before})")
                
                # Random delay between requests
                await asyncio.sleep(random.uniform(0.2, 0.7))
                current_page += 1
                
            except TimeoutError:
                logger.warning(f"⚠️ Timeout sur la page {current_page}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur sur la page {current_page}: {str(e)}")
                continue
        
        return list(sorted(all_links))

    async def get_product_details(self, page: Page, url: str) -> Dict:
        """Get product details from a single product page."""
        try:
            logger.info(f"🔍 Scraping du produit : {url}")
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_selector('h1.-fs20', timeout=SELECTOR_TIMEOUT)
            
            # Extract product details
            product_data = await page.evaluate('''() => {
                const getText = (selector) => {
                    const el = document.querySelector(selector);
                    return el ? el.textContent.trim() : 'Non disponible';
                };
                
                const img = document.querySelector('#imgs img');
                return {
                    designation: getText('h1.-fs20.-pts.-pbxs'),
                    marque: getText('#jm > main > div:nth-child(1) > section > div > div.col10 > div.-phs > div.-pvxs'),
                    prix_vente: getText('span.-b.-ubpt.-tal.-fs24.-prxs'),
                    prix_barre: getText('span.-tal.-gy5.-lthr.-fs16.-pvxs.-ubpt'),
                    image_url: img ? img.src : 'Non disponible',
                    lien_produit: window.location.href,
                    date_extraction: new Date().toISOString()
                };
            }''')
            
            logger.info(f"✅ Produit scrapé : {product_data['designation']}")
            return product_data
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du scraping du produit {url}: {str(e)}")
            return None

    async def scrape_products(self):
        """Main scraping function."""
        page = None
        try:
            logger.info("🔄 Démarrage du scraping des produits...")
            start_total = time.time()
            
            page = await self.browser.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
            
            # Set user agent
            await page.set_extra_http_headers({
                "User-Agent": self.user_agent
            })
            
            # Get all product links
            links = await self.get_product_links(page)
            logger.info(f"📦 Total des liens trouvés : {len(links)}")
            
            # Process each product
            for index, link in enumerate(links):
                try:
                    product_data = await self.get_product_details(page, link)
                    if product_data:
                        # Calculate score (highest for first product, lowest for last)
                        product_data['score'] = len(links) - index
                        self.products.append(product_data)
                except Exception as e:
                    logger.error(f"❌ Erreur lors du traitement du produit {index + 1}: {str(e)}")
                    continue
            
            if not self.products:
                logger.warning("⚠️ Aucun produit n'a été scrapé")
                return
            
            # Create DataFrame and save to CSV
            df = pd.DataFrame(self.products)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f'jumia_products_{timestamp}.csv'
            
            # Save to CSV buffer
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8')
            
            # Convert to bytes for S3 upload
            csv_bytes_buffer = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
            
            # Upload to S3
            if self.upload_to_s3_buffer(csv_bytes_buffer, csv_filename, content_type='text/csv'):
                logger.info("✅ Upload CSV S3 terminé avec succès")
            else:
                logger.error("❌ Échec de l'upload CSV S3")
            
            # Cleanup
            csv_buffer.close()
            csv_bytes_buffer.close()
            
            elapsed_total = time.time() - start_total
            logger.info(f"⏱️ Temps total d'exécution: {elapsed_total:.2f} secondes")
            
        except Exception as e:
            logger.error(f"❌ Erreur pendant le scraping: {str(e)}")
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la fermeture de la page: {str(e)}")

async def main():
    logger.info("🚀 Démarrage du script de scraping Jumia")
    scraper = JumiaScraper()
    try:
        await scraper.init_browser()
        await scraper.scrape_products()
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {str(e)}")
    finally:
        await scraper.close_browser()
        logger.info("🏁 Fin du script de scraping")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Script interrompu par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {str(e)}")
    finally:
        # Cleanup event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()
            if not loop.is_closed():
                loop.close()
        except Exception as e:
            logger.error(f"❌ Erreur lors de la fermeture de l'event loop: {str(e)}")

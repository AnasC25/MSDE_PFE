import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor
import io
import time

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
S3_PREFIX = 'cotepara'

# Configuration des timeouts
PAGE_TIMEOUT = 30000  # 30 secondes
NAVIGATION_TIMEOUT = 60000  # 60 secondes
SELECTOR_TIMEOUT = 30000  # 30 secondes

class CoteParaScraper:
    def __init__(self):
        self.browser: Browser = None
        self.context = None
        self.products: List[Dict] = []
        self.base_url = "https://cotepara.ma/best-sellers/1/"
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.start_time = time.time()
        logger.info("🚀 Initialisation du scraper CotePara")

    def log_time(self, action: str):
        """Log the time taken for an action."""
        current_time = time.time()
        elapsed = current_time - self.start_time
        logger.info(f"⏱️ {action}: {elapsed:.2f} secondes")

    async def init_browser(self):
        """Initialize the browser and context."""
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
            # Create a new context with specific settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.user_agent,
                ignore_https_errors=True
            )
            elapsed = time.time() - start
            logger.info(f"✅ Navigateur démarré avec succès en {elapsed:.2f} secondes")
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage du navigateur: {str(e)}")
            raise

    async def close_browser(self):
        """Close the browser and context."""
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                logger.error(f"❌ Erreur lors de la fermeture du contexte: {str(e)}")
        
        if self.browser:
            try:
                logger.info("🔒 Fermeture du navigateur...")
                start = time.time()
                await self.browser.close()
                elapsed = time.time() - start
                logger.info(f"✅ Navigateur fermé avec succès en {elapsed:.2f} secondes")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la fermeture du navigateur: {str(e)}")

    def upload_to_s3(self, file_path: str) -> bool:
        """Upload a file to S3 bucket."""
        try:
            logger.info(f"📤 Début de l'upload vers S3: {file_path}")
            start = time.time()
            
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=BUCKET_NAME)
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    logger.error(f"❌ Le bucket S3 '{BUCKET_NAME}' n'existe pas. Veuillez créer le bucket ou vérifier le nom.")
                    return False
                elif error_code == '403':
                    logger.error(f"❌ Accès refusé au bucket S3 '{BUCKET_NAME}'. Vérifiez vos permissions AWS.")
                    return False
                else:
                    raise
            
            # Get the filename from the path
            filename = file_path.split('/')[-1]
            
            # Construct the S3 key
            s3_key = f"{S3_PREFIX}/{filename}/eventdate:{datetime.now().strftime('%Y-%m-%d')}"
            
            # Upload the file
            self.s3_client.upload_file(
                file_path,
                BUCKET_NAME,
                s3_key
            )
            
            elapsed = time.time() - start
            logger.info(f"✅ Upload S3 réussi: s3://{BUCKET_NAME}/{s3_key} en {elapsed:.2f} secondes")
            return True
            
        except ClientError as e:
            logger.error(f"❌ Erreur lors de l'upload S3: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur inattendue lors de l'upload S3: {str(e)}")
            return False

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
                    logger.error(f"❌ Le bucket S3 '{BUCKET_NAME}' n'existe pas. Veuillez créer le bucket ou vérifier le nom.")
                    return False
                elif error_code == '403':
                    logger.error(f"❌ Accès refusé au bucket S3 '{BUCKET_NAME}'. Vérifiez vos permissions AWS.")
                    return False
                else:
                    raise
            s3_key = f"{S3_PREFIX}/{filename}/eventdate:{datetime.now().strftime('%Y-%m-%d')}"
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
        except ClientError as e:
            logger.error(f"❌ Erreur lors de l'upload S3: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur inattendue lors de l'upload S3: {str(e)}")
            return False

    async def scrape_products(self):
        """Scrape products from the page."""
        page = None
        try:
            logger.info("🔄 Démarrage du scraping des produits...")
            start_total = time.time()
            
            # Create a new page from the context
            page = await self.context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
            
            logger.info(f"🌐 Navigation vers {self.base_url}")
            try:
                start_nav = time.time()
                response = await page.goto(
                    self.base_url,
                    wait_until='domcontentloaded',
                    timeout=NAVIGATION_TIMEOUT
                )
                elapsed_nav = time.time() - start_nav
                logger.info(f"⏱️ Navigation vers la page: {elapsed_nav:.2f} secondes")
                
                if not response:
                    raise Exception("Failed to get response from page")
                if response.status != 200:
                    raise Exception(f"Page returned status code {response.status}")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la navigation: {str(e)}")
                return
            
            logger.info("⏳ Attente du chargement des produits...")
            
            # Wait for the page to be fully loaded
            await page.wait_for_load_state('networkidle', timeout=SELECTOR_TIMEOUT)
            
            # Wait for products with retry mechanism
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    await page.wait_for_selector('.porto-tb-item.product', timeout=SELECTOR_TIMEOUT)
                    break
                except TimeoutError:
                    if attempt < max_attempts - 1:
                        logger.warning(f"⚠️ Tentative {attempt + 1}/{max_attempts} échouée, nouvelle tentative...")
                        await page.reload(wait_until='domcontentloaded')
                        continue
                    else:
                        raise
            
            # Get all products
            products = await page.query_selector_all('.porto-tb-item.product')
            logger.info(f"📦 {len(products)} produits trouvés sur la page")
            
            if not products:
                logger.warning("⚠️ Aucun produit trouvé sur la page")
                return
            
            # Process each product
            start_scraping = time.time()
            for index, product in enumerate(products):
                try:
                    logger.info(f"🔄 Traitement du produit {index + 1}/{len(products)}")
                    start_product = time.time()
                    
                    # Extract product data with retry
                    for attempt in range(3):
                        try:
                            title = await product.query_selector('.porto-heading a')
                            price = await product.query_selector('.tb-woo-price ins .woocommerce-Price-amount')
                            old_price = await product.query_selector('.tb-woo-price del .woocommerce-Price-amount')
                            discount = await product.query_selector('.labels .onsale')
                            
                            # Get text content
                            title_text = await title.text_content() if title else "N/A"
                            price_text = await price.text_content() if price else "N/A"
                            old_price_text = await old_price.text_content() if old_price else "N/A"
                            discount_text = await discount.text_content() if discount else "N/A"
                            
                            # Calculate score (highest for first product, lowest for last)
                            score = len(products) - index
                            
                            # Add to products list
                            self.products.append({
                                "title": title_text.strip(),
                                "price": price_text.strip(),
                                "old_price": old_price_text.strip(),
                                "discount": discount_text.strip(),
                                "score": score
                            })
                            
                            elapsed_product = time.time() - start_product
                            logger.info(f"✅ Produit scrapé: {title_text.strip()} en {elapsed_product:.2f} secondes")
                            logger.info(f"💰 Prix: {price_text.strip()}")
                            if old_price_text.strip() != "N/A":
                                logger.info(f"💲 Prix barré: {old_price_text.strip()}")
                            if discount_text.strip() != "N/A":
                                logger.info(f"🎯 Réduction: {discount_text.strip()}")
                            logger.info(f"⭐ Score: {score}")
                            logger.info("➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖")
                            break
                            
                        except TimeoutError:
                            if attempt < 2:
                                logger.warning(f"⚠️ Timeout lors de l'extraction du produit {index + 1}, nouvelle tentative...")
                                await asyncio.sleep(2)
                                continue
                            else:
                                raise
                    
                except Exception as e:
                    logger.error(f"❌ Erreur lors du scraping du produit {index + 1}: {str(e)}")
                    continue
            
            elapsed_scraping = time.time() - start_scraping
            logger.info(f"⏱️ Temps total de scraping des produits: {elapsed_scraping:.2f} secondes")
            
            if not self.products:
                logger.warning("⚠️ Aucun produit n'a été scrapé")
                return
            
            # Création du DataFrame pandas
            logger.info("📝 Création du DataFrame pandas...")
            start_df = time.time()
            df = pd.DataFrame(self.products)
            elapsed_df = time.time() - start_df
            logger.info(f"⏱️ Création du DataFrame: {elapsed_df:.2f} secondes")
            
            # Génération du nom de fichier avec timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            parquet_filename = f'cotepara_products_{timestamp}.parquet'
            
            # Conversion en buffer Parquet
            logger.info("📤 Préparation de l'upload vers S3...")
            parquet_buffer = io.BytesIO()
            
            # Écriture du DataFrame en Parquet dans le buffer
            table = pa.Table.from_pandas(df)
            pq.write_table(table, parquet_buffer)
            
            # Upload direct vers S3 depuis la mémoire
            if self.upload_to_s3_buffer(parquet_buffer, parquet_filename, content_type='application/octet-stream'):
                logger.info("✅ Upload Parquet S3 terminé avec succès")
            else:
                logger.error("❌ Échec de l'upload Parquet S3")
            
            # Nettoyage du buffer
            parquet_buffer.close()
            
            elapsed_total = time.time() - start_total
            logger.info(f"⏱️ Temps total d'exécution: {elapsed_total:.2f} secondes")
            
        except TimeoutError as e:
            logger.error(f"❌ Timeout pendant le scraping: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Erreur pendant le scraping: {str(e)}")
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la fermeture de la page: {str(e)}")

async def main():
    logger.info("🚀 Démarrage du script de scraping CotePara")
    scraper = CoteParaScraper()
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

def scrape_products_batch(links):
    driver = open_browser()
    results = []
    try:
        for link in links:
            result = get_product_details(link, driver)
            if result:
                results.append(result)
    finally:
        driver.quit()
    return results

def chunked(iterable, n):
    """Découpe une liste en sous-listes de taille n."""
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]

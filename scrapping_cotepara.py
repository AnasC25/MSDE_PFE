import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
import boto3
from botocore.exceptions import ClientError

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration AWS
AWS_REGION = 'eu-west-3'
BUCKET_NAME = 'msde-pfe-scraping'
S3_PREFIX = 'cotepara'

# Configuration des timeouts
PAGE_TIMEOUT = 120000  # 120 secondes
NAVIGATION_TIMEOUT = 120000  # 120 secondes
SELECTOR_TIMEOUT = 90000  # 90 secondes

class CoteParaScraper:
    def __init__(self):
        self.browser: Browser = None
        self.products: List[Dict] = []
        self.base_url = "https://cotepara.ma/best-sellers/1/"
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        logger.info("🚀 Initialisation du scraper CotePara")

    async def init_browser(self):
        """Initialize the browser."""
        try:
            logger.info("🌐 Démarrage du navigateur...")
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
            logger.info("✅ Navigateur démarré avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage du navigateur: {str(e)}")
            raise

    async def close_browser(self):
        """Close the browser."""
        if self.browser:
            try:
                logger.info("🔒 Fermeture du navigateur...")
                await self.browser.close()
                logger.info("✅ Navigateur fermé avec succès")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la fermeture du navigateur: {str(e)}")

    def upload_to_s3(self, file_path: str) -> bool:
        """Upload a file to S3 bucket."""
        try:
            logger.info(f"📤 Début de l'upload vers S3: {file_path}")
            
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
            s3_key = f"{S3_PREFIX}/{filename}"
            
            # Upload the file
            self.s3_client.upload_file(
                file_path,
                BUCKET_NAME,
                s3_key
            )
            
            logger.info(f"✅ Upload S3 réussi: s3://{BUCKET_NAME}/{s3_key}")
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
            page = await self.browser.new_page()
            page.set_default_timeout(PAGE_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
            
            logger.info(f"🌐 Navigation vers {self.base_url}")
            await page.goto(self.base_url, wait_until='networkidle')
            
            logger.info("⏳ Attente du chargement des produits...")
            # Attendre que la page soit complètement chargée
            await page.wait_for_load_state('networkidle')
            
            # Attendre que les produits soient visibles
            await page.wait_for_selector('.porto-tb-item.product', timeout=SELECTOR_TIMEOUT)
            
            # Get all products
            products = await page.query_selector_all('.porto-tb-item.product')
            logger.info(f"📦 {len(products)} produits trouvés sur la page")
            
            if not products:
                logger.warning("⚠️ Aucun produit trouvé sur la page")
                return
            
            # Process each product
            for index, product in enumerate(products):
                try:
                    logger.info(f"🔄 Traitement du produit {index + 1}/{len(products)}")
                    
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
                            
                            logger.info(f"✅ Produit scrapé: {title_text.strip()}")
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
            
            if not self.products:
                logger.warning("⚠️ Aucun produit n'a été scrapé")
                return
            
            # Save to JSON file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"cotepara_products_{timestamp}.json"
            
            logger.info(f"💾 Sauvegarde des données dans {filename}")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ {len(self.products)} produits sauvegardés avec succès")
            
            # Upload to S3
            logger.info("📤 Début de l'upload vers S3...")
            if self.upload_to_s3(filename):
                logger.info("✅ Upload S3 terminé avec succès")
            else:
                logger.error("❌ Échec de l'upload S3")
            
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
    finally:
        # Nettoyage de l'event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()
            if not loop.is_closed():
                loop.close()
        except Exception as e:
            logger.error(f"❌ Erreur lors de la fermeture de l'event loop: {str(e)}")

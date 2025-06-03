import asyncio
import csv
import re
import random
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError, Error as PlaywrightError
from typing import List, Dict, Optional
import logging
from asyncio import Semaphore
import time
import boto3
import os
from botocore.exceptions import ClientError

# Configuration du système de logs pour afficher des messages d'information et d'erreur
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes de configuration du script
FILENAME = "produits_Scrapper.csv"  # Nom du fichier CSV de sortie
MAX_CONCURRENT_REQUESTS = 30  # Nombre maximum de requêtes simultanées
MAX_RETRIES = 8  # Nombre de tentatives en cas d'échec réseau
TIMEOUT = 90000  # Timeout général en millisecondes
PAGE_LOAD_TIMEOUT = 60000  # Timeout pour le chargement d'une page
RETRY_DELAY = 10  # Délai de base entre les tentatives (secondes)
BATCH_SIZE = 10 # Nombre de produits traités en parallèle

# Configuration AWS S3
AWS_ACCESS_KEY = "VOTRE_ACCESS_KEY"  # À remplacer par votre clé d'accès
AWS_SECRET_KEY = "VOTRE_SECRET_KEY"  # À remplacer par votre clé secrète
AWS_REGION = "eu-west-3"  # Région AWS (Paris par défaut)
S3_BUCKET_NAME = "VOTRE_BUCKET_NAME"  # À remplacer par le nom de votre bucket

def upload_to_s3(file_path: str, bucket: str, object_name: str = None) -> bool:
    """
    Upload un fichier vers un bucket S3.
    
    Args:
        file_path: Chemin du fichier à uploader
        bucket: Nom du bucket S3
        object_name: Nom de l'objet dans S3 (si None, utilise le nom du fichier)
    
    Returns:
        bool: True si l'upload a réussi, False sinon
    """
    if object_name is None:
        object_name = os.path.basename(file_path)

    # Création du client S3
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    )

    try:
        s3_client.upload_file(file_path, bucket, object_name)
        logger.info(f"✅ Fichier {file_path} uploadé avec succès vers s3://{bucket}/{object_name}")
        return True
    except ClientError as e:
        logger.error(f"❌ Erreur lors de l'upload vers S3: {e}")
        return False

def clean_price(price_text: str) -> float:
    """
    Nettoie et convertit un texte de prix en float.
    Ex : '199,99 د.م' -> 199.99
    Retourne 0.0 si le texte n'est pas convertible.
    """
    if not price_text:
        return 0.0
    price_text = price_text.replace("د.م", "").replace("\u200f", "").strip()
    cleaned = re.sub(r"[^\d,\.]", "", price_text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def save_to_csv(products: List[Dict], filename: str) -> None:
    """
    Sauvegarde la liste des produits dans un fichier CSV et l'upload vers S3.
    """
    try:
        # Sauvegarde locale
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "title", "description", "normal_price", "promo_price",
                "price_value", "image_url", "product_link", "score"
            ])
            writer.writeheader()
            writer.writerows(products)
        logger.info(f"✅ Successfully saved {len(products)} products to {filename}")

        # Upload vers S3
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_object_name = f"products_{timestamp}.csv"
        if upload_to_s3(filename, S3_BUCKET_NAME, s3_object_name):
            logger.info(f"✅ Fichier uploadé vers S3 avec succès: {s3_object_name}")
        else:
            logger.error("❌ Échec de l'upload vers S3")

    except Exception as e:
        logger.error(f"❌ Error saving to CSV: {e}")

async def wait_for_network_idle(page, timeout=10000):
    """
    Attend que le réseau soit inactif (plus de chargement de ressources).
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except TimeoutError:
        logger.warning("Network idle timeout, continuing anyway")

async def scrape_product_detail(page, url: str, semaphore: Semaphore, total_products: int, current_index: int) -> Optional[Dict]:
    """
    Récupère les détails d'un produit à partir de son URL.
    Utilise un sémaphore pour limiter le nombre de requêtes simultanées.
    Gère les erreurs réseau et les retries.
    """
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                # Petite pause aléatoire pour ne pas surcharger le serveur
                await asyncio.sleep(random.uniform(2, 5))
                
                # Navigation vers la page produit avec gestion des erreurs réseau
                try:
                    response = await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    if not response:
                        raise PlaywrightError("No response received")
                    if response.status >= 400:
                        raise PlaywrightError(f"HTTP {response.status}")
                    await wait_for_network_idle(page)
                except PlaywrightError as e:
                    # Gestion des erreurs réseau courantes
                    if any(err in str(e) for err in ["net::ERR_ABORTED", "net::ERR_CONNECTION_RESET", "net::ERR_CONNECTION_TIMED_OUT"]):
                        logger.warning(f"Network error on attempt {attempt + 1}/{MAX_RETRIES} for {url}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                            continue
                    raise

                # Attente de l'élément titre du produit
                try:
                    await page.wait_for_selector(".product_title", timeout=15000)
                except TimeoutError:
                    logger.warning(f"Timeout waiting for product title on {url}")
                    if attempt < MAX_RETRIES - 1:
                        continue
                    return None

                # Récupération des différents éléments de la page produit
                try:
                    title_elem, description_elem, normal_price_elem, promo_price_elem, image_elem = await asyncio.gather(
                        page.query_selector(".product_title"),
                        page.query_selector(".woocommerce-Tabs-panel--description"),
                        page.query_selector(".price del .woocommerce-Price-amount"),
                        page.query_selector(".price ins .woocommerce-Price-amount"),
                        page.query_selector(".woocommerce-product-gallery__image img"),
                        return_exceptions=True
                    )
                except Exception as e:
                    logger.error(f"Error querying elements: {e}")
                    if attempt < MAX_RETRIES - 1:
                        continue
                    return None

                # Extraction du texte de chaque élément (ou chaîne vide si absent)
                title = await title_elem.inner_text() if title_elem and not isinstance(title_elem, Exception) else ""
                description = await description_elem.inner_text() if description_elem and not isinstance(description_elem, Exception) else ""

                # Gestion des prix (normal et promo)
                if normal_price_elem and promo_price_elem and not isinstance(normal_price_elem, Exception) and not isinstance(promo_price_elem, Exception):
                    normal_price_text = await normal_price_elem.inner_text()
                    promo_price_text = await promo_price_elem.inner_text()
                else:
                    price_elem = await page.query_selector(".price .woocommerce-Price-amount")
                    price_text = await price_elem.inner_text() if price_elem else ""
                    normal_price_text = price_text
                    promo_price_text = ""

                # Nettoyage des prix
                normal_price = normal_price_text.replace("د.م", "DHS").replace("\u200f", "").strip()
                promo_price = promo_price_text.replace("د.م", "DHS").replace("\u200f", "").strip()
                price_value = clean_price(promo_price_text if promo_price_text else normal_price_text)
                image_url = await image_elem.get_attribute("src") if image_elem and not isinstance(image_elem, Exception) else ""

                # Calcul du score (le premier produit scrappé a le score le plus élevé)
                score = total_products - current_index

                # Retourne un dictionnaire avec toutes les infos du produit
                return {
                    "title": title.strip(),
                    "description": description.strip(),
                    "normal_price": normal_price,
                    "promo_price": promo_price,
                    "price_value": price_value,
                    "image_url": image_url.strip(),
                    "product_link": url,
                    "score": score
                }

            except TimeoutError:
                logger.warning(f"Timeout on {url} (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return None
            except Exception as e:
                logger.error(f"❌ Error on {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return None

async def scrape_all_products(start_page: int = 1, max_pages: Optional[int] = None) -> List[Dict]:
    """
    Fonction principale qui parcourt toutes les pages de la boutique,
    récupère les liens des produits et lance le scraping des détails pour chaque produit.
    """
    all_products = []  # Liste de tous les produits scrappés
    semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)  # Limite le nombre de requêtes simultanées
    total_products_scraped = 0  # Compteur total

    async with async_playwright() as p:
        # Lancement du navigateur avec des options pour le scraping
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-gpu',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-extensions',
                '--disable-component-extensions-with-background-pages',
                '--disable-default-apps',
                '--mute-audio',
                '--no-default-browser-check',
                '--no-first-run',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-client-side-phishing-detection',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-renderer-backgrounding',
                '--disable-sync',
                '--force-color-profile=srgb',
                '--metrics-recording-only',
                '--password-store=basic'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            ignore_https_errors=True,
            bypass_csp=True
        )
        
        # Définition du timeout par défaut pour toutes les actions
        context.set_default_timeout(TIMEOUT)
        
        page = await context.new_page()
        
        # Interception des requêtes (ici on laisse tout passer)
        await page.route("**/*", lambda route: route.continue_())

        page_number = start_page
        while True:
            if max_pages and page_number > max_pages:
                break

            url = f"https://cotepara.ma/best-sellers/{page_number}/"
            logger.info(f"📄 Processing page {page_number}: {url}")
            
            # Tentatives multiples pour charger la page de produits
            for attempt in range(MAX_RETRIES):
                try:
                    response = await page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    if not response:
                        raise PlaywrightError("No response received")
                    if response.status >= 400:
                        raise PlaywrightError(f"HTTP {response.status}")
                    await wait_for_network_idle(page)
                    await page.wait_for_selector("a.porto-tb-link", timeout=15000)
                    break
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        logger.error(f"⛔ Failed to load page {page_number} after {MAX_RETRIES} attempts: {e}")
                        return all_products
                    logger.warning(f"Retrying page {page_number} (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            # Récupération des liens de tous les produits sur la page
            links = await page.query_selector_all("a.porto-tb-link")
            product_links = [await link.get_attribute("href") for link in links if await link.get_attribute("href")]

            if not product_links:
                logger.info("✅ No more products found. Finishing.")
                break

            # Scraping des produits par petits lots pour éviter de surcharger le serveur
            for i in range(0, len(product_links), BATCH_SIZE):
                batch_links = product_links[i:i + BATCH_SIZE]
                tasks = [
                    scrape_product_detail(
                        page, 
                        link, 
                        semaphore, 
                        len(product_links), 
                        i + idx
                    ) for idx, link in enumerate(batch_links)
                ]
                results = await asyncio.gather(*tasks)
                
                # Ajout des produits valides à la liste globale
                valid_products = [p for p in results if p is not None]
                all_products.extend(valid_products)
                total_products_scraped += len(valid_products)

                logger.info(f"🧺 Page {page_number}: Found {len(valid_products)} products in batch. Total: {total_products_scraped}")
                
                # Sauvegarde après chaque lot
                save_to_csv(all_products, FILENAME)
                
                # Pause entre les lots
                await asyncio.sleep(random.uniform(3.0, 6.0))

            page_number += 1
            # Pause entre les pages
            await asyncio.sleep(random.uniform(5.0, 8.0))

        await context.close()
        await browser.close()
        logger.info("✅ Scraping completed successfully")
        return all_products

async def main():
    """
    Point d'entrée du script : lance le scraping à partir de la première page.
    """
    try:
        await scrape_all_products(start_page=1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    # Exécute le script principal si ce fichier est lancé directement
    asyncio.run(main())

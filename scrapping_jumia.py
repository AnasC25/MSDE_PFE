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
import os
import logging
import tempfile
import boto3
from botocore.config import Config
from selenium.common.exceptions import TimeoutException

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration des dossiers
OUTPUT_DIR = "jumia_products"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Configuration S3
S3_CONFIG = Config(max_pool_connections=50)
s3_client = boto3.client("s3", config=S3_CONFIG)
BUCKET_NAME = "msde-pfe-blobs"

def open_browser():
    """Initialise et configure le navigateur Chrome."""
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
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument(f'--user-data-dir={tempfile.mkdtemp()}')

        # Ajout d'experimental options pour éviter la détection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = Service("/usr/local/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Modification des propriétés du navigateur pour éviter la détection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        logger.error(f"Erreur navigateur : {e}")
        raise

def get_product_links(browser, category_url):
    """Récupère les liens des produits d'une catégorie."""
    try:
        logger.info(f"Récupération des liens depuis : {category_url}")
        all_product_links = set()  # Pour stocker tous les liens de toutes les pages
        current_page = 1
        max_pages = 50  # Limite de sécurité pour éviter une boucle infinie
        
        while current_page <= max_pages:
            # Construction de l'URL avec la pagination
            page_url = f"{category_url}?page={current_page}" if current_page > 1 else category_url
            logger.info(f"Traitement de la page {current_page} : {page_url}")
            
            browser.get(page_url)
            time.sleep(5)  # Augmentation du temps d'attente initial

            # Attente explicite pour le chargement des produits avec plusieurs tentatives
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Attente pour différents sélecteurs possibles
                    selectors = [
                        (By.CSS_SELECTOR, "article.prd._fb._spn.c-prd.col"),
                        (By.CSS_SELECTOR, "article.prd a.core"),
                        (By.CSS_SELECTOR, "a.core[href*='.html']")
                    ]
                    
                    for selector_type, selector in selectors:
                        try:
                            WebDriverWait(browser, 10).until(
                                EC.presence_of_element_located((selector_type, selector))
                            )
                            logger.info(f"Élément trouvé avec le sélecteur : {selector}")
                            break
                        except TimeoutException:
                            continue
                    break
                except TimeoutException:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Tentative {attempt + 1} échouée, nouvelle tentative...")
                    browser.refresh()
                    time.sleep(5)

            # Scroll progressif pour charger tous les produits
            last_height = browser.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scroll_attempts = 5

            while scroll_attempts < max_scroll_attempts:
                browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = browser.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1

            # Récupération du contenu de la page
            page_source = browser.page_source
            soup = BeautifulSoup(page_source, "lxml")
            
            # Essai de différents sélecteurs pour trouver les liens
            page_product_links = set()  # Pour les liens de la page courante
            
            # Sélecteurs possibles pour les liens de produits
            selectors = [
                "article.prd._fb._spn.c-prd.col a.core",
                "article.prd a.core",
                "a.core[href*='.html']"
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                logger.info(f"Trouvé {len(elements)} éléments avec le sélecteur : {selector}")
                
                for element in elements:
                    if 'href' in element.attrs:
                        href = element['href']
                        # Construction de l'URL complète si nécessaire
                        if not href.startswith('http'):
                            href = f"https://www.jumia.ma{href}"
                        page_product_links.add(href)
                        logger.debug(f"Lien trouvé : {href}")

            # Si aucun lien n'est trouvé sur la page, on essaie l'approche alternative
            if not page_product_links:
                logger.warning("Aucun lien trouvé avec les sélecteurs standards, tentative avec une approche alternative...")
                
                # Recherche de tous les liens dans la page
                all_links = soup.find_all('a', class_='core')
                logger.info(f"Nombre total de liens trouvés dans la page : {len(all_links)}")
                
                for link in all_links:
                    if 'href' in link.attrs:
                        href = link['href']
                        if not href.startswith('http'):
                            href = f"https://www.jumia.ma{href}"
                        page_product_links.add(href)
                        logger.debug(f"Lien trouvé (approche alternative) : {href}")

            # Si aucun lien n'est trouvé sur cette page, on arrête la pagination
            if not page_product_links:
                logger.info(f"Aucun lien trouvé sur la page {current_page}, fin de la pagination.")
                break

            # Ajout des liens de la page courante à l'ensemble total
            all_product_links.update(page_product_links)
            logger.info(f"✅ {len(page_product_links)} liens trouvés sur la page {current_page}")
            logger.info(f"Total cumulé : {len(all_product_links)} liens")

            # Vérification si on a atteint la dernière page
            next_page = soup.select_one("a[aria-label='Page suivante']")
            if not next_page:
                logger.info("Pas de page suivante trouvée, fin de la pagination.")
                break

            # Vérification du numéro de la dernière page
            last_page_link = soup.select_one("a[aria-label='Dernière page']")
            if last_page_link:
                try:
                    last_page = int(last_page_link.text.strip())
                    logger.info(f"Dernière page disponible : {last_page}")
                    if current_page >= last_page:
                        logger.info("Dernière page atteinte.")
                        break
                except ValueError:
                    pass

            current_page += 1
            time.sleep(2)  # Pause entre les pages

        # Conversion en liste et tri
        product_links = list(all_product_links)
        product_links.sort()

        logger.info(f"✅ Total final : {len(product_links)} liens trouvés sur {current_page - 1} pages")
        if len(product_links) > 0:
            logger.info(f"Premier lien trouvé : {product_links[0]}")
            logger.info(f"Dernier lien trouvé : {product_links[-1]}")

        return product_links
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des liens : {e}")
        logger.error(traceback.format_exc())
        return []

def get_product_details(url, browser):
    """Extrait les détails d'un produit."""
    try:
        logger.info(f"Extraction des détails : {url}")
        browser.get(url)
        time.sleep(2)

        WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "-fs20"))
        )

        soup = BeautifulSoup(browser.page_source, "lxml")

        def safe_extract(selector, multiple=False):
            try:
                return soup.select_one(selector).text.strip()
            except:
                return "Non disponible"

        designation = safe_extract("h1.-fs20.-pts.-pbxs")
        marque = safe_extract("#jm > main > div:nth-child(1) > section > div > div.col10 > div.-phs > div.-pvxs")
        prix_vente = safe_extract("span.-b.-ubpt.-tal.-fs24.-prxs")
        prix_barre = safe_extract("span.-tal.-gy5.-lthr.-fs16.-pvxs.-ubpt")
        image = soup.select_one("#imgs img")
        image_url = image['src'] if image and 'src' in image.attrs else "Non disponible"

        return {
            "designation": designation,
            "marque": marque,
            "prix_vente": prix_vente,
            "prix_barre": prix_barre,
            "image_url": image_url,
            "lien_produit": url,
            "date_extraction": datetime.now()
        }
    except Exception as e:
        logger.warning(f"Erreur détails produit : {e}")
        return None

def upload_to_s3(file_path):
    """Upload un fichier vers S3."""
    s3_key = f"jumia/products/{os.path.basename(file_path)}"
    try:
        s3_client.upload_file(file_path, BUCKET_NAME, s3_key)
        logger.info(f"✅ Fichier uploadé : s3://{BUCKET_NAME}/{s3_key}")
    except Exception as e:
        logger.error(f"❌ Upload S3 échoué : {e}")

def main():
    """Fonction principale qui orchestre le processus complet."""
    logger.info("🚀 DÉMARRAGE DU SCRAPING JUMIA")
    
    browser = open_browser()
    try:
        # Liste des catégories à scraper
        categories = [
            "https://www.jumia.ma/beaute-hygiene-sante/"
        ]

        all_products = []
        
        # Pour chaque catégorie
        for category_url in categories:
            # Récupération des liens
            product_links = get_product_links(browser, category_url)
            
            # Pour chaque produit
            for idx, url in enumerate(product_links, 1):
                logger.info(f"Produit {idx}/{len(product_links)}")
                details = get_product_details(url, browser)
                if details:
                    all_products.append(details)
                time.sleep(1.5)

        # Sauvegarde des résultats
        if all_products:
            df_results = pd.DataFrame(all_products)
            # Calcul du score basé sur la date d'extraction (plus récent = meilleur score)
            df_results['score'] = range(len(df_results), 0, -1)
            
            filename = f"jumia_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            df_results.to_excel(filepath, index=False, engine='openpyxl')
            logger.info(f"✅ {len(all_products)} produits sauvegardés : {filepath}")
            
            # Upload vers S3
            upload_to_s3(filepath)
        else:
            logger.warning("Aucun produit n'a été extrait.")

    finally:
        browser.quit()

    logger.info("🏁 FIN DU SCRIPT")

if __name__ == "__main__":
    main()

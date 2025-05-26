# Importation des bibliothèques nécessaires
from selenium import webdriver  # Pour l'automatisation du navigateur
from selenium.webdriver.chrome.service import Service  # Pour le service Chrome
from selenium.webdriver.common.by import By  # Pour localiser les éléments
from selenium.webdriver.support.ui import WebDriverWait  # Pour les attentes explicites
from selenium.webdriver.support import expected_conditions as EC  # Pour les conditions d'attente
from bs4 import BeautifulSoup  # Pour le parsing HTML
import pandas as pd  # Pour la manipulation des données
from datetime import datetime, timedelta  # Pour la gestion des dates
import time  # Pour les délais
import traceback  # Pour le débogage
from webdriver_manager.chrome import ChromeDriverManager  # Pour la gestion du driver Chrome
from selenium.webdriver.chrome.options import Options  # Pour les options Chrome
import re  # Pour les expressions régulières
import os  # Pour la gestion des fichiers
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from functools import lru_cache
import logging

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
MAX_PAGES = 1000  # Nombre élevé pour scraper toutes les pages disponibles
SCROLL_ATTEMPTS = 3
WAIT_TIME = 3
BASE_URL = "https://www.jumia.ma"
SAVE_INTERVAL = 100  # Sauvegarde tous les 100 produits

@lru_cache(maxsize=1)
def get_chrome_options() -> Options:
    """Retourne les options Chrome configurées."""
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return chrome_options

def open_browser() -> webdriver.Chrome:
    """Initialise et configure le navigateur Chrome."""
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=get_chrome_options())
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du navigateur : {e}")
        raise

def scroll_page(browser: webdriver.Chrome) -> None:
    """Défile la page pour charger tout le contenu."""
    last_height = browser.execute_script("return document.body.scrollHeight")
    for _ in range(SCROLL_ATTEMPTS):
        browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = browser.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_product_links(soup: BeautifulSoup) -> List[str]:
    """Extrait les liens des produits d'une page."""
    return [
        f"{BASE_URL}{link['href']}" if not link['href'].startswith('http') else link['href']
        for article in soup.find_all("article", class_="prd")
        if (link := article.find("a", class_="core")) and 'href' in link.attrs
    ]

def process_page(page_url: str, browser: webdriver.Chrome) -> List[str]:
    """Traite une page et extrait les liens des produits."""
    try:
        browser.get(page_url)
        time.sleep(WAIT_TIME)
        
        # Attente des articles avec la classe prd
        WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "prd"))
        )
        
        scroll_page(browser)
        return extract_product_links(BeautifulSoup(browser.page_source, "lxml"))
        
    except Exception as e:
        logger.warning(f"Erreur lors du traitement de la page {page_url}: {e}")
        return []

def save_intermediate_results(product_urls: List[str], page: int) -> None:
    """Sauvegarde les résultats intermédiaires."""
    if len(product_urls) % SAVE_INTERVAL == 0:
        filename = f"jumia_products_links_intermediate_page{page}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_results(product_urls, filename)
        logger.info(f"Sauvegarde intermédiaire effectuée : {len(product_urls)} produits")

def get_product_links(category_url: str) -> List[str]:
    """Récupère les liens des produits d'une catégorie."""
    logger.info("Démarrage de la récupération des liens...")
    browser = open_browser()
    all_links = []
    
    try:
        base_url = re.sub(r'\?page=\d+', '', category_url)
        
        for page in range(1, MAX_PAGES + 1):
            page_url = f"{base_url}?page={page}"
            logger.info(f"Traitement de la page {page}")
            
            if page_links := process_page(page_url, browser):
                all_links.extend(page_links)
                logger.info(f"{len(page_links)} liens récupérés sur la page {page}")
                logger.info(f"Total des liens récupérés : {len(all_links)}")
                
                # Sauvegarde intermédiaire
                save_intermediate_results(all_links, page)
            else:
                logger.info("Fin de la pagination - Plus de produits trouvés")
                break
                
            time.sleep(WAIT_TIME)
            
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des liens : {e}")
        logger.error(traceback.format_exc())
    finally:
        browser.quit()
        
    return all_links

def save_results(product_urls: List[str], filename: str) -> None:
    """Sauvegarde les résultats dans un fichier Excel."""
    # Création d'une liste de scores qui décroît de 1 pour chaque produit
    scores = [len(product_urls) - i for i in range(len(product_urls))]
    
    df = pd.DataFrame({
        "lien_du_produit": product_urls,
        "score": scores
    })
    
    output_path = os.path.join(output_dir, filename)
    df.to_excel(output_path, index=False, engine='openpyxl')
    logger.info(f"{len(product_urls)} liens sauvegardés dans : {output_path}")

def main():
    """Fonction principale du script."""
    logger.info("=== DÉMARRAGE DU SCRAPING ===")
    
    category_url = "https://www.jumia.ma/beaute-hygiene-sante/"
    product_urls = get_product_links(category_url)
    
    if not product_urls:
        logger.error("Aucun lien de produit trouvé. Arrêt du script.")
        return
        
    filename = f"jumia_products_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    save_results(product_urls, filename)
    
    logger.info("=== FIN DU SCRIPT ===")

if __name__ == "__main__":
    main()

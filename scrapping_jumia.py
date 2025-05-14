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

# Création du dossier de sortie pour les fichiers Excel
output_dir = "jumia_product_link"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

def open_browser():
    """
    Initialise et configure le navigateur Chrome avec des options spécifiques
    pour éviter la détection d'automatisation.
    """
    try:
        chrome_options = Options()
        # Option pour exécuter en mode headless (sans interface graphique)
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        # Configuration d'un user-agent standard
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation du navigateur : {e}")
        raise

def get_product_links(category_url):
    """
    Récupère tous les liens des produits d'une catégorie Jumia en parcourant toutes les pages.
    
    Args:
        category_url (str): URL de la catégorie à scraper
        
    Returns:
        list: Liste des URLs des produits
    """
    print("🔄 Démarrage de la récupération des liens...")
    browser = open_browser()
    product_links = []
    
    try:
        # Extraction du numéro de page initial
        page_match = re.search(r'page=(\d+)', category_url)
        current_page = int(page_match.group(1)) if page_match else 1
        
        # Nettoyage de l'URL de base
        base_url = re.sub(r'\?page=\d+', '', category_url)
        
        # Boucle principale de pagination
        while True:
            page_url = f"{base_url}?page={current_page}"
            print(f"\n📄 Traitement de la page {current_page}")
            print(f"🌐 Chargement de la page : {page_url}")
            
            browser.get(page_url)
            time.sleep(5)  # Attente du chargement
            
            # Attente de la présence des produits
            print("⏳ Attente du chargement de la liste des produits...")
            try:
                WebDriverWait(browser, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "prd"))
                )
            except Exception as e:
                print(f"⚠️ Timeout lors de l'attente de la liste des produits : {e}")
                print("Tentative de continuer avec le contenu actuel...")
            
            # Défilement de la page pour charger tous les produits
            print("📜 Défilement de la page pour charger tous les produits...")
            scroll_attempts = 0
            max_scroll_attempts = 10
            last_height = browser.execute_script("return document.body.scrollHeight")
            
            while scroll_attempts < max_scroll_attempts:
                browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                new_height = browser.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1
                print(f"📜 Défilement {scroll_attempts}/{max_scroll_attempts}")
            
            # Extraction des liens des produits
            print("🔍 Recherche des liens des produits...")
            soup = BeautifulSoup(browser.page_source, "lxml")
            product_articles = soup.find_all("article", class_="prd")
            
            if not product_articles:
                print("❌ Aucun produit trouvé sur cette page. Fin de la pagination.")
                break
                
            print(f"📦 Nombre d'articles trouvés sur la page {current_page}: {len(product_articles)}")
            
            # Traitement des articles trouvés
            page_links = []
            for i, article in enumerate(product_articles, 1):
                try:
                    link_element = article.find("a", class_="core")
                    if link_element and 'href' in link_element.attrs:
                        product_url = link_element['href']
                        if not product_url.startswith('http'):
                            product_url = 'https://www.jumia.ma' + product_url
                        page_links.append(product_url)
                        print(f"✅ Lien {i}/{len(product_articles)} récupéré")
                        
                        # Arrêt après 5 produits
                        if len(product_links) + len(page_links) >= 5:
                            page_links = page_links[:5 - len(product_links)]
                            print("🛑 Limitation atteinte : 5 produits récupérés")
                            break
                except Exception as e:
                    print(f"⚠️ Erreur lors de la récupération du lien {i} : {e}")
            
            if not page_links:
                print("❌ Aucun lien trouvé sur cette page. Fin de la pagination.")
                break
                
            # Mise à jour des résultats
            product_links.extend(page_links)
            print(f"✅ {len(page_links)} liens récupérés sur la page {current_page}")
            print(f"📊 Total des liens récupérés jusqu'à présent : {len(product_links)}")
            
            # Arrêt après 5 produits
            if len(product_links) >= 5:
                break
            
            # Préparation pour la page suivante
            next_page = current_page + 1
            time.sleep(3)  # Pause entre les pages
            
            # Sauvegarde intermédiaire tous les 1000 produits
            if len(product_links) % 1000 == 0:
                intermediate_df = pd.DataFrame({
                    "lien_du_produit": product_links,
                    "DateInsertion": datetime.now() + timedelta(hours=4)
                })
                intermediate_filename = os.path.join(output_dir, f"jumia_products_links_intermediate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
                intermediate_df.to_excel(intermediate_filename, index=False, engine='openpyxl')
                print(f"💾 Sauvegarde intermédiaire effectuée : {intermediate_filename}")
            
            current_page = next_page
                
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des liens : {e}")
        print("Détails de l'erreur :")
        print(traceback.format_exc())
    finally:
        print("🔄 Fermeture du navigateur...")
        browser.quit()
        
    print(f"✅ {len(product_links)} liens récupérés au total")
    return product_links

# Point d'entrée du script
category_url = "https://www.jumia.ma/beaute-hygiene-sante/"

# Démarrage du scraping
print("\n=== DÉMARRAGE DU SCRAPING ===")
product_urls = get_product_links(category_url)

# Vérification des résultats
if not product_urls:
    print("❌ Aucun lien de produit trouvé. Arrêt du script.")
    exit()

# Création et sauvegarde du DataFrame final
df = pd.DataFrame({
    "lien_du_produit": product_urls,
    "DateInsertion": datetime.now() + timedelta(hours=4)
})

# Génération du nom de fichier avec horodatage
filename = os.path.join(output_dir, f"jumia_products_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

# Sauvegarde en Excel
df.to_excel(filename, index=False, engine='openpyxl')
print(f"✅ {len(product_urls)} liens sauvegardés dans le fichier : {filename}")

print("\n=== FIN DU SCRIPT ===")

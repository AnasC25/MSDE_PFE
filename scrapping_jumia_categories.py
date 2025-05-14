from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import traceback
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import re
import os

# Création du dossier pour stocker les fichiers
output_dir = "jumia_product_link_categories"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

def open_browser():
    try:
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation du navigateur : {e}")
        raise

def get_product_links(category_url):
    print("🔄 Démarrage de la récupération des liens...")
    browser = open_browser()
    product_links = []
    
    try:
        print(f"🌐 Chargement de la page : {category_url}")
        browser.get(category_url)
        time.sleep(5)
        
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
        
        print("🔍 Recherche des liens des produits...")
        soup = BeautifulSoup(browser.page_source, "lxml")
        products = soup.find_all("article", class_="prd _box _hvr")
        
        if not products:
            print("❌ Aucun produit trouvé sur la page.")
            return []
            
        print(f"📦 Nombre de produits trouvés : {len(products)}")
        
        for i, product in enumerate(products, 1):
            try:
                link_element = product.find("a", class_="core")
                if link_element and 'href' in link_element.attrs:
                    product_url = link_element['href']
                    if not product_url.startswith('http'):
                        product_url = 'https://www.jumia.ma' + product_url
                    product_links.append(product_url)
                    print(f"✅ Lien {i}/{len(products)} récupéré")
            except Exception as e:
                print(f"⚠️ Erreur lors de la récupération du lien {i} : {e}")
        
        print(f"✅ {len(product_links)} liens récupérés au total")
        
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des liens : {e}")
        print("Détails de l'erreur :")
        print(traceback.format_exc())
    finally:
        print("🔄 Fermeture du navigateur...")
        browser.quit()
        
    return product_links

# === DÉBUT DU SCRAPING ===
category_url = "https://www.jumia.ma/beaute-hygiene-sante/"

# Récupération des liens
print("\n=== DÉMARRAGE DU SCRAPING ===")
product_links = get_product_links(category_url)

if not product_links:
    print("❌ Aucun lien trouvé. Arrêt du script.")
    exit()

# Création du DataFrame avec les liens
df = pd.DataFrame({
    "lien_du_produit": product_links,
    "DateInsertion": datetime.now() + timedelta(hours=4)
})

# Génération du nom de fichier avec la date
filename = os.path.join(output_dir, f"jumia_products_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

# Sauvegarde en Excel
df.to_excel(filename, index=False, engine='openpyxl')
print(f"✅ {len(product_links)} liens sauvegardés dans le fichier : {filename}")

print("\n=== FIN DU SCRIPT ===") 
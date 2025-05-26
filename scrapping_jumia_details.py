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
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import os

def open_browser():
    try:
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation du navigateur : {e}")
        raise

def get_product_details(url, browser):
    try:
        print(f"\n🌐 Chargement de la page : {url}")
        browser.get(url)
        time.sleep(3)  # Attente du chargement initial

        # Attendre que la page soit complètement chargée
        WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "-fs20"))
        )

        soup = BeautifulSoup(browser.page_source, "lxml")
        
        # Extraction des données
        designation = soup.find("h1", class_="-fs20 -pts -pbxs")
        designation = designation.text.strip() if designation else "Non disponible"
        
        marque = soup.select_one("#jm > main > div:nth-child(1) > section > div > div.col10 > div.-phs > div.-pvxs")
        marque = marque.text.strip() if marque else "Non disponible"
        
        prix_vente = soup.find("span", class_="-b -ubpt -tal -fs24 -prxs")
        prix_vente = prix_vente.text.strip() if prix_vente else "Non disponible"
        
        prix_barre = soup.find("span", class_="-tal -gy5 -lthr -fs16 -pvxs -ubpt")
        prix_barre = prix_barre.text.strip() if prix_barre else "Non disponible"
        
        image = soup.find("img", class_="#imgs > a > img")
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
        print(f"❌ Erreur lors de l'extraction des détails : {e}")
        print(traceback.format_exc())
        return None
    # finally:
        # browser.quit()

def main():
    print("=== DÉMARRAGE DE L'EXTRACTION DES DÉTAILS ===")
    
    try:
        # Vérifier si le dossier existe
        if not os.path.exists('jumia_product_link'):
            print("❌ Le dossier 'jumia_product_link' n'existe pas")
            return
            
        # Créer le dossier jumia_product_details s'il n'existe pas
        if not os.path.exists('jumia_product_details'):
            print("📁 Création du dossier jumia_product_details...")
            os.makedirs('jumia_product_details')
            print("✅ Dossier créé avec succès")
            
        # Trouver le fichier Excel le plus récent dans le dossier jumia_product_link
        excel_files = [f for f in os.listdir('jumia_product_link') if f.startswith('jumia_products_links_') and f.endswith('.xlsx')]
        if not excel_files:
            print("❌ Aucun fichier Excel trouvé dans le dossier jumia_product_link")
            return
            
        print(f"📁 Fichiers Excel trouvés : {excel_files}")
        
        try:
            # Nouvelle approche pour trouver le fichier le plus récent
            file_paths = [os.path.join('jumia_product_link', f) for f in excel_files]
            latest_file = max(file_paths, key=lambda x: os.path.getmtime(x))
            
            print(f"📁 Lecture du fichier : {latest_file}")
            print(f"📁 Chemin absolu du fichier : {os.path.abspath(latest_file)}")
            
            # Vérifier si le fichier existe
            if not os.path.exists(latest_file):
                print(f"❌ Le fichier {latest_file} n'existe pas")
                return
                
            # Lecture des liens
            print("📖 Tentative de lecture du fichier Excel...")
            df_links = pd.read_excel(latest_file)
            print(f"✅ Fichier Excel lu avec succès. Colonnes trouvées : {df_links.columns.tolist()}")
            
            total_products = len(df_links)
            print(f"📊 Nombre total de produits à traiter : {total_products}")
            
            # Liste pour stocker les résultats
            results = []
            
            # Traitement des produits
            for index, row in df_links.iterrows():
                browser = open_browser()
                url = row['lien_du_produit']
                print(f"\n🔄 Traitement du produit {index + 1}/{total_products}")
                
                product_details = get_product_details(url, browser)
                if product_details:
                    results.append(product_details)
                    print("✅ Détails extraits avec succès")
                else:
                    print("❌ Échec de l'extraction des détails")
                
                time.sleep(2) # Pause entre les requêtes
            
            browser.quit()
                
            # Création du DataFrame final
            if results:
                df_results = pd.DataFrame(results)
                
                # Ajout de la colonne score avec des valeurs décroissantes
                df_results['score'] = range(len(df_results), 0, -1)
                print(f"\n🏆 Scores attribués : Premier produit = {len(df_results)}, Dernier produit = 1")
                
                # Génération du nom de fichier avec la date au format jour_heure_min_sec
                output_filename = f"jumia_product_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                output_path = os.path.join('jumia_product_details', output_filename)
                
                # Sauvegarde en Excel
                df_results.to_excel(output_path, index=False, engine='openpyxl')
                print(f"\n✅ {len(results)} produits sauvegardés dans le fichier : {output_path}")
            else:
                print("\n❌ Aucun détail n'a pu être extrait")
                
        except Exception as e:
            print(f"❌ Erreur lors du traitement du fichier : {e}")
            print(traceback.format_exc())
            
    except Exception as e:
        print(f"❌ Erreur générale : {e}")
        print(traceback.format_exc())
    
    print("\n=== FIN DU SCRIPT ===")

if __name__ == "__main__":
    main() 
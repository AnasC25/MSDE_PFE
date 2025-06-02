# Projet de Scraping Jumia

Ce projet est un outil de web scraping avancé pour extraire des informations de produits depuis le site Jumia. Il permet de collecter les détails des produits et leurs liens, avec une intégration AWS S3 pour le stockage des données.

## Fonctionnalités

- Extraction des liens de produits avec pagination automatique
- Collecte détaillée des informations produits :
  - Désignation
  - Marque
  - Prix de vente
  - Prix barré
  - URL de l'image
  - Date d'extraction
- Sauvegarde automatique des données au format Excel
- Intégration avec AWS S3 pour le stockage des données
- Gestion automatique du navigateur avec Selenium
- Système de logging complet
- Gestion des erreurs et reprise sur erreur
- Sauvegarde intermédiaire des données

## Architecture Technique

Le projet est composé de deux scripts principaux :

1. `scrapping_jumia.py` :
   - Extraction des liens produits
   - Gestion de la pagination
   - Sauvegarde intermédiaire des données
   - Upload vers AWS S3

2. `scrapping_jumia_details.py` :
   - Extraction des détails produits
   - Traitement des données
   - Sauvegarde des résultats
   - Upload vers AWS S3

## Prérequis

- Python 3.x
- Chrome Browser
- ChromeDriver (inclus dans le projet)
- Compte AWS avec accès S3 (pour l'upload des données)

## Installation

1. Clonez ce dépôt :
```bash
git clone https://github.com/AnasC25/MSDE_PFE.git
```

2. Installez les dépendances requises :
```bash
pip install -r requirements.txt
```

3. Configurez vos credentials AWS :
   - Créez un fichier `~/.aws/credentials`
   - Ajoutez vos clés d'accès AWS :
```ini
[default]
aws_access_key_id = VOTRE_ACCESS_KEY
aws_secret_access_key = VOTRE_SECRET_KEY
```

## Structure du Projet

```
.
├── jumia_product_details/    # Dossier contenant les détails des produits
├── jumia_product_link/       # Dossier contenant les liens des produits
├── scrapping_jumia.py        # Script principal pour l'extraction des liens
├── scrapping_jumia_details.py # Script pour l'extraction des détails
├── requirements.txt          # Liste des dépendances Python
└── chromedriver.exe         # Pilote Chrome pour Selenium
```

## Utilisation

1. Pour extraire les liens des produits :
```bash
python scrapping_jumia.py
```
Le script va :
- Parcourir les pages de produits
- Extraire les liens
- Sauvegarder les données localement
- Uploader les données vers S3

2. Pour extraire les détails des produits :
```bash
python scrapping_jumia_details.py
```
Le script va :
- Lire le dernier fichier de liens généré
- Extraire les détails de chaque produit
- Sauvegarder les résultats localement
- Uploader les données vers S3

## Dépendances Principales

- selenium==4.15.2 : Automatisation du navigateur
- beautifulsoup4==4.12.2 : Parsing HTML
- pandas==2.1.3 : Manipulation des données
- openpyxl==3.1.2 : Export Excel
- lxml==4.9.3 : Parser HTML rapide
- webdriver-manager==4.0.1 : Gestion du ChromeDriver
- boto3 : Intégration AWS S3

## Fonctionnalités Avancées

- Gestion automatique du scroll pour charger tous les produits
- Détection automatique de la fin de pagination
- Système de scoring des produits
- Sauvegarde intermédiaire pour éviter la perte de données
- Gestion des timeouts et des erreurs réseau
- User-Agent personnalisé pour éviter la détection
- Logging détaillé des opérations

## Notes

- Assurez-vous d'avoir une connexion Internet stable
- Le script utilise ChromeDriver pour l'automatisation du navigateur
- Les données sont sauvegardées localement et sur AWS S3
- Le script inclut des délais entre les requêtes pour éviter le blocage
- Les données sont sauvegardées dans des dossiers dédiés

## Sécurité

- Les credentials AWS ne doivent pas être partagés
- Le script utilise des options Chrome sécurisées
- Les données sensibles sont gérées de manière sécurisée

## Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails. 
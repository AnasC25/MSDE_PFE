# Projet de Web Scraping E-commerce

Ce projet est un outil de web scraping avancé pour extraire des informations de produits depuis les sites Jumia et CotePara. Il permet de collecter les détails des produits et leurs liens, avec une intégration AWS S3 pour le stockage des données.

## Fonctionnalités

### Scraping Jumia
- Extraction des liens de produits avec pagination automatique
- Collecte détaillée des informations produits :
  - Désignation
  - Marque
  - Prix de vente
  - Prix barré
  - URL de l'image
  - Date d'extraction

### Scraping CotePara
- Scraping asynchrone pour une meilleure performance
- Collecte détaillée des informations produits :
  - Titre
  - Description
  - Prix normal
  - Prix promotionnel
  - URL de l'image
  - Score de popularité
- Gestion avancée des erreurs et retries
- Traitement par lots pour optimiser les performances

## Fonctionnalités Communes
- Sauvegarde automatique des données au format Excel/CSV
- Intégration avec AWS S3 pour le stockage des données
- Système de logging complet
- Gestion des erreurs et reprise sur erreur
- Sauvegarde intermédiaire des données

## Architecture Technique

Le projet est composé de deux scripts principaux :

1. `scrapping_jumia.py` :
   - Utilise Selenium pour l'automatisation
   - Extraction des liens produits
   - Gestion de la pagination
   - Sauvegarde intermédiaire des données
   - Upload vers AWS S3

2. `scrapping_cotepara.py` :
   - Utilise Playwright pour l'automatisation asynchrone
   - Extraction des détails produits
   - Traitement par lots
   - Gestion avancée des erreurs
   - Upload vers AWS S3

## Prérequis

- Python 3.x
- Chrome Browser
- ChromeDriver (pour Jumia)
- Playwright (pour CotePara)
- Compte AWS avec accès S3

## Installation

1. Clonez ce dépôt :
```bash
git clone https://github.com/AnasC25/MSDE_PFE.git
```

2. Installez les dépendances requises :
```bash
pip install -r requirements.txt
```

3. Installez les navigateurs Playwright :
```bash
playwright install
```

4. Configurez vos credentials AWS :
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
├── jumia_products/          # Dossier contenant les données Jumia
├── produits_Scrapper.csv    # Fichier de sortie CotePara
├── scrapping_jumia.py       # Script pour Jumia
├── scrapping_cotepara.py    # Script pour CotePara
├── requirements.txt         # Liste des dépendances Python
└── README.md               # Documentation
```

## Utilisation

### Scraping Jumia
```bash
python scrapping_jumia.py
```
Le script va :
- Parcourir les pages de produits
- Extraire les liens
- Sauvegarder les données localement
- Uploader les données vers S3

### Scraping CotePara
```bash
python scrapping_cotepara.py
```
Le script va :
- Parcourir les pages de produits de manière asynchrone
- Extraire les détails de chaque produit
- Sauvegarder les résultats localement
- Uploader les données vers S3

## Dépendances Principales

- selenium==4.15.2 : Automatisation du navigateur (Jumia)
- playwright==1.41.2 : Automatisation asynchrone (CotePara)
- beautifulsoup4==4.12.2 : Parsing HTML
- pandas==2.1.3 : Manipulation des données
- openpyxl==3.1.2 : Export Excel
- lxml==4.9.3 : Parser HTML rapide
- webdriver-manager==4.0.1 : Gestion du ChromeDriver
- boto3==1.34.34 : Intégration AWS S3
- psutil==5.9.8 : Surveillance système

## Fonctionnalités Avancées

### Jumia
- Gestion automatique du scroll
- Détection automatique de la fin de pagination
- Système de scoring des produits
- User-Agent personnalisé

### CotePara
- Scraping asynchrone avec gestion de concurrence
- Traitement par lots avec sémaphore
- Gestion avancée des erreurs réseau
- Système de retry intelligent

## Notes

- Assurez-vous d'avoir une connexion Internet stable
- Les scripts incluent des délais entre les requêtes pour éviter le blocage
- Les données sont sauvegardées localement et sur AWS S3
- Le scraping CotePara est plus performant grâce à l'asynchronicité

## Sécurité

- Les credentials AWS ne doivent pas être partagés
- Les scripts utilisent des options de navigateur sécurisées
- Les données sensibles sont gérées de manière sécurisée
- Gestion des timeouts et des erreurs réseau

## Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails. 
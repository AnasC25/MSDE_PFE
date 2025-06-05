# Projet de Web Scraping E-commerce pour Marjanemall

## Contexte du Projet

Ce projet s'inscrit dans le cadre de la transformation digitale du Groupe Marjane et de sa plateforme e-commerce Marjanemall. L'objectif est d'optimiser la sélection des produits à promouvoir sur la marketplace en exploitant des données internes et externes.

### À propos de Marjanemall

Marjanemall est la marketplace du Groupe Marjane, lancée dans le cadre de sa stratégie de transformation digitale. La plateforme :
- Permet aux vendeurs tiers de commercialiser leurs produits
- S'appuie sur les capacités logistiques du Groupe Marjane
- Propose une expérience client optimisée et cohérente
- Utilise deux modèles logistiques : FFM (Fulfillment by Marjane) et Cross-Docking

### Objectifs du Projet

1. Automatiser la collecte et l'exploitation des données pertinentes
2. Mettre en place des indicateurs de performance pour le pilotage des mises en avant
3. Concevoir un modèle intelligent d'aide à la décision basé sur des algorithmes de scoring
4. Offrir une visualisation claire et interactive via une application

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
- Sauvegarde des résultats au format CSV et Excel dans le dossier `jumia_products/`
- Upload automatique des fichiers vers AWS S3

### Scraping CotePara
- Scraping asynchrone pour une meilleure performance
- Collecte détaillée des informations produits :
  - Titre
  - Prix
  - Ancien prix
  - Réduction
  - Score de popularité
- Sauvegarde des résultats au format CSV et JSON (fichiers nommés `cotepara_products_YYYYMMDD_HHMMSS.csv` et `.json`)
- Upload automatique des fichiers vers AWS S3
- Gestion avancée des erreurs et retries

## Fonctionnalités Communes
- Sauvegarde automatique des données au format Excel/CSV/JSON
- Intégration avec AWS S3 pour le stockage des données
- Système de logging complet
- Gestion des erreurs et reprise sur erreur

## Architecture Technique

Le projet est composé de deux scripts principaux :

1. `scrapping_jumia.py` :
   - Utilise Selenium pour l'automatisation
   - Extraction des liens produits
   - Gestion de la pagination
   - Sauvegarde des données dans `jumia_products/`
   - Upload vers AWS S3

2. `scrapping_cotepara.py` :
   - Utilise Playwright pour l'automatisation asynchrone
   - Extraction des détails produits
   - Gestion avancée des erreurs
   - Sauvegarde des données localement (CSV/JSON)
   - Upload vers AWS S3

## Méthodologie de Développement

Le projet suit une approche Agile avec :
- Sprints hebdomadaires
- Réunions régulières avec les parties prenantes
- Suivi via Trello/Jira
- Revues de sprint pour validation des livrables

### Planification
- Phase de cadrage : 1 semaine
- Conception technique : 1 semaine
- Développement : 3 semaines
- Tests & validation : 1 semaine
- Documentation & livraison : 1 semaine

## Prérequis

- Python 3.x
- Chrome Browser
- ChromeDriver (pour Jumia) — le fichier `chromedriver.exe` est inclus pour Windows
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
├── jumia_products/                # Dossier contenant les données Jumia (CSV, XLSX)
├── chromedriver.exe               # ChromeDriver pour Windows (Jumia)
├── scrapping_jumia.py             # Script pour Jumia
├── scrapping_cotepara.py          # Script pour CotePara
├── requirements.txt               # Liste des dépendances Python
└── README.md                      # Documentation
```

## Utilisation

### Scraping Jumia
```bash
python scrapping_jumia.py
```
Le script va :
- Parcourir les pages de produits
- Extraire les liens
- Sauvegarder les données dans `jumia_products/`
- Uploader les données vers S3

### Scraping CotePara
```bash
python scrapping_cotepara.py
```
Le script va :
- Parcourir les pages de produits de manière asynchrone
- Extraire les détails de chaque produit
- Sauvegarder les résultats localement (CSV/JSON)
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
- Scraping asynchrone avec gestion des timeouts et retries
- Gestion avancée des erreurs réseau
- Système de scoring des produits

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
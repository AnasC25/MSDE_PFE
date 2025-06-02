# Projet de Scraping Jumia

Ce projet est un outil de web scraping pour extraire des informations de produits depuis le site Jumia. Il permet de collecter les détails des produits et leurs liens.

## Fonctionnalités

- Extraction des liens de produits
- Collecte des détails des produits
- Sauvegarde des données au format Excel
- Gestion automatique du navigateur avec Selenium

## Prérequis

- Python 3.x
- Chrome Browser
- ChromeDriver (inclus dans le projet)

## Installation

1. Clonez ce dépôt :
```bash
git clone https://github.com/AnasC25/MSDE_PFE.git
```

2. Installez les dépendances requises :
```bash
pip install -r requirements.txt
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

2. Pour extraire les détails des produits :
```bash
python scrapping_jumia_details.py
```

## Dépendances Principales

- selenium==4.15.2
- beautifulsoup4==4.12.2
- pandas==2.1.3
- openpyxl==3.1.2
- lxml==4.9.3
- webdriver-manager==4.0.1

## Notes

- Assurez-vous d'avoir une connexion Internet stable
- Le script utilise ChromeDriver pour l'automatisation du navigateur
- Les données sont sauvegardées dans des dossiers dédiés

## Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails. 
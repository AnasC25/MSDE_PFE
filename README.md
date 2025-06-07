# Web Scraping Project for E-commerce Products

Ce projet est un système de scraping web qui collecte des données de produits depuis les sites e-commerce Jumia et CotePara au Maroc.

## 🚀 Fonctionnalités

- Scraping de produits depuis Jumia et CotePara
- Extraction des informations détaillées des produits :
  - Désignation
  - Marque
  - Prix de vente
  - Prix barré
  - URL de l'image
  - Lien du produit
  - Date d'extraction
- Sauvegarde des données en format CSV et Excel
- Upload automatique vers Amazon S3
- Gestion de la mémoire et des ressources
- Logging détaillé des opérations

## 📋 Prérequis

- Python 3.11+
- Chrome/Chromium
- ChromeDriver
- Accès AWS avec les permissions S3

## 🔧 Installation

1. Clonez le repository :
```bash
git clone [URL_DU_REPO]
cd [NOM_DU_REPO]
```

2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

3. Configurez les variables d'environnement AWS :
```bash
export AWS_ACCESS_KEY_ID=votre_access_key
export AWS_SECRET_ACCESS_KEY=votre_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

## 📦 Structure du Projet

```
.
├── scrapping_jumia.py      # Script de scraping pour Jumia
├── scrapping_cotepara.py   # Script de scraping pour CotePara
├── requirements.txt        # Dépendances Python
└── README.md              # Documentation
```

## 🛠️ Configuration

### Configuration S3
- Bucket : `msde-pfe-blobs`
- Préfixes :
  - Jumia : `jumia/products/`
  - CotePara : `cotepara/`

### Configuration du Scraping
- Timeouts configurés pour éviter les blocages
- Gestion automatique de la mémoire
- Rotation des User-Agents
- Gestion des erreurs et retries

## 🚀 Utilisation

### Scraping Jumia
```bash
python scrapping_jumia.py
```

### Scraping CotePara
```bash
python scrapping_cotepara.py
```

## 📊 Format des Données

Les données sont sauvegardées dans deux formats :

### CSV
- Encodage : UTF-8
- Séparateur : Virgule
- En-têtes : designation, marque, prix_vente, prix_barre, image_url, lien_produit, date_extraction

### Excel
- Format : .xlsx
- Mêmes colonnes que le CSV

## 🔒 Sécurité

- Les clés AWS ne sont jamais stockées en dur dans le code
- Utilisation de variables d'environnement pour les credentials
- Gestion sécurisée des sessions de scraping

## 📝 Logging

Le système utilise un logging détaillé avec les niveaux suivants :
- INFO : Opérations normales
- WARNING : Problèmes non critiques
- ERROR : Erreurs critiques

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
1. Fork le projet
2. Créer une branche pour votre fonctionnalité
3. Commiter vos changements
4. Pousser vers la branche
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## ⚠️ Avertissement

Ce projet est destiné à un usage éducatif uniquement. Assurez-vous de respecter les conditions d'utilisation des sites web ciblés. 
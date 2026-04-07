# Downloader Universel Premium

Cet outil est un utilitaire simple et puissant pour récupérer des contenus depuis diverses plateformes sociales. J'ai conçu cette interface pour qu'elle soit intuitive, tout en permettant une personnalisation précise de vos téléchargements.

## Ce que l'outil propose

L'application permet de gérer vos téléchargements de médias de manière flexible :

- **Support multi-plateforme** : Fonctionne avec YouTube, TikTok, Instagram, Pinterest, Facebook, X (Twitter) et bien d'autres services.
- **Gestion des formats** : Vous pouvez choisir entre plusieurs formats audio (MP3, WAV, M4A, FLAC) ou vidéo (MP4, MKV, WEBM).
- **Rognage précis** : Un système de curseurs vous permet de sélectionner précisément le début et la fin d'une séquence pour ne télécharger que ce qui vous intéresse.
- **Téléchargement par lots** : Si vous avez une liste de liens, vous pouvez simplement les mettre dans un fichier .txt et l'importer pour tout traiter d'un coup.
- **Gestion des playlists** : L'outil gère le téléchargement de playlists entières automatiquement.
- **Installation automatique de FFmpeg** : Pour simplifier la vie, l'application détecte si FFmpeg est présent sur votre système et peut s'occuper de l'installer si ce n'est pas le cas.
- **Interface soignée** : Utilisation de CustomTkinter pour un rendu moderne qui s'adapte au mode sombre ou clair de votre système.
- **Aperçu intégré** : Vous pouvez voir la miniature et les informations du média avant de lancer le téléchargement.

## Installation et démarrage

### Avant de commencer
Vous aurez besoin de Python 3.8 ou une version plus récente. FFmpeg est nécessaire pour le traitement, mais si vous ne l'avez pas, l'application vous proposera de l'installer lors du premier lancement.

### Installation des bibliothèques
Pour installer les dépendances nécessaires, lancez cette commande dans votre terminal :
```bash
pip install -r requirements.txt
```

## Comment s'en servir

1. Lancez le script principal :
   ```bash
   python main.py
   ```
2. Collez le lien du média que vous souhaitez récupérer.
3. Cliquez sur le bouton d'aperçu pour charger les informations. C'est ici que vous pourrez ajuster le début et la fin de la séquence si besoin.
4. Sélectionnez le format de sortie souhaité.
5. Lancez le téléchargement.

### Téléchargement en série (Batch)
Si vous avez beaucoup de liens, placez-les simplement dans un fichier texte (un lien par ligne) et utilisez l'option d'importation .txt dans l'interface.

## Créer un exécutable

Si vous préférez utiliser l'application sans lancer Python à chaque fois, vous pouvez générer une version portable (.exe) avec le script de build :
```bash
python build.py
```
Le résultat sera disponible dans le dossier `dist/`.

## Les technologies derrière le projet

Ce projet s'appuie sur plusieurs outils robustes :
- **yt-dlp** pour le moteur de téléchargement.
- **CustomTkinter** pour l'interface graphique.
- **FFmpeg** pour tout ce qui concerne le traitement et le rognage des fichiers.
- **Pillow** pour la manipulation des images et miniatures.

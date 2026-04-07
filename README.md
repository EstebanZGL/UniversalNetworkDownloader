# 🎬 Downloader Universel Premium

Un outil de téléchargement de médias polyvalent, puissant et facile à utiliser, conçu pour récupérer du contenu depuis diverses plateformes sociales avec une interface moderne et intuitive.

![Splash Screen](splash.png)

## ✨ Caractéristiques

- **Support Multi-plateforme** : Téléchargez depuis YouTube, TikTok, Instagram, Pinterest, Facebook, X (Twitter), et bien d'autres.
- **Formats Variés** : 
  - **Audio** : MP3, WAV, M4A, FLAC.
  - **Vidéo** : MP4, MKV, WEBM.
- **Rognage de Précision** : Sélectionnez exactement la partie du média que vous souhaitez télécharger grâce aux curseurs de début et de fin.
- **Téléchargement par Lot (Batch)** : Importez un fichier `.txt` contenant une liste d'URLs pour tout télécharger d'un coup.
- **Support des Playlists** : Téléchargez des playlists entières en un seul clic.
- **Gestion Intégrée de FFmpeg** : L'application détecte, télécharge et configure automatiquement FFmpeg si nécessaire.
- **Interface Moderne** : Développé avec `CustomTkinter` pour un look "Premium" et un support du mode sombre/clair système.
- **Aperçu en Temps Réel** : Visualisez la miniature et les informations du média avant le téléchargement.

## 🚀 Installation

### Prérequis
- Python 3.8+
- [FFmpeg](https://ffmpeg.org/) (optionnel, l'application peut l'installer pour vous)

### Installation des dépendances
Clonez le dépôt et installez les bibliothèques nécessaires :
```bash
pip install -r requirements.txt
```

## 🛠️ Utilisation

1. Lancez l'application :
   ```bash
   python main.py
   ```
2. Collez l'URL du média dans le champ dédié.
3. (Optionnel) Utilisez le bouton **Aperçu** pour charger les informations et régler le rognage.
4. Choisissez votre format de sortie.
5. Cliquez sur **Télécharger**.

### Mode Batch (.txt)
Créez un fichier texte avec une URL par ligne, puis utilisez le bouton `📂 .txt` dans l'application pour l'importer.

## 📦 Compilation en Exécutable

Pour créer une version portable (`.exe`), utilisez le script de build fourni :
```bash
python build.py
```
L'exécutable se trouvera dans le dossier `dist/`.

## 📝 Technologies utilisées

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** : Le moteur de téléchargement ultra-puissant.
- **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** : Pour l'interface graphique moderne.
- **[FFmpeg](https://ffmpeg.org/)** : Pour le traitement audio/vidéo et le rognage.
- **Pillow** : Pour la gestion des images et miniatures.

---
*Développé avec ❤️ pour une expérience de téléchargement simplifiée.*

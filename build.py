import os
import PyInstaller.__main__
import customtkinter

# Chemin vers la bibliothèque customtkinter pour forcer l'inclusion des assets (thèmes, polices)
customtkinter_path = os.path.dirname(customtkinter.__file__)

print(f"Compilation de l'exécutable... Base CTK detectée à : {customtkinter_path}")

# Chemins absolus pour éviter les erreurs liées aux dossiers temporaires
splash_img_path = os.path.abspath("splash.png")
icon_path = os.path.abspath("app_icon.ico")
ffmpeg_path = os.path.abspath("ffmpeg.exe")
ffplay_path = os.path.abspath("ffplay.exe")
ffprobe_path = os.path.abspath("ffprobe.exe")

# Configuration des chemins locaux (pour éviter les conflits OneDrive)
import tempfile
import shutil

temp_dir = os.path.join(tempfile.gettempdir(), "pyinstaller_build_yt")
build_dir = os.path.join(temp_dir, "build")
spec_dir = os.path.join(temp_dir, "spec")
dist_temp_dir = os.path.join(temp_dir, "dist")

# Nettoyage des dossiers temporaires
for d in [build_dir, spec_dir, dist_temp_dir]:
    if os.path.exists(d):
        try: shutil.rmtree(d)
        except: pass
    os.makedirs(d, exist_ok=True)

print(f"Lancement de PyInstaller (Temp: {temp_dir})...")

PyInstaller.__main__.run([
    'main.py',
    '--name=Downloader_Universel_Local',
    '--onedir',
    '--windowed',
    '--noconfirm',
    '--clean',
    f'--icon={icon_path}',
    f'--splash={splash_img_path}', 
    f'--add-data={customtkinter_path};customtkinter/', 
    f'--add-binary={ffmpeg_path};.',
    f'--add-binary={ffplay_path};.',
    f'--add-binary={ffprobe_path};.',
    f'--workpath={build_dir}',
    f'--specpath={spec_dir}',
    f'--distpath={dist_temp_dir}',
])

# Déplacement vers le dossier dist local
local_dist = os.path.abspath("dist")
import time
timestamp = int(time.time())
target_path = os.path.join(local_dist, "Downloader_Universel_Local")

print(f"Finalisation : Tentative de mise a jour de {target_path}...")

if os.path.exists(target_path):
    try:
        # On tente de renommer pour liberer le verrou
        old_path_temp = target_path + f"_old_{timestamp}"
        os.rename(target_path, old_path_temp)
        print(f"Ancienne version deplacee vers {old_path_temp}")
        # On ne tente pas de supprimer rmtree ici car OneDrive risque de bloquer
    except Exception as e:
        print(f"Note: Impossible de deplacer l'ancienne version ({e}). L'application est peut-etre ouverte.")

os.makedirs(local_dist, exist_ok=True)
try:
    shutil.move(os.path.join(dist_temp_dir, "Downloader_Universel_Local"), target_path)
    print(f"Succes : Compilation terminee ! Retrouvez votre application dans : {target_path}")
except Exception as e:
    print(f"Erreur de deplacement final : {e}")
    print(f"Les fichiers sont disponibles ici : {os.path.join(dist_temp_dir, 'Downloader_Universel_Local')}")

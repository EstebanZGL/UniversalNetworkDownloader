import os
import PyInstaller.__main__
import customtkinter

# Chemin vers la bibliothèque customtkinter pour forcer l'inclusion des assets (thèmes, polices)
customtkinter_path = os.path.dirname(customtkinter.__file__)

print(f"Compilation de l'exécutable... Base CTK detectée à : {customtkinter_path}")

PyInstaller.__main__.run([
    'main.py',
    '--name=YT_Converter',
    '--onefile',       # Un seul fichier .exe
    '--windowed',      # Pas de console msdos qui pop up
    '--noconfirm',     # Ecrase l'ancien build
    f'--add-data={customtkinter_path};customtkinter/', # Emballe les assets du GUI
])
print("Compilation terminée. Le fichier .exe se trouve dans le dossier 'dist'.")

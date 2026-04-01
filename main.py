import os
import sys
import shutil
import threading
import urllib.request
import zipfile
import io
import json
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import requests
    from PIL import Image
    import customtkinter as ctk
    import yt_dlp
    import fitz # PyMuPDF
except ImportError as e:
    print(f"Dépendance manquante ({e}). Lancez 'pip install -r requirements.txt'")
    exit(1)

APP_DIR = os.path.join(os.getenv('APPDATA', os.path.expanduser('~')), 'YT_Universal_Converter')
APP_BIN_DIR = os.path.join(APP_DIR, 'bin')
CONFIG_FILE = os.path.join(APP_DIR, 'config.json')
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings: dict):
    os.makedirs(APP_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
    except Exception:
        pass

class YTDLPLogger:
    def __init__(self, log_callback):
        self.log_callback = log_callback
    def debug(self, msg): pass
    def warning(self, msg):
        if "JavaScript runtime" in msg or "ffmpeg not found" in msg: return
        self.log_callback(f"⚠️ AVERTISSEMENT: {msg}")
    def error(self, msg):
        self.log_callback(f"❌ ERREUR: {msg}")


class SplashScreen(ctk.CTkToplevel):
    """Fenêtre de démarrage animée affichée pendant l'initialisation."""
    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)   # Pas de barre de titre
        self.resizable(False, False)
        self.attributes("-topmost", True)

        W, H = 440, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")

        # ── Fond principal ──────────────────────────────────────────────────
        outer = ctk.CTkFrame(
            self, corner_radius=18,
            fg_color="#0f0f1a",
            border_width=1, border_color="#3a3a60"
        )
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        # Icône
        ctk.CTkLabel(
            outer, text="🎬",
            font=ctk.CTkFont(size=52)
        ).pack(pady=(32, 6))

        # Titre
        ctk.CTkLabel(
            outer, text="Universal Downloader",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#e0e0f0"
        ).pack()

        # Sous-titre plateformes
        ctk.CTkLabel(
            outer,
            text="YouTube · TikTok · Instagram · Pinterest",
            font=ctk.CTkFont(size=11),
            text_color="#6060a0"
        ).pack(pady=(3, 22))

        # Spinner + statut
        self._spin_idx = 0
        self._spinner_lbl = ctk.CTkLabel(
            outer,
            text="⠋  Initialisation…",
            font=ctk.CTkFont(size=13),
            text_color="#9090c0"
        )
        self._spinner_lbl.pack()

        self._status_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk.CTkFont(size=11),
            text_color="#505080"
        )
        self._status_lbl.pack(pady=(4, 0))

        self.lift()
        self.focus_force()
        self._animate()

    def _animate(self):
        if not self.winfo_exists():
            return
        self._spin_idx = (self._spin_idx + 1) % len(self._SPINNER)
        ch = self._SPINNER[self._spin_idx]
        try:
            self._spinner_lbl.configure(text=f"{ch}  Chargement du moteur A/V…")
        except Exception:
            return
        self.after(90, self._animate)

    def set_status(self, text: str):
        """Met à jour le texte de statut (thread-safe via after())."""
        try:
            self._status_lbl.configure(text=text)
        except Exception:
            pass

def parse_time_to_seconds(t_str: str):
    if not t_str or not t_str.strip(): return None
    parts = t_str.strip().split(':')
    try:
        if len(parts) == 3: return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        elif len(parts) == 2: return float(parts[0])*60 + float(parts[1])
        elif len(parts) == 1: return float(parts[0])
    except ValueError: pass
    return None

def format_seconds_to_time(seconds: float):
    if seconds is None: return ""
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0: return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def get_platform_subfolder(url: str) -> str:
    """Détermine le sous-dossier de sortie d'après la plateforme."""
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'YouTube'
    if 'tiktok.com' in u:
        return 'TikTok'
    if 'instagram.com' in u:
        return 'Instagram'
    if 'pinterest.com' in u or 'pin.it' in u:
        return 'Pinterest'
    return 'Autres'

class UniversalStudioApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Suite Universelle - Médias & PDF (Responsive Edition)")
        self.geometry("950x700")
        self.minsize(800, 600)
        self.resizable(True, True)

        settings = load_settings()
        saved_dir = settings.get("output_dir", os.path.expanduser("~\\Downloads"))
        
        self.output_dir = ctk.StringVar(value=saved_dir)
        self.url_var = ctk.StringVar()
        self.ext_var = ctk.StringVar(value="mp3")
        self.crop_start_var = ctk.StringVar()
        self.crop_end_var = ctk.StringVar()

        # Variables mode batch (fichier .txt)
        self.batch_urls = []          # Liste des URLs chargées depuis un .txt
        self.batch_file_var = ctk.StringVar()

        # Variables de l'éditeur PDF
        self.pdf_merge_files = []
        self.pdf_split_file = ctk.StringVar()
        self.pdf_split_start = ctk.StringVar(value="1")
        self.pdf_split_end = ctk.StringVar()
        
        self.pdf_extract_file = ctk.StringVar()
        
        self.pdf_mod_file = ctk.StringVar()
        self.pdf_mod_old = ctk.StringVar()
        self.pdf_mod_new = ctk.StringVar()
        self.pdf_mod_case = ctk.BooleanVar(value=False)
        self.playlist_mode = ctk.BooleanVar(value=False)
        
        self.is_downloading = False
        self.is_ready = False
        self.ffmpeg_path = None
        self.video_metadata = None
        self.video_duration = 0 
        self.preview_image_ref = None 

        self.withdraw()   # Masquer la fenêtre principale jusqu'à ce que le splash ferme
        self._build_ui()

        self.crop_start_var.trace_add("write", self._on_text_crop_change)
        self.crop_end_var.trace_add("write", self._on_text_crop_change)

        self.splash = SplashScreen(self)
        threading.Thread(target=self._resolve_dependencies, daemon=True).start()

    def _build_ui(self):
        self.title_label = ctk.CTkLabel(self, text="Espace de Travail Sécure", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(pady=(15, 5))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        tab_yt = self.tabview.add("Download Vidéos")
        tab_pdf = self.tabview.add("Edit PDF")

        self._build_yt_ui(tab_yt)
        self._build_pdf_ui(tab_pdf)
        
        # Barre commune pour le dossier de sortie (Mise au global tout en bas)
        env_frame = ctk.CTkFrame(self, fg_color="transparent")
        env_frame.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkLabel(env_frame, text="Dossier Global d'Export :", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkEntry(env_frame, textvariable=self.output_dir, state="disabled", width=350).pack(side="left", padx=10, fill="x", expand=True)
        ctk.CTkButton(env_frame, text="Modifier", command=self._select_directory, width=80).pack(side="left")

    def _build_yt_ui(self, parent):
        self.main_container = ctk.CTkFrame(parent, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=5, pady=5)

        self.main_container.grid_columnconfigure(0, weight=3)
        self.main_container.grid_columnconfigure(1, weight=2)
        self.main_container.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.right_panel = ctk.CTkFrame(self.main_container)
        self.right_panel.grid(row=0, column=1, sticky="nsew")

        self.url_label = ctk.CTkLabel(
            self.left_panel,
            text="Lien Média (YouTube · TikTok · Instagram · Pinterest) :",
            font=ctk.CTkFont(weight="bold")
        )
        self.url_label.pack(anchor="w")

        url_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 5))
        self.url_entry = ctk.CTkEntry(
            url_row, textvariable=self.url_var,
            placeholder_text="https://... (YouTube, TikTok, Instagram, Pinterest)"
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # ── Bouton import fichier .txt ──
        self.import_txt_btn = ctk.CTkButton(
            url_row, text="📂 .txt", width=70,
            fg_color="#555568", hover_color="#3a3a50",
            command=self._import_batch_file
        )
        self.import_txt_btn.pack(side="left")

        # Étiquette compteur batch
        self.batch_label = ctk.CTkLabel(
            self.left_panel, text="", text_color="#7EC8E3",
            font=ctk.CTkFont(size=11, slant="italic")
        )
        self.batch_label.pack(anchor="w", pady=(0, 2))

        playlist_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        playlist_row.pack(fill="x", pady=(0, 5))
        self.playlist_checkbox = ctk.CTkCheckBox(
            playlist_row, text="🎵 Télécharger toute la Playlist",
            variable=self.playlist_mode, command=self._on_playlist_toggle
        )
        self.playlist_checkbox.pack(side="left")

        self.load_btn = ctk.CTkButton(self.left_panel, text="🔍 Charger l'Aperçu", fg_color="#E07A5F", hover_color="#D16043", command=self._start_preview_thread)
        self.load_btn.pack(pady=5)

        self.format_label = ctk.CTkLabel(self.left_panel, text="Format Cible :")
        self.format_label.pack(anchor="w", pady=(10, 0))
        self.format_menu = ctk.CTkOptionMenu(
            self.left_panel, values=["mp3", "wav", "m4a", "flac", "mp4", "mkv", "webm"], variable=self.ext_var, width=200
        )
        self.format_menu.pack(anchor="w", pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(self.left_panel)
        self.progress_bar.pack(fill="x", pady=(20, 5))
        self.progress_bar.set(0.0)

        self.log_textbox = ctk.CTkTextbox(self.left_panel, state="disabled")
        self.log_textbox.pack(fill="both", expand=True)

        self.download_button = ctk.CTkButton(self.left_panel, text="🔄 Initialisation Système A/V...", font=ctk.CTkFont(weight="bold", size=15), height=40, state="disabled", command=self._start_download_thread)
        self.download_button.pack(fill="x", pady=15)

        # Panneau de droite (Rognage)
        self.hdr_label = ctk.CTkLabel(self.right_panel, text="Rognage des sections Média", font=ctk.CTkFont(weight="bold", size=16))
        self.hdr_label.pack(pady=(10, 5))

        self.img_label = ctk.CTkLabel(self.right_panel, text="[Insérez l'URL pour la miniature]", height=158, fg_color="gray20", corner_radius=8)
        self.img_label.pack(pady=5, padx=20, fill="x")

        self.play_btn = ctk.CTkButton(self.right_panel, text="▶ Lire la vidéo", width=120, fg_color="#2E8B57", hover_color="#1F5F3A", state="disabled", command=self._play_video_preview)
        self.play_btn.pack(pady=(0, 5))

        self.info_title = ctk.CTkLabel(self.right_panel, text="Titre: N/A", wraplength=280)
        self.info_title.pack(padx=10)
        self.info_dur = ctk.CTkLabel(self.right_panel, text="Durée Totale: N/A")
        self.info_dur.pack(padx=10, pady=(0, 10))

        crop_frame = ctk.CTkFrame(self.right_panel)
        crop_frame.pack(fill="x", padx=15, pady=5)
        
        val_frame = ctk.CTkFrame(crop_frame, fg_color="transparent")
        val_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(val_frame, text="Début:").pack(side="left")
        self.entry_start = ctk.CTkEntry(val_frame, textvariable=self.crop_start_var, width=70, justify="center")
        self.entry_start.pack(side="left", padx=5)
        
        self.entry_end = ctk.CTkEntry(val_frame, textvariable=self.crop_end_var, width=70, justify="center")
        self.entry_end.pack(side="right", padx=5)
        ctk.CTkLabel(val_frame, text="Fin:").pack(side="right")

        self.slider_start = ctk.CTkSlider(crop_frame, from_=0, to=1, command=self._on_start_slide, state="disabled", button_color="#E07A5F", progress_color="gray30", fg_color="#E07A5F")
        self.slider_start.pack(fill="x", padx=10, pady=(10, 5))
        self.slider_start.set(0)

        self.slider_end = ctk.CTkSlider(crop_frame, from_=0, to=1, command=self._on_end_slide, state="disabled", button_color="#E07A5F", progress_color="#E07A5F", fg_color="gray30")
        self.slider_end.pack(fill="x", padx=10, pady=(0, 15))
        self.slider_end.set(1)

    def _build_pdf_ui(self, parent):
        pdf_tabs = ctk.CTkTabview(parent)
        pdf_tabs.pack(fill="both", expand=True, padx=5, pady=5)
        
        tab_merge = pdf_tabs.add("Fusionner")
        tab_split = pdf_tabs.add("Découper")
        tab_extract = pdf_tabs.add("Extraire Texte")
        tab_replace = pdf_tabs.add("Modifier Texte")

        # Tab: Fusionner
        ctk.CTkLabel(tab_merge, text="Sélectionnez plusieurs fichiers PDF à lier dans le même document :", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        self.lbl_merge_files = ctk.CTkLabel(tab_merge, text="Aucun fichier", text_color="gray60")
        self.lbl_merge_files.pack()
        ctk.CTkButton(tab_merge, text="... Parcourir pour ajouter", command=self._select_merge_files).pack(pady=15)
        ctk.CTkButton(tab_merge, text="🗜️ Fusionner en 1 PDF", height=40, font=ctk.CTkFont(weight="bold"), fg_color="#2E8B57", hover_color="#1F5F3A", command=lambda: threading.Thread(target=self._task_pdf_merge, daemon=True).start()).pack(pady=20)

        # Tab: Découper
        ctk.CTkLabel(tab_split, text="Fichier PDF d'origine à scinder :").pack(pady=10)
        frame_spl_f = ctk.CTkFrame(tab_split, fg_color="transparent")
        frame_spl_f.pack(fill="x", padx=40)
        ctk.CTkEntry(frame_spl_f, textvariable=self.pdf_split_file, state="disabled").pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(frame_spl_f, text="Parcourir", width=70, command=lambda: self._select_single_pdf(self.pdf_split_file)).pack(side="left")
        
        frame_spl_rng = ctk.CTkFrame(tab_split, fg_color="transparent")
        frame_spl_rng.pack(pady=20)
        ctk.CTkLabel(frame_spl_rng, text="Conserver les pages").pack(side="left", padx=10)
        ctk.CTkLabel(frame_spl_rng, text="De :").pack(side="left")
        ctk.CTkEntry(frame_spl_rng, textvariable=self.pdf_split_start, width=40).pack(side="left", padx=5)
        ctk.CTkLabel(frame_spl_rng, text="A :").pack(side="left")
        ctk.CTkEntry(frame_spl_rng, textvariable=self.pdf_split_end, width=40).pack(side="left", padx=5)

        ctk.CTkButton(tab_split, text="✂️ Extraire l'intervalle", height=40, font=ctk.CTkFont(weight="bold"), fg_color="#E07A5F", hover_color="#D16043", command=lambda: threading.Thread(target=self._task_pdf_split, daemon=True).start()).pack(pady=10)

        # Tab: Extraire
        ctk.CTkLabel(tab_extract, text="Extraction du texte brut sans formatage (Numérisation pure) :", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        frame_ext_f = ctk.CTkFrame(tab_extract, fg_color="transparent")
        frame_ext_f.pack(fill="x", padx=40)
        ctk.CTkEntry(frame_ext_f, textvariable=self.pdf_extract_file, state="disabled").pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(frame_ext_f, text="Parcourir", width=70, command=lambda: self._select_single_pdf(self.pdf_extract_file)).pack(side="left")
        ctk.CTkButton(tab_extract, text="📄 Scanner en Texte (.txt)", height=40, command=lambda: threading.Thread(target=self._task_pdf_extract, daemon=True).start()).pack(pady=30)

        # Tab: Remplacer/Modifier
        warn_txt = "Avertissement : Le moteur invisibilisera mathématiquement les coordonnées de l'ancien mot pour imposer\nle nouveau. Limite du PDF : Les phrases environnantes ne se décaleront pas si votre mot cible déborde."
        ctk.CTkLabel(tab_replace, text=warn_txt, text_color="#D16043", font=ctk.CTkFont(size=11, slant="italic")).pack(pady=5)
        
        frame_mod_f = ctk.CTkFrame(tab_replace, fg_color="transparent")
        frame_mod_f.pack(fill="x", padx=40, pady=5)
        ctk.CTkEntry(frame_mod_f, textvariable=self.pdf_mod_file, state="disabled").pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(frame_mod_f, text="Parcourir", width=70, command=lambda: self._select_single_pdf(self.pdf_mod_file)).pack(side="left")

        ctk.CTkLabel(tab_replace, text="Phrase ou mot existant (A effacer) :", font=ctk.CTkFont(weight="bold")).pack(pady=(15,0))
        ctk.CTkEntry(tab_replace, textvariable=self.pdf_mod_old, width=400).pack(pady=5)
        ctk.CTkLabel(tab_replace, text="Texte de remplacement (A injecter) :", font=ctk.CTkFont(weight="bold")).pack(pady=(10,0))
        ctk.CTkEntry(tab_replace, textvariable=self.pdf_mod_new, width=400).pack(pady=5)
        ctk.CTkCheckBox(tab_replace, text="Sensibilité à la casse (Majuscules strictes)", variable=self.pdf_mod_case).pack(pady=15)

        ctk.CTkButton(tab_replace, text="🖌️ Appliquer le Tampon Réécrit", height=40, fg_color="#8A2BE2", font=ctk.CTkFont(weight="bold"), command=lambda: threading.Thread(target=self._task_pdf_replace, daemon=True).start()).pack(pady=10)

        # Global Reader App
        reader_frame = ctk.CTkFrame(parent, fg_color="transparent")
        reader_frame.pack(fill="x", pady=0)
        ctk.CTkButton(reader_frame, text="👀 Prévisualiser / Sélectionner le texte d'un PDF (Lecteur Externe)", height=30, font=ctk.CTkFont(weight="bold"), fg_color="#4F4F4F", hover_color="#2F2F2F", command=self._open_pdf_viewer).pack(pady=10)

    # ── Batch import ──────────────────────────────────────────────────────────
    def _import_batch_file(self):
        """Charge un fichier .txt contenant des URLs (une par ligne)."""
        filepath = filedialog.askopenfilename(
            title="Sélectionner un fichier de liens",
            filetypes=[("Fichier texte", "*.txt"), ("Tous les fichiers", "*.*")]
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines()]
            urls = [ln for ln in lines if ln and ln.startswith('http')]
            if not urls:
                self.log_message("⚠️ Aucun lien valide trouvé dans le fichier (les lignes doivent commencer par http).")
                return
            self.batch_urls = urls
            self.batch_file_var.set(filepath)
            # Vider l'URL individuelle pour éviter la confusion
            self.url_var.set("")
            # Désactiver les sliders de rognage (non applicable en batch)
            self.slider_start.configure(state="disabled")
            self.slider_end.configure(state="disabled")
            self.entry_start.configure(state="disabled")
            self.entry_end.configure(state="disabled")
            self.batch_label.configure(
                text=f"📋 Batch actif : {len(urls)} lien(s) chargé(s) depuis '{os.path.basename(filepath)}'"
            )
            self.log_message(f"✅ Fichier batch chargé : {len(urls)} URL(s) détectée(s).")
            for i, u in enumerate(urls, 1):
                self.log_message(f"  {i}. {u[:80]}{'...' if len(u) > 80 else ''}")
            # Activer le bouton de téléchargement si le système est prêt
            if self.is_ready:
                self.download_button.configure(state="normal")
        except Exception as e:
            self.log_message(f"❌ Erreur lecture fichier batch : {str(e)}")

    def _clear_batch(self):
        """Réinitialise le mode batch."""
        self.batch_urls = []
        self.batch_file_var.set("")
        self.batch_label.configure(text="")

    # UI Callbacks
    def _select_merge_files(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        if files:
            self.pdf_merge_files = list(files)
            self.lbl_merge_files.configure(text=f"{len(files)} document(s) détecté(s)")

    def _select_single_pdf(self, var):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if f: var.set(f)

    def _select_directory(self):
        d = filedialog.askdirectory(initialdir=self.output_dir.get(), title="Sélectionnez le dossier de réception (Vidéos & PDFs)")
        if d: 
            self.output_dir.set(d)
            settings = load_settings()
            settings["output_dir"] = d
            save_settings(settings)

    def _open_pdf_viewer(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")], title="Lecteur Interactif Sécurisé")
        if f:
            try:
                import webbrowser
                webbrowser.open(f"file:///{f.replace(chr(92), '/')}")
                self.log_message("✅ Projection instantanée : PDF ouvert de manière interactive.")
            except Exception as e:
                self.log_message(f"❌ Impossible de projeter le PDF: {str(e)}")

    # PDF Processing Tasks
    def _task_pdf_merge(self):
        if not self.pdf_merge_files: return
        try:
            self.log_message("\n⏳ Tâche PDF : Algorithme d'Assemblage lancé...")
            out_pdf = os.path.join(self.output_dir.get(), "FUSION_" + os.path.basename(self.pdf_merge_files[0]))
            doc = fitz.open()
            for p in self.pdf_merge_files:
                with fitz.open(p) as f: doc.insert_pdf(f)
            doc.save(out_pdf)
            self.log_message(f"🎉 Fusion PDF validée ! Sortie : {out_pdf}")
        except Exception as e: self.log_message(f"❌ Erreur PDF: {str(e)}")

    def _task_pdf_split(self):
        f = self.pdf_split_file.get()
        if not f: return
        try:
            self.log_message("\n⏳ Tâche PDF : Algorithme de Scission lancé...")
            s_page = int(self.pdf_split_start.get()) - 1
            e_page = int(self.pdf_split_end.get()) - 1
            out_pdf = os.path.join(self.output_dir.get(), "A_EXTRAIT_" + os.path.basename(f))
            
            doc = fitz.open(f)
            # max() et min() purgent les erreurs humaines (ex: demande de la page 10 alors que le pdf fait 5 pages)
            max_p = max(0, min(e_page + 1, doc.page_count))
            safe_s = max(0, min(s_page, max_p-1))
            doc.select(range(safe_s, max_p))
            doc.save(out_pdf)
            self.log_message(f"🎉 Scission réussie ! Fichier isolé : {out_pdf}")
        except Exception as e: self.log_message(f"❌ Erreur PDF: {str(e)}")

    def _task_pdf_extract(self):
        f = self.pdf_extract_file.get()
        if not f: return
        try:
            self.log_message("\n⏳ Tâche PDF : Aspiration du Texte Brut via OCR PyMuPDF...")
            out_txt = os.path.join(self.output_dir.get(), "TXT_" + os.path.basename(f).replace('.pdf', '.txt'))
            
            doc = fitz.open(f)
            text = ""
            for i, page in enumerate(doc):
                text += f"\n--- [PAGE {i+1}] ---\n"
                text += page.get_text()
            
            with open(out_txt, 'w', encoding='utf-8') as ft: ft.write(text)
            self.log_message(f"🎉 Aspiration en Fichier Txt terminée : {out_txt}")
        except Exception as e: self.log_message(f"❌ Erreur PDF: {str(e)}")

    def _task_pdf_replace(self):
        f = self.pdf_mod_file.get()
        old_t = self.pdf_mod_old.get()
        new_t = self.pdf_mod_new.get()
        
        if not f or not old_t: return
        try:
            self.log_message(f"\n⏳ Algorithme d'Altération de Flux (Stream Patching) sur ['{old_t}']...")
            out_pdf = os.path.join(self.output_dir.get(), "EDITION_" + os.path.basename(f))
            doc = fitz.open(f)
            
            import zlib
            def _decompress(raw):
                try: return zlib.decompress(raw)
                except Exception:
                    try: return zlib.decompress(raw, -15)
                    except Exception: return raw

            def _scan_stream_spans(data):
                spans = []
                i, n = 0, len(data)
                while i < n:
                    if data[i:i+1] == b'(':
                        j = i + 1
                        depth = 1
                        while j < n and depth > 0:
                            b = data[j:j+1]
                            if b == b'\\': j += 2; continue
                            if b == b'(': depth += 1
                            elif b == b')': depth -= 1
                            j += 1
                        spans.append((i, j, 'lit', data[i:j]))
                        i = j
                    elif data[i:i+1] == b'<' and data[i:i+2] != b'<<':
                        j = i + 1
                        while j < n and data[j:j+1] != b'>': j += 1
                        j += 1
                        raw_s = data[i:j]
                        inner = raw_s[1:-1].decode('ascii', errors='replace').replace(' ','').replace('\n','').replace('\r','')
                        valid = set('0123456789abcdefABCDEF')
                        if inner and all(c in valid for c in inner):
                            spans.append((i, j, 'hex', raw_s))
                        i = j
                    else:
                        i += 1
                return spans

            def _decode_pdf_string(kind, raw_s):
                if kind == 'lit':
                    inner = raw_s[1:-1]
                    out = bytearray()
                    i = 0
                    while i < len(inner):
                        if inner[i:i+1] == b'\\':
                            nxt = inner[i+1:i+2]
                            esc = {b'n':b'\n',b'r':b'\r',b't':b'\t',b'b':b'\b',
                                   b'f':b'\f',b'(':b'(',b')':b')',b'\\':b'\\'}
                            out += esc.get(nxt, nxt)
                            i += 2
                        else:
                            out += inner[i:i+1]
                            i += 1
                    try: return out.decode('latin-1'), 'lat'
                    except Exception: return None, None
                inner = raw_s[1:-1].decode('ascii', errors='replace').replace(' ','').replace('\n','').replace('\r','')
                if len(inner) % 2 != 0: inner += '0'
                try: b = bytes(int(inner[k:k+2], 16) for k in range(0, len(inner), 2))
                except Exception: return None, None
                if len(b) >= 2 and len(b) % 2 == 0:
                    try:
                        t = b.decode('utf-16-be')
                        if t and not all(ord(c) in (0xFFFD, 0x25A1) for c in t): return t, 'cid'
                    except Exception: pass
                try: return b.decode('latin-1'), 'lat'
                except Exception: return None, None

            def _encode_new_string(new_text, kind, hint, old_raw):
                if kind == 'lit':
                    esc = new_text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
                    try: return b'(' + esc.encode('latin-1', errors='replace') + b')'
                    except Exception: return old_raw
                inner = old_raw[1:-1].decode('ascii', errors='replace').replace(' ','')
                orig_bytes = len(inner) // 2
                bpc = 2 if hint == 'cid' else 1
                pad = b'\x00\x20' if hint == 'cid' else b'\x20'
                enc_name = 'utf-16-be' if hint == 'cid' else 'latin-1'
                try:
                    enc = bytearray(new_text.encode(enc_name, errors='replace'))
                    if len(enc) < orig_bytes:
                        while len(enc) < orig_bytes: enc += pad
                        enc = bytes(enc[:orig_bytes])
                    elif len(enc) > orig_bytes:
                        enc = bytes(enc[:orig_bytes - (orig_bytes % bpc)])
                    return b'<' + ''.join(f'{x:02x}' for x in enc).encode('ascii') + b'>'
                except Exception: return old_raw

            def _text_to_variants(text):
                v = []
                esc = text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
                try: v.append(('lit', b'(' + esc.encode('latin-1', errors='replace') + b')'))
                except Exception: pass
                try:
                    h = ''.join(f'{b:02x}' for b in text.encode('latin-1'))
                    v.append(('hex', f'<{h}>'.encode('ascii')))
                except Exception: pass
                try:
                    h = ''.join(f'{b:02x}' for b in text.encode('utf-16-be'))
                    v.append(('hex', f'<{h}>'.encode('ascii')))
                except Exception: pass
                return v

            def _patch_stream(page, old_text, new_text):
                xrefs = page.get_contents()
                if not xrefs: return False
                is_cid = any(ord(c) in (0xFFFD, 0x25A1) for c in old_text)
                found = False
                for xref in xrefs:
                    raw = page.parent.xref_stream(xref)
                    if raw is None: continue
                    decoded = _decompress(raw)
                    modified = decoded
                    if not is_cid:
                        for kind, variant in _text_to_variants(old_text):
                            if variant in modified:
                                rep = _encode_new_string(new_text, kind, 'cid' if kind == 'hex' else 'lat', variant)
                                modified = modified.replace(variant, rep)
                                found = True
                    else:
                        spans_in_stream = _scan_stream_spans(decoded)
                        target_len = len(old_text)
                        for (start, end, kind, raw_span) in spans_in_stream:
                            txt, hint = _decode_pdf_string(kind, raw_span)
                            if txt is None or hint != 'cid': continue
                            if abs(len(txt) - target_len) <= 1:
                                rep = _encode_new_string(new_text, kind, hint, raw_span)
                                modified = decoded[:start] + rep + decoded[end:]
                                found = True
                                break
                    if modified != decoded:
                        page.parent.update_stream(xref, zlib.compress(modified, 9))
                return found

            def _detect_bg(page, rect):
                for path in reversed(page.get_drawings()):
                    fill = path.get("fill")
                    if not fill: continue
                    pr = fitz.Rect(path["rect"])
                    if pr.contains(rect) or pr.intersects(rect):
                        if isinstance(fill, (list, tuple)) and len(fill) >= 3:
                            return tuple(fill[:3])
                return None

            def _get_page_font_ref(page, span_font_name):
                """
                Cherche dans les polices DÉJÀ embarquées sur la page (via page.get_fonts())
                le nom local PDF (ex: 'F1', 'TT2') correspondant à la police du span.
                Ce nom local peut être passé directement à insert_text() sans aucun buffer.
                Retourne None si non trouvé.
                """
                try:
                    span_clean = span_font_name.split("+")[-1].lower().replace("-", "").replace(" ", "")
                    for xref, ext, ftype, basefont, local_name, enc in page.get_fonts(full=True):
                        bf_clean = basefont.split("+")[-1].lower().replace("-", "").replace(" ", "")
                        if bf_clean == span_clean or span_clean[:6] in bf_clean or bf_clean[:6] in span_clean:
                            if local_name:
                                return local_name  # ex: 'F1', 'TT0', 'C2_0' — déjà dans les ressources
                except Exception:
                    pass
                return None

            def _guess_base14(font_name, bold, italic):
                """Fallback ultime : mappe vers Base14. Jamais d'erreur."""
                n = font_name.lower()
                b = bold or "bold" in n or "black" in n or "heavy" in n
                i = italic or "italic" in n or "oblique" in n
                mono = any(x in n for x in ["courier", "mono", "consolas", "typewriter"])
                serif = any(x in n for x in ["times", "georgia", "garamond", "palatino", "serif"]) and "sans" not in n
                if mono:   return "cobi" if (b and i) else "cobo" if b else "coit" if i else "cour"
                elif serif: return "tibi" if (b and i) else "tibo" if b else "tiit" if i else "tiro"
                else:       return "hebi" if (b and i) else "hebo" if b else "heit" if i else "helv"



            replaced_count = 0
            for page in doc:
                text_instances = page.search_for(old_t)
                if not text_instances: continue
                
                # Édition chirurgicale du flux Zlib
                success = _patch_stream(page, old_t, new_t)
                if success:
                    replaced_count += len(text_instances)
                else:
                    self.log_message(f"⚠️ Flux crypté. Basculement sur le Clone-Optique pour {len(text_instances)} occurrence(s)...")
                    page_dict = page.get_text("dict")
                    replacements = []
                    
                    for rect in text_instances:
                        r_size, r_color, r_font = 11, (0, 0, 0), "helv"
                        r_origin_y = rect.y1 - 2
                        r_bold, r_italic = False, False
                        
                        found = False
                        if "blocks" in page_dict:
                            for b in page_dict["blocks"]:
                                if "lines" in b:
                                    for l in b["lines"]:
                                        for s in l["spans"]:
                                            s_rect = fitz.Rect(s["bbox"])
                                            if s_rect.intersects(rect):
                                                r_size = s["size"]
                                                c = s["color"]
                                                r_color = (((c >> 16) & 255)/255.0, ((c >> 8) & 255)/255.0, (c & 255)/255.0)
                                                r_origin_y = s["origin"][1]
                                                flg = s.get("flags", 0)
                                                r_bold = bool(flg & (1 << 4))
                                                r_italic = bool(flg & (1 << 1))
                                                r_font_raw = s.get("font", "helv")
                                                # Priorité 1 : nom local déjà dans les ressources PDF (police exacte)
                                                r_font = _get_page_font_ref(page, r_font_raw)
                                                # Priorité 2 : approximation Base14 (fallback sans erreur possible)
                                                if not r_font:
                                                    r_font = _guess_base14(r_font_raw, r_bold, r_italic)
                                                found = True
                                                break
                                        if found: break
                                if found: break
                                
                        replacements.append((rect, r_origin_y, r_font, r_size, r_color))
                        bg_col = _detect_bg(page, rect)
                        # Retouche la decoupe pour limiter l'impact de la gomme
                        safe_rect = rect + (0.5, 0.5, -0.5, -0.5)
                        page.add_redact_annot(safe_rect, fill=bg_col)
                        replaced_count += 1
                        
                    # Gomme sans toucher aux tracés ou images environnantes
                    try:
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
                    except Exception:
                        page.apply_redactions()
                        
                    for rect, origin_y, font, size, color in replacements:
                        pt = fitz.Point(rect.x0, origin_y) 
                        page.insert_text(pt, new_t, fontname=font, fontsize=size, color=color)

            if replaced_count > 0:
                doc.save(out_pdf, garbage=4, deflate=True)
                msg = f"🎉 Remplacement Réussi ! {replaced_count} correspondances traitées.\nDocument sauvegardé : {out_pdf}"
                self.log_message(msg)
                self.after(0, lambda: messagebox.showinfo("Succès PDF", msg))
            else:
                msg = "⚠️ Motif totalement introuvable dans le document ou sensible à la casse (espaces, majuscules...)."
                self.log_message(msg)
                self.after(0, lambda: messagebox.showwarning("Introuvable", msg))
                
            doc.close()
        except Exception as e:
            msg = f"❌ Erreur PDF: {str(e)}"
            self.log_message(msg)
            self.after(0, lambda: messagebox.showerror("Erreur Fatale", msg))

    # YouTube Sliders & Preview logic
    def _on_start_slide(self, value):
        if value >= self.slider_end.get():
            self.slider_start.set(self.slider_end.get() - 1)
            value = self.slider_start.get()
        self.crop_start_var.trace_vdelete("w", self.crop_start_var.trace_info()[0][1])
        self.crop_start_var.set(format_seconds_to_time(value))
        self.crop_start_var.trace_add("write", self._on_text_crop_change)

    def _on_end_slide(self, value):
        if value <= self.slider_start.get():
            self.slider_end.set(self.slider_start.get() + 1)
            value = self.slider_end.get()
        self.crop_end_var.trace_vdelete("w", self.crop_end_var.trace_info()[0][1])
        self.crop_end_var.set(format_seconds_to_time(value))
        self.crop_end_var.trace_add("write", self._on_text_crop_change)

    def _on_text_crop_change(self, *args):
        if not self.video_duration: return
        try:
            s_val = parse_time_to_seconds(self.crop_start_var.get())
            if s_val is not None and 0 <= s_val <= self.video_duration:
                self.slider_start.set(s_val)
                
            e_val = parse_time_to_seconds(self.crop_end_var.get())
            if e_val is not None and 0 <= e_val <= self.video_duration:
                self.slider_end.set(e_val)
                
            if s_val is not None and e_val is not None and s_val >= e_val:
                self.slider_start.set(max(0, e_val - 1))
        except: pass

    def log_message(self, message: str):
        def update_ui():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", message + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
            self.update_idletasks()
        self.after(0, update_ui)

    def _set_splash_status(self, text: str):
        """Met à jour le splash depuis n'importe quel thread."""
        if hasattr(self, 'splash') and self.splash and self.splash.winfo_exists():
            self.after(0, lambda t=text: self.splash.set_status(t))

    def _resolve_dependencies(self):
        self.log_message("🔍 Vérification intégrale système (FFmpeg & FFplay)...")
        self._set_splash_status("Recherche de FFmpeg sur le système…")
        sys_ffmpeg = shutil.which("ffmpeg")
        sys_ffplay = shutil.which("ffplay")
        if sys_ffmpeg and sys_ffplay:
            self.ffmpeg_path = os.path.dirname(sys_ffmpeg)
            self._set_splash_status("✔ Binaires natifs trouvés !")
            self._finalize_init("✔️ Binaires natifs de traitement prêts.")
            return

        local_base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(local_base, "ffmpeg.exe")) and os.path.exists(os.path.join(local_base, "ffplay.exe")):
            self.ffmpeg_path = local_base
            self._set_splash_status("✔ Moteur local trouvé !")
            self._finalize_init("✔️ Routines locales parées.")
            return

        appdata_ffmpeg = os.path.join(APP_BIN_DIR, "ffmpeg.exe")
        appdata_ffplay = os.path.join(APP_BIN_DIR, "ffplay.exe")
        if os.path.exists(appdata_ffmpeg) and os.path.exists(appdata_ffplay):
            self.ffmpeg_path = APP_BIN_DIR
            self._set_splash_status("✔ Moteur A/V en cache trouvé !")
            self._finalize_init("✔️ Moteur A/V persistant chargé.")
            return

        self.log_message("⚙️ Dépendance manquante. Auto-Déploiement en cache AppData...")
        self._set_splash_status("⬇ Téléchargement de FFmpeg (première utilisation)…")
        try:
            os.makedirs(APP_BIN_DIR, exist_ok=True)
            zip_path = os.path.join(APP_BIN_DIR, "ffm_deps.zip")
            urllib.request.urlretrieve(FFMPEG_URL, zip_path)
            self._set_splash_status("📦 Extraction de FFmpeg…")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for f_info in zip_ref.infolist():
                    if f_info.filename.endswith('ffmpeg.exe') or f_info.filename.endswith('ffprobe.exe') or f_info.filename.endswith('ffplay.exe'):
                        xp = zip_ref.extract(f_info, APP_BIN_DIR)
                        shutil.move(xp, os.path.join(APP_BIN_DIR, os.path.basename(xp)))

            os.remove(zip_path)
            for item in os.listdir(APP_BIN_DIR):
                ip = os.path.join(APP_BIN_DIR, item)
                if os.path.isdir(ip): shutil.rmtree(ip)

            self.ffmpeg_path = APP_BIN_DIR
            self._set_splash_status("✔ FFmpeg installé avec succès !")
            self._finalize_init("✅ Déploiement A/V réussi.")

        except Exception as e:
            self._set_splash_status(f"❌ Erreur FFmpeg : {str(e)[:50]}")
            self.log_message(f"❌ Échec de déploiement réseau. Code: {str(e)}")

    def _finalize_init(self, msg: str):
        self.log_message(msg)
        self.is_ready = True
        self.after(0, self._check_ready_state)
        self.after(200, self._show_main_window)  # Petit délai pour que l'utilisateur voie l'état final du splash

    def _show_main_window(self):
        """Ferme le splash et affiche la fenêtre principale."""
        try:
            if hasattr(self, 'splash') and self.splash and self.splash.winfo_exists():
                self.splash.destroy()
            self.splash = None
        except Exception:
            pass
        self.deiconify()
        self.lift()
        self.focus_force()

    def _check_ready_state(self):
        self.download_button.configure(text="📥 Télécharger la section ciblée")
        if self.video_duration > 0:
             self.download_button.configure(state="normal")
             self.play_btn.configure(state="normal")

    def _on_playlist_toggle(self):
        if self.playlist_mode.get():
            self.slider_start.configure(state="disabled")
            self.slider_end.configure(state="disabled")
            self.entry_start.configure(state="disabled")
            self.entry_end.configure(state="disabled")
            self.log_message("📋 Mode Playlist activé – rognage désactivé (non applicable sur une série de vidéos).")
        else:
            if self.video_duration > 0:
                self.slider_start.configure(state="normal")
                self.slider_end.configure(state="normal")
            self.entry_start.configure(state="normal")
            self.entry_end.configure(state="normal")
            self.log_message("🎬 Mode Vidéo Unique – rognage réactivé.")

    def _start_preview_thread(self):
        url = self.url_var.get().strip()
        if not url:
            self.log_message("⚠️ Saisissez une URL YouTube avant de charger l'aperçu.")
            return
        
        self.load_btn.configure(state="disabled")
        self.play_btn.configure(state="disabled")
        if self.playlist_mode.get():
            self.log_message(f"📋 Récupération des infos playlist : {url[:40]}...")
        else:
            self.log_message(f"🌐 Prise d'empreinte digitale : {url[:30]}...")
        threading.Thread(target=self._fetch_preview_task, args=(url,), daemon=True).start()

    def _play_video_preview(self):
        url = self.url_var.get().strip()
        if not url:
            return

        self.log_message("▶ Redirection native vers l'URL officielle...")
        try:
            import webbrowser
            webbrowser.open(url)
            self.log_message("✅ Onglet média déployé dans le navigateur par défaut.")
        except Exception as e:
            self.log_message(f"❌ Échec de la redirection: {str(e)}")

    def _fetch_preview_task(self, url):
        logger = YTDLPLogger(self.log_message)
        is_playlist = self.playlist_mode.get()
        ydl_opts = {
            'skip_download': True, 'quiet': False, 'no_warnings': True,
            'noplaylist': not is_playlist, 'logger': logger
        }
        if self.ffmpeg_path: ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if info is None:
                self.log_message("❌ Vidéo ou playlist inaccessible.")
                self.after(0, lambda: self.load_btn.configure(state="normal"))
                return

            # Mode playlist : afficher le résumé de la playlist
            if is_playlist and info.get('_type') == 'playlist':
                entries = info.get('entries', [])
                count = len(list(entries))
                title = info.get('title', 'Playlist Inconnue')
                self.log_message(f"✅ Playlist détectée : '{title}' — {count} vidéo(s) trouvée(s).")
                self.after(0, lambda: [
                    self.info_title.configure(text=f"📋 {title}"),
                    self.info_dur.configure(text=f"{count} vidéo(s) dans la playlist"),
                    self.img_label.configure(image=None, text=f"🎵 {count} pistes à télécharger"),
                    self.load_btn.configure(state="normal"),
                    self.download_button.configure(state="normal") if self.is_ready else None
                ])
                return
                
            self.video_metadata = info
            title = info.get('title', 'Titre Inconnu')
            duration = info.get('duration', 0)
            if not duration: duration = 0
            self.video_duration = int(duration)
            
            dur_str = format_seconds_to_time(self.video_duration)

            thumb_url = info.get('thumbnail')
            img = None
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=5)
                    if resp.status_code == 200:
                        raw_img = Image.open(io.BytesIO(resp.content))
                        img = ctk.CTkImage(light_image=raw_img, size=(280, 158))
                except Exception: pass

            self.after(0, self._update_preview_ui, title, dur_str, img)
            
        except Exception as e:
            self.log_message(f"❌ Exception Réseau : {str(e)}")
            self.after(0, lambda: self.load_btn.configure(state="normal"))

    def _update_preview_ui(self, title, dur_str, img_obj):
        self.info_title.configure(text=f"Titre: {title}")
        self.info_dur.configure(text=f"Durée Totale: {dur_str}")
        
        if img_obj:
            self.preview_image_ref = img_obj
            self.img_label.configure(image=img_obj, text="")
        else:
            self.img_label.configure(image=None, text="[Pas de visuel]")

        if self.video_duration > 0:
            self.slider_start.configure(state="normal", from_=0, to=self.video_duration)
            self.slider_end.configure(state="normal", from_=0, to=self.video_duration)
            self.slider_start.set(0)
            self.slider_end.set(self.video_duration)
            self.crop_start_var.set("00:00")
            self.crop_end_var.set(format_seconds_to_time(self.video_duration))
            
        self.load_btn.configure(state="normal")
        
        if self.is_ready:
            self.download_button.configure(state="normal")
            self.play_btn.configure(state="normal")
            self.log_message("✅ Prêt.")
        else:
            self.log_message("⏳ En attente de FFmpeg...")

    def _start_download_thread(self):
        if not self.is_ready: return

        out_path = self.output_dir.get().strip()
        ext = self.ext_var.get()

        # ── Mode BATCH (fichier .txt) ──────────────────────────────────────────
        if self.batch_urls:
            self.is_downloading = True
            self.download_button.configure(state="disabled")
            self.load_btn.configure(state="disabled")
            self.progress_bar.set(0.0)
            self.log_message(f"\n🚀 Démarrage du batch : {len(self.batch_urls)} lien(s) à télécharger...")
            threading.Thread(
                target=self._download_batch_task,
                args=(list(self.batch_urls), out_path, ext),
                daemon=True
            ).start()
            return

        # ── Mode INDIVIDUEL (URL unique) ───────────────────────────────────────
        url = self.url_var.get().strip()
        if not url:
            self.log_message("⚠️ Saisissez une URL ou chargez un fichier .txt de liens.")
            return

        is_playlist = self.playlist_mode.get()
        s_sec, e_sec = None, None

        if not is_playlist:
            s_sec = parse_time_to_seconds(self.crop_start_var.get())
            e_sec = parse_time_to_seconds(self.crop_end_var.get())
            if s_sec is not None and e_sec is not None and s_sec >= e_sec:
                messagebox.showerror("Cropping Invalide", "Temps inversé.")
                return

        self.is_downloading = True
        self.download_button.configure(state="disabled")
        self.load_btn.configure(state="disabled")
        self.progress_bar.set(0.0)

        if is_playlist:
            self.log_message("\n🚀 Téléchargement de la Playlist en cours (peut durer plusieurs minutes)...")
        else:
            self.log_message("\n🚀 Extraction cible en cours...")

        threading.Thread(target=self._download_task, args=(url, out_path, ext, s_sec, e_sec), daemon=True).start()

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                import re
                p_str = re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', '', p_str)
                pct = float(p_str) / 100.0
                self.after(0, lambda: self.progress_bar.set(pct))
            except Exception: pass
        elif d['status'] == 'finished':
            self.after(0, lambda: self.progress_bar.set(1.0))
            self.log_message("⏳ Téléchargement achevé, encodage en cours...")

    def _progress_hook_playlist(self, d):
        """Progress hook pour playlist : afficher le titre de chaque vidéo au lancement."""
        if d['status'] == 'downloading':
            try:
                p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                import re
                p_str = re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', '', p_str)
                pct = float(p_str) / 100.0
                self.after(0, lambda: self.progress_bar.set(pct))
            except Exception: pass
        elif d['status'] == 'finished':
            title = d.get('info_dict', {}).get('title', '?')
            self.log_message(f"✅ Encodé : {title}")

    def _download_batch_task(self, urls: list, output_path: str, ext: str):
        """Télécharge une liste d'URLs en séquence (mode batch fichier .txt)."""
        logger = YTDLPLogger(self.log_message)
        total = len(urls)
        is_audio = ext in ['mp3', 'wav', 'm4a', 'flac']

        for idx, url in enumerate(urls, 1):
            subfolder = get_platform_subfolder(url)
            final_output = os.path.join(output_path, subfolder)
            os.makedirs(final_output, exist_ok=True)
            self.log_message(f"\n⬇️  [{idx}/{total}] [{subfolder}] {url[:65]}{'...' if len(url) > 65 else ''}")

            def make_hook(current, tot):
                def hook(d):
                    if d['status'] == 'downloading':
                        try:
                            import re
                            p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                            p_str = re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', '', p_str)
                            pct_video = float(p_str) / 100.0
                            # Progression globale = (vidéos terminées + pct vidéo actuelle) / total
                            global_pct = ((current - 1) + pct_video) / tot
                            self.after(0, lambda v=global_pct: self.progress_bar.set(v))
                        except Exception:
                            pass
                    elif d['status'] == 'finished':
                        title = d.get('info_dict', {}).get('title', '?')
                        self.log_message(f"  ✅ Encodé : {title}")
                        global_pct = current / tot
                        self.after(0, lambda v=global_pct: self.progress_bar.set(v))
                return hook

            ydl_opts = {
                'outtmpl': os.path.join(final_output, '%(title)s.%(ext)s'),
                'writethumbnail': True,
                'logger': logger,
                'progress_hooks': [make_hook(idx, total)],
                'noplaylist': True,
                'noprogress': True,
                'ignoreerrors': True,
            }
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path

            if is_audio:
                ydl_opts['format'] = 'bestaudio/best'
                pa = [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': ext},
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata', 'add_metadata': True},
                ]
                if ext == 'mp3':
                    pa[0]['preferredquality'] = '0'
                ydl_opts['postprocessors'] = pa
            else:
                ydl_opts['format'] = f'bestvideo[ext={ext}]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
                ydl_opts['merge_output_format'] = ext
                ydl_opts['postprocessors'] = [
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata', 'add_metadata': True}
                ]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except yt_dlp.utils.DownloadError:
                self.log_message(f"  ❌ [{idx}/{total}] Échec DRM/Token pour cette URL, passage au suivant.")
            except Exception as e:
                self.log_message(f"  ❌ [{idx}/{total}] Erreur : {str(e)}, passage au suivant.")

        self.log_message(f"\n🎉 Batch terminé ! {total} lien(s) traité(s). Fichiers exportés dans : {output_path}")
        self.after(0, self._on_download_complete)

    def _download_task(self, url: str, output_path: str, ext: str, start_sec: float, end_sec: float):
        logger = YTDLPLogger(self.log_message)
        is_audio = ext in ['mp3', 'wav', 'm4a', 'flac']
        is_playlist = self.playlist_mode.get()

        hook = self._progress_hook_playlist if is_playlist else self._progress_hook

        # Dossier plateforme
        subfolder = get_platform_subfolder(url)
        final_output = os.path.join(output_path, subfolder)
        os.makedirs(final_output, exist_ok=True)
        self.log_message(f"📁 Dossier de sortie : {subfolder}/")

        ydl_opts = {
            'outtmpl': os.path.join(final_output, '%(playlist_index)s - %(title)s.%(ext)s' if is_playlist else '%(title)s.%(ext)s'),
            'writethumbnail': True, 'logger': logger, 'progress_hooks': [hook],
            'noplaylist': not is_playlist, 'noprogress': True,
            'ignoreerrors': True,  # Passe à la suivante si une vidéo est indisponible
        }

        if self.ffmpeg_path: ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        use_crop = False
        if start_sec is not None and start_sec > 0: use_crop = True
        if end_sec is not None and self.video_duration and end_sec < self.video_duration: use_crop = True

        if use_crop:
            def gen_range(info, ydl):
                s = start_sec if start_sec is not None else 0
                e = end_sec if end_sec is not None else float('inf')
                return [{'start_time': s, 'end_time': e}]
            ydl_opts['download_ranges'] = gen_range

        if is_audio:
            ydl_opts['format'] = 'bestaudio/best'
            pa = [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': ext},
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegMetadata', 'add_metadata': True},
            ]
            if ext == 'mp3': pa[0]['preferredquality'] = '0' 
            ydl_opts['postprocessors'] = pa
        else:
            ydl_opts['format'] = f'bestvideo[ext={ext}]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = ext
            ydl_opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata', 'add_metadata': True}]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.log_message(f"🎉 Rendu Terminé ! Fichier {ext.upper()} exporté.")
        except yt_dlp.utils.DownloadError as e: self.log_message("❌ Echec DRM ou Token serveur.")
        except Exception as e: self.log_message(f"❌ Erreur Interne : {str(e)}")
        finally: self.after(0, self._on_download_complete)

    def _on_download_complete(self):
        self.is_downloading = False
        self.download_button.configure(state="normal")
        self.load_btn.configure(state="normal")
        self.play_btn.configure(state="normal")

if __name__ == "__main__":
    app = UniversalStudioApp()
    app.mainloop()

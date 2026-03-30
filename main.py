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
        
        self.is_downloading = False
        self.is_ready = False
        self.ffmpeg_path = None
        self.video_metadata = None
        self.video_duration = 0 
        self.preview_image_ref = None 

        self._build_ui()
        
        self.crop_start_var.trace_add("write", self._on_text_crop_change)
        self.crop_end_var.trace_add("write", self._on_text_crop_change)

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

        self.url_label = ctk.CTkLabel(self.left_panel, text="Lien YouTube :", font=ctk.CTkFont(weight="bold"))
        self.url_label.pack(anchor="w")
        
        self.url_entry = ctk.CTkEntry(self.left_panel, textvariable=self.url_var, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.pack(fill="x", pady=(0, 10))

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
            self.log_message(f"\n⏳ Algorithme Geométrique lancé : 'Clone & Replace' sur ['{old_t}']...")
            out_pdf = os.path.join(self.output_dir.get(), "EDITION_" + os.path.basename(f))
            
            doc = fitz.open(f)
            flags = fitz.TEXT_MATCH_CASE if self.pdf_mod_case.get() else 0
            
            replaced_count = 0
            for page in doc:
                rects = page.search_for(old_t, flags=flags)
                page_dict = page.get_text("dict")
                
                for rect in rects:
                    # Valeurs de clonage par défaut
                    r_size, r_color, r_font = 11, (0, 0, 0), "helv"
                    
                    # Scanning géométrique d'intersection pour cloner la taille et couleur
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
                                            # Détection heuristique de la famille de police (Serif / Sans-Serif / MonoSpace)
                                            fn = s["font"].lower()
                                            if any(x in fn for x in ["times", "serif", "georgia", "garamond", "palatino", "cambria"]):
                                                r_font = "TiRo" # Times Roman
                                            elif any(x in fn for x in ["courier", "mono", "consolas", "typewriter"]):
                                                r_font = "Cour" # Courier
                                            else:
                                                r_font = "helv" # Helvetica (Standard Arial-like)
                                            break
                                            
                    # Redaction dessine la gomme numérique et tamponne la lettre avec clônage Taille+Couleur+Style
                    page.add_redact_annot(rect, text=new_t, fontname=r_font, fontsize=r_size, fill=(1,1,1), text_color=r_color, align=fitz.TEXT_ALIGN_LEFT)
                    replaced_count += 1
                if rects:
                    page.apply_redactions()

            if replaced_count > 0:
                doc.save(out_pdf, garbage=4, deflate=True)
                self.log_message(f"🎉 Substitution parfaite ! {replaced_count} retouches clonées (Style/Taille/Couleur).\nDocument : {out_pdf}")
            else:
                self.log_message("⚠️ Motif introuvable.")
                
            doc.close()
        except Exception as e: self.log_message(f"❌ Erreur PDF: {str(e)}")


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

    def _resolve_dependencies(self):
        self.log_message("🔍 Vérification intégrale système (FFmpeg & FFplay)...")
        sys_ffmpeg = shutil.which("ffmpeg")
        sys_ffplay = shutil.which("ffplay")
        if sys_ffmpeg and sys_ffplay:
            self.ffmpeg_path = os.path.dirname(sys_ffmpeg)
            self._finalize_init("✔️ Binaires natifs de traitement prêts.")
            return

        local_base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(local_base, "ffmpeg.exe")) and os.path.exists(os.path.join(local_base, "ffplay.exe")):
            self.ffmpeg_path = local_base
            self._finalize_init("✔️ Routines locales parées.")
            return

        appdata_ffmpeg = os.path.join(APP_BIN_DIR, "ffmpeg.exe")
        appdata_ffplay = os.path.join(APP_BIN_DIR, "ffplay.exe")
        if os.path.exists(appdata_ffmpeg) and os.path.exists(appdata_ffplay):
            self.ffmpeg_path = APP_BIN_DIR
            self._finalize_init("✔️ Moteur A/V persistant chargé.")
            return

        self.log_message("⚙️ Dépendance manquante. Auto-Déploiement en cache AppData...")
        try:
            os.makedirs(APP_BIN_DIR, exist_ok=True)
            zip_path = os.path.join(APP_BIN_DIR, "ffm_deps.zip")
            urllib.request.urlretrieve(FFMPEG_URL, zip_path)
            
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
            self._finalize_init("✅ Déploiement A/V réussi.")

        except Exception as e:
            self.log_message(f"❌ Échec de déploiement réseau. Code: {str(e)}")

    def _finalize_init(self, msg: str):
        self.log_message(msg)
        self.is_ready = True
        self.after(0, self._check_ready_state)

    def _check_ready_state(self):
        self.download_button.configure(text="📥 Télécharger la section ciblée")
        if self.video_duration > 0:
             self.download_button.configure(state="normal")
             self.play_btn.configure(state="normal")

    def _start_preview_thread(self):
        url = self.url_var.get().strip()
        if not url:
            self.log_message("⚠️ Saisissez une URL YouTube avant de charger l'aperçu.")
            return
        
        self.load_btn.configure(state="disabled")
        self.play_btn.configure(state="disabled")
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
        ydl_opts = {
            'skip_download': True, 'quiet': False, 'no_warnings': True, 'noplaylist': True, 'logger': logger
        }
        if self.ffmpeg_path: ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if info is None:
                self.log_message("❌ Vidéo cryptée.")
                self.after(0, lambda: self.load_btn.configure(state="normal"))
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
        url = self.url_var.get().strip()
        if not url: return

        s_sec = parse_time_to_seconds(self.crop_start_var.get())
        e_sec = parse_time_to_seconds(self.crop_end_var.get())
        
        if s_sec is not None and e_sec is not None:
            if s_sec >= e_sec:
                messagebox.showerror("Cropping Invalide", "Temps inversé.")
                return

        self.is_downloading = True
        self.download_button.configure(state="disabled")
        self.load_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.log_message("\n🚀 Extraction cible en cours...")

        out_path = self.output_dir.get().strip()
        ext = self.ext_var.get()
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

    def _download_task(self, url: str, output_path: str, ext: str, start_sec: float, end_sec: float):
        logger = YTDLPLogger(self.log_message)
        is_audio = ext in ['mp3', 'wav', 'm4a', 'flac']

        ydl_opts = {
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'writethumbnail': True, 'logger': logger, 'progress_hooks': [self._progress_hook],
            'noplaylist': True, 'noprogress': True
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

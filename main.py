import os
import sys
import shutil
import threading
import urllib.request
import zipfile
import io
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import requests
    from PIL import Image
    import customtkinter as ctk
    import yt_dlp
except ImportError:
    print("Dépendances manquantes. Lancez 'pip install customtkinter yt-dlp requests pillow'")
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

    def debug(self, msg):
        pass

    def warning(self, msg):
        # Ignore les alertes cosmétiques
        if "JavaScript runtime" in msg or "ffmpeg not found" in msg: 
            return
        self.log_callback(f"⚠️ AVERTISSEMENT: {msg}")

    def error(self, msg):
        self.log_callback(f"❌ ERREUR: {msg}")

def parse_time_to_seconds(t_str: str):
    if not t_str or not t_str.strip():
        return None
    parts = t_str.strip().split(':')
    try:
        if len(parts) == 3:
            return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0])*60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except ValueError:
        pass
    return None

def format_seconds_to_time(seconds: float):
    if seconds is None: return ""
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

class YouTubeConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader & Converter - Premium Slider Edition")
        self.geometry("880x640")
        self.resizable(False, False)

        settings = load_settings()
        saved_dir = settings.get("output_dir", os.path.expanduser("~\\Downloads"))
        
        self.output_dir = ctk.StringVar(value=saved_dir)
        self.url_var = ctk.StringVar()
        self.ext_var = ctk.StringVar(value="mp3")
        
        self.crop_start_var = ctk.StringVar()
        self.crop_end_var = ctk.StringVar()
        
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
        self.title_label = ctk.CTkLabel(self, text="Convertisseur YouTube Universel", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(pady=(15, 10))

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=5)

        self.left_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.right_panel = ctk.CTkFrame(self.main_container, width=340)
        self.right_panel.pack(side="right", fill="y")
        self.right_panel.pack_propagate(False)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self):
        self.url_label = ctk.CTkLabel(self.left_panel, text="Lien YouTube :", font=ctk.CTkFont(weight="bold"))
        self.url_label.pack(anchor="w")
        self.url_entry = ctk.CTkEntry(self.left_panel, textvariable=self.url_var, width=450, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.pack(fill="x", pady=(0, 10))

        self.load_btn = ctk.CTkButton(self.left_panel, text="🔍 Charger l'Aperçu", fg_color="#E07A5F", hover_color="#D16043", command=self._start_preview_thread)
        self.load_btn.pack(pady=5)

        self.format_label = ctk.CTkLabel(self.left_panel, text="Format Cible :")
        self.format_label.pack(anchor="w", pady=(10, 0))
        self.format_menu = ctk.CTkOptionMenu(
            self.left_panel,
            values=["mp3", "wav", "m4a", "flac", "mp4", "mkv", "webm"],
            variable=self.ext_var,
            width=200
        )
        self.format_menu.pack(anchor="w", pady=(0, 10))

        self.dir_label = ctk.CTkLabel(self.left_panel, text="Dossier MP3/Vidéo :")
        self.dir_label.pack(anchor="w")
        
        dir_subframe = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        dir_subframe.pack(fill="x", pady=(0, 15))
        self.dir_entry = ctk.CTkEntry(dir_subframe, textvariable=self.output_dir, state="disabled")
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.dir_button = ctk.CTkButton(dir_subframe, text="Parcourir", width=80, command=self._select_directory)
        self.dir_button.pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(self.left_panel)
        self.progress_bar.pack(fill="x", pady=(10, 5))
        self.progress_bar.set(0.0)

        self.log_textbox = ctk.CTkTextbox(self.left_panel, height=130, state="disabled")
        self.log_textbox.pack(fill="x", expand=True)

        self.download_button = ctk.CTkButton(self.left_panel, text="🔄 Initialisation Système...", font=ctk.CTkFont(weight="bold", size=15), height=40, state="disabled", command=self._start_download_thread)
        self.download_button.pack(fill="x", pady=15)

    def _build_right_panel(self):
        self.hdr_label = ctk.CTkLabel(self.right_panel, text="Rognage et Lecteur", font=ctk.CTkFont(weight="bold", size=16))
        self.hdr_label.pack(pady=(10, 5))

        self.img_label = ctk.CTkLabel(self.right_panel, text="[Insérez l'URL pour la miniature]", width=280, height=158, fg_color="gray20", corner_radius=8)
        self.img_label.pack(pady=5, padx=20)

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

        self.slider_start = ctk.CTkSlider(crop_frame, from_=0, to=1, command=self._on_start_slide, state="disabled", 
                                          button_color="#E07A5F", 
                                          progress_color="gray30", 
                                          fg_color="#E07A5F")
        self.slider_start.pack(fill="x", padx=10, pady=(10, 5))
        self.slider_start.set(0)

        self.slider_end = ctk.CTkSlider(crop_frame, from_=0, to=1, command=self._on_end_slide, state="disabled", 
                                        button_color="#E07A5F", 
                                        progress_color="#E07A5F", 
                                        fg_color="gray30")
        self.slider_end.pack(fill="x", padx=10, pady=(0, 15))
        self.slider_end.set(1)

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

    def _select_directory(self):
        d = filedialog.askdirectory(initialdir=self.output_dir.get(), title="Sélectionnez le dossier")
        if d: 
            self.output_dir.set(d)
            settings = load_settings()
            settings["output_dir"] = d
            save_settings(settings)

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
        # Si la prévisualisation est déjà chargée mais attendait les moteurs graphiques
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
        if not self.video_metadata or not url:
            return

        extractor = self.video_metadata.get('extractor', '').lower()
        vid_id = self.video_metadata.get('id')

        # Mode Web-Sandbox (Pour requêtes YouTube pures) - C'est la solution sécurisée 0-Bloatware
        if 'youtube' in extractor and vid_id:
            self.log_message("▶ Génération d'une Sandbox Web Sécure (Lecteur YouTube Interactif)...")
            try:
                html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>YT Universal - Lecteur Sécurisé</title>
    <style>
        body {{ margin: 0; padding: 0; background-color: #0f0f0f; overflow: hidden; }}
        iframe {{ width: 100vw; height: 100vh; border: none; }}
    </style>
</head>
<body>
    <iframe src="https://www.youtube.com/embed/{vid_id}?autoplay=1&rel=0&modestbranding=1" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>
</body>
</html>"""
                player_path = os.path.join(APP_DIR, "secure_player.html")
                with open(player_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                import webbrowser
                webbrowser.open(f"file:///{player_path.replace(chr(92), '/')}")
                self.log_message("✅ Lecteur interactif (Iframe) déployé.")
            except Exception as e:
                self.log_message(f"❌ Erreur Sandbox HTML: {str(e)}")
            return

        # Fallback de secours (FFplay) si ce n'est pas un lien YouTube mais un autre site
        if not self.ffmpeg_path:
            self.log_message("⚠️ Fichier 'ffplay.exe' introuvable dans les dépendances.")
            return

        self.play_btn.configure(state="disabled", text="▶ Lancement...")

        direct_url = None
        formats = self.video_metadata.get('formats', [])
        
        for f in formats:
            if str(f.get('format_id')) == '18':
                direct_url = f.get('url')
                break
                
        if not direct_url:
            for f in formats:
                if f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                    direct_url = f.get('url')
                    break

        if not direct_url:
            self.log_message("⚠️ Flux vidéo combiné introuvable.")
            self.play_btn.configure(state="normal", text="▶ Lire la vidéo")
            return

        # Utilitaire d'identification pour rassurer les pares-feux serveur distant
        headers = self.video_metadata.get('http_headers', {})
        user_agent = headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        self.log_message("▶ Ouverture du lecteur natif de secours (FFplay)...")
        def play_thread():
            try:
                cmd = [
                    os.path.join(self.ffmpeg_path, "ffplay.exe"),
                    "-window_title", "YT Universal - Aperçu Premium",
                    "-x", "640", "-y", "360",
                    "-autoexit",
                    "-user_agent", user_agent,
                    direct_url
                ]
                subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
                self.log_message("✅ Session de visionnage terminée.")
            except Exception as e:
                self.log_message(f"❌ Erreur critique mémoire: {str(e)}")
            finally:
                self.after(0, lambda: self.play_btn.configure(state="normal", text="▶ Lire la vidéo"))

        threading.Thread(target=play_thread, daemon=True).start()

    def _fetch_preview_task(self, url):
        logger = YTDLPLogger(self.log_message)
        
        ydl_opts = {
            'skip_download': True,
            'quiet': False,
            'no_warnings': True,
            'noplaylist': True,
            'logger': logger
        }
        if self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if info is None:
                self.log_message("❌ Vidéo cryptée ou restreinte.")
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
                except Exception as e:
                   pass

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
        
        # Blocage de sécurité de l'interface graphique : on attend que l'installation FFmpeg soit finalisée d'abord
        if self.is_ready:
            self.download_button.configure(state="normal")
            self.play_btn.configure(state="normal")
            self.log_message("✅ Prêt.")
        else:
            self.log_message("⏳ En attente de l'installation des moteurs FFmpeg en tâche de fond...")

    def _start_download_thread(self):
        if not self.is_ready: return
        
        url = self.url_var.get().strip()
        if not url:
            self.log_message("⚠️ URL absente.")
            return

        s_sec = parse_time_to_seconds(self.crop_start_var.get())
        e_sec = parse_time_to_seconds(self.crop_end_var.get())
        
        if s_sec is not None and e_sec is not None:
            if s_sec >= e_sec:
                messagebox.showerror("Cropping Invalide", "Le temps cible de fin doit excéder le temps initial.")
                return

        self.is_downloading = True
        self.download_button.configure(state="disabled")
        self.load_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.log_message("🚀 Extraction ciblée en cours...")

        out_path = self.output_dir.get().strip()
        ext = self.ext_var.get()
        threading.Thread(target=self._download_task, args=(url, out_path, ext, s_sec, e_sec), daemon=True).start()

    def _download_task(self, url: str, output_path: str, ext: str, start_sec: float, end_sec: float):
        logger = YTDLPLogger(self.log_message)
        is_audio = ext in ['mp3', 'wav', 'm4a', 'flac']

        ydl_opts = {
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'writethumbnail': True,
            'logger': logger,
            'progress_hooks': [self._progress_hook],
            'noplaylist': True,
            'noprogress': True
        }

        if self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        if start_sec is not None or end_sec is not None:
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

        except yt_dlp.utils.DownloadError as e:
            self.log_message("❌ YT-DLP: Echec DRM ou Token serveur.")
        except Exception as e:
            self.log_message(f"❌ Erreur Interne : {str(e)}")
        finally:
            self.after(0, self._on_download_complete)

    def _on_download_complete(self):
        self.is_downloading = False
        self.download_button.configure(state="normal")
        self.load_btn.configure(state="normal")
        self.play_btn.configure(state="normal")

if __name__ == "__main__":
    app = YouTubeConverterApp()
    app.mainloop()

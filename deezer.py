#!/usr/bin/env python3
"""
GUI do streamrip. Wyszukuje i dodaje do kolejki piosenki z serwisu deezer.com,
pozwala również wkleić i pobrać własny link do np. playlisty z deezer.
Program pozwala na pobieranie mp3 w jakości 128kbps wymaga wpisania do pliku konfiguracyjnego ARL.
Użytkownicy premium mogą pobierać nawet w jakości flac. W programie nie ma playera do odsłuchania utworu.
Shebang w windows musisz usunąć, a w linux ustawić na własną ścieżkę do python3.  
pip install brakujacy_modul
Autor: Remik
Wersja: 1.1.0
Instrukcja:
1) Uruchom: python deezer.py lub deezer.pyw
2) Zależności potrzebne do uruchomienia programu:
   pip install streamrip requests pyperclip
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import subprocess
from datetime import datetime
import os
import requests
import webbrowser
import pyperclip
import re
import sqlite3
import shutil
import tempfile
from pathlib import Path
import sys


# ─── Kolory motywu ────────────────────────────────────────────────────────────
CLR_ACCENT   = "#54aaef"
CLR_GREEN    = "#4CAF50"
CLR_BLUE     = "#2196F3"
CLR_ORANGE   = "#FF9800"
CLR_PURPLE   = "#9C27B0"
CLR_DEEP_PUR = "#673AB7"
CLR_RED      = "#F44336"
CLR_WHITE    = "white"

# ─── Czcionki ─────────────────────────────────────────────────────────────────
# Zmień BASE_FONT_SIZE żeby skalować całą aplikację naraz.
BASE_FONT_SIZE = 11

FONT_HEADER    = ("Arial", BASE_FONT_SIZE + 2, "bold")   # 13 – nagłówek
FONT_ENTRY     = ("Arial", BASE_FONT_SIZE + 1)            # 12 – pola tekstowe
FONT_BTN_MAIN  = ("Arial", BASE_FONT_SIZE,     "bold")   # 11 – przyciski główne
FONT_BTN_SMALL = ("Arial", BASE_FONT_SIZE - 1, "bold")   # 10 – ARL / StreamRip
FONT_LABEL     = ("Arial", BASE_FONT_SIZE - 1)            # 10 – etykiety
FONT_LIST      = ("Arial", BASE_FONT_SIZE)                # 11 – Treeview / Listbox
FONT_LOG       = ("Arial", BASE_FONT_SIZE - 1)            # 10 – log / status


def _dpi_scaling(root: tk.Tk) -> None:
    """
    Ustawia skalowanie DPI w sposób przenośny (Windows / Linux / macOS).
    Na Windows dodatkowo włącza świadomość DPI przez ctypes,
    żeby uniknąć rozmycia przy skalowaniu systemu 125 %/150 %.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            # Per-monitor DPI awareness (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    # Oblicz skalowanie na podstawie rozdzielczości ekranu
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        # Zakładamy, że "standardowy" ekran to 1920×1080
        scale = max(screen_w / 1920, screen_h / 1080)
        # Ogranicz do rozsądnego przedziału
        scale = max(0.9, min(scale, 1.8))
        root.tk.call("tk", "scaling", scale)
    except Exception:
        pass


class DeezerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Deezer Search & Download v1.1.0 by Remik")
        self.geometry("820x640")
        self.minsize(700, 560)

        # Skalowanie DPI – musi być przed build_ui
        _dpi_scaling(self)

        self.process = None
        self.search_results = []
        self.download_queue = []

        self._build_ui()
        self._create_context_menu()
        self._set_icon()

    # ──────────────────────────────────────────────────────────────────────────
    # Inicjalizacja
    # ──────────────────────────────────────────────────────────────────────────

    def _set_icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "deezer.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Nagłówek ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=CLR_ACCENT, height=36)
        header.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        header.grid_propagate(False)
        tk.Label(
            header,
            text="Deezer Search & Download",
            font=FONT_HEADER,
            fg=CLR_WHITE,
            bg=CLR_ACCENT,
        ).pack(pady=8)

        # ── Notebook (karty) ──────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        tab1 = tk.Frame(self.notebook)
        tab2 = tk.Frame(self.notebook)

        self.notebook.add(tab1, text="🔍  Wyszukiwarka")
        self.notebook.add(tab2, text="⬇️  Pobieranie & Log")

        self._build_tab_search(tab1)
        self._build_tab_download(tab2)

        # ── Pasek statusu ─────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Gotowy do wyszukiwania...")
        tk.Label(
            self,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor="w",
            font=FONT_LOG,
        ).grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 3))

    # ──────────────────────────────────────────────────────────────────────────
    # Karta 1 – Wyszukiwarka
    # ──────────────────────────────────────────────────────────────────────────

    def _build_tab_search(self, parent: tk.Frame):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Pole wyszukiwania
        search_frame = tk.LabelFrame(parent, text="Wyszukiwanie", padx=10, pady=8)
        search_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        search_frame.grid_columnconfigure(0, weight=1)

        tk.Label(search_frame, text="Wpisz tytuł utworu lub artystę:", font=FONT_LABEL).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        entry_frame = tk.Frame(search_frame)
        entry_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        entry_frame.grid_columnconfigure(1, weight=1)

        self.search_clear_btn = tk.Label(
            entry_frame,
            text="✕",
            fg=CLR_RED,
            font=FONT_ENTRY,
            cursor="hand2",
        )
        self.search_clear_btn.bind("<Button-1>", lambda _e: self._clear_search_entry())

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._toggle_search_clear_btn)

        self.search_entry = tk.Entry(entry_frame, font=FONT_ENTRY, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.search_entry.bind("<Return>", lambda _e: self.search_tracks())
        self._bind_context(self.search_entry)

        self.search_btn = tk.Button(
            entry_frame,
            text="🔍 Szukaj",
            command=self.search_tracks,
            bg=CLR_GREEN,
            fg=CLR_WHITE,
            font=FONT_BTN_MAIN,
        )
        self.search_btn.grid(row=0, column=2)

        # Wyniki wyszukiwania
        results_frame = tk.LabelFrame(parent, text="Wyniki wyszukiwania", padx=5, pady=5)
        results_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)

        # Styl czcionki dla Treeview
        style = ttk.Style()
        style.configure("Treeview", font=FONT_LIST, rowheight=int(BASE_FONT_SIZE * 2.2))
        style.configure("Treeview.Heading", font=FONT_BTN_SMALL)

        self.results_tree = ttk.Treeview(
            results_frame,
            columns=("Artist", "Title", "Album", "Duration"),
            show="headings",
        )
        for col, label, width in [
            ("Artist",   "Artysta", 160),
            ("Title",    "Tytuł",   210),
            ("Album",    "Album",   160),
            ("Duration", "Czas",     80),
        ]:
            self.results_tree.heading(col, text=label)
            self.results_tree.column(col, width=width)

        self.results_tree.grid(row=0, column=0, sticky="nsew")

        res_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        res_scroll.grid(row=0, column=1, sticky="ns")
        self.results_tree.configure(yscrollcommand=res_scroll.set)

        # Przyciski akcji
        btn_frame = tk.Frame(results_frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=6)

        tk.Button(
            btn_frame, text="📋 Kopiuj link", command=self.copy_track_link,
            bg=CLR_BLUE, fg=CLR_WHITE, font=FONT_LABEL,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame, text="🌐 Otwórz w przeglądarce", command=self.open_in_browser,
            bg=CLR_ORANGE, fg=CLR_WHITE, font=FONT_LABEL,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame, text="➕ Dodaj do kolejki", command=self.add_to_download_queue,
            bg=CLR_PURPLE, fg=CLR_WHITE, font=FONT_LABEL,
        ).pack(side="left", padx=5)

    # ──────────────────────────────────────────────────────────────────────────
    # Karta 2 – Pobieranie & Log
    # ──────────────────────────────────────────────────────────────────────────

    def _build_tab_download(self, parent: tk.Frame):
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # ── Ustawienia ────────────────────────────────────────────────────────
        settings_frame = tk.LabelFrame(parent, text="Ustawienia pobierania", padx=10, pady=8)
        settings_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        settings_frame.grid_columnconfigure(2, weight=1)

        tk.Label(settings_frame, text="Jakość (0–2):", font=FONT_LABEL).grid(row=0, column=0, sticky="w")
        self.quality_cb = ttk.Combobox(
            settings_frame, values=["0", "1", "2"], state="readonly", width=5,
            font=FONT_LABEL,
        )
        self.quality_cb.current(0)
        self.quality_cb.grid(row=0, column=1, padx=(4, 20), sticky="w")

        tk.Label(settings_frame, text="Zapisz do:", font=FONT_LABEL).grid(row=0, column=2, sticky="w")
        self.save_entry = tk.Entry(settings_frame, font=FONT_LABEL)
        self.save_entry.grid(row=0, column=3, sticky="ew", padx=(4, 4))
        settings_frame.grid_columnconfigure(3, weight=1)
        self._bind_context(self.save_entry)

        tk.Button(settings_frame, text="…", command=self.browse_folder, width=3).grid(
            row=0, column=4, padx=(0, 10)
        )

        # Przyciski ARL / StreamRip
        tool_frame = tk.Frame(settings_frame)
        tool_frame.grid(row=0, column=5, sticky="e")

        self.arl_button = tk.Button(
            tool_frame, text="ARL", command=self.handle_arl_extraction,
            font=FONT_BTN_SMALL, width=10, bg=CLR_GREEN, fg=CLR_WHITE,
        )
        self.arl_button.pack(side="left", padx=2)

        self.streamrip_button = tk.Button(
            tool_frame, text="StreamRip", command=self.handle_streamrip_update,
            font=FONT_BTN_SMALL, width=10, bg=CLR_GREEN, fg=CLR_WHITE,
        )
        self.streamrip_button.pack(side="left", padx=2)

        threading.Thread(target=self.check_streamrip_status, daemon=True).start()

        # ── Kolejka + własny link ─────────────────────────────────────────────
        queue_frame = tk.LabelFrame(parent, text="Kolejka pobierania", padx=8, pady=8)
        queue_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        queue_frame.grid_columnconfigure(0, weight=1)

        # Własny link Deezer
        link_row = tk.Frame(queue_frame)
        link_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        link_row.grid_columnconfigure(0, weight=1)

        tk.Label(link_row, text="Wklej link Deezer:", font=FONT_LABEL).pack(side="left")

        link_entry_wrap = tk.Frame(link_row)
        link_entry_wrap.pack(side="left", fill="x", expand=True, padx=(6, 0))
        link_entry_wrap.grid_columnconfigure(0, weight=1)

        self.link_entry = tk.Entry(link_entry_wrap, font=FONT_ENTRY)
        self.link_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._bind_context(self.link_entry)

        tk.Button(
            link_entry_wrap, text="➕ Dodaj link", command=self.add_link_to_queue,
            bg=CLR_DEEP_PUR, fg=CLR_WHITE, font=FONT_LABEL,
        ).grid(row=0, column=1)

        # Lista kolejki
        list_wrap = tk.Frame(queue_frame)
        list_wrap.grid(row=1, column=0, sticky="ew")
        list_wrap.grid_columnconfigure(0, weight=1)

        self.queue_listbox = tk.Listbox(list_wrap, height=10, font=FONT_LIST)
        self.queue_listbox.grid(row=0, column=0, sticky="ew")

        q_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.queue_listbox.yview)
        q_scroll.grid(row=0, column=1, sticky="ns")
        self.queue_listbox.configure(yscrollcommand=q_scroll.set)

        # Przyciski kolejki
        qbtn_frame = tk.Frame(queue_frame)
        qbtn_frame.grid(row=2, column=0, pady=(6, 0))

        tk.Button(
            qbtn_frame, text="📁 Wczytaj plik z linkami", command=self.load_links_from_file,
            bg=CLR_BLUE, fg=CLR_WHITE, font=FONT_LABEL,
        ).pack(side="left", padx=4)
        tk.Button(
            qbtn_frame, text="💾 Zapisz listę", command=self.save_queue_to_file,
            bg="#FF5722", fg=CLR_WHITE, font=FONT_LABEL,
        ).pack(side="left", padx=4)
        tk.Button(
            qbtn_frame, text="🗑️ Usuń zaznaczone", command=self.remove_from_queue,
            font=FONT_LABEL,
        ).pack(side="left", padx=4)
        tk.Button(
            qbtn_frame, text="🗑️ Wyczyść kolejkę", command=self.clear_queue,
            font=FONT_LABEL,
        ).pack(side="left", padx=4)

        # Pasek postępu
        self.progress = ttk.Progressbar(queue_frame, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        # Przyciski pobierania
        dl_btn_frame = tk.Frame(queue_frame)
        dl_btn_frame.grid(row=4, column=0, pady=(6, 0))

        self.download_button = tk.Button(
            dl_btn_frame, text="⬇️ Pobierz kolejkę", command=self.start_download,
            bg=CLR_GREEN, fg=CLR_WHITE, font=FONT_BTN_MAIN,
        )
        self.download_button.pack(side="left", padx=5)

        self.cancel_button = tk.Button(
            dl_btn_frame, text="❌ Anuluj", command=self.cancel_download,
            bg=CLR_RED, fg=CLR_WHITE, font=FONT_BTN_MAIN, state=tk.DISABLED,
        )
        self.cancel_button.pack(side="left", padx=5)

        # ── Log ───────────────────────────────────────────────────────────────
        log_frame = tk.LabelFrame(parent, text="Log", padx=5, pady=5)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_output = scrolledtext.ScrolledText(log_frame, state="normal", wrap="word", height=4, font=FONT_LOG)
        self.log_output.grid(row=0, column=0, sticky="nsew")
        self._bind_context(self.log_output)

    # ──────────────────────────────────────────────────────────────────────────
    # Menu kontekstowe
    # ──────────────────────────────────────────────────────────────────────────

    def _create_context_menu(self):
        self.ctx_menu = tk.Menu(self, tearoff=0)
        self.ctx_menu.add_command(label="Wytnij",           command=lambda: self._context_action("cut"))
        self.ctx_menu.add_command(label="Kopiuj",           command=lambda: self._context_action("copy"))
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Wklej",            command=lambda: self._context_action("paste"))
        self.ctx_menu.add_command(label="Zaznacz wszystko", command=lambda: self._context_action("select_all"))

    def _bind_context(self, widget):
        widget.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        self.ctx_widget = event.widget
        try:
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx_menu.grab_release()

    def _context_action(self, action):
        try:
            if action == "cut":
                self.ctx_widget.event_generate("<<Cut>>")
            elif action == "copy":
                self.ctx_widget.event_generate("<<Copy>>")
            elif action == "paste":
                self.ctx_widget.event_generate("<<Paste>>")
            elif action == "select_all":
                self.ctx_widget.event_generate("<<SelectAll>>")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Wyszukiwanie
    # ──────────────────────────────────────────────────────────────────────────

    def _toggle_search_clear_btn(self, *_args):
        if self.search_var.get():
            self.search_clear_btn.grid(row=0, column=0, padx=(0, 4))
        else:
            self.search_clear_btn.grid_remove()

    def _clear_search_entry(self):
        self.search_entry.delete(0, tk.END)
        self.search_entry.focus_set()

    def search_tracks(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Błąd", "Wpisz zapytanie!")
            return
        self.status_var.set("Wyszukiwanie…")
        self.search_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query):
        try:
            r = requests.get(
                "https://api.deezer.com/search",
                params={"q": query, "limit": 50},
                timeout=10,
            )
            r.raise_for_status()
            items = r.json().get("data", [])
            self.after(0, self._update_search_results, items)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Błąd", f"Błąd wyszukiwania:\n{e}"))
        finally:
            self.after(0, lambda: self.search_btn.config(state=tk.NORMAL))

    def _update_search_results(self, items):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.search_results = []

        for track in items:
            title    = track.get("title", "")
            artist   = track.get("artist", {}).get("name", "")
            album    = track.get("album",  {}).get("title", "")
            duration = track.get("duration", 0)
            track_id = track.get("id")
            if not track_id:
                continue

            dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"
            item_id = self.results_tree.insert("", "end", values=(artist, title, album, dur_str))
            self.search_results.append({
                "id":      track_id,
                "title":   title,
                "artist":  artist,
                "album":   album,
                "duration": duration,
                "tree_id": item_id,
                "url":     f"https://www.deezer.com/pl/track/{track_id}",
            })

        self.status_var.set(f"Znaleziono {len(self.search_results)} utworów")

    def get_selected_track(self):
        selection = self.results_tree.selection()
        if not selection:
            return None
        tree_id = selection[0]
        for track in self.search_results:
            if track["tree_id"] == tree_id:
                return track
        return None

    def copy_track_link(self):
        track = self.get_selected_track()
        if not track:
            messagebox.showwarning("Błąd", "Wybierz utwór z listy!")
            return
        pyperclip.copy(track["url"])
        messagebox.showinfo("Skopiowano", f"Link skopiowany:\n{track['url']}")

    def open_in_browser(self):
        track = self.get_selected_track()
        if not track:
            messagebox.showwarning("Błąd", "Wybierz utwór z listy!")
            return
        webbrowser.open(track["url"])

    def add_to_download_queue(self):
        track = self.get_selected_track()
        if not track:
            messagebox.showwarning("Błąd", "Wybierz utwór z listy!")
            return
        for item in self.download_queue:
            if item["url"] == track["url"]:
                messagebox.showinfo("Informacja", "Ten utwór już jest w kolejce!")
                return
        self.download_queue.append(track)
        self.queue_listbox.insert(tk.END, f"{track['artist']} – {track['title']}")
        self.status_var.set(f"Dodano do kolejki. Razem: {len(self.download_queue)} utworów")

    # ──────────────────────────────────────────────────────────────────────────
    # Obsługa linków Deezer
    # ──────────────────────────────────────────────────────────────────────────

    def normalize_deezer_url(self, url):
        patterns = [
            (r"deezer\.com/(?:[a-z]{2}/)?track/(\d+)",    "track"),
            (r"deezer\.com/(?:[a-z]{2}/)?album/(\d+)",    "album"),
            (r"deezer\.com/(?:[a-z]{2}/)?playlist/(\d+)", "playlist"),
        ]
        for pattern, resource_type in patterns:
            match = re.search(pattern, url)
            if match:
                return f"https://www.deezer.com/pl/{resource_type}/{match.group(1)}"
        return None

    def extract_track_info_from_url(self, url):
        return self.normalize_deezer_url(url)

    def add_link_to_queue(self):
        url = self.link_entry.get().strip()
        if not url:
            messagebox.showwarning("Błąd", "Wklej link Deezer!")
            return
        if "deezer.com" not in url.lower():
            messagebox.showwarning("Błąd", "To nie jest prawidłowy link Deezer!")
            return
        validated_url = self.extract_track_info_from_url(url)
        if not validated_url:
            messagebox.showwarning("Błąd", "Nieprawidłowy format linku Deezer!")
            return
        for item in self.download_queue:
            if item["url"] == validated_url:
                messagebox.showinfo("Informacja", "Ten link już jest w kolejce!")
                return
        track_item = {
            "url":    validated_url,
            "title":  "Link Deezer",
            "artist": "Nieznany",
            "album":  "Nieznany",
            "id":     url.split("/")[-1] if "/" in url else "unknown",
        }
        self.download_queue.append(track_item)
        self.queue_listbox.insert(tk.END, f"Link Deezer: {validated_url}")
        self.link_entry.delete(0, tk.END)
        self.status_var.set(f"Dodano link do kolejki. Razem: {len(self.download_queue)} utworów")

    # ──────────────────────────────────────────────────────────────────────────
    # Zarządzanie kolejką
    # ──────────────────────────────────────────────────────────────────────────

    def remove_from_queue(self):
        selection = self.queue_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.queue_listbox.delete(index)
        self.download_queue.pop(index)
        self.status_var.set(f"Kolejka: {len(self.download_queue)} utworów")

    def clear_queue(self):
        self.queue_listbox.delete(0, tk.END)
        self.download_queue = []
        self.status_var.set("Kolejka wyczyszczona")

    def save_queue_to_file(self):
        if not self.download_queue:
            messagebox.showwarning("Błąd", "Kolejka pobierania jest pusta!")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            title="Zapisz listę linków",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for track in self.download_queue:
                    f.write(f"{track['url']}\n")
            messagebox.showinfo("Sukces", f"Zapisano {len(self.download_queue)} linków do:\n{file_path}")
            self.log(f"Zapisano kolejkę ({len(self.download_queue)} linków) do: {file_path}\n")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można zapisać pliku:\n{e}")
            self.log(f"Błąd zapisu pliku: {e}\n")

    def load_links_from_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            title="Wczytaj plik z linkami",
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            added = skipped = 0
            for line in lines:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                if "deezer.com" not in url.lower():
                    skipped += 1
                    self.log(f"Pominięto nieprawidłowy link: {url}\n")
                    continue
                validated_url = self.extract_track_info_from_url(url)
                if not validated_url:
                    skipped += 1
                    self.log(f"Pominięto nieprawidłowy format: {url}\n")
                    continue
                if any(item["url"] == validated_url for item in self.download_queue):
                    skipped += 1
                    continue
                self.download_queue.append({
                    "url":    validated_url,
                    "title":  "Link Deezer",
                    "artist": "Nieznany",
                    "album":  "Nieznany",
                    "id":     url.split("/")[-1] if "/" in url else "unknown",
                })
                self.queue_listbox.insert(tk.END, f"Link Deezer: {validated_url}")
                added += 1

            msg = f"Wczytano {added} linków z pliku"
            if skipped:
                msg += f"\nPominięto: {skipped}"
            messagebox.showinfo("Wczytano plik", msg)
            self.log(f"Wczytano {added} linków z pliku: {file_path}\n")
            self.status_var.set(f"Kolejka: {len(self.download_queue)} utworów")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można wczytać pliku:\n{e}")
            self.log(f"Błąd wczytywania pliku: {e}\n")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_entry.delete(0, tk.END)
            self.save_entry.insert(0, folder)

    # ──────────────────────────────────────────────────────────────────────────
    # Pobieranie
    # ──────────────────────────────────────────────────────────────────────────

    def start_download(self):
        if not self.download_queue:
            messagebox.showwarning("Błąd", "Kolejka pobierania jest pusta!")
            return
        quality = self.quality_cb.get()
        save_to = self.save_entry.get().strip()
        self.download_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.progress.start(10)
        threading.Thread(target=self._download_worker, args=(quality, save_to), daemon=True).start()

    def _download_worker(self, quality, save_to):
        try:
            for i, track in enumerate(self.download_queue):
                if self.process and self.process.poll() is None:
                    break
                self.after(0, lambda i=i: self.status_var.set(
                    f"Pobieranie {i + 1}/{len(self.download_queue)}…"
                ))
                url = track["url"]
                cmd = ["rip", "-ndb", "-q", quality, "--no-progress"]
                if save_to:
                    cmd += ["-f", save_to]
                cmd += ["url", url]

                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                )
                for line in self.process.stdout:
                    self.after(0, lambda msg=line: self.log(msg))

                ret = self.process.wait()
                if ret != 0:
                    self.after(0, lambda u=url: self.log(f"Błąd pobierania: {u}\n"))
                else:
                    self.after(0, lambda u=url: self.log(f"Pobrano: {u}\n"))
        except Exception as e:
            self.after(0, lambda: self.log(f"Błąd podczas pobierania: {e}\n"))
        finally:
            self.after(0, self._download_finished)

    def cancel_download(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.log("Pobieranie przerwane przez użytkownika.\n")

    def _download_finished(self):
        self.progress.stop()
        self.download_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)
        self.process = None
        self.status_var.set("Pobieranie zakończone")
        self.log("Pobieranie kolejki zakończone.\n")

    # ──────────────────────────────────────────────────────────────────────────
    # Log
    # ──────────────────────────────────────────────────────────────────────────

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in message.rstrip().splitlines():
            self.log_output.insert(tk.END, f"[{timestamp}] {line}\n")
        self.log_output.see(tk.END)

    # ──────────────────────────────────────────────────────────────────────────
    # StreamRip – status i aktualizacja
    # ──────────────────────────────────────────────────────────────────────────

    def check_streamrip_status(self):
        try:
            if os.name == "nt":
                cmd = 'py -m pip list --outdated | findstr /i "streamrip"'
            else:
                cmd = 'pip list --outdated | grep -i streamrip'
            process = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if process.returncode == 0 and process.stdout.strip():
                self.after(0, lambda: self.streamrip_button.config(
                    bg=CLR_RED, fg=CLR_WHITE, text="StreamRip⬆️"))
                self.after(0, lambda: self.log("StreamRip – dostępna aktualizacja\n"))
            else:
                self.after(0, lambda: self.streamrip_button.config(
                    bg=CLR_GREEN, fg=CLR_WHITE, text="StreamRip✅"))
                self.after(0, lambda: self.log("StreamRip – aktualny\n"))
        except subprocess.TimeoutExpired:
            self.after(0, lambda: self.streamrip_button.config(
                bg=CLR_ORANGE, fg=CLR_WHITE, text="StreamRip?"))
            self.after(0, lambda: self.log("StreamRip – timeout sprawdzania\n"))
        except Exception as e:
            self.after(0, lambda: self.streamrip_button.config(
                bg="#9E9E9E", fg=CLR_WHITE, text="StreamRip"))
            self.after(0, lambda: self.log(f"StreamRip – błąd sprawdzania: {e}\n"))

    def handle_streamrip_update(self):
        if self.streamrip_button.cget("bg") == CLR_RED:
            self.update_streamrip()
        else:
            self.streamrip_button.config(text="Sprawdzam…", state=tk.DISABLED)
            threading.Thread(target=self._recheck_and_enable, daemon=True).start()

    def _recheck_and_enable(self):
        self.check_streamrip_status()
        self.after(0, lambda: self.streamrip_button.config(state=tk.NORMAL))

    def update_streamrip(self):
        self.streamrip_button.config(text="Aktualizuję…", state=tk.DISABLED, bg=CLR_ORANGE)
        self.log("Rozpoczęcie aktualizacji StreamRip…\n")
        threading.Thread(target=self._update_streamrip_worker, daemon=True).start()

    def _update_streamrip_worker(self):
        try:
            cmd = (
                ["py", "-m", "pip", "install", "--upgrade", "streamrip"]
                if os.name == "nt"
                else ["pip", "install", "--upgrade", "streamrip"]
            )
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            for line in process.stdout:
                self.after(0, lambda msg=line: self.log(f"[UPDATE] {msg}"))
            ret = process.wait()
            if ret == 0:
                self.after(0, lambda: self.log("✅ StreamRip zaktualizowany pomyślnie!\n"))
                self.after(1000, lambda: threading.Thread(
                    target=self.check_streamrip_status, daemon=True).start())
            else:
                self.after(0, lambda: self.log("❌ Błąd podczas aktualizacji StreamRip\n"))
        except Exception as e:
            self.after(0, lambda: self.log(f"❌ Błąd aktualizacji StreamRip: {e}\n"))
        finally:
            self.after(0, lambda: self.streamrip_button.config(state=tk.NORMAL))

    # ──────────────────────────────────────────────────────────────────────────
    # StreamRip – konfiguracja (config.toml)
    # ──────────────────────────────────────────────────────────────────────────

    def find_streamrip_config(self):
        possible_paths = [
            os.path.expanduser("~/.config/streamrip/config.toml"),
            os.path.join(os.environ.get("APPDATA", ""), "streamrip", "config.toml"),
            os.path.join(os.environ.get("USERPROFILE", ""), ".config", "streamrip", "config.toml"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    def update_streamrip_config(self, arl):
        config_path = self.find_streamrip_config()
        if not config_path:
            self.log("⚠️  Nie znaleziono pliku config.toml StreamRip\n")
            self.log("Uruchom najpierw StreamRip aby utworzyć config:\n")
            self.log("   rip config --open\n")
            return False
        self.log(f"✅ Znaleziono config.toml: {config_path}\n")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()
            backup_path = config_path + ".backup"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(config_content)
            self.log(f"💾 Utworzono backup: {backup_path}\n")

            pattern = r'(arl\s*=\s*")[^"]*(")'
            if re.search(pattern, config_content):
                new_content = re.sub(pattern, f"\\g<1>{arl}\\g<2>", config_content)
                self.log("✅ Zaktualizowano istniejącą wartość ARL\n")
            elif "[deezer]" in config_content:
                new_content = re.sub(
                    r"(\[deezer\]\n)",
                    f'\\1arl = "{arl}"\n',
                    config_content,
                )
                self.log("✅ Dodano wartość ARL do sekcji [deezer]\n")
            else:
                self.log("⚠️  Nie znaleziono sekcji [deezer] w config.toml\n")
                return False

            with open(config_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            self.log(f"   ARL: {arl[:30]}…{arl[-10:]}\n")
            return True
        except Exception as e:
            self.log(f"❌ Błąd aktualizacji config.toml: {e}\n")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # ARL – odczyt z Firefox
    # ──────────────────────────────────────────────────────────────────────────

    def find_firefox_profile(self):
        if os.name == "nt":
            firefox_path = os.path.join(os.environ["APPDATA"], "Mozilla", "Firefox", "Profiles")
        elif sys.platform == "darwin":
            firefox_path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        else:
            firefox_path = os.path.expanduser("~/.mozilla/firefox")

        if not os.path.exists(firefox_path):
            return None

        profiles = [
            os.path.join(firefox_path, item)
            for item in os.listdir(firefox_path)
            if os.path.isdir(os.path.join(firefox_path, item))
            and os.path.exists(os.path.join(firefox_path, item, "cookies.sqlite"))
        ]
        if not profiles:
            return None

        for profile in profiles:
            if "default-release" in profile.lower() or "default" in profile.lower():
                return profile
        return profiles[0]

    def get_arl_from_firefox(self):
        profile_path = self.find_firefox_profile()
        if not profile_path:
            self.log("❌ Nie znaleziono profilu Firefox\n")
            return None
        self.log(f"✅ Znaleziono profil Firefox: {os.path.basename(profile_path)}\n")

        cookies_path = os.path.join(profile_path, "cookies.sqlite")
        if not os.path.exists(cookies_path):
            self.log(f"❌ Nie znaleziono pliku cookies: {cookies_path}\n")
            return None
        self.log("✅ Znaleziono plik cookies\n")
        self.log("[Firefox] Odczyt cookie 'arl'…\n")

        temp_cookies = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        temp_cookies.close()
        try:
            shutil.copy2(cookies_path, temp_cookies.name)
        except Exception as e:
            self.log(f"❌ Nie można skopiować cookies (Firefox otwarty?): {e}\n")
            return None

        try:
            conn = sqlite3.connect(temp_cookies.name)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            table = "moz_cookies" if "moz_cookies" in tables else "cookies"
            cursor.execute(
                f"SELECT value FROM {table} WHERE host LIKE '%deezer.com%' AND name = 'arl'"
            )
            result = cursor.fetchone()
            conn.close()
            os.unlink(temp_cookies.name)

            if result and result[0]:
                self.log("✅ Znaleziono cookie 'arl'!\n")
                return result[0]
            else:
                self.log("❌ Nie znaleziono cookie 'arl' w Firefox\n")
                self.log("Upewnij się, że jesteś zalogowany na deezer.com w Firefox\n")
                return None
        except Exception as e:
            self.log(f"❌ Błąd odczytu SQLite: {e}\n")
            try:
                os.unlink(temp_cookies.name)
            except Exception:
                pass
            return None

    def handle_arl_extraction(self):
        self.arl_button.config(state=tk.DISABLED, text="Pobieram ARL…")
        self.log("=" * 60 + "\n")
        self.log("ODCZYT COOKIE 'arl' Z DEEZER (Firefox)\n")
        self.log("=" * 60 + "\n")
        threading.Thread(target=self._arl_extraction_worker, daemon=True).start()

    def _arl_extraction_worker(self):
        try:
            arl = self.get_arl_from_firefox()
            self.after(0, lambda: self.log("=" * 60 + "\n"))

            if arl and len(arl) > 50:
                self.after(0, lambda: self.log("✅ SUCCESS!\n"))
                output_file = os.path.join(os.path.dirname(__file__), "arl.txt")
                try:
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(arl)
                    self.after(0, lambda: self.log(f"📁 Zapisano do pliku: {output_file}\n"))
                except Exception as e:
                    self.after(0, lambda: self.log(f"⚠️  Nie można zapisać do pliku: {e}\n"))

                success = self.update_streamrip_config(arl)
                if success:
                    self.after(0, lambda: self.log("🎉 GOTOWE! StreamRip jest skonfigurowany!\n"))
                    self.after(0, lambda: messagebox.showinfo(
                        "Sukces", "ARL został pomyślnie odczytany i zapisany do config.toml!"))
                else:
                    self.after(0, lambda: self.log(
                        f'Ręczna konfiguracja: rip config --open → [deezer] arl = "{arl}"\n'))
                    self.after(0, lambda: messagebox.showwarning(
                        "Częściowy sukces",
                        f"ARL odczytany, ale nie znaleziono config.toml.\n\nARL: {arl[:50]}…\n\nZapisz ręcznie.",
                    ))
            else:
                self.after(0, lambda: self.log("❌ NIE UDAŁO SIĘ ODCZYTAĆ ARL\n"))
                self.after(0, lambda: messagebox.showerror(
                    "Błąd",
                    "Nie udało się odczytać ARL z Firefox.\n\n"
                    "Upewnij się, że:\n"
                    "– Firefox jest zainstalowany\n"
                    "– Jesteś zalogowany na deezer.com w Firefox\n"
                    "– Masz konto PREMIUM\n"
                    "– Firefox jest zamknięty",
                ))
        except Exception as e:
            self.after(0, lambda: self.log(f"❌ NIEOCZEKIWANY BŁĄD: {e}\n"))
            self.after(0, lambda: messagebox.showerror("Błąd", f"Wystąpił błąd:\n{e}"))
        finally:
            self.after(0, lambda: self.arl_button.config(state=tk.NORMAL, text="ARL"))


if __name__ == "__main__":
    app = DeezerApp()
    app.mainloop()

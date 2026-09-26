#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plaso_gui.py - Grafische Oberfläche für den Plaso Docker Helper
Reines Tkinter – keine externen Abhängigkeiten nötig.
"""

import os
import re
import sys
import time
import queue
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ══════════════════════════════════════════════════════════════════════════
#  Parser-Katalog
# ══════════════════════════════════════════════════════════════════════════

def build_catalog():
    return {
        "presets": ("Presets & Kombinationen", [
            ("win10",     "Windows 10/11 – Registry, EVTX, MFT, Prefetch, Browser", []),
            ("win8",      "Windows 8/8.1 – Kombination", []),
            ("win7",      "Windows 7 – Registry, EVTX, Prefetch, LNK", []),
            ("win7_slow", "Windows 7 inkl. ESE + MFT (langsam)", []),
            ("winxp",     "Windows XP – EVT, Recycle.INFO2", []),
            ("winxp_slow","Windows XP inkl. ESE + MFT", []),
            ("win_gen",   "Generische Windows-Artefakte", []),
            ("webhist",   "Browser-Verlauf (alle Browser)", []),
            ("linux",     "Linux – Systemd, Bash, APT, Syslog", []),
            ("macos",     "macOS – FSEvents, TCC, Plist", []),
            ("ios",       "iOS – App Privacy, iMessage", []),
            ("android",   "Android – AppUsage, Calls, SMS", []),
            ("atlassian", "Atlassian – Confluence, Jira, Bitbucket", []),
            ("mactime",   "SleuthKit bodyfile", []),
        ]),
        "windows": ("Windows-Kern", [
            ("winevtx", "Windows EventLog (EVTX) – XML-Ereignisprotokolle ab Vista", []),
            ("winevt",  "Alte Windows EventLogs (EVT) – XP/2003-Format", []),
            ("winreg",  "Windows Registry – NTUSER.DAT, SYSTEM, SOFTWARE, SAM, SECURITY, USRCLASS", [
                ("winreg/amcache",         "AmCache.hve – Programmausführung, SHA1-Hashes"),
                ("winreg/appcompatcache",  "AppCompatCache / ShimCache – Programm-Kompatibilität"),
                ("winreg/bam",             "Background Activity Moderator – App-Ausführung"),
                ("winreg/userassist",      "UserAssist – GUI-Programme mit Ausführungszähler"),
                ("winreg/usbdevices",      "USB-Geräte-Verbindungen mit Zeitstempeln"),
                ("winreg/usbstor_devices", "USBStor – Massenspeicher-Historie"),
                ("winreg/network_drives",  "Zuletzt verbundene Netzlaufwerke"),
                ("winreg/networks",        "Bekannte Netzwerke (NetworkList)"),
                ("winreg/mstsc_rdp",       "RDP-Client-Verbindungen"),
                ("winreg/mstsc_rdp_mru",   "RDP MRU-Historie"),
                ("winreg/bagmru",          "ShellBags (BagMRU) – Ordnernavigation"),
                ("winreg/windows_run",     "Autostart-Einträge (Run / RunOnce)"),
                ("winreg/windows_services","Dienste & Treiber mit Starttyp"),
                ("winreg/windows_shutdown","Letzter Shutdown/Start"),
                ("winreg/windows_timezone","Aktive Zeitzone"),
                ("winreg/windows_version", "Installierte Windows-Version"),
                ("winreg/winlogon",        "Logon-Einstellungen und Shell"),
                ("winreg/microsoft_office_mru",  "Office MRU-Listen"),
                ("winreg/microsoft_outlook_mru", "Outlook Search MRU"),
                ("winreg/windows_task_cache",    "Task Scheduler Cache"),
                ("winreg/windows_sam_users",     "SAM Users – lokale Benutzerkonten"),
                ("winreg/explorer_mountpoints2", "Explorer MountPoints2 – Laufwerks-Mounts"),
                ("winreg/explorer_programscache","Explorer Programs Cache"),
                ("winreg/ccleaner",              "CCleaner-Nutzung"),
                ("winreg/winreg_default",        "Sonstige Registry-Werte"),
            ]),
            ("mft",          "NTFS $MFT – Master File Table mit allen Datei-Metadaten", []),
            ("usnjrnl",      "NTFS USN Change Journal – Dateiänderungen seit $UsnJrnl-Erstellung", []),
            ("prefetch",     "Windows Prefetch – Ausführungsnachweise mit Laufzeiten", []),
            ("lnk",          "Windows Shortcuts (LNK) – Verknüpfungsdateien mit Zielpfaden", []),
            ("winjob",       "Geplante Tasks – Job-Dateien des Task Scheduler", []),
            ("recycle_bin",  "Papierkorb ($Recycle.Bin $I) – gelöschte Dateien", []),
            ("custom_destinations","Jump Lists – Anwendungsverlauf pro App", []),
            ("rplog",        "System Restore Points (rp.log)", []),
            ("windefender_history","Windows Defender DetectionHistory", []),
            ("filestat",     "Dateisystem-Statistiken – MACB-Zeiten", []),
            ("pe",           "Portable Executables – PE-Header-Informationen", []),
            ("bodyfile",     "SleuthKit v3 bodyfile", []),
        ]),
        "browser": ("Browser & Web", [
            ("chrome_cache",       "Chrome Cache – gecachte Web-Inhalte", []),
            ("chrome_preferences", "Chrome Preferences – Einstellungen", []),
            ("firefox_cache",      "Firefox Cache v1 (≤ 31)", []),
            ("firefox_cache2",     "Firefox Cache v2 (≥ 32)", []),
            ("msiecf",             "Internet Explorer Cache (index.dat)", []),
            ("opera_global",       "Opera global history", []),
            ("opera_typed_history","Opera typed history – manuell eingegebene URLs", []),
            ("binary_cookies",     "Safari Binary Cookies", []),
            ("java_idx",           "Java WebStart Cache IDX", []),
        ]),
        "mobile": ("Mobile (iOS / Android)", [
            ("android_app_usage", "Android usage-history.xml – App-Nutzung", []),
            ("discord_ios",       "iOS Discord Nachrichten", []),
            ("unified_logging",   "Apple Unified Logging (tracev3)", []),
            ("sqlite", "SQLite – mobile App-Datenbanken", [
                ("sqlite/android_calls",   "Android Anrufhistorie (contacts2.db)"),
                ("sqlite/android_sms",     "Android SMS/MMS (mmssms.db)"),
                ("sqlite/android_turbo",   "Android Turbo (Facebook Messenger)"),
                ("sqlite/android_webview", "Android WebView-Historie"),
                ("sqlite/imessage",        "Apple iMessage (chat.db, sms.db)"),
                ("sqlite/ios_accounts",    "iOS Accounts (Accounts3.db)"),
                ("sqlite/ios_health",      "iOS Health-Datenbank"),
                ("sqlite/ios_notes",       "iOS Notes"),
                ("sqlite/ios_powerlog",    "iOS PowerLog (CurrentPowerlog.PLSQL)"),
                ("sqlite/ios_screentime",  "iOS Screen Time (RMAdminStore-Local.sqlite)"),
                ("sqlite/kik_ios",         "iOS Kik Messenger (kik.sqlite)"),
                ("sqlite/twitter_ios",     "iOS Twitter (twitter.db)"),
                ("sqlite/instagram_ios",   "iOS Instagram (threads-DB)"),
            ]),
        ]),
        "macos": ("macOS", [
            ("asl_log",          "Apple System Log (ASL) – Systemprotokoll", []),
            ("bsm_log",          "Basic Security Module (BSM) – Audit-Trail", []),
            ("fseventsd",        "File System Events – Dateiänderungen", []),
            ("mac_keychain",     "Keychain-Datenbank – Passwörter und Zertifikate", []),
            ("spotlight_storedb","Spotlight store.db – Suchindex", []),
            ("utmpx",            "utmpx Login-Datensätze – Benutzeranmeldungen", []),
            ("plist", "Property Lists", [
                ("plist/airport",         "Airport (WLAN) – bekannte Netze"),
                ("plist/macos_bluetooth", "Bluetooth-Geräte-Historie"),
                ("plist/safari_history",  "Safari Verlauf"),
                ("plist/time_machine",    "Time Machine Backup-Konfiguration"),
            ]),
            ("sqlite", "SQLite – macOS Apps", [
                ("sqlite/appusage",       "Application Usage – App-Nutzung"),
                ("sqlite/mac_knowledgec", "Duet / KnowledgeC – Aktivitätsdaten"),
                ("sqlite/macostcc",       "TCC – Datenschutz-Berechtigungen"),
                ("sqlite/safari_historydb","Safari History.db"),
            ]),
        ]),
        "linux": ("Linux", [
            ("systemd_journal", "Systemd Journal – zentrales Log", []),
            ("utmp",            "libc6 utmp – Login-Datensätze", []),
            ("fish_history",    "Fish Shell History", []),
            ("text", "Textbasierte Logs", [
                ("text/apt_history", "APT History – Paket-Installationen"),
                ("text/bash_history","Bash History – Shell-Befehle"),
                ("text/dpkg",        "Dpkg Log – Paket-Manager"),
                ("text/syslog",      "Syslog – Systemmeldungen"),
                ("text/selinux",     "SELinux Audit-Log"),
                ("text/zsh_extended_history", "ZSH Extended History"),
            ]),
        ]),
        "databases": ("Datenbanken & Formate", [
            ("sqlite", "SQLite-Datenbanken (Desktop)", [
                ("sqlite/chrome_27_history", "Chrome History ≥ 27"),
                ("sqlite/chrome_66_cookies", "Chrome Cookies ≥ 66"),
                ("sqlite/chrome_autofill",   "Chrome Autofill (Web Data)"),
                ("sqlite/firefox_history",   "Firefox History (places.sqlite)"),
                ("sqlite/firefox_downloads", "Firefox Downloads"),
                ("sqlite/skype",             "Skype main.db – Chat-Verlauf"),
                ("sqlite/windows_timeline",  "Windows ActivitiesCache – Timeline"),
                ("sqlite/windows_push_notification","Push Notifications (wpndatabase.db)"),
                ("sqlite/windows_eventtranscript", "EventTranscript.db"),
                ("sqlite/dropbox",           "Dropbox sync_history.db"),
                ("sqlite/google_drive",      "Google Drive snapshot.db"),
                ("sqlite/zeitgeist",         "Zeitgeist Activity"),
            ]),
            ("esedb", "ESE-Datenbanken", [
                ("esedb/srum",          "SRUM – System Resource Usage Monitor"),
                ("esedb/msie_webcache", "IE/Edge WebCache (WebCacheV01.dat)"),
                ("esedb/file_history",  "Windows File History"),
            ]),
            ("olecf", "OLE Compound Files", [
                ("olecf/olecf_automatic_destinations", "Automatic Destinations – Jump Lists"),
                ("olecf/olecf_summary",  "Summary Information"),
            ]),
            ("czip", "Compound ZIP (OpenXML)", [
                ("czip/oxml", "OpenXML – Office-Dokumente (.docx, .xlsx)"),
            ]),
            ("jsonl", "JSON-L Logs (Cloud)", [
                ("jsonl/aws_cloudtrail_log",    "AWS CloudTrail – API-Aufrufe"),
                ("jsonl/azure_activity_log",    "Azure Activity Log"),
                ("jsonl/gcp_log",               "Google Cloud Log"),
                ("jsonl/microsoft_audit_log",   "Microsoft 365 Audit-Log"),
                ("jsonl/docker_container_log",  "Docker Container Logs"),
            ]),
        ]),
        "win_apps": ("Windows-Anwendungen", [
            ("mcafee_protection", "McAfee Anti-Virus Protection Logs", []),
            ("symantec_scanlog",  "Symantec AV Scan-Logs", []),
            ("trendmicro_url",    "Trend Micro Web Reputation", []),
            ("trendmicro_vd",     "Trend Micro Virus Detection", []),
            ("onedrive_log",      "OneDrive Logs", []),
        ]),
        "network": ("Netzwerk, Server & Sonstiges", [
            ("networkminer_fileinfo", "NetworkMiner .fileinfos", []),
            ("text", "Server- & Netzwerk-Logs", [
                ("text/apache_access",         "Apache Access Log"),
                ("text/aws_elb_access",        "AWS ELB Access Log"),
                ("text/postgresql",            "PostgreSQL Application Log"),
                ("text/snort_fastlog",         "Snort / Suricata fast.log"),
                ("text/winfirewall",           "Windows Firewall Log"),
                ("text/winiis",                "Microsoft IIS Log"),
                ("text/powershell_transcript", "PowerShell Transcript"),
                ("text/sccm",                  "SCCM Client Log"),
                ("text/setupapi",              "SetupAPI Log"),
                ("text/teamviewer_application_log", "TeamViewer Application Log"),
            ]),
        ]),
    }


# ══════════════════════════════════════════════════════════════════════════
#  Konstanten
# ══════════════════════════════════════════════════════════════════════════

COLOR_BG        = "#f3f3f3"
COLOR_HEADER_BG = "#1F6AA5"
COLOR_HEADER_FG = "#ffffff"
COLOR_STEP_ACT  = "#1F6AA5"
COLOR_STEP_DONE = "#d0d0d0"
COLOR_STEP_PEND = "#e8e8e8"
COLOR_ACCENT    = "#1F8B4C"
COLOR_ERROR     = "#C0392B"

# psort-Ausgabeformate: (Label, psort-Wert, Dateiendung, Beschreibung)
OUTPUT_FORMATS = [
    ("CSV (l2tcsv)",   "l2tcsv",   ".csv",     "Für Excel / Timeline Explorer (Standard)"),
    ("JSON Lines",     "json_line",".jsonl",   "Eine JSON-Zeile pro Ereignis (Streaming)"),
    ("JSON",           "json",     ".json",    "Vollständiges JSON-Array"),
    ("Bodyfile",       "bodyfile", ".bodyfile","SleuthKit v3 bodyfile (mactime)"),
    ("SQLite",         "sqlite",   ".sqlite",  "SQLite-Datenbank – für eigene Abfragen"),
    ("Dynamic (XLSX)", "dynamic",  ".xlsx",    "Timeline Explorer-optimiertes XLSX"),
]


# ══════════════════════════════════════════════════════════════════════════
#  Wizard
# ══════════════════════════════════════════════════════════════════════════

class PlasoWizard:
    STEPS = ["Image", "Ausgabe", "BitLocker", "Partition",
             "Parser", "Optionen", "Ausführen"]

    def __init__(self, root):
        self.root = root
        root.title("Plaso Docker Helper")
        root.geometry("1220x860")
        root.minsize(1020, 740)
        root.configure(bg=COLOR_BG)

        self.catalog = build_catalog()
        self.current_step = 0

        self.state = {
            # Image
            "input_path": None,
            "input_dir": None,
            "input_file": None,
            "batch_mode": False,
            "batch_files": [],
            # Ausgabe
            "out_dir": None,
            "name": None,
            "output_format": "l2tcsv",
            "output_ext": ".csv",
            # BitLocker
            "credential_arg": [],
            # Partition
            "partitions_arg": [],
            # Parser
            "selected_parsers": set(),
            # Zeitfilter
            "time_filter_enabled": False,
            "time_from": None,
            "time_to": None,
        }

        self.log_queue = queue.Queue()
        self.process = None
        self.process_start_time = None
        self.timer_running = False

        self.expanded_categories = set()
        self.expanded_parsers = set()

        self._setup_style()
        self._build_layout()
        self._show_step(0)

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────
    #  Style
    # ─────────────────────────────────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        for theme in ("vista", "winnative", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", foreground="#555555", font=("Segoe UI", 9))
        style.configure("Success.TLabel", foreground="#1F8B4C",
                        font=("Segoe UI", 9, "bold"))
        style.configure("Error.TLabel", foreground=COLOR_ERROR,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Timer.TLabel", foreground="#1F6AA5",
                        font=("Consolas", 11, "bold"))

        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TCheckbutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("TRadiobutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    # ─────────────────────────────────────────────────────────────
    #  Layout
    # ─────────────────────────────────────────────────────────────

    def _build_layout(self):
        header = tk.Frame(self.root, bg=COLOR_HEADER_BG, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🕒  Plaso Docker Helper",
                 bg=COLOR_HEADER_BG, fg=COLOR_HEADER_FG,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=25)

        # Step-Bar
        self.step_bar = tk.Frame(self.root, bg="#e2e2e2", height=48)
        self.step_bar.pack(fill="x")
        self.step_bar.pack_propagate(False)

        self.step_labels = []
        inner = tk.Frame(self.step_bar, bg="#e2e2e2")
        inner.pack(expand=True)
        for i, name in enumerate(self.STEPS):
            lbl = tk.Label(inner, text=f"  {i+1}  {name}  ",
                           bg=COLOR_STEP_PEND, fg="#555555",
                           font=("Segoe UI", 10), padx=6, pady=6)
            lbl.pack(side="left", padx=3, pady=9)
            self.step_labels.append(lbl)
            if i < len(self.STEPS) - 1:
                tk.Label(inner, text="›", bg="#e2e2e2", fg="#888888",
                         font=("Segoe UI", 12, "bold")).pack(side="left")

        # Content
        self.content = tk.Frame(self.root, bg=COLOR_BG)
        self.content.pack(fill="both", expand=True, padx=22, pady=(15, 5))

        # Footer
        footer = tk.Frame(self.root, bg="#e2e2e2", height=70)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.btn_back = ttk.Button(footer, text="◀   Zurück", width=14,
                                   command=self._go_back)
        self.btn_back.pack(side="left", padx=22, pady=15)

        self.btn_next = ttk.Button(footer, text="Weiter   ▶", width=16,
                                   style="Accent.TButton",
                                   command=self._go_next)
        self.btn_next.pack(side="right", padx=22, pady=15)

        self.footer_status = tk.Label(footer, text="", bg="#e2e2e2",
                                      fg="#555555", font=("Segoe UI", 9))
        self.footer_status.pack(side="right", padx=15)

    # ─────────────────────────────────────────────────────────────
    #  Navigation
    # ─────────────────────────────────────────────────────────────

    def _show_step(self, index):
        self.current_step = index

        for w in self.content.winfo_children():
            w.destroy()

        for i, lbl in enumerate(self.step_labels):
            if i == index:
                lbl.configure(bg=COLOR_STEP_ACT, fg="white",
                              font=("Segoe UI", 10, "bold"))
            elif i < index:
                lbl.configure(bg=COLOR_STEP_DONE, fg="#222222",
                              font=("Segoe UI", 10))
            else:
                lbl.configure(bg=COLOR_STEP_PEND, fg="#555555",
                              font=("Segoe UI", 10))

        self.btn_back.configure(state="normal" if index > 0 else "disabled")

        if index == len(self.STEPS) - 1:
            self.btn_next.configure(text="🚀  Starten")
        else:
            self.btn_next.configure(text="Weiter   ▶")

        builders = [
            self._step_image,
            self._step_output,
            self._step_bitlocker,
            self._step_partition,
            self._step_parser,
            self._step_options,
            self._step_run,
        ]
        builders[index]()

        self.footer_status.configure(
            text=f"Schritt {index + 1} von {len(self.STEPS)}")

    def _go_back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _go_next(self):
        # Validierung je Schritt
        if self.current_step == 0:
            if self.state["batch_mode"]:
                if not self.state["batch_files"]:
                    messagebox.showerror("Fehler",
                        "Batch-Modus aktiv, aber keine Images gefunden.")
                    return
            elif not self.state["input_path"]:
                messagebox.showerror("Fehler", "Bitte eine Eingabedatei auswählen.")
                return

        if self.current_step == 1:
            if not self.state["out_dir"]:
                messagebox.showerror("Fehler", "Bitte einen Ausgabeordner wählen.")
                return
            if not self.state["name"]:
                messagebox.showerror("Fehler", "Bitte einen Dateinamen angeben.")
                return

        if self.current_step == 2:
            if self.bitlocker_yes_var.get() == "yes":
                cred_type = self.bitlocker_type_var.get().split("  (")[0]
                value = self.bitlocker_value_var.get().strip()
                if not value:
                    messagebox.showerror(
                        "Fehler", "Bitte den BitLocker-Schlüssel eingeben.")
                    return
                self.state["credential_arg"] = [
                    "--credential", f"{cred_type}:{value}"]
            else:
                self.state["credential_arg"] = []

        if self.current_step == 3:
            if self.partition_mode_var.get() == "specific":
                num = self.partition_num_var.get().strip()
                if not num.isdigit():
                    messagebox.showerror(
                        "Fehler", "Bitte eine gültige Partitionsnummer eingeben.")
                    return
                self.state["partitions_arg"] = ["--partitions", num]
            else:
                self.state["partitions_arg"] = ["--partitions", "all"]

        if self.current_step == 5:  # Optionen
            if self.time_filter_var.get():
                tf = self.time_from_var.get().strip()
                tt = self.time_to_var.get().strip()
                if not tf or not tt:
                    messagebox.showerror(
                        "Fehler", "Bitte Von- und Bis-Zeit eingeben.")
                    return
                # Einfache Format-Validierung
                pat = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
                if not re.match(pat, tf) or not re.match(pat, tt):
                    messagebox.showerror(
                        "Fehler",
                        "Format muss YYYY-MM-DD HH:MM:SS sein.\n\n"
                        "Beispiel: 2024-01-15 08:00:00")
                    return
                self.state["time_filter_enabled"] = True
                self.state["time_from"] = tf
                self.state["time_to"] = tt
            else:
                self.state["time_filter_enabled"] = False
                self.state["time_from"] = None
                self.state["time_to"] = None

        if self.current_step < len(self.STEPS) - 1:
            self._show_step(self.current_step + 1)
        else:
            self._start_processing()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 1: Image
    # ─────────────────────────────────────────────────────────────

    def _step_image(self):
        ttk.Label(self.content, text="Eingabedatei(en)",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Wähle ein einzelnes Forensik-Image (.E01, .dd, .raw, "
                       ".vmdk) oder aktiviere den Batch-Modus für mehrere Images.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 15))

        # ── Batch-Modus-Toggle ─────────────────────────────────
        self.batch_mode_var = tk.BooleanVar(value=self.state["batch_mode"])
        batch_cb = ttk.Checkbutton(
            self.content,
            text="Batch-Modus: Mehrere Images in einem Durchlauf verarbeiten",
            variable=self.batch_mode_var,
            command=self._toggle_batch_mode)
        batch_cb.pack(anchor="w", pady=(0, 12))

        # ── Einzel-Image-UI ────────────────────────────────────
        self.single_frame = ttk.Frame(self.content)

        ttk.Label(self.single_frame, text="Pfad zum Image:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(self.single_frame)
        row.pack(fill="x", pady=(4, 0))

        self.image_path_var = tk.StringVar(value=self.state["input_path"] or "")
        ttk.Entry(row, textvariable=self.image_path_var,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="📂  Durchsuchen",
                   command=self._browse_image).pack(side="left")

        # ── Batch-Modus-UI (mehrere Dateien auswählen) ─────────
        self.batch_frame = ttk.Frame(self.content)

        ttk.Label(self.batch_frame,
                  text="Ausgewählte Images:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))

        btn_row = ttk.Frame(self.batch_frame)
        btn_row.pack(fill="x", pady=(0, 6))

        ttk.Button(btn_row, text="➕  Images hinzufügen",
                   command=self._browse_batch_files).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="🗑  Einzelne entfernen",
                   command=self._remove_selected_batch_file).pack(side="left", padx=6)
        ttk.Button(btn_row, text="✕  Alle leeren",
                   command=self._clear_batch_files).pack(side="left", padx=6)

        # Listbox mit Scrollbar
        list_container = ttk.Frame(self.batch_frame)
        list_container.pack(fill="both", expand=True)

        self.batch_list = tk.Listbox(list_container, height=10,
                                     font=("Consolas", 9),
                                     selectmode="extended")
        list_vsb = ttk.Scrollbar(list_container, orient="vertical",
                                 command=self.batch_list.yview)
        self.batch_list.configure(yscrollcommand=list_vsb.set)
        self.batch_list.pack(side="left", fill="both", expand=True)
        list_vsb.pack(side="right", fill="y")

        # ── Status ─────────────────────────────────────────────
        self.image_status = ttk.Label(self.content, text="", style="Muted.TLabel")
        self.image_status.pack(anchor="w", pady=(15, 0))

        self.image_path_var.trace("w", lambda *a: self._validate_image())

        # Initial-Zustand
        self._toggle_batch_mode()
        self._rebuild_batch_list()
        self._validate_image()

    def _toggle_batch_mode(self):
        if self.batch_mode_var.get():
            self.state["batch_mode"] = True
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill="both", expand=True, pady=5)
            self.state["input_path"] = None
            self.state["input_dir"] = None
            self.state["input_file"] = None
        else:
            self.state["batch_mode"] = False
            self.batch_frame.pack_forget()
            self.single_frame.pack(fill="x", pady=5)
            # Batch-Liste NICHT löschen – falls Nutzer zurückwechselt
        self._validate_image()

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Forensik-Image auswählen",
            filetypes=[("Forensik-Images",
                        "*.E01 *.e01 *.dd *.raw *.img *.vmdk"),
                       ("Alle Dateien", "*.*")])
        if path:
            self.image_path_var.set(path)

    def _browse_batch_files(self):
        """Öffnet einen Dialog zur Mehrfach-Auswahl von Image-Dateien."""
        paths = filedialog.askopenfilenames(
            title="Images auswählen (mit Strg oder Shift mehrere markieren)",
            filetypes=[("Forensik-Images",
                        "*.E01 *.e01 *.dd *.raw *.img *.vmdk"),
                       ("Alle Dateien", "*.*")])
        if not paths:
            return

        # Bereits vorhandene Dateien nicht doppelt hinzufügen
        existing = set(self.state["batch_files"])
        added = 0
        for p in paths:
            if p not in existing:
                self.state["batch_files"].append(p)
                existing.add(p)
                added += 1

        self._rebuild_batch_list()
        self._validate_image()
        if added > 0:
            self.image_status.configure(
                text=f"✔  {added} Image(s) hinzugefügt",
                style="Success.TLabel")

    def _remove_selected_batch_file(self):
        """Entfernt die in der Listbox markierten Dateien."""
        sel = list(self.batch_list.curselection())
        if not sel:
            messagebox.showinfo(
                "Hinweis",
                "Bitte zuerst eine oder mehrere Dateien in der Liste markieren.")
            return
        # Von hinten nach vorne löschen, damit Indizes stabil bleiben
        for idx in sorted(sel, reverse=True):
            del self.state["batch_files"][idx]
        self._rebuild_batch_list()
        self._validate_image()

    def _clear_batch_files(self):
        """Leert die gesamte Liste."""
        if not self.state["batch_files"]:
            return
        if confirm := messagebox.askyesno(
                "Bestätigung",
                f"Wirklich alle {len(self.state['batch_files'])} "
                "Images aus der Liste entfernen?"):
            self.state["batch_files"].clear()
            self._rebuild_batch_list()
            self._validate_image()

    def _rebuild_batch_list(self):
        """Zeichnet die Listbox neu."""
        self.batch_list.delete(0, "end")
        for path_str in self.state["batch_files"]:
            p = Path(path_str)
            try:
                size_gb = p.stat().st_size / (1024 ** 3)
                size_txt = f"{size_gb:.2f} GB"
            except OSError:
                size_txt = "?"
            self.batch_list.insert("end", f"  {p.name}   ({size_txt})")

    def _validate_image(self):
        if self.state["batch_mode"]:
            n = len(self.state["batch_files"])
            if n == 0:
                self.image_status.configure(text="")
            else:
                total_gb = 0
                for p_str in self.state["batch_files"]:
                    try:
                        total_gb += Path(p_str).stat().st_size / (1024 ** 3)
                    except OSError:
                        pass
                self.image_status.configure(
                    text=f"✔  {n} Image(s) ausgewählt – gesamt {total_gb:.2f} GB",
                    style="Success.TLabel")
        else:
            p = Path(self.image_path_var.get())
            if p.is_file():
                self.state["input_path"] = str(p)
                self.state["input_dir"] = str(p.parent)
                self.state["input_file"] = p.name
                size_gb = p.stat().st_size / (1024 ** 3)
                self.image_status.configure(
                    text=f"✔  {p.name}  ({size_gb:.2f} GB)",
                    style="Success.TLabel")
            else:
                self.state["input_path"] = None
                self.image_status.configure(text="", style="Muted.TLabel")

    # ─────────────────────────────────────────────────────────────
    #  Schritt 2: Ausgabe
    # ─────────────────────────────────────────────────────────────

    def _step_output(self):
        ttk.Label(self.content, text="Ausgabeort & Dateiname",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Hierhin werden die Ergebnisdateien gespeichert.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 18))

        # Zielordner
        ttk.Label(self.content, text="Zielordner:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        out_row = ttk.Frame(self.content)
        out_row.pack(fill="x", pady=(5, 18))

        default_dir = ""
        if self.state["out_dir"]:
            default_dir = self.state["out_dir"]
        elif self.state["batch_mode"] and self.batch_dir_var.get():
            default_dir = str(Path(self.batch_dir_var.get()) / "plaso")
        elif self.state["input_dir"]:
            default_dir = str(Path(self.state["input_dir"]) / "plaso")

        self.out_dir_var = tk.StringVar(value=default_dir)
        ttk.Entry(out_row, textvariable=self.out_dir_var,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(out_row, text="📁  Ordner wählen",
                   command=self._browse_outdir).pack(side="left")

        # Dateiname
        ttk.Label(self.content, text="Basis-Dateiname:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(self.content,
                  text="(Erweiterung wird je nach Format automatisch gesetzt. "
                       "Im Batch-Modus wird der Image-Name verwendet.)",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))

        self.filename_var = tk.StringVar(value=self.state["name"] or "timeline")
        ttk.Entry(self.content, textvariable=self.filename_var,
                  font=("Segoe UI", 10)).pack(fill="x", pady=(0, 18))

        # Ausgabeformat
        ttk.Label(self.content, text="Ausgabeformat:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")

        fmt_frame = ttk.Frame(self.content)
        fmt_frame.pack(fill="x", pady=(5, 0))

        self.format_var = tk.StringVar(
            value=next(f[0] for f in OUTPUT_FORMATS
                       if f[1] == self.state["output_format"]))

        for label, value, ext, desc in OUTPUT_FORMATS:
            row = ttk.Frame(fmt_frame)
            row.pack(fill="x", pady=2)
            ttk.Radiobutton(row, text=label, variable=self.format_var,
                            value=label,
                            command=self._on_format_change).pack(side="left")
            ttk.Label(row, text=f"  {desc}",
                      style="Muted.TLabel").pack(side="left")

        self.out_status = ttk.Label(self.content, text="", style="Muted.TLabel")
        self.out_status.pack(anchor="w", pady=(15, 0))

        self.out_dir_var.trace("w", lambda *a: self._validate_out())
        self.filename_var.trace("w", lambda *a: self._validate_out())
        self._validate_out()

    def _on_format_change(self):
        label = self.format_var.get()
        for l, v, e, d in OUTPUT_FORMATS:
            if l == label:
                self.state["output_format"] = v
                self.state["output_ext"] = e
                break
        self._validate_out()

    def _browse_outdir(self):
        path = filedialog.askdirectory(title="Zielordner wählen")
        if path:
            self.out_dir_var.set(path)

    def _validate_out(self):
        out_dir = self.out_dir_var.get().strip()
        name = self.filename_var.get().strip() or "timeline"

        # Erweiterung abschneiden, falls der User eine getippt hat
        for _, _, ext, _ in OUTPUT_FORMATS:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break

        if not out_dir:
            self.state["out_dir"] = None
            self.state["name"] = None
            self.out_status.configure(text="")
            return
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            self.state["out_dir"] = str(Path(out_dir).resolve())
            self.state["name"] = name
            self.out_status.configure(
                text=f"✔  {Path(out_dir).resolve()}\\{name}{self.state['output_ext']}",
                style="Success.TLabel")
        except OSError as e:
            self.state["out_dir"] = None
            self.out_status.configure(text=f"✘  {e}", style="Error.TLabel")

    # ─────────────────────────────────────────────────────────────
    #  Schritt 3: BitLocker
    # ─────────────────────────────────────────────────────────────

    def _step_bitlocker(self):
        ttk.Label(self.content, text="BitLocker / Volume-Verschlüsselung",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Falls das Image verschlüsselte Volumes enthält, kann "
                       "Plaso diese mit dem passenden Schlüssel entsperren.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 18))

        ttk.Label(self.content,
                  text="Ist das Image BitLocker-verschlüsselt?",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        radio_frame = ttk.Frame(self.content)
        radio_frame.pack(anchor="w", pady=(0, 8))

        self.bitlocker_yes_var = tk.StringVar(
            value="yes" if self.state["credential_arg"] else "no")

        ttk.Radiobutton(radio_frame, text="Ja",
                        variable=self.bitlocker_yes_var, value="yes",
                        command=self._toggle_bitlocker).pack(
            side="left", padx=(0, 30))
        ttk.Radiobutton(radio_frame, text="Nein",
                        variable=self.bitlocker_yes_var, value="no",
                        command=self._toggle_bitlocker).pack(side="left")

        self.bitlocker_frame = ttk.LabelFrame(self.content,
                                              text="BitLocker-Details",
                                              padding=15)

        ttk.Label(self.bitlocker_frame, text="Schlüsseltyp:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.bitlocker_type_var = tk.StringVar(
            value="recovery_password  (48-stelliger Wiederherstellungsschlüssel)")
        ttk.Combobox(self.bitlocker_frame,
                     textvariable=self.bitlocker_type_var,
                     values=[
                         "recovery_password  (48-stelliger Wiederherstellungsschlüssel)",
                         "password  (Benutzerpasswort)",
                         "startup_key  (Pfad zur .BEK-Datei)",
                         "key_data  (Hex-String 0x...)",
                     ],
                     state="readonly", width=60).pack(anchor="w", pady=(0, 14))

        ttk.Label(self.bitlocker_frame, text="Schlüsselwert:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.bitlocker_value_var = tk.StringVar()
        ttk.Entry(self.bitlocker_frame, textvariable=self.bitlocker_value_var,
                  width=80).pack(fill="x", pady=(0, 4))

        ttk.Label(self.bitlocker_frame,
                  text="Beispiel: 123456-789012-345678-901234-567890-123456-789012-345678",
                  style="Muted.TLabel").pack(anchor="w")

        self._toggle_bitlocker()

    def _toggle_bitlocker(self):
        if self.bitlocker_yes_var.get() == "yes":
            self.bitlocker_frame.pack(fill="x", pady=(15, 0))
        else:
            self.bitlocker_frame.pack_forget()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 4: Partition
    # ─────────────────────────────────────────────────────────────

    def _step_partition(self):
        ttk.Label(self.content, text="Partition auswählen",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Bei mehreren Partitionen muss angegeben werden, welche "
                       "verarbeitet werden soll. 'Alle' verarbeitet das gesamte Image.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 18))

        self.partition_mode_var = tk.StringVar(
            value="specific" if self.state["partitions_arg"] and
                  self.state["partitions_arg"][-1] != "all" else "all")

        ttk.Radiobutton(self.content,
                        text="Alle Partitionen verarbeiten "
                             "(empfohlen bei Unsicherheit)",
                        variable=self.partition_mode_var, value="all",
                        command=self._toggle_partition).pack(anchor="w", pady=5)
        ttk.Radiobutton(self.content,
                        text="Nur eine bestimmte Partition verarbeiten",
                        variable=self.partition_mode_var, value="specific",
                        command=self._toggle_partition).pack(anchor="w", pady=5)

        self.partition_num_frame = ttk.LabelFrame(self.content,
                                                  text="Partitionsnummer",
                                                  padding=15)
        ttk.Label(self.partition_num_frame,
                  text="Nummer der Partition (z. B. 2):").pack(
            side="left", padx=(0, 10))
        self.partition_num_var = tk.StringVar(value="2")
        ttk.Entry(self.partition_num_frame,
                  textvariable=self.partition_num_var,
                  width=10).pack(side="left")

        self._toggle_partition()

    def _toggle_partition(self):
        if self.partition_mode_var.get() == "specific":
            self.partition_num_frame.pack(fill="x", pady=(15, 0))
        else:
            self.partition_num_frame.pack_forget()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 5: Parser
    # ─────────────────────────────────────────────────────────────

    def _step_parser(self):
        head = ttk.Frame(self.content)
        head.pack(fill="x", pady=(5, 10))
        ttk.Label(head, text="Parser auswählen",
                  style="Title.TLabel").pack(side="left")
        self.parser_count_lbl = ttk.Label(head, text="", style="Success.TLabel")
        self.parser_count_lbl.pack(side="right")

        bar = ttk.Frame(self.content)
        bar.pack(fill="x", pady=(0, 10))

        ttk.Label(bar, text="Suche:").pack(side="left", padx=(0, 6))
        self.parser_search_var = tk.StringVar()
        self.parser_search_var.trace("w", lambda *a: self._refresh_parser_tree())
        ttk.Entry(bar, textvariable=self.parser_search_var,
                  width=40).pack(side="left")

        ttk.Button(bar, text="Empf. Win-Set",
                   command=self._apply_win_preset).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Alle abwählen",
                   command=self._deselect_all).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle erweitern",
                   command=lambda: self._expand_all(True)).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle einklappen",
                   command=lambda: self._expand_all(False)).pack(side="left", padx=4)

        main = ttk.Frame(self.content)
        main.pack(fill="both", expand=True)

        # Links: Parser-Tree
        tree_frame = ttk.Frame(main)
        tree_frame.pack(side="left", fill="both", expand=True)

        self.parser_tree = ttk.Treeview(
            tree_frame,
            columns=("check", "name", "desc"),
            show="tree headings",
            selectmode="none",
            height=18,
        )
        self.parser_tree.heading("#0", text="")
        self.parser_tree.heading("check", text="")
        self.parser_tree.heading("name", text="Name")
        self.parser_tree.heading("desc", text="Beschreibung")
        self.parser_tree.column("#0", width=40, stretch=False)
        self.parser_tree.column("check", width=32, stretch=False, anchor="center")
        self.parser_tree.column("name", width=250, stretch=False)
        self.parser_tree.column("desc", width=380, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.parser_tree.yview)
        self.parser_tree.configure(yscroll=vsb.set)
        self.parser_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.parser_tree.bind("<Button-1>", self._on_tree_click)
        self.parser_tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.parser_tree.bind("<<TreeviewClose>>", self._on_tree_close)

        self.parser_tree.tag_configure("category",
                                       background="#dfe8f2",
                                       font=("Segoe UI", 10, "bold"))
        self.parser_tree.tag_configure("plugin", foreground="#444444")
        self.parser_tree.tag_configure("selected", background="#eaf6ee")

        # Rechts: Auswahl-Panel
        panel = ttk.LabelFrame(main, text="✓ Ausgewählte Parser",
                               padding=(6, 6))
        panel.pack(side="right", fill="y", padx=(12, 0))

        self.selected_tree = ttk.Treeview(
            panel,
            columns=("remove", "name"),
            show="headings",
            selectmode="none",
            height=22,
        )
        self.selected_tree.heading("remove", text="")
        self.selected_tree.heading("name", text="")
        self.selected_tree.column("remove", width=30, stretch=False, anchor="center")
        self.selected_tree.column("name", width=220, stretch=False)

        sel_vsb = ttk.Scrollbar(panel, orient="vertical",
                                command=self.selected_tree.yview)
        self.selected_tree.configure(yscroll=sel_vsb.set)
        self.selected_tree.pack(side="left", fill="both", expand=True)
        sel_vsb.pack(side="right", fill="y")

        self.selected_tree.bind("<Button-1>", self._on_selected_tree_click)
        self.selected_tree.bind("<Motion>", self._on_selected_tree_motion)
        self.selected_tree.bind("<Leave>",
                                lambda e: self.selected_tree.configure(cursor=""))

        self.selected_tree.tag_configure("plugin", foreground="#666666")
        self.selected_tree.tag_configure("empty", foreground="#999999")

        self.selected_tree_name_map = {}

        # Eltern-Parser mit Plugins vorab aufklappen
        if not self.expanded_parsers:
            for _, (_, parsers) in self.catalog.items():
                for name, _, plugins in parsers:
                    if plugins:
                        self.expanded_parsers.add(name)

        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _refresh_parser_tree(self):
        self._save_expanded_state()

        for iid in self.parser_tree.get_children():
            self.parser_tree.delete(iid)
        self.parser_tree_map = {}

        search = self.parser_search_var.get().strip().lower()

        for cat_key, (cat_label, parsers) in self.catalog.items():
            visible = []
            for name, desc, plugins in parsers:
                plugins_shown = []
                if search:
                    main_match = (search in name.lower() or
                                  search in desc.lower())
                    if main_match:
                        plugins_shown = plugins
                    else:
                        plugins_shown = [
                            pl for pl in plugins
                            if search in pl[0].lower() or search in pl[1].lower()
                        ]
                        if not plugins_shown:
                            continue
                else:
                    plugins_shown = plugins
                visible.append((name, desc, plugins_shown))

            if not visible:
                continue

            cat_open = bool(search) or (cat_key in self.expanded_categories)

            cat_iid = self.parser_tree.insert(
                "", "end", text="",
                values=("", f"  {cat_label}", ""),
                tags=("category",),
                open=cat_open,
            )
            self.parser_tree_map[cat_iid] = ("category", cat_key)

            for name, desc, plugins in visible:
                checked = name in self.state["selected_parsers"]
                mark = "☑" if checked else "☐"

                parser_open = bool(search) or (name in self.expanded_parsers)

                if plugins:
                    arrow = "▾" if parser_open else "▸"
                    display_name = f"  {arrow} {name}"
                else:
                    display_name = f"      {name}"

                main_iid = self.parser_tree.insert(
                    cat_iid, "end", text="",
                    values=(mark, display_name, desc),
                    tags=("selected",) if checked else (),
                    open=parser_open,
                )
                self.parser_tree_map[main_iid] = ("main", name)

                for pl_name, pl_desc in plugins:
                    pl_checked = pl_name in self.state["selected_parsers"]
                    pl_mark = "☑" if pl_checked else "☐"
                    pl_iid = self.parser_tree.insert(
                        main_iid, "end", text="",
                        values=(pl_mark,
                                f"    └─ {pl_name.split('/')[-1]}", pl_desc),
                        tags=("plugin", "selected") if pl_checked else ("plugin",),
                    )
                    self.parser_tree_map[pl_iid] = ("plugin", pl_name)

    def _save_expanded_state(self):
        if not hasattr(self, "parser_tree_map"):
            return
        for iid in self.parser_tree_map:
            try:
                is_open = self.parser_tree.item(iid, "open")
            except tk.TclError:
                continue
            kind, name = self.parser_tree_map[iid]
            if kind == "category":
                if is_open:
                    self.expanded_categories.add(name)
                else:
                    self.expanded_categories.discard(name)
            elif kind == "main":
                if is_open:
                    self.expanded_parsers.add(name)
                else:
                    self.expanded_parsers.discard(name)

    def _on_tree_open(self, event):
        iid = self.parser_tree.focus()
        info = self.parser_tree_map.get(iid)
        if not info:
            return
        kind, name = info
        if kind == "category":
            self.expanded_categories.add(name)
        elif kind == "main":
            self.expanded_parsers.add(name)

    def _on_tree_close(self, event):
        iid = self.parser_tree.focus()
        info = self.parser_tree_map.get(iid)
        if not info:
            return
        kind, name = info
        if kind == "category":
            self.expanded_categories.discard(name)
        elif kind == "main":
            self.expanded_parsers.discard(name)

    def _on_tree_click(self, event):
        region = self.parser_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self.parser_tree.identify_row(event.y)
        if not iid:
            return
        col = self.parser_tree.identify_column(event.x)

        if col != "#1":
            info = self.parser_tree_map.get(iid)
            if not info:
                return
            kind, name = info
            if kind == "main":
                has_plugins = False
                for _, (_, parsers) in self.catalog.items():
                    for p_name, _, p_plugins in parsers:
                        if p_name == name and p_plugins:
                            has_plugins = True
                            break
                if has_plugins:
                    is_open = self.parser_tree.item(iid, "open")
                    self.parser_tree.item(iid, open=not is_open)
                    if is_open:
                        self.expanded_parsers.discard(name)
                    else:
                        self.expanded_parsers.add(name)
            return

        info = self.parser_tree_map.get(iid)
        if not info:
            return
        kind, name = info
        if kind == "category":
            return

        if name in self.state["selected_parsers"]:
            self.state["selected_parsers"].discard(name)
            if kind == "main":
                for _, (_, parsers) in self.catalog.items():
                    for p_name, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].discard(pl_name)
        else:
            self.state["selected_parsers"].add(name)
            if kind == "main":
                for _, (_, parsers) in self.catalog.items():
                    for p_name, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].add(pl_name)

        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _expand_all(self, expand: bool):
        if expand:
            for cat_key in self.catalog:
                self.expanded_categories.add(cat_key)
            for _, (_, parsers) in self.catalog.items():
                for name, _, plugins in parsers:
                    if plugins:
                        self.expanded_parsers.add(name)
        else:
            self.expanded_categories.clear()
            self.expanded_parsers.clear()
        self._refresh_parser_tree()

    def _apply_win_preset(self):
        preset = {"win10", "winevtx", "winreg", "mft", "prefetch",
                  "usnjrnl", "lnk", "sqlite"}
        for _, (_, parsers) in self.catalog.items():
            for name, _, plugins in parsers:
                if name in preset:
                    for pl_name, _ in plugins:
                        preset.add(pl_name)
        self.state["selected_parsers"] = set(preset)
        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _deselect_all(self):
        self.state["selected_parsers"].clear()
        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _refresh_selected_panel(self):
        if not hasattr(self, "selected_tree"):
            return

        for iid in self.selected_tree.get_children():
            self.selected_tree.delete(iid)
        self.selected_tree_name_map = {}

        if not self.state["selected_parsers"]:
            iid = self.selected_tree.insert(
                "", "end", values=("", "(noch keine Auswahl)"),
                tags=("empty",))
            self.selected_tree_name_map[iid] = None
            return

        for name in sorted(self.state["selected_parsers"]):
            is_plugin = "/" in name
            display = name if not is_plugin else f"└─ {name.split('/', 1)[1]}"
            tag = "plugin" if is_plugin else ""
            iid = self.selected_tree.insert(
                "", "end", values=("✕", display),
                tags=(tag,) if tag else ())
            self.selected_tree_name_map[iid] = name

    def _on_selected_tree_click(self, event):
        region = self.selected_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.selected_tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.selected_tree.identify_row(event.y)
        if not iid:
            return
        name = self.selected_tree_name_map.get(iid)
        if name:
            self._remove_parser(name)

    def _on_selected_tree_motion(self, event):
        col = self.selected_tree.identify_column(event.x)
        row = self.selected_tree.identify_row(event.y)
        if row and col == "#1" and self.selected_tree_name_map.get(row):
            self.selected_tree.configure(cursor="hand2")
        else:
            self.selected_tree.configure(cursor="")

    def _remove_parser(self, name):
        self.state["selected_parsers"].discard(name)
        for _, (_, parsers) in self.catalog.items():
            for p_name, _, p_plugins in parsers:
                if p_name == name:
                    for pl_name, _ in p_plugins:
                        self.state["selected_parsers"].discard(pl_name)
        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _update_parser_count(self):
        n = len(self.state["selected_parsers"])
        if n == 0:
            self.parser_count_lbl.configure(
                text="Keine Auswahl – es werden ALLE Parser verwendet",
                style="Muted.TLabel")
        else:
            self.parser_count_lbl.configure(
                text=f"✔  {n} Parser ausgewählt", style="Success.TLabel")

    # ─────────────────────────────────────────────────────────────
    #  Schritt 6: Optionen (Zeitfilter)
    # ─────────────────────────────────────────────────────────────

    def _step_options(self):
        ttk.Label(self.content, text="Optionen",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Zusätzliche Filter und Optionen für den Export.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

        # ── Zeitfilter ────────────────────────────────────────
        ctk_lbl = ttk.Label(self.content, text="Zeitfilter",
                            font=("Segoe UI", 11, "bold"))
        ctk_lbl.pack(anchor="w", pady=(0, 6))

        ttk.Label(self.content,
                  text="Nur Ereignisse aus einem bestimmten Zeitraum exportieren. "
                       "Die .plaso-Datei enthält weiterhin alle Ereignisse – "
                       "der Filter wirkt erst beim Export.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 8))

        self.time_filter_var = tk.BooleanVar(
            value=self.state["time_filter_enabled"])
        ttk.Checkbutton(self.content,
                        text="Zeitfilter aktivieren",
                        variable=self.time_filter_var,
                        command=self._toggle_time_filter).pack(anchor="w", pady=(0, 10))

        self.time_frame = ttk.LabelFrame(self.content,
                                         text="Zeitraum (UTC)",
                                         padding=15)

        # Von
        row1 = ttk.Frame(self.time_frame)
        row1.pack(fill="x", pady=(0, 10))
        ttk.Label(row1, text="Von:", width=6,
                  font=("Segoe UI", 10, "bold")).pack(side="left")
        self.time_from_var = tk.StringVar(
            value=self.state["time_from"] or "2024-01-01 00:00:00")
        ttk.Entry(row1, textvariable=self.time_from_var,
                  width=30, font=("Consolas", 10)).pack(side="left", padx=(5, 15))
        ttk.Label(row1, text="Format: YYYY-MM-DD HH:MM:SS",
                  style="Muted.TLabel").pack(side="left")

        # Bis
        row2 = ttk.Frame(self.time_frame)
        row2.pack(fill="x", pady=(0, 10))
        ttk.Label(row2, text="Bis:", width=6,
                  font=("Segoe UI", 10, "bold")).pack(side="left")
        self.time_to_var = tk.StringVar(
            value=self.state["time_to"] or "2024-12-31 23:59:59")
        ttk.Entry(row2, textvariable=self.time_to_var,
                  width=30, font=("Consolas", 10)).pack(side="left", padx=(5, 15))
        ttk.Label(row2, text="Format: YYYY-MM-DD HH:MM:SS",
                  style="Muted.TLabel").pack(side="left")

        # Beispiele
        ttk.Label(self.time_frame,
                  text="Beispiel: 2024-03-15 08:00:00 bis 2024-03-15 18:00:00 "
                       "(ein Arbeitstag)",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        self._toggle_time_filter()

    def _toggle_time_filter(self):
        if self.time_filter_var.get():
            self.time_frame.pack(fill="x", pady=(10, 0))
        else:
            self.time_frame.pack_forget()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 7: Ausführen
    # ─────────────────────────────────────────────────────────────

    def _step_run(self):
        ttk.Label(self.content, text="Verarbeitung starten",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 12))

        summary = ttk.LabelFrame(self.content, text="Zusammenfassung",
                                 padding=15)
        summary.pack(fill="x", pady=(0, 15))

        # Format-Label holen
        fmt_label = "?"
        for label, value, ext, desc in OUTPUT_FORMATS:
            if value == self.state["output_format"]:
                fmt_label = label
                break

        if self.state["batch_mode"]:
            img_display = f"Batch-Modus ({len(self.state['batch_files'])} Images)"
        else:
            img_display = self.state["input_path"] or "-"

        if self.state["time_filter_enabled"]:
            tf_display = f"{self.state['time_from']}  →  {self.state['time_to']}"
        else:
            tf_display = "inaktiv"

        rows = [
            ("Image",     img_display),
            ("Ausgabe",   f"{self.state['out_dir']}\\{self.state['name']}"
                          f"{self.state['output_ext']}"
                          if self.state["out_dir"] else "-"),
            ("Format",    fmt_label),
            ("BitLocker", "aktiv" if self.state["credential_arg"] else "nein"),
            ("Partition", self.state["partitions_arg"][-1]
                          if self.state["partitions_arg"] else "auto"),
            ("Parser",    f"{len(self.state['selected_parsers'])} ausgewählt"
                          if self.state["selected_parsers"] else "alle"),
            ("Zeitfilter",tf_display),
        ]
        for k, v in rows:
            row = ttk.Frame(summary)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"{k}:", width=12,
                      font=("Segoe UI", 10, "bold")).pack(side="left")
            ttk.Label(row, text=str(v),
                      font=("Segoe UI", 10)).pack(side="left", padx=(5, 0))

        # Timer + Progress
        prog_frame = ttk.Frame(self.content)
        prog_frame.pack(fill="x", pady=(5, 10))

        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)

        self.timer_lbl = ttk.Label(prog_frame, text="00:00:00",
                                   style="Timer.TLabel", width=12,
                                   anchor="e")
        self.timer_lbl.pack(side="right", padx=(10, 0))

        ttk.Label(self.content, text="Live-Ausgabe:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 4))

        log_frame = ttk.Frame(self.content)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="none", height=18,
                                font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white")
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical",
                                command=self.log_text.yview)
        log_hsb = ttk.Scrollbar(log_frame, orient="horizontal",
                                command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_vsb.set,
                                xscrollcommand=log_hsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")
        log_hsb.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────
    #  Verarbeitung
    # ─────────────────────────────────────────────────────────────

    def _start_processing(self):
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(state="disabled", text="⏳  Läuft...")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

        self.process_start_time = time.time()
        self.timer_running = True
        self._update_timer()

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        threading.Thread(target=self._run_pipeline, daemon=True).start()
        self.root.after(100, self._poll_log_queue)

    def _update_timer(self):
        if not self.timer_running:
            return
        elapsed = int(time.time() - self.process_start_time)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        self.timer_lbl.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.root.after(1000, self._update_timer)

    def _append_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if isinstance(msg, tuple) and msg[0] == "DONE":
                    self._processing_done(msg[1])
                    return
                self._append_log(str(msg))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _processing_done(self, rc):
        self.timer_running = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        if rc == 0:
            self.progress["value"] = 100
            self._append_log("\n✔ Fertig!\n")
            self.btn_next.configure(state="normal", text="✓  Erneut starten")
        else:
            self._append_log(f"\n✘ Fehler (Exit-Code {rc})\n")
            self.btn_next.configure(state="normal", text="🔄  Wiederholen")
        self.btn_back.configure(state="normal")

    # ─────────────────────────────────────────────────────────────
    #  Pipeline (Batch-fähig, mit Format + Zeitfilter)
    # ─────────────────────────────────────────────────────────────

    def _check_existing_plaso(self, name):
        """Prüft, ob die Zieldatei existiert, und fragt den Nutzer."""
        target = Path(self.state["out_dir"]) / f"{name}.plaso"
        if target.exists():
            answer = messagebox.askyesno(
                "Datei existiert bereits",
                f"Die Datei '{target.name}' existiert bereits.\n\n"
                "Möchtest du sie überschreiben?\n\n"
                "(Bei 'Nein' wird die Verarbeitung abgebrochen.)"
            )
            if answer:
                try:
                    target.unlink()
                    self.log_queue.put(
                        f"Existierende Datei gelöscht: {target.name}\n")
                except OSError as e:
                    self.log_queue.put(
                        f"✘ Konnte Datei nicht löschen: {e}\n")
                    return False
            else:
                self.log_queue.put("Abbruch: Datei existiert bereits.\n")
                return False
        return True

    def _run_pipeline(self):
        try:
            if self.state["batch_mode"]:
                self._run_batch()
            else:
                self._run_single()
        except Exception as e:
            self.log_queue.put(f"\n✘ Ausnahme: {e}\n")
            self.log_queue.put(("DONE", 1))


    # ─────────────────────────────────────────────────────────────
    #  Pipeline (Batch-fähig, mit Format + Zeitfilter)
    # ─────────────────────────────────────────────────────────────

    def _run_pipeline(self):
        try:
            if self.state["batch_mode"]:
                self._run_batch()
            else:
                self._run_single()
        except Exception as e:
            self.log_queue.put(f"\n✘ Ausnahme: {e}\n")
            self.log_queue.put(("DONE", 1))

    def _run_single(self):
        """Verarbeitet ein einzelnes Image."""
        # 0. Prüfen, ob die Zieldatei bereits existiert
        if not self._check_existing_plaso(self.state["name"]):
            self.log_queue.put(("DONE", 1))
            return

        # 1. log2timeline
        cmd = self._build_log2timeline_cmd(
            self.state["input_dir"],
            self.state["input_file"],
            self.state["name"])
        self.log_queue.put(f"$ {' '.join(cmd)}\n\n")
        rc = self._run_and_stream(cmd)
        if rc != 0:
            self.log_queue.put(("DONE", rc))
            return

        # 2. psort (mit optionalem Zeitfilter und Format)
        psort_cmd = self._build_psort_cmd(
            self.state["name"],
            self.state["name"] + self.state["output_ext"])
        self.log_queue.put(f"\n$ {' '.join(psort_cmd)}\n\n")
        rc = self._run_and_stream(psort_cmd)
        self.log_queue.put(("DONE", rc))

    def _run_batch(self):
        """Verarbeitet alle Images in state['batch_files']."""
        files = self.state["batch_files"]
        total = len(files)
        last_rc = 0

        for idx, path_str in enumerate(files, 1):
            p = Path(path_str)
            self.log_queue.put(
                f"\n{'═' * 70}\n"
                f"[{idx}/{total}] Verarbeite: {p.name}\n"
                f"{'═' * 70}\n\n")

            # Jedes Image bekommt seinen eigenen Namen
            base_name = p.stem  # Dateiname ohne Erweiterung

            # 0. Prüfen, ob die Zieldatei bereits existiert
            if not self._check_existing_plaso(base_name):
                self.log_queue.put(
                    f"Überspringe {p.name} (Abbruch durch Nutzer)\n")
                last_rc = 1
                continue

            # 1. log2timeline
            cmd = self._build_log2timeline_cmd(
                str(p.parent), p.name, base_name)
            self.log_queue.put(f"$ {' '.join(cmd)}\n\n")
            rc = self._run_and_stream(cmd)
            if rc != 0:
                self.log_queue.put(f"\n✘ Fehler bei {p.name} (rc={rc}), "
                                   f"fahre mit nächstem Image fort...\n")
                last_rc = rc
                continue

            # 2. psort
            psort_cmd = self._build_psort_cmd(
                base_name, base_name + self.state["output_ext"])
            self.log_queue.put(f"\n$ {' '.join(psort_cmd)}\n\n")
            rc = self._run_and_stream(psort_cmd)
            if rc != 0:
                self.log_queue.put(f"\n✘ psort-Fehler bei {p.name}\n")
                last_rc = rc

        self.log_queue.put(("\n" + "═" * 70 +
                            f"\nBatch abgeschlossen: {total} Images verarbeitet\n" +
                            "═" * 70 + "\n"))
        self.log_queue.put(("DONE", last_rc))

    def _build_log2timeline_cmd(self, input_dir, input_file, storage_name):
        """Baut den log2timeline-Docker-Befehl zusammen."""
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{input_dir}:/mnt/input",
            "-v", f"{self.state['out_dir']}:/mnt/output",
            "log2timeline/plaso",
            "log2timeline",
            *self.state["credential_arg"],
            *self.state["partitions_arg"],
        ]
        if self.state["selected_parsers"]:
            cmd += ["--parsers",
                    ",".join(sorted(self.state["selected_parsers"]))]
        cmd += [
            "--storage-file", f"/mnt/output/{storage_name}.plaso",
            f"/mnt/input/{input_file}",
        ]
        return cmd

    def _build_psort_cmd(self, storage_name, output_filename):
        """Baut den psort-Docker-Befehl mit Format + optionalem Zeitfilter."""
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{self.state['out_dir']}:/mnt/output",
            "log2timeline/plaso",
            "psort",
            "-o", self.state["output_format"],
        ]
        if self.state["time_filter_enabled"]:
            cmd += ["--slice",
                    self.state["time_from"],
                    self.state["time_to"]]
        cmd += [
            "-w", f"/mnt/output/{output_filename}",
            f"/mnt/output/{storage_name}.plaso",
        ]
        return cmd

    def _run_and_stream(self, cmd):
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        for line in self.process.stdout:
            self.log_queue.put(line)
        self.process.wait()
        return self.process.returncode

    # ─────────────────────────────────────────────────────────────
    #  Aufräumen
    # ─────────────────────────────────────────────────────────────

    def _on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(
                    "Bestätigung",
                    "Ein Prozess läuft noch. Wirklich beenden?"):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self.timer_running = False
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════
#  Einstiegspunkt
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = PlasoWizard(root)
    root.mainloop()
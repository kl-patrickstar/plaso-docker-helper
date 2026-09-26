#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plaso_gui.py - Grafische Oberfläche für den Plaso Docker Helper
Reines Tkinter – keine externen Abhängigkeiten nötig.
"""

import os
import sys
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
            ("winevtx", "Windows EventLog (EVTX)", []),
            ("winevt",  "Alte Windows EventLogs (EVT)", []),
            ("winreg",  "Windows Registry (NTUSER, SYSTEM, SOFTWARE, SAM)", [
                ("winreg/amcache",         "AmCache.hve – Programmausführung"),
                ("winreg/appcompatcache",  "AppCompatCache / ShimCache"),
                ("winreg/bam",             "Background Activity Moderator"),
                ("winreg/userassist",      "UserAssist – GUI-Programme"),
                ("winreg/usbdevices",      "USB-Geräte-Verbindungen"),
                ("winreg/usbstor_devices", "USBStor – Massenspeicher"),
                ("winreg/network_drives",  "Netzlaufwerke"),
                ("winreg/networks",        "Bekannte Netzwerke"),
                ("winreg/mstsc_rdp",       "RDP-Verbindungen"),
                ("winreg/mstsc_rdp_mru",   "RDP MRU-Historie"),
                ("winreg/bagmru",          "ShellBags (BagMRU)"),
                ("winreg/windows_run",     "Autostart (Run / RunOnce)"),
                ("winreg/windows_services","Dienste & Treiber"),
                ("winreg/windows_shutdown","Letzter Shutdown"),
                ("winreg/windows_timezone","Zeitzone"),
                ("winreg/windows_version", "Windows-Version"),
                ("winreg/winlogon",        "Logon-Einstellungen"),
                ("winreg/microsoft_office_mru",  "Office MRU"),
                ("winreg/microsoft_outlook_mru", "Outlook Search MRU"),
                ("winreg/windows_task_cache",    "Task Scheduler Cache"),
                ("winreg/windows_sam_users",     "SAM Users"),
                ("winreg/explorer_mountpoints2", "Explorer MountPoints2"),
                ("winreg/explorer_programscache","Explorer Programs Cache"),
                ("winreg/ccleaner",              "CCleaner"),
                ("winreg/winreg_default",        "Sonstige Registry-Werte"),
            ]),
            ("mft",          "NTFS $MFT – Master File Table", []),
            ("usnjrnl",      "NTFS USN Change Journal", []),
            ("prefetch",     "Windows Prefetch", []),
            ("lnk",          "Windows Shortcuts (LNK)", []),
            ("winjob",       "Geplante Tasks", []),
            ("recycle_bin",  "Papierkorb ($Recycle.Bin $I)", []),
            ("custom_destinations","Jump Lists", []),
            ("rplog",        "System Restore Points", []),
            ("windefender_history","Defender DetectionHistory", []),
            ("filestat",     "Dateisystem-Statistiken", []),
            ("pe",           "Portable Executables", []),
            ("bodyfile",     "SleuthKit v3 bodyfile", []),
        ]),
        "browser": ("Browser & Web", [
            ("chrome_cache",       "Chrome Cache", []),
            ("chrome_preferences", "Chrome Preferences", []),
            ("firefox_cache",      "Firefox Cache v1", []),
            ("firefox_cache2",     "Firefox Cache v2", []),
            ("msiecf",             "IE Cache (index.dat)", []),
            ("opera_global",       "Opera global history", []),
            ("opera_typed_history","Opera typed history", []),
            ("binary_cookies",     "Safari Binary Cookies", []),
            ("java_idx",           "Java WebStart Cache", []),
        ]),
        "mobile": ("Mobile (iOS / Android)", [
            ("android_app_usage", "Android usage-history.xml", []),
            ("discord_ios",       "iOS Discord Nachrichten", []),
            ("unified_logging",   "Apple Unified Logging", []),
            ("sqlite", "SQLite – mobile App-Datenbanken", [
                ("sqlite/android_calls",   "Android Anrufhistorie"),
                ("sqlite/android_sms",     "Android SMS/MMS"),
                ("sqlite/android_turbo",   "Android Turbo (Facebook Messenger)"),
                ("sqlite/android_webview", "Android WebView"),
                ("sqlite/imessage",        "Apple iMessage"),
                ("sqlite/ios_accounts",    "iOS Accounts"),
                ("sqlite/ios_health",      "iOS Health"),
                ("sqlite/ios_notes",       "iOS Notes"),
                ("sqlite/ios_powerlog",    "iOS PowerLog"),
                ("sqlite/ios_screentime",  "iOS Screen Time"),
                ("sqlite/kik_ios",         "iOS Kik Messenger"),
                ("sqlite/twitter_ios",     "iOS Twitter"),
                ("sqlite/instagram_ios",   "iOS Instagram"),
            ]),
        ]),
        "macos": ("macOS", [
            ("asl_log",          "Apple System Log", []),
            ("bsm_log",          "Basic Security Module", []),
            ("fseventsd",        "File System Events", []),
            ("mac_keychain",     "Keychain-Datenbank", []),
            ("spotlight_storedb","Spotlight store.db", []),
            ("utmpx",            "utmpx Login-Datensätze", []),
            ("plist", "Property Lists", [
                ("plist/airport",         "Airport (WLAN)"),
                ("plist/macos_bluetooth", "Bluetooth-Geräte"),
                ("plist/safari_history",  "Safari Verlauf"),
                ("plist/time_machine",    "Time Machine"),
            ]),
            ("sqlite", "SQLite – macOS Apps", [
                ("sqlite/appusage",       "Application Usage"),
                ("sqlite/mac_knowledgec", "Duet / KnowledgeC"),
                ("sqlite/macostcc",       "TCC"),
                ("sqlite/safari_historydb","Safari History.db"),
            ]),
        ]),
        "linux": ("Linux", [
            ("systemd_journal", "Systemd Journal", []),
            ("utmp",            "libc6 utmp", []),
            ("fish_history",    "Fish Shell History", []),
            ("text", "Textbasierte Logs", [
                ("text/apt_history", "APT History"),
                ("text/bash_history","Bash History"),
                ("text/dpkg",        "Dpkg Log"),
                ("text/syslog",      "Syslog"),
                ("text/selinux",     "SELinux Audit"),
                ("text/zsh_extended_history", "ZSH Extended History"),
            ]),
        ]),
        "databases": ("Datenbanken & Formate", [
            ("sqlite", "SQLite-Datenbanken", [
                ("sqlite/chrome_27_history", "Chrome History"),
                ("sqlite/chrome_66_cookies", "Chrome Cookies"),
                ("sqlite/chrome_autofill",   "Chrome Autofill"),
                ("sqlite/firefox_history",   "Firefox History"),
                ("sqlite/firefox_downloads", "Firefox Downloads"),
                ("sqlite/skype",             "Skype"),
                ("sqlite/windows_timeline",  "Windows ActivitiesCache"),
                ("sqlite/windows_push_notification","Push Notifications"),
                ("sqlite/windows_eventtranscript", "EventTranscript"),
                ("sqlite/dropbox",           "Dropbox"),
                ("sqlite/google_drive",      "Google Drive"),
                ("sqlite/zeitgeist",         "Zeitgeist"),
            ]),
            ("esedb", "ESE-Datenbanken", [
                ("esedb/srum",          "SRUM"),
                ("esedb/msie_webcache", "IE/Edge WebCache"),
                ("esedb/file_history",  "Windows File History"),
            ]),
            ("olecf", "OLE Compound Files", [
                ("olecf/olecf_automatic_destinations", "Automatic Destinations"),
                ("olecf/olecf_summary",  "Summary Information"),
            ]),
            ("czip", "Compound ZIP (OpenXML)", [
                ("czip/oxml", "OpenXML"),
            ]),
            ("jsonl", "JSON-L Logs (Cloud)", [
                ("jsonl/aws_cloudtrail_log",    "AWS CloudTrail"),
                ("jsonl/azure_activity_log",    "Azure Activity Log"),
                ("jsonl/gcp_log",               "Google Cloud Log"),
                ("jsonl/microsoft_audit_log",   "Microsoft 365 Audit"),
                ("jsonl/docker_container_log",  "Docker Container Log"),
            ]),
        ]),
        "win_apps": ("Windows-Anwendungen", [
            ("mcafee_protection", "McAfee Protection Logs", []),
            ("symantec_scanlog",  "Symantec AV Scan-Logs", []),
            ("trendmicro_url",    "Trend Micro Web Reputation", []),
            ("trendmicro_vd",     "Trend Micro Virus Detection", []),
            ("onedrive_log",      "OneDrive Logs", []),
        ]),
        "network": ("Netzwerk, Server & Sonstiges", [
            ("networkminer_fileinfo", "NetworkMiner .fileinfos", []),
            ("text", "Server- & Netzwerk-Logs", [
                ("text/apache_access",         "Apache Access"),
                ("text/aws_elb_access",        "AWS ELB Access"),
                ("text/postgresql",            "PostgreSQL"),
                ("text/snort_fastlog",         "Snort / Suricata"),
                ("text/winfirewall",           "Windows Firewall"),
                ("text/winiis",                "Microsoft IIS"),
                ("text/powershell_transcript", "PowerShell Transcript"),
                ("text/sccm",                  "SCCM Client Log"),
                ("text/setupapi",              "SetupAPI"),
                ("text/teamviewer_application_log", "TeamViewer App"),
            ]),
        ]),
    }


# ══════════════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════════════

COLOR_BG        = "#f3f3f3"
COLOR_HEADER_BG = "#1F6AA5"
COLOR_HEADER_FG = "#ffffff"
COLOR_STEP_ACT  = "#1F6AA5"
COLOR_STEP_DONE = "#d0d0d0"
COLOR_STEP_PEND = "#e8e8e8"
COLOR_ACCENT    = "#1F8B4C"
COLOR_ERROR     = "#C0392B"


class PlasoWizard:
    STEPS = ["Image", "Ausgabe", "BitLocker", "Partition", "Parser", "Ausführen"]

    def __init__(self, root):
        self.root = root
        root.title("Plaso Docker Helper")
        root.geometry("1180x820")
        root.minsize(980, 700)
        root.configure(bg=COLOR_BG)

        self.catalog = build_catalog()
        self.current_step = 0

        # Status
        self.state = {
            "input_path": None,
            "input_dir": None,
            "input_file": None,
            "out_dir": None,
            "name": None,
            "credential_arg": [],
            "partitions_arg": [],
            "selected_parsers": set(),
        }

        # Threading
        self.log_queue = queue.Queue()
        self.process = None
        self.parser_check_state = {}  # name -> tk.BooleanVar

        self._setup_style()
        self._build_layout()
        self._show_step(0)

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────
    #  Style
    # ─────────────────────────────────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        # "vista" ist native Windows-Optik, "clam" ist neutral
        for theme in ("vista", "winnative", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("Header.TLabel",
                        background=COLOR_HEADER_BG, foreground=COLOR_HEADER_FG,
                        font=("Segoe UI", 16, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", foreground="#555555", font=("Segoe UI", 9))
        style.configure("Success.TLabel", foreground="#1F8B4C", font=("Segoe UI", 9, "bold"))
        style.configure("Error.TLabel", foreground=COLOR_ERROR, font=("Segoe UI", 9, "bold"))

        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TCheckbutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("TRadiobutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    # ─────────────────────────────────────────────────────────────
    #  Grundlayout
    # ─────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Header
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
            lbl.pack(side="left", padx=4, pady=9)
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
    #  Step-Navigation
    # ─────────────────────────────────────────────────────────────

    def _show_step(self, index):
        self.current_step = index

        # Content leeren
        for w in self.content.winfo_children():
            w.destroy()

        # Step-Bar aktualisieren
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
            self._step_run,
        ]
        builders[index]()

        self.footer_status.configure(text=f"Schritt {index + 1} von {len(self.STEPS)}")

    def _go_back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _go_next(self):
        # Validierung pro Schritt
        if self.current_step == 0 and not self.state["input_path"]:
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
            if self.bitlocker_var.get():
                cred_type = self.bitlocker_type_var.get().split("  (")[0]
                value = self.bitlocker_value_var.get().strip()
                if not value:
                    messagebox.showerror("Fehler", "Bitte den BitLocker-Schlüssel eingeben.")
                    return
                self.state["credential_arg"] = ["--credential", f"{cred_type}:{value}"]
            else:
                self.state["credential_arg"] = []
        if self.current_step == 3:
            if self.partition_mode_var.get() == "specific":
                num = self.partition_num_var.get().strip()
                if not num.isdigit():
                    messagebox.showerror("Fehler", "Bitte eine gültige Partitionsnummer eingeben.")
                    return
                self.state["partitions_arg"] = ["--partitions", num]
            else:
                self.state["partitions_arg"] = ["--partitions", "all"]

        if self.current_step < len(self.STEPS) - 1:
            self._show_step(self.current_step + 1)
        else:
            self._start_processing()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 1: Image
    # ─────────────────────────────────────────────────────────────

    def _step_image(self):
        ttk.Label(self.content, text="Eingabedatei (Forensik-Image)",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Wähle ein Beweis-Image (.E01, .dd, .raw, .vmdk).",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 18))

        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=5)

        self.image_path_var = tk.StringVar(value=self.state["input_path"] or "")
        entry = ttk.Entry(row, textvariable=self.image_path_var, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ttk.Button(row, text="📂  Durchsuchen", command=self._browse_image).pack(side="left")

        self.image_status = ttk.Label(self.content, text="", style="Muted.TLabel")
        self.image_status.pack(anchor="w", pady=(15, 0))

        # Automatische Validierung
        self.image_path_var.trace("w", lambda *a: self._validate_image())

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Forensik-Image auswählen",
            filetypes=[("Forensik-Images", "*.E01 *.e01 *.dd *.raw *.img *.vmdk"),
                       ("Alle Dateien", "*.*")]
        )
        if path:
            self.image_path_var.set(path)

    def _validate_image(self):
        p = Path(self.image_path_var.get())
        if p.is_file():
            self.state["input_path"] = str(p)
            self.state["input_dir"] = str(p.parent)
            self.state["input_file"] = p.name
            size_gb = p.stat().st_size / (1024 ** 3)
            self.image_status.configure(
                text=f"✔  {p.name}  ({size_gb:.2f} GB)", style="Success.TLabel")
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
                  text="Hierhin wird die .plaso-Datei gespeichert.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 18))

        # Ausgabeordner
        ttk.Label(self.content, text="Zielordner:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        out_row = ttk.Frame(self.content)
        out_row.pack(fill="x", pady=(5, 18))

        default_out = self.state["out_dir"] or (
            str(Path(self.state["input_dir"]) / "plaso") if self.state["input_dir"] else ""
        )
        self.out_dir_var = tk.StringVar(value=default_out)
        ttk.Entry(out_row, textvariable=self.out_dir_var, font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(out_row, text="📁  Ordner wählen", command=self._browse_outdir).pack(side="left")

        # Dateiname
        ttk.Label(self.content, text="Dateiname:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.filename_var = tk.StringVar(value=self.state["name"] or "timeline.plaso")
        ttk.Entry(self.content, textvariable=self.filename_var,
                  font=("Segoe UI", 10)).pack(fill="x", pady=(5, 0))

        self.out_status = ttk.Label(self.content, text="", style="Muted.TLabel")
        self.out_status.pack(anchor="w", pady=(15, 0))

        self.out_dir_var.trace("w", lambda *a: self._validate_out())
        self.filename_var.trace("w", lambda *a: self._validate_out())
        self._validate_out()

    def _browse_outdir(self):
        path = filedialog.askdirectory(title="Zielordner wählen")
        if path:
            self.out_dir_var.set(path)

    def _validate_out(self):
        out_dir = self.out_dir_var.get().strip()
        name = self.filename_var.get().strip() or "timeline.plaso"
        if not name.endswith(".plaso"):
            name += ".plaso"

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
                text=f"✔  {Path(out_dir).resolve()}\\{name}",
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
                  text="Falls das Image verschlüsselte Volumes enthält, kann Plaso "
                       "diese mit dem passenden Schlüssel entsperren.",
                  style="Muted.TLabel", wraplength=900, justify="left").pack(
            anchor="w", pady=(0, 18))

        self.bitlocker_var = tk.BooleanVar(value=bool(self.state["credential_arg"]))
        ttk.Checkbutton(self.content,
                        text="Ist das Image BitLocker-verschlüsselt?",
                        variable=self.bitlocker_var,
                        command=self._toggle_bitlocker).pack(anchor="w", pady=4)

        self.bitlocker_frame = ttk.LabelFrame(self.content, text="BitLocker-Details", padding=15)

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
        if self.bitlocker_var.get():
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
                        text="Alle Partitionen verarbeiten (empfohlen bei Unsicherheit)",
                        variable=self.partition_mode_var, value="all",
                        command=self._toggle_partition).pack(anchor="w", pady=5)
        ttk.Radiobutton(self.content,
                        text="Nur eine bestimmte Partition verarbeiten",
                        variable=self.partition_mode_var, value="specific",
                        command=self._toggle_partition).pack(anchor="w", pady=5)

        self.partition_num_frame = ttk.LabelFrame(self.content,
                                                  text="Partitionsnummer", padding=15)
        ttk.Label(self.partition_num_frame,
                  text="Nummer der Partition (z. B. 2):").pack(side="left", padx=(0, 10))
        self.partition_num_var = tk.StringVar(value="2")
        ttk.Entry(self.partition_num_frame, textvariable=self.partition_num_var,
                  width=10).pack(side="left")

        self._toggle_partition()

    def _toggle_partition(self):
        if self.partition_mode_var.get() == "specific":
            self.partition_num_frame.pack(fill="x", pady=(15, 0))
        else:
            self.partition_num_frame.pack_forget()

    # ─────────────────────────────────────────────────────────────
    #  Schritt 5: Parser-Auswahl (Treeview mit Checkboxen)
    # ─────────────────────────────────────────────────────────────

    def _step_parser(self):
        # Kopfzeile
        head = ttk.Frame(self.content)
        head.pack(fill="x", pady=(5, 10))
        ttk.Label(head, text="Parser auswählen", style="Title.TLabel").pack(side="left")
        self.parser_count_lbl = ttk.Label(head, text="", style="Success.TLabel")
        self.parser_count_lbl.pack(side="right")

        # Toolbar
        bar = ttk.Frame(self.content)
        bar.pack(fill="x", pady=(0, 10))

        ttk.Label(bar, text="Suche:").pack(side="left", padx=(0, 6))
        self.parser_search_var = tk.StringVar()
        self.parser_search_var.trace("w", lambda *a: self._refresh_parser_tree())
        ttk.Entry(bar, textvariable=self.parser_search_var, width=40).pack(side="left")

        ttk.Button(bar, text="Empf. Win-Set",
                   command=self._apply_win_preset).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Alle abwählen",
                   command=self._deselect_all).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle erweitern",
                   command=lambda: self._expand_all(True)).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle einklappen",
                   command=lambda: self._expand_all(False)).pack(side="left", padx=4)

        # Treeview
        tree_frame = ttk.Frame(self.content)
        tree_frame.pack(fill="both", expand=True)

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
        self.parser_tree.column("#0", width=20, stretch=False)
        self.parser_tree.column("check", width=32, stretch=False, anchor="center")
        self.parser_tree.column("name", width=280, stretch=False)
        self.parser_tree.column("desc", width=520, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.parser_tree.yview)
        self.parser_tree.configure(yscroll=vsb.set)
        self.parser_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Klick-Handling
        self.parser_tree.bind("<Button-1>", self._on_tree_click)

        # Tags für Aussehen
        self.parser_tree.tag_configure("category",
                                       background="#dfe8f2",
                                       font=("Segoe UI", 10, "bold"))
        self.parser_tree.tag_configure("plugin",
                                       foreground="#444444")
        self.parser_tree.tag_configure("selected",
                                       background="#eaf6ee")

        self._refresh_parser_tree()
        self._update_parser_count()

    def _refresh_parser_tree(self):
        # Alles löschen
        for iid in self.parser_tree.get_children():
            self.parser_tree.delete(iid)
        self.parser_tree_map = {}  # iid -> ("category"/"main"/"plugin", name)

        search = self.parser_search_var.get().strip().lower()

        for cat_key, (cat_label, parsers) in self.catalog.items():
            # Prüfen, ob in dieser Kategorie Treffer sind
            visible = []
            for name, desc, plugins in parsers:
                plugins_shown = []
                if search:
                    main_match = (search in name.lower() or search in desc.lower())
                    if main_match:
                        plugins_shown = plugins
                    else:
                        plugins_shown = [pl for pl in plugins
                                         if search in pl[0].lower() or search in pl[1].lower()]
                        if not plugins_shown:
                            continue
                else:
                    plugins_shown = plugins
                visible.append((name, desc, plugins_shown))

            if not visible:
                continue

            cat_iid = self.parser_tree.insert(
                "", "end",
                text="",
                values=("", f"▼ {cat_label}", ""),
                tags=("category",),
                open=bool(search),
            )
            self.parser_tree_map[cat_iid] = ("category", None)

            for name, desc, plugins in visible:
                checked = name in self.state["selected_parsers"]
                mark = "☑" if checked else "☐"
                main_iid = self.parser_tree.insert(
                    cat_iid, "end",
                    text="",
                    values=(mark, f"  {name}", desc),
                    tags=("selected",) if checked else (),
                )
                self.parser_tree_map[main_iid] = ("main", name)

                for pl_name, pl_desc in plugins:
                    pl_checked = pl_name in self.state["selected_parsers"]
                    pl_mark = "☑" if pl_checked else "☐"
                    pl_iid = self.parser_tree.insert(
                        main_iid, "end",
                        text="",
                        values=(pl_mark, f"    └─ {pl_name.split('/')[-1]}", pl_desc),
                        tags=("plugin", "selected") if pl_checked else ("plugin",),
                    )
                    self.parser_tree_map[pl_iid] = ("plugin", pl_name)

    def _on_tree_click(self, event):
        # Welche Spalte wurde geklickt?
        region = self.parser_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        iid = self.parser_tree.identify_row(event.y)
        if not iid:
            return

        col = self.parser_tree.identify_column(event.x)
        # Nur bei Klick auf Checkbox-Spalte (#1) umschalten
        if col != "#1":
            return

        info = self.parser_tree_map.get(iid)
        if not info:
            return
        kind, name = info
        if kind == "category":
            return

        # Toggle
        if name in self.state["selected_parsers"]:
            self.state["selected_parsers"].discard(name)
            # Wenn Hauptparser, auch alle Plugins entfernen
            if kind == "main":
                for cat_key, (_, parsers) in self.catalog.items():
                    for p_name, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].discard(pl_name)
        else:
            self.state["selected_parsers"].add(name)
            if kind == "main":
                for cat_key, (_, parsers) in self.catalog.items():
                    for p_name, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].add(pl_name)

        self._refresh_parser_tree()
        self._update_parser_count()

    def _expand_all(self, expand: bool):
        def walk(item):
            self.parser_tree.item(item, open=expand)
            for child in self.parser_tree.get_children(item):
                walk(child)
        for top in self.parser_tree.get_children():
            walk(top)

    def _apply_win_preset(self):
        preset = {"win10", "winevtx", "winreg", "mft", "prefetch",
                  "usnjrnl", "lnk", "sqlite"}
        # Plugins von winreg + sqlite automatisch mitnehmen
        for cat_key, (_, parsers) in self.catalog.items():
            for name, _, plugins in parsers:
                if name in preset:
                    for pl_name, _ in plugins:
                        preset.add(pl_name)
        self.state["selected_parsers"] = set(preset)
        self._refresh_parser_tree()
        self._update_parser_count()

    def _deselect_all(self):
        self.state["selected_parsers"].clear()
        self._refresh_parser_tree()
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
    #  Schritt 6: Ausführen
    # ─────────────────────────────────────────────────────────────

    def _step_run(self):
        ttk.Label(self.content, text="Verarbeitung starten",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 12))

        # Zusammenfassung
        summary = ttk.LabelFrame(self.content, text="Zusammenfassung", padding=15)
        summary.pack(fill="x", pady=(0, 15))

        rows = [
            ("Image",     self.state["input_path"] or "-"),
            ("Ausgabe",   f"{self.state['out_dir']}\\{self.state['name']}"
                          if self.state["out_dir"] else "-"),
            ("BitLocker", "aktiv" if self.state["credential_arg"] else "nein"),
            ("Partition", self.state["partitions_arg"][-1]
                          if self.state["partitions_arg"] else "auto"),
            ("Parser",    f"{len(self.state['selected_parsers'])} ausgewählt"
                          if self.state["selected_parsers"] else "alle"),
        ]
        for k, v in rows:
            row = ttk.Frame(summary)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"{k}:", width=12, font=("Segoe UI", 10, "bold")).pack(side="left")
            ttk.Label(row, text=str(v), font=("Segoe UI", 10)).pack(side="left", padx=(5, 0))

        # Progressbar
        self.progress = ttk.Progressbar(self.content, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(5, 10))

        # Log
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
        self.log_text.configure(yscrollcommand=log_vsb.set, xscrollcommand=log_hsb.set)
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

        # Log leeren
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        threading.Thread(target=self._run_pipeline, daemon=True).start()
        self.root.after(100, self._poll_log_queue)

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

    def _run_pipeline(self):
        try:
            # 1. log2timeline
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{self.state['input_dir']}:/mnt/input",
                "-v", f"{self.state['out_dir']}:/mnt/output",
                "log2timeline/plaso",
                "log2timeline",
                *self.state["credential_arg"],
                *self.state["partitions_arg"],
            ]
            if self.state["selected_parsers"]:
                cmd += ["--parsers", ",".join(sorted(self.state["selected_parsers"]))]
            cmd += [
                "--storage-file", f"/mnt/output/{self.state['name']}",
                f"/mnt/input/{self.state['input_file']}",
            ]

            self.log_queue.put(f"$ {' '.join(cmd)}\n\n")
            rc = self._run_and_stream(cmd)
            if rc != 0:
                self.log_queue.put(("DONE", rc))
                return

            # 2. psort → CSV
            self.log_queue.put("\n$ psort → CSV...\n\n")
            psort_cmd = [
                "docker", "run", "--rm",
                "-v", f"{self.state['out_dir']}:/mnt/output",
                "log2timeline/plaso",
                "psort",
                "-o", "l2tcsv",
                "-w", "/mnt/output/timeline.csv",
                f"/mnt/output/{self.state['name']}",
            ]
            rc = self._run_and_stream(psort_cmd)
            self.log_queue.put(("DONE", rc))
        except Exception as e:
            self.log_queue.put(f"\n✘ Ausnahme: {e}\n")
            self.log_queue.put(("DONE", 1))

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
            if not messagebox.askyesno("Bestätigung",
                                       "Ein Prozess läuft noch. Wirklich beenden?"):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════
#  Einstiegspunkt
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    # Skalierung auf HiDPI-Bildschirmen
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = PlasoWizard(root)
    root.mainloop()
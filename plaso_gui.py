#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plaso_gui.py - Plaso DFIR Helper (Final Edition + Quell-Modus "Vorhandene .plaso")

Architektur:
    GUI (Tkinter)
       │
       ▼
    Preflight (Validierung VOR dem Start)
       │
       ▼
    PlasoCommandBuilder → baut log2timeline / pinfo / psort Kommandos
       │
       ▼
    DockerRunner         → Prozessausführung, Streaming, Exit-Codes
       │
       ▼
    Plaso                → log2timeline → pinfo → psort
                           ODER (.plaso-Modus) → pinfo → psort

Neu:
  * Schritt 1 hat VIER Quell-Modi:
      - Einzel-Image
      - Ordner (Triage/KAPE)
      - Batch (mehrere Quellen)
      - Vorhandene .plaso-Datei  ← log2timeline wird übersprungen
  * Im .plaso-Modus werden Zielordner, Basisname und Exportformat
    direkt in Schritt 1 gewählt.
  * Der Workflow springt dann von Schritt 1 direkt zu Optionen → Ausführen.
  * Die Step-Leiste passt sich dem Modus dynamisch an.
"""

import os
import sys
import time
import queue
import hashlib
import threading
import subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ══════════════════════════════════════════════════════════════════════════
#  Konfiguration
# ══════════════════════════════════════════════════════════════════════════

PLASO_DOCKER_IMAGE = "log2timeline/plaso:20260720"

PLASO_DOCKER_DIGEST = "sha256:a8d42e64dcd3af2dffed8ddb25d34f34def69b672eec97ea9af62885c9332950"

OUTPUT_TIMEZONE = None

OUTPUT_FORMATS = [
    ("CSV (l2tcsv)", "l2tcsv",    ".csv",      "Für Excel / Timeline Explorer (Standard)"),
    ("JSON Lines",   "json_line", ".jsonl",    "Eine JSON-Zeile pro Ereignis (Streaming)"),
    ("JSON",         "json",      ".json",     "Vollständiges JSON-Array"),
    ("Bodyfile",     "bodyfile",  ".bodyfile", "SleuthKit v3 bodyfile (mactime)"),
    ("SQLite",       "sqlite",    ".sqlite",   "SQLite-Datenbank – für eigene Abfragen"),
    ("XLSX (Excel)", "xlsx",      ".xlsx",     "Excel Spreadsheet"),
]

PSORT_FILTER_PRESETS = [
    ("Alles (kein Filter)", ""),

    ("Benutzeraktivität",
     "data_type contains 'userassist' or "
     "data_type contains 'bagmru' or "
     "data_type contains 'typedurls' or "
     "data_type contains 'shell_item'"),

    ("Programmausführung",
     "data_type contains 'prefetch' or "
     "data_type contains 'amcache' or "
     "data_type contains 'appcompatcache' or "
     "data_type contains 'windows:registry:bam' or "
     "data_type contains 'userassist'"),

    ("Persistenz (Autostart)",
     "data_type contains 'windows:registry:run' or "
     "data_type contains 'windows:registry:service' or "
     "data_type contains 'windows:task_scheduler' or "
     "data_type contains 'boot_execute' or "
     "data_type contains 'winlogon'"),

    ("USB / externe Geräte",
     "data_type contains 'usb' or "
     "data_type contains 'mount_points' or "
     "data_type contains 'mountpoints'"),

    ("Browser-Aktivität",
     "data_type contains 'chrome' or "
     "data_type contains 'firefox' or "
     "data_type contains 'msie' or "
     "data_type contains 'edge' or "
     "data_type contains 'opera' or "
     "data_type contains 'safari'"),

    ("An-/Abmeldungen & Shutdown",
     "data_type contains 'shutdown' or "
     "data_type contains 'startup' or "
     "data_type contains 'timezone' or "
     "data_type contains 'logon' or "
     "data_type contains 'logoff'"),

    ("Eigener Filter …", "__CUSTOM__"),
]

CUSTOM_FILTER_SENTINEL = "__CUSTOM__"

PHYSICAL_ONLY_PARSERS = set()


# ══════════════════════════════════════════════════════════════════════════
#  Parser-Katalog
# ══════════════════════════════════════════════════════════════════════════

def build_catalog():
    """
    Parser-Katalog.
    Format pro Parser: (name, beschreibung, quelle, plugins)
    quelle:
      "both"                            → ✅ Image + Triage-Ordner
      "triage"                          → 📁 Nur Triage-Ordner
      ("image", "<spezifische Rohdatei>") → 💾 Image oder Ordner mit <Datei>
    """
    return {
        "recommended": ("⭐ Empfohlen für Windows-Triage", [
            ("winreg",       "Windows Registry – wichtigste Quelle für Benutzeraktivität", "both", []),
            ("winevtx",      "Windows EventLog – Anmeldungen, Prozesse, Dienste",          "both", []),
            ("prefetch",     "Prefetch – Programmausführung mit Laufzeit",                  "both", []),
            ("lnk",          "Verknüpfungsdateien – zuletzt geöffnete Dateien",             "both", []),
            ("mft",          "NTFS Master File Table – Datei-Metadaten",                    ("image", "$MFT"), []),
            ("usnjrnl",      "USN Change Journal – Dateiänderungen",                        ("image", "$UsnJrnl:$J"), []),
            ("recycle_bin",  "Papierkorb – gelöschte Dateien",                              "both", []),
            ("winjob",       "Geplante Tasks – Persistenz-Mechanismus",                     "both", []),
            ("sqlite",       "SQLite-Datenbanken – Browser, Apps",                          "both", []),
            ("chrome_cache", "Chrome Cache – Web-Aktivität",                                "both", []),
            ("firefox_cache2","Firefox Cache – Web-Aktivität",                              "both", []),
        ]),
        "windows": ("Windows-Kern", [
            ("winevtx", "Windows EventLog (EVTX) – XML-Ereignisprotokolle ab Vista", "both", []),
            ("winevt",  "Alte Windows EventLogs (EVT) – XP/2003-Format",              "both", []),
            ("winreg",  "Windows Registry – NTUSER.DAT, SYSTEM, SOFTWARE, SAM, SECURITY, USRCLASS", "both", [
                ("winreg/amcache",         "AmCache.hve – Programmausführung, SHA1-Hashes"),
                ("winreg/appcompatcache",  "AppCompatCache / ShimCache – Programm-Kompatibilität"),
                ("winreg/bam",             "Background Activity Moderator – App-Ausführung"),
                ("winreg/userassist",      "UserAssist – GUI-Programme mit Ausführungszähler"),
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
            ("mft",          "NTFS $MFT – Master File Table mit allen Datei-Metadaten",           ("image", "$MFT"), []),
            ("usnjrnl",      "NTFS USN Change Journal – Dateiänderungen seit $UsnJrnl-Erstellung", ("image", "$UsnJrnl:$J"), []),
            ("prefetch",     "Windows Prefetch – Ausführungsnachweise mit Laufzeiten",             "both", []),
            ("lnk",          "Windows Shortcuts (LNK) – Verknüpfungsdateien mit Zielpfaden",        "both", []),
            ("winjob",       "Geplante Tasks – Job-Dateien des Task Scheduler",                     "both", []),
            ("recycle_bin",  "Papierkorb ($Recycle.Bin $I) – gelöschte Dateien",                    "both", []),
            ("custom_destinations","Jump Lists – Anwendungsverlauf pro App",                        "both", []),
            ("rplog",        "System Restore Points (rp.log)",                                      "both", []),
            ("windefender_history","Windows Defender DetectionHistory",                             "both", []),
            ("filestat",     "Dateisystem-Statistiken – MACB-Zeiten",                               ("image", "$MFT / Dateisystem-Metadaten"), []),
            ("pe",           "Portable Executables – PE-Header-Informationen",                      "both", []),
            ("bodyfile",     "SleuthKit v3 bodyfile",                                               ("image", "Bodyfile-Datei (.bodyfile)"), []),
        ]),
        "browser": ("Browser & Web", [
            ("chrome_cache",       "Chrome Cache – gecachte Web-Inhalte", "both", []),
            ("chrome_preferences", "Chrome Preferences – Einstellungen",   "both", []),
            ("firefox_cache",      "Firefox Cache v1 (≤ 31)",             "both", []),
            ("firefox_cache2",     "Firefox Cache v2 (≥ 32)",             "both", []),
            ("msiecf",             "Internet Explorer Cache (index.dat)", "both", []),
            ("opera_global",       "Opera global history",                "both", []),
            ("opera_typed_history","Opera typed history – manuell eingegebene URLs","both", []),
            ("binary_cookies",     "Safari Binary Cookies",               "both", []),
            ("java_idx",           "Java WebStart Cache IDX",             "both", []),
        ]),
        "mobile": ("Mobile (iOS / Android)", [
            ("android_app_usage", "Android usage-history.xml – App-Nutzung", "both", []),
            ("discord_ios",       "iOS Discord Nachrichten",                  "both", []),
            ("unified_logging",   "Apple Unified Logging (tracev3)",          "both", []),
            ("sqlite", "SQLite – mobile App-Datenbanken", "both", [
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
            ("asl_log",          "Apple System Log (ASL) – Systemprotokoll",        "both", []),
            ("bsm_log",          "Basic Security Module (BSM) – Audit-Trail",        "both", []),
            ("fseventsd",        "File System Events – Dateiänderungen",             "both", []),
            ("mac_keychain",     "Keychain-Datenbank – Passwörter und Zertifikate",  "both", []),
            ("spotlight_storedb","Spotlight store.db – Suchindex",                   "both", []),
            ("utmpx",            "utmpx Login-Datensätze – Benutzeranmeldungen",     "both", []),
            ("plist", "Property Lists", "both", [
                ("plist/airport",         "Airport (WLAN) – bekannte Netze"),
                ("plist/macos_bluetooth", "Bluetooth-Geräte-Historie"),
                ("plist/safari_history",  "Safari Verlauf"),
                ("plist/time_machine",    "Time Machine Backup-Konfiguration"),
            ]),
            ("sqlite", "SQLite – macOS Apps", "both", [
                ("sqlite/appusage",       "Application Usage – App-Nutzung"),
                ("sqlite/mac_knowledgec", "Duet / KnowledgeC – Aktivitätsdaten"),
                ("sqlite/macostcc",       "TCC – Datenschutz-Berechtigungen"),
                ("sqlite/safari_historydb","Safari History.db"),
            ]),
        ]),
        "linux": ("Linux", [
            ("systemd_journal", "Systemd Journal – zentrales Log", "both", []),
            ("utmp",            "libc6 utmp – Login-Datensätze",    "both", []),
            ("fish_history",    "Fish Shell History",               "both", []),
            ("text", "Textbasierte Logs", "both", [
                ("text/apt_history", "APT History – Paket-Installationen"),
                ("text/bash_history","Bash History – Shell-Befehle"),
                ("text/dpkg",        "Dpkg Log – Paket-Manager"),
                ("text/syslog",      "Syslog – Systemmeldungen"),
                ("text/selinux",     "SELinux Audit-Log"),
                ("text/zsh_extended_history", "ZSH Extended History"),
            ]),
        ]),
        "databases": ("Datenbanken & Formate", [
            ("sqlite", "SQLite-Datenbanken (Desktop)", "both", [
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
            ("esedb", "ESE-Datenbanken", "both", [
                ("esedb/srum",          "SRUM – System Resource Usage Monitor"),
                ("esedb/msie_webcache", "IE/Edge WebCache (WebCacheV01.dat)"),
                ("esedb/file_history",  "Windows File History"),
            ]),
            ("olecf", "OLE Compound Files", "both", [
                ("olecf/olecf_automatic_destinations", "Automatic Destinations – Jump Lists"),
                ("olecf/olecf_summary",  "Summary Information"),
            ]),
            ("czip", "Compound ZIP (OpenXML)", "both", [
                ("czip/oxml", "OpenXML – Office-Dokumente (.docx, .xlsx)"),
            ]),
            ("jsonl", "JSON-L Logs (Cloud)", "both", [
                ("jsonl/aws_cloudtrail_log",    "AWS CloudTrail – API-Aufrufe"),
                ("jsonl/azure_activity_log",    "Azure Activity Log"),
                ("jsonl/gcp_log",               "Google Cloud Log"),
                ("jsonl/microsoft_audit_log",   "Microsoft 365 Audit-Log"),
                ("jsonl/docker_container_log",  "Docker Container Logs"),
            ]),
        ]),
        "win_apps": ("Windows-Anwendungen", [
            ("mcafee_protection", "McAfee Anti-Virus Protection Logs", "both", []),
            ("symantec_scanlog",  "Symantec AV Scan-Logs",             "both", []),
            ("trendmicro_url",    "Trend Micro Web Reputation",        "both", []),
            ("trendmicro_vd",     "Trend Micro Virus Detection",       "both", []),
            ("onedrive_log",      "OneDrive Logs",                     "both", []),
        ]),
        "network": ("Netzwerk, Server & Sonstiges", [
            ("networkminer_fileinfo", "NetworkMiner .fileinfos", "both", []),
            ("text", "Server- & Netzwerk-Logs", "both", [
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
#  Farben
# ══════════════════════════════════════════════════════════════════════════

COLOR_BG        = "#f3f3f3"
COLOR_HEADER_BG = "#1F6AA5"
COLOR_HEADER_FG = "#ffffff"
COLOR_STEP_ACT  = "#1F6AA5"
COLOR_STEP_DONE = "#d0d0d0"
COLOR_STEP_PEND = "#e8e8e8"
COLOR_ERROR     = "#C0392B"
COLOR_WARN      = "#B8860B"
COLOR_SUCCESS   = "#1F8B4C"


# ══════════════════════════════════════════════════════════════════════════
#  Helper
# ══════════════════════════════════════════════════════════════════════════

def format_docker_path(path_str) -> str:
    if not path_str:
        return ""
    raw = str(path_str)          # ← akzeptiert auch Path / WindowsPath
    try:
        p = Path(raw.strip().strip('"').strip("'")).resolve()
        return str(p).replace("\\", "/")
    except (OSError, RuntimeError):
        return raw.strip().strip('"').strip("'").replace("\\", "/")


def sha256_of_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════════
#  DockerRunner
# ══════════════════════════════════════════════════════════════════════════

class DockerRunner:
    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self.process = None

    def run_cmd(self, cmd: list) -> int:
        self.log_queue.put(f"$ {' '.join(cmd)}\n\n")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=creationflags,
            )
            for line in self.process.stdout:
                self.log_queue.put(line)
            self.process.wait()
            return self.process.returncode
        except FileNotFoundError:
            self.log_queue.put("✘ FEHLER: 'docker' wurde nicht gefunden. "
                               "Läuft Docker Desktop?\n")
            return -1
        except PermissionError as e:
            self.log_queue.put(f"✘ FEHLER (Permission): {e}\n")
            return -1
        except Exception as e:
            self.log_queue.put(f"✘ FEHLER (Unexpected): {e}\n")
            return -1
        finally:
            self.process = None

    def terminate(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════
#  PlasoCommandBuilder
# ══════════════════════════════════════════════════════════════════════════

class PlasoCommandBuilder:
    def __init__(self, docker_image: str = PLASO_DOCKER_IMAGE,
                 timezone: str = OUTPUT_TIMEZONE):
        self.docker_image = docker_image
        self.timezone = timezone

    def build_log2timeline(self, mount_source, input_arg, out_dir,
                           storage_name, *, is_folder=False,
                           credential_arg=None, partitions_arg=None,
                           vss_arg=None, parsers=None):
        credential_arg = credential_arg or []
        partitions_arg = partitions_arg or []
        vss_arg = vss_arg or []
        parsers = parsers or set()

        host_src = format_docker_path(mount_source)
        host_out = format_docker_path(out_dir)

        cmd = ["docker", "run", "--rm",
               "-v", f"{host_src}:/mnt/input:ro",
               "-v", f"{host_out}:/mnt/output",
               self.docker_image, "log2timeline"]

        if not is_folder:
            cmd += credential_arg
            cmd += partitions_arg
            cmd += vss_arg

        if parsers:
            cmd += ["--parsers", ",".join(sorted(parsers))]

        cmd += ["--storage-file", f"/mnt/output/{storage_name}.plaso"]
        cmd += [input_arg]
        return cmd

    def build_pinfo(self, out_dir: str, storage_name: str) -> list:
        host_out = format_docker_path(out_dir)
        return ["docker", "run", "--rm",
                "-v", f"{host_out}:/mnt/output:ro",
                self.docker_image, "pinfo",
                f"/mnt/output/{storage_name}.plaso"]

    def build_pinfo_on_file(self, plaso_path: str) -> list:
        p = Path(plaso_path).resolve()
        return ["docker", "run", "--rm",
                "-v", f"{format_docker_path(str(p.parent))}:/mnt/input:ro",   # ← mit str()
                self.docker_image, "pinfo",
                f"/mnt/input/{p.name}"]

    def build_psort(self, out_dir, storage_name, output_filename, fmt,
                    filter_expression=None):
        host_out = format_docker_path(out_dir)
        cmd = ["docker", "run", "--rm",
               "-v", f"{host_out}:/mnt/output",
               self.docker_image, "psort", "-o", fmt]
        if self.timezone:
            cmd += ["--output-time-zone", self.timezone]
        cmd += ["-w", f"/mnt/output/{output_filename}",
                f"/mnt/output/{storage_name}.plaso"]
        if filter_expression:
            cmd.append(filter_expression)
        return cmd

    def build_psort_from_existing(self, plaso_path, out_dir,
                                  output_filename, fmt,
                                  filter_expression=None):
        p = Path(plaso_path).resolve()
        host_src = format_docker_path(str(p.parent))  # ← mit str()
        host_out = format_docker_path(out_dir)
        cmd = ["docker", "run", "--rm",
               "-v", f"{host_src}:/mnt/input:ro",
               "-v", f"{host_out}:/mnt/output",
               self.docker_image, "psort", "-o", fmt]
        if self.timezone:
            cmd += ["--output-time-zone", self.timezone]
        cmd += ["-w", f"/mnt/output/{output_filename}",
                f"/mnt/input/{p.name}"]
        if filter_expression:
            cmd.append(filter_expression)
        return cmd


# ══════════════════════════════════════════════════════════════════════════
#  Wizard
# ══════════════════════════════════════════════════════════════════════════

class PlasoWizard:

    def __init__(self, root):
        self.root = root
        root.title("Plaso DFIR Helper")
        root.geometry("1220x880")
        root.minsize(1020, 740)
        root.configure(bg=COLOR_BG)

        self.catalog = build_catalog()

        PHYSICAL_ONLY_PARSERS.clear()
        for _, (_, parsers) in self.catalog.items():
            for name, _, source, _ in parsers:
                category = source[0] if isinstance(source, tuple) else source
                if category == "image":
                    PHYSICAL_ONLY_PARSERS.add(name)

        self.current_step = 0

        self.state = {
            # NEU: vierter Modus "plaso"
            "input_mode": "single",       # single | folder | batch | plaso
            "input_path": None,
            "input_dir": None,
            "input_file": None,
            "batch_items": [],
            # .plaso-Modus
            "existing_plaso_path": None,
            # Ausgabe
            "out_dir": None,
            "name": None,
            "selected_formats": [("json_line", ".jsonl")],
            # log2timeline-Optionen (nur Image-Modi)
            "credential_arg": [],
            "partitions_arg": [],
            "vss_arg": [],
            "selected_parsers": set(),
            # Optionen (beide Modi)
            "time_filter_enabled": False,
            "time_from": None,
            "time_to": None,
            "filter_presets": set(),
            "filter_custom": "",
        }

        self.steps = self._get_steps()      # ← NEU hier

        self.log_queue = queue.Queue()
        self.runner = DockerRunner(self.log_queue)
        self.builder = PlasoCommandBuilder()
        self.process_start_time = None
        self.timer_running = False
        self.batch_results = []

        self.expanded_categories = set()
        self.expanded_parsers = set()

        self._setup_style()
        self._build_layout()
        self._show_step(0)

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────
    #  Style
    # ─────────────────────────────────────────────────────────

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
        style.configure("Success.TLabel", foreground=COLOR_SUCCESS,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Error.TLabel", foreground=COLOR_ERROR,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Warn.TLabel", foreground=COLOR_WARN,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Timer.TLabel", foreground="#1F6AA5",
                        font=("Consolas", 11, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TCheckbutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("TRadiobutton", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    # ─────────────────────────────────────────────────────────
    #  Layout
    # ─────────────────────────────────────────────────────────

    def _build_layout(self):
        header = tk.Frame(self.root, bg=COLOR_HEADER_BG, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🕒  Plaso DFIR Helper",
                 bg=COLOR_HEADER_BG, fg=COLOR_HEADER_FG,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=25)

        self.step_bar = tk.Frame(self.root, bg="#e2e2e2", height=48)
        self.step_bar.pack(fill="x")
        self.step_bar.pack_propagate(False)

        self.content = tk.Frame(self.root, bg=COLOR_BG)
        self.content.pack(fill="both", expand=True, padx=22, pady=(15, 5))

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

        self._rebuild_step_bar()

    # ─────────────────────────────────────────────────────────
    #  Step-Leiste (dynamisch je Modus)
    # ─────────────────────────────────────────────────────────

    def _get_steps(self):
        if self.state["input_mode"] == "plaso":
            return ["Quelle", "Optionen", "Ausführen"]
        return ["Quelle", "Ausgabe", "BitLocker", "Partition",
                "Parser", "Optionen", "Ausführen"]

    def _rebuild_step_bar(self):
        for w in self.step_bar.winfo_children():
            w.destroy()
        inner = tk.Frame(self.step_bar, bg="#e2e2e2")
        inner.pack(expand=True)
        self.step_labels = []
        for i, name in enumerate(self.steps):
            lbl = tk.Label(inner, text=f"  {i+1}  {name}  ",
                           bg=COLOR_STEP_PEND, fg="#555555",
                           font=("Segoe UI", 10), padx=6, pady=6)
            lbl.pack(side="left", padx=3, pady=9)
            self.step_labels.append(lbl)
            if i < len(self.steps) - 1:
                tk.Label(inner, text="›", bg="#e2e2e2", fg="#888888",
                         font=("Segoe UI", 12, "bold")).pack(side="left")
        self._update_step_bar_colors()

    def _update_step_bar_colors(self):
        for i, lbl in enumerate(self.step_labels):
            if i == self.current_step:
                lbl.configure(bg=COLOR_STEP_ACT, fg="white",
                              font=("Segoe UI", 10, "bold"))
            elif i < self.current_step:
                lbl.configure(bg=COLOR_STEP_DONE, fg="#222222",
                              font=("Segoe UI", 10))
            else:
                lbl.configure(bg=COLOR_STEP_PEND, fg="#555555",
                              font=("Segoe UI", 10))

    # ─────────────────────────────────────────────────────────
    #  Navigation
    # ─────────────────────────────────────────────────────────

    def _show_step(self, index):
        self.steps = self._get_steps()
        if index >= len(self.steps):
            index = len(self.steps) - 1
        self.current_step = index

        for w in self.content.winfo_children():
            w.destroy()

        self._update_step_bar_colors()

        self.btn_back.configure(state="normal" if index > 0 else "disabled")
        if index == len(self.steps) - 1:
            self.btn_next.configure(text="🚀  Starten")
        else:
            self.btn_next.configure(text="Weiter   ▶")

        step_name = self.steps[index]
        builders = {
            "Quelle":     self._step_source,
            "Ausgabe":    self._step_output,
            "BitLocker":  self._step_bitlocker,
            "Partition":  self._step_partition,
            "Parser":     self._step_parser,
            "Optionen":   self._step_options,
            "Ausführen":  self._step_run,
        }
        builders[step_name]()
        self.footer_status.configure(
            text=f"Schritt {index + 1} von {len(self.steps)}")

    def _go_back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _go_next(self):
        step_name = self.steps[self.current_step]

        if step_name == "Quelle":
            if not self._validate_source_step():
                return
        elif step_name == "Ausgabe":
            if not self._validate_output_step():
                return
        elif step_name == "BitLocker":
            if not self._validate_bitlocker_step():
                return
        elif step_name == "Partition":
            if not self._validate_partition_step():
                return
        elif step_name == "Optionen":
            if not self._validate_options_step():
                return

        if self.current_step < len(self.steps) - 1:
            self._show_step(self.current_step + 1)
        else:
            if not self._preflight_check():
                return
            self._start_processing()

    # ─────────────────────────────────────────────────────────
    #  Validierung Schritt 1
    # ─────────────────────────────────────────────────────────

    def _validate_source_step(self):
        mode = self.state["input_mode"]

        if mode == "plaso":
            p = self.state.get("existing_plaso_path")
            if not p or not Path(p).is_file():
                messagebox.showerror("Fehler",
                    "Bitte eine gültige .plaso-Datei auswählen.")
                return False
            if not self.state.get("out_dir"):
                messagebox.showerror("Fehler", "Bitte einen Zielordner wählen.")
                return False
            if not self.state.get("name"):
                messagebox.showerror("Fehler", "Bitte einen Basis-Dateinamen angeben.")
                return False
            if not self.state.get("selected_formats"):
                messagebox.showerror("Fehler",
                    "Bitte mindestens ein Exportformat anhaken.")
                return False
            return True

        if mode == "batch":
            if not self.state["batch_items"]:
                messagebox.showerror("Fehler",
                    "Batch-Modus aktiv, aber keine Quellen hinzugefügt.")
                return False
            return True

        if not self.state.get("input_path"):
            if mode == "folder":
                messagebox.showerror("Fehler", "Bitte einen Ordner auswählen.")
            else:
                messagebox.showerror("Fehler", "Bitte eine Eingabedatei auswählen.")
            return False
        return True

    def _validate_output_step(self):
        if not self.state.get("out_dir"):
            messagebox.showerror("Fehler", "Bitte einen Ausgabeordner wählen.")
            return False
        if not self.state.get("name"):
            messagebox.showerror("Fehler", "Bitte einen Dateinamen angeben.")
            return False
        if not self.state.get("selected_formats"):
            messagebox.showerror("Fehler",
                "Bitte mindestens ein Ausgabeformat anhaken.")
            return False
        return True

    def _validate_bitlocker_step(self):
        if self.bitlocker_yes_var.get() == "yes":
            cred_type = self.bitlocker_type_var.get().split("  (")[0]
            value = self.bitlocker_value_var.get().strip()
            if not value:
                messagebox.showerror("Fehler",
                    "Bitte den BitLocker-Schlüssel eingeben.")
                return False
            self.state["credential_arg"] = [
                "--credential", f"{cred_type}:{value}"]
        else:
            self.state["credential_arg"] = []
        return True

    def _validate_partition_step(self):
        if self.partition_mode_var.get() == "specific":
            num = self.partition_num_var.get().strip()
            if not num.isdigit():
                messagebox.showerror("Fehler",
                    "Bitte eine gültige Partitionsnummer eingeben.")
                return False
            self.state["partitions_arg"] = ["--partitions", num]
        else:
            self.state["partitions_arg"] = ["--partitions", "all"]

        vss_mode = self.vss_mode_var.get()
        if vss_mode == "none":
            self.state["vss_arg"] = ["--vss_stores", "none"]
        elif vss_mode == "all":
            self.state["vss_arg"] = ["--vss_stores", "all"]
        elif vss_mode == "specific":
            vss_sel = self.vss_specific_var.get().strip()
            if not vss_sel:
                messagebox.showerror("Fehler",
                    "Bitte VSS-Store-Nummern eingeben (z. B. 1,4,5).")
                return False
            self.state["vss_arg"] = ["--vss_stores", vss_sel]
        else:
            self.state["vss_arg"] = []
        return True

    def _validate_options_step(self):
        if self.time_filter_var.get():
            tf = self.time_from_var.get().strip()
            tt = self.time_to_var.get().strip()
            if not tf or not tt:
                messagebox.showerror("Fehler",
                    "Bitte Von- und Bis-Zeit eingeben.")
                return False
            try:
                start_dt = datetime.strptime(tf, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(tt, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                messagebox.showerror("Fehler",
                    "Ungültiger Zeitpunkt.\n\n"
                    "Erwartetes Format: YYYY-MM-DD HH:MM:SS\n"
                    "Beispiel: 2026-09-26 14:30:15")
                return False
            if start_dt > end_dt:
                messagebox.showerror("Fehler",
                    "Der Startzeitpunkt muss vor dem Endzeitpunkt liegen.")
                return False
            self.state["time_filter_enabled"] = True
            self.state["time_from"] = tf
            self.state["time_to"] = tt
        else:
            self.state["time_filter_enabled"] = False
            self.state["time_from"] = None
            self.state["time_to"] = None

        self.state["filter_presets"] = {
            label for label, var in self.filter_vars.items() if var.get()
        }
        self.state["filter_custom"] = self.filter_custom_var.get().strip()

        if "Eigener Filter …" in self.state["filter_presets"]:
            if not self.state["filter_custom"]:
                messagebox.showerror("Fehler",
                    "Bitte einen eigenen Filterausdruck eingeben.")
                return False

        preset_expr = self._get_preset_filter_expression()
        if preset_expr:
            ok, msg = self._validate_filter_expression(preset_expr)
            if not ok:
                messagebox.showerror("Fehler",
                    f"Der Filterausdruck ist ungültig:\n\n{msg}\n\n"
                    f"Ausdruck:\n{preset_expr}")
                return False
        return True

    # ══════════════════════════════════════════════════════════
    #  Schritt 1: Quelle  (4 Modi, inkl. .plaso-Wiederverwendung)
    # ══════════════════════════════════════════════════════════

    def _step_source(self):
        ttk.Label(self.content, text="Eingabequelle",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Wähle, ob du ein Image / einen Triage-Ordner parsen "
                       "oder eine bereits vorhandene .plaso-Datei "
                       "wiederverwenden willst.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 12))

        mode_frame = ttk.LabelFrame(self.content, text="Quell-Modus", padding=10)
        mode_frame.pack(fill="x", pady=(0, 12))

        self.mode_var = tk.StringVar(value=self.state["input_mode"])
        ttk.Radiobutton(mode_frame,
                        text="Einzel-Image (.E01, .dd, .raw, .vmdk)",
                        variable=self.mode_var, value="single",
                        command=self._on_mode_change).pack(anchor="w", pady=2)
        ttk.Radiobutton(mode_frame,
                        text="Ordner (entpacktes Triage-/KAPE-Verzeichnis)",
                        variable=self.mode_var, value="folder",
                        command=self._on_mode_change).pack(anchor="w", pady=2)
        ttk.Radiobutton(mode_frame,
                        text="Batch-Modus (mehrere Images und/oder Ordner)",
                        variable=self.mode_var, value="batch",
                        command=self._on_mode_change).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            mode_frame,
            text="Vorhandene .plaso-Datei wiederverwenden "
                 "(nur psort – spart sehr viel Zeit)",
            variable=self.mode_var, value="plaso",
            command=self._on_mode_change).pack(anchor="w", pady=2)

        self.single_frame = ttk.Frame(self.content)
        self.folder_frame = ttk.Frame(self.content)
        self.batch_frame  = ttk.Frame(self.content)
        self.plaso_frame  = ttk.Frame(self.content)

        # ── Einzel-Image ────────────────────────────────────
        ttk.Label(self.single_frame, text="Pfad zum Image:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(self.single_frame)
        row.pack(fill="x", pady=(4, 0))
        self.image_path_var = tk.StringVar(value=self.state["input_path"] or "")
        ent = ttk.Entry(row, textvariable=self.image_path_var, font=("Segoe UI", 10))
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ent.bind("<Return>",     lambda e: self._validate_image(full=True))
        ent.bind("<FocusOut>",   lambda e: self._validate_image(full=True))
        self.image_path_var.trace("w", lambda *a: self._validate_image(full=False))
        ttk.Button(row, text="📂  Durchsuchen",
                   command=self._browse_image).pack(side="left")

        # ── Ordner ──────────────────────────────────────────
        ttk.Label(self.folder_frame, text="Pfad zum Ordner:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        frow = ttk.Frame(self.folder_frame)
        frow.pack(fill="x", pady=(4, 0))
        self.folder_path_var = tk.StringVar(value=self.state["input_path"] or "")
        fent = ttk.Entry(frow, textvariable=self.folder_path_var, font=("Segoe UI", 10))
        fent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        fent.bind("<Return>",   lambda e: self._validate_image(full=True))
        fent.bind("<FocusOut>", lambda e: self._validate_image(full=True))
        self.folder_path_var.trace("w", lambda *a: self._validate_image(full=False))
        ttk.Button(frow, text="📁  Ordner wählen",
                   command=self._browse_folder).pack(side="left")

        # ── Batch ───────────────────────────────────────────
        ttk.Label(self.batch_frame,
                  text="Ausgewählte Quellen (Images und/oder Ordner):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        btn_row = ttk.Frame(self.batch_frame)
        btn_row.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text="➕  Images hinzufügen",
                   command=self._browse_batch_images).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="📁  Ordner hinzufügen",
                   command=self._browse_batch_folders).pack(side="left", padx=6)
        ttk.Button(btn_row, text="🗑  Entfernen",
                   command=self._remove_selected_batch_item).pack(side="left", padx=6)
        ttk.Button(btn_row, text="✕  Alle leeren",
                   command=self._clear_batch).pack(side="left", padx=6)

        list_container = ttk.Frame(self.batch_frame)
        list_container.pack(fill="both", expand=True)
        self.batch_list = tk.Listbox(list_container, height=8,
                                     font=("Consolas", 9), selectmode="extended")
        list_vsb = ttk.Scrollbar(list_container, orient="vertical",
                                 command=self.batch_list.yview)
        self.batch_list.configure(yscrollcommand=list_vsb.set)
        self.batch_list.pack(side="left", fill="both", expand=True)
        list_vsb.pack(side="right", fill="y")

        # ── .plaso-Wiederverwendung ─────────────────────────
        self._build_plaso_panel(self.plaso_frame)

        self.image_status = ttk.Label(self.content, text="", style="Muted.TLabel")
        self.image_status.pack(anchor="w", pady=(15, 0))

        self._on_mode_change(initial=True)
        self._rebuild_batch_list()

    # ─────────────────────────────────────────────────────────
    #  .plaso-Panel (inkl. Ziel, Name, Format)
    # ─────────────────────────────────────────────────────────

    def _build_plaso_panel(self, parent):
        tk.Label(
            parent,
            text=("ℹ  Im .plaso-Modus wird log2timeline (und damit auch "
                  "BitLocker, Partition, Parser) übersprungen.\n"
                  "    Die .plaso-Datei wird read-only gemountet und NICHT "
                  "verändert. Nur pinfo + psort laufen."),
            bg="#e7f1fb", fg="#0b4a80", justify="left",
            font=("Segoe UI", 9), padx=10, pady=6, anchor="w"
        ).pack(fill="x", pady=(0, 10))

        ttk.Label(parent, text="Vorhandene .plaso-Datei:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 0))
        self.existing_plaso_var = tk.StringVar(
            value=self.state.get("existing_plaso_path") or "")
        ttk.Entry(row, textvariable=self.existing_plaso_var,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="📄  .plaso wählen",
                   command=self._browse_existing_plaso).pack(side="left")

        self.existing_plaso_status = ttk.Label(
            parent, text="", style="Muted.TLabel",
            wraplength=900, justify="left")
        self.existing_plaso_status.pack(anchor="w", pady=(4, 12))
        self.existing_plaso_var.trace(
            "w", lambda *a: self._validate_existing_plaso())

        # Zielordner + Basisname + Formate (leben normalerweise in "Ausgabe")
        self._build_output_section(parent)
        self._build_format_section(parent,
            info_text="ℹ  Du kannst mehrere Formate gleichzeitig wählen. "
                      "Die .plaso-Datei wird nicht neu erzeugt – jedes "
                      "Format wird direkt daraus exportiert.")

        self.out_status = ttk.Label(parent, text="", style="Muted.TLabel",
                                    wraplength=1100, justify="left")
        self.out_status.pack(anchor="w", pady=(12, 0))
        self._validate_out()

    def _build_output_section(self, parent):
        ttk.Label(parent, text="Zielordner:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 0))
        out_row = ttk.Frame(parent)
        out_row.pack(fill="x", pady=(5, 10))

        default_dir = self.state.get("out_dir") or ""
        if not default_dir:
            if self.state["input_mode"] == "plaso" and \
               self.state.get("existing_plaso_path"):
                default_dir = str(Path(self.state["existing_plaso_path"]).parent)
            elif self.state["input_mode"] == "folder" and self.state["input_path"]:
                default_dir = str(Path(self.state["input_path"]).parent / "plaso")
            elif self.state.get("input_dir"):
                default_dir = str(Path(self.state["input_dir"]) / "plaso")
            elif self.state["input_mode"] == "batch" and self.state["batch_items"]:
                first = Path(self.state["batch_items"][0]["path"])
                base = first.parent if first.is_file() else first
                default_dir = str(base / "plaso")

        self.out_dir_var = tk.StringVar(value=default_dir)
        ttk.Entry(out_row, textvariable=self.out_dir_var,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(out_row, text="📁  Ordner wählen",
                   command=self._browse_outdir).pack(side="left")

        ttk.Label(parent, text="Basis-Dateiname:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(parent,
                  text="(Erweiterung wird je nach Format automatisch gesetzt. "
                       "Im Batch-Modus pro Quelle ein Unterordner.)",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))

        self.filename_var = tk.StringVar(value=self.state["name"] or "timeline")
        ttk.Entry(parent, textvariable=self.filename_var,
                  font=("Segoe UI", 10)).pack(fill="x", pady=(0, 10))

        self.out_dir_var.trace("w", lambda *a: self._validate_out())
        self.filename_var.trace("w", lambda *a: self._validate_out())

    def _build_format_section(self, parent, info_text):
        ttk.Label(parent, text="Ausgabeformat(e):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(parent, text=info_text, bg="#fff8dc", fg="#664d03",
                 justify="left", font=("Segoe UI", 9),
                 padx=10, pady=6, anchor="w").pack(fill="x", pady=(4, 8))

        fmt_frame = ttk.Frame(parent)
        fmt_frame.pack(fill="x", pady=(0, 6))

        self.format_vars = {}
        selected_values = {v for v, e in self.state["selected_formats"]}

        for label, value, ext, desc in OUTPUT_FORMATS:
            row = ttk.Frame(fmt_frame)
            row.pack(fill="x", pady=2)
            var = tk.BooleanVar(value=(value in selected_values))
            self.format_vars[label] = var
            ttk.Checkbutton(row, text=label, variable=var,
                            command=self._on_format_change).pack(side="left")
            if value == "l2tcsv":
                desc_style = "Warn.TLabel"
                desc = "⚠ Nur Sekunden-Genauigkeit – für DFIR ist JSON Lines oder XLSX empfohlen"
            else:
                desc_style = "Muted.TLabel"
            ttk.Label(row, text=f"  {desc}",
                      style=desc_style).pack(side="left")

    def _on_mode_change(self, initial=False):
        mode = self.mode_var.get()
        old_mode = self.state["input_mode"]
        self.state["input_mode"] = mode

        # Step-Leiste anpassen, wenn Modus-Kategorie wechselt
        old_is_plaso = (old_mode == "plaso")
        new_is_plaso = (mode == "plaso")
        if old_is_plaso != new_is_plaso:
            self.steps = self._get_steps()
            self._rebuild_step_bar()

        self.single_frame.pack_forget()
        self.folder_frame.pack_forget()
        self.batch_frame.pack_forget()
        self.plaso_frame.pack_forget()

        if mode == "single":
            self.single_frame.pack(fill="x", pady=5)
        elif mode == "folder":
            self.folder_frame.pack(fill="x", pady=5)
        elif mode == "batch":
            self.batch_frame.pack(fill="both", expand=True, pady=5)
        elif mode == "plaso":
            self.plaso_frame.pack(fill="both", expand=True, pady=5)

        self._validate_image(full=False)

    # ─────────────────────────────────────────────────────────
    #  .plaso-Auswahl / Validierung
    # ─────────────────────────────────────────────────────────

    def _browse_existing_plaso(self):
        path = filedialog.askopenfilename(
            title="Vorhandene .plaso-Datei auswählen",
            filetypes=[("Plaso Storage", "*.plaso"),
                       ("Alle Dateien", "*.*")])
        if path:
            self.existing_plaso_var.set(path)

    def _validate_existing_plaso(self):
        raw = self.existing_plaso_var.get().strip()
        if not raw:
            self.state["existing_plaso_path"] = None
            self.existing_plaso_status.configure(text="")
            self._validate_out()
            return
        p = Path(raw)
        if p.is_file() and p.suffix.lower() == ".plaso":
            self.state["existing_plaso_path"] = str(p.resolve())
            # Wenn Zielordner noch leer → auf .plaso-Verzeichnis setzen
            if not self.out_dir_var.get().strip():
                self.out_dir_var.set(str(p.parent))
            try:
                size_mb = p.stat().st_size / (1024 * 1024)
                self.existing_plaso_status.configure(
                    text=f"✔  {p.name}  ({size_mb:.1f} MB)",
                    style="Success.TLabel")
            except OSError as e:
                self.existing_plaso_status.configure(
                    text=f"✘  {e}", style="Error.TLabel")
        else:
            self.state["existing_plaso_path"] = None
            self.existing_plaso_status.configure(
                text="✘  Datei nicht gefunden oder keine .plaso-Datei.",
                style="Error.TLabel")
        self._validate_out()

    # ─────────────────────────────────────────────────────────
    #  Formate / Zielordner-Validierung (gemeinsam genutzt)
    # ─────────────────────────────────────────────────────────

    def _on_format_change(self):
        selected = []
        for label, value, ext, desc in OUTPUT_FORMATS:
            if self.format_vars.get(label) and self.format_vars[label].get():
                selected.append((value, ext))
        self.state["selected_formats"] = selected
        self._validate_out()

    def _browse_outdir(self):
        path = filedialog.askdirectory(title="Zielordner wählen")
        if path:
            self.out_dir_var.set(path)

    def _validate_out(self):
        if not hasattr(self, "out_dir_var") or not hasattr(self, "filename_var"):
            return
        out_dir = self.out_dir_var.get().strip()
        name = self.filename_var.get().strip() or "timeline"

        for _, _, ext, _ in OUTPUT_FORMATS:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break

        if not out_dir:
            self.state["out_dir"] = None
            self.state["name"] = None
            if hasattr(self, "out_status"):
                self.out_status.configure(text="")
            return
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            self.state["out_dir"] = str(Path(out_dir).resolve())
            self.state["name"] = name

            if not self.state["selected_formats"]:
                if hasattr(self, "out_status"):
                    self.out_status.configure(
                        text="⚠  Kein Ausgabeformat ausgewählt – "
                             "bitte mindestens eines anhaken.",
                        style="Error.TLabel")
                return

            mode = self.state["input_mode"]

            if mode == "plaso":
                plaso_src = Path(self.state["existing_plaso_path"]).name \
                    if self.state.get("existing_plaso_path") else "?"
                files = [f"{self.state['out_dir']}\\{name}{ext}"
                         for _, ext in self.state["selected_formats"]]
                preview = files[0]
                if len(files) > 1:
                    preview += f"   (+{len(files) - 1} weitere)"
                if hasattr(self, "out_status"):
                    self.out_status.configure(
                        text=f"✔  Quelle: {plaso_src}  (read-only)\n"
                             f"✔  Ziel:   {preview}\n"
                             f"ℹ  log2timeline wird übersprungen – "
                             f"nur pinfo + psort laufen.",
                        style="Success.TLabel")
                return

            if mode == "batch":
                preview = (f"{self.state['out_dir']}\\<NN_quelle>\\{name}"
                           f"<endung>   (Unterordner pro Quelle)")
            else:
                files = [f"{self.state['out_dir']}\\{name}{ext}"
                         for _, ext in self.state["selected_formats"]]
                preview = files[0]
                if len(files) > 1:
                    preview += f"   (+{len(files) - 1} weitere)"
            if hasattr(self, "out_status"):
                self.out_status.configure(text=f"✔  {preview}",
                                          style="Success.TLabel")
        except OSError as e:
            self.state["out_dir"] = None
            if hasattr(self, "out_status"):
                self.out_status.configure(text=f"✘  {e}",
                                          style="Error.TLabel")

    # ─────────────────────────────────────────────────────────
    #  Image-/Ordner-/Batch-Browse + Validierung
    # ─────────────────────────────────────────────────────────

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Forensik-Image auswählen",
            filetypes=[("Forensik-Images",
                        "*.E01 *.e01 *.dd *.raw *.img *.vmdk"),
                       ("Alle Dateien", "*.*")])
        if path:
            self.image_path_var.set(path)
            self._validate_image(full=True)

    def _browse_folder(self):
        path = filedialog.askdirectory(
            title="Entpacktes Triage-/KAPE-Verzeichnis wählen")
        if path:
            self.folder_path_var.set(path)
            self._validate_image(full=True)

    def _browse_batch_images(self):
        paths = filedialog.askopenfilenames(
            title="Images auswählen (Strg/Shift für mehrere)",
            filetypes=[("Forensik-Images",
                        "*.E01 *.e01 *.dd *.raw *.img *.vmdk"),
                       ("Alle Dateien", "*.*")])
        if not paths:
            return
        existing = {i["path"] for i in self.state["batch_items"]}
        added = 0
        for p in paths:
            if p not in existing:
                self.state["batch_items"].append({
                    "path": p, "type": "image", "size_bytes": None})
                added += 1
        self._rebuild_batch_list()
        self._validate_image(full=False)
        self._start_batch_size_worker()
        if added:
            self.image_status.configure(
                text=f"✔  {added} Image(s) hinzugefügt", style="Success.TLabel")

    def _browse_batch_folders(self):
        while True:
            path = filedialog.askdirectory(
                title="Ordner hinzufügen (Abbrechen beendet die Auswahl)")
            if not path:
                break
            existing = {i["path"] for i in self.state["batch_items"]}
            if path not in existing:
                self.state["batch_items"].append({
                    "path": path, "type": "folder", "size_bytes": None})
                self._rebuild_batch_list()
                self._validate_image(full=False)
                self._start_batch_size_worker()
            if not messagebox.askyesno(
                    "Weiteren Ordner hinzufügen?",
                    "Möchtest du einen weiteren Ordner hinzufügen?"):
                break

    def _start_batch_size_worker(self):
        def worker():
            for item in self.state["batch_items"]:
                if item.get("size_bytes") is not None:
                    continue
                p = Path(item["path"])
                try:
                    if item["type"] == "image":
                        total = p.stat().st_size
                        n = None
                    else:
                        total = 0
                        n = 0
                        for f in p.rglob("*"):
                            if f.is_file():
                                n += 1
                                try:
                                    total += f.stat().st_size
                                except OSError:
                                    pass
                    item["size_bytes"] = total
                    item["n_files"] = n
                except (OSError, PermissionError):
                    item["size_bytes"] = -1
                    item["n_files"] = None
            try:
                self.root.after(0, self._rebuild_batch_list)
            except tk.TclError:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _remove_selected_batch_item(self):
        sel = list(self.batch_list.curselection())
        if not sel:
            messagebox.showinfo("Hinweis",
                "Bitte zuerst einen oder mehrere Einträge markieren.")
            return
        for idx in sorted(sel, reverse=True):
            del self.state["batch_items"][idx]
        self._rebuild_batch_list()
        self._validate_image(full=False)

    def _clear_batch(self):
        if not self.state["batch_items"]:
            return
        if messagebox.askyesno("Bestätigung",
                f"Wirklich alle {len(self.state['batch_items'])} "
                "Einträge entfernen?"):
            self.state["batch_items"].clear()
            self._rebuild_batch_list()
            self._validate_image(full=False)

    def _rebuild_batch_list(self):
        if not hasattr(self, "batch_list"):
            return
        self.batch_list.delete(0, "end")
        for item in self.state["batch_items"]:
            p = Path(item["path"])
            typ = "[IMG]" if item["type"] == "image" else "[DIR]"
            size_bytes = item.get("size_bytes")
            n_files = item.get("n_files")
            if size_bytes is None:
                size_txt = "berechne…"
            elif size_bytes < 0:
                size_txt = "?"
            elif item["type"] == "image":
                size_txt = f"{size_bytes / (1024**3):.2f} GB"
            else:
                n_txt = f"{n_files} Dateien, " if n_files is not None else ""
                size_txt = f"{n_txt}{size_bytes / (1024**3):.2f} GB"
            self.batch_list.insert("end", f"  {typ} {p.name}   ({size_txt})")

    def _validate_image(self, full=False):
        mode = self.state["input_mode"]
        if mode == "plaso":
            return
        if mode == "single":
            p = Path(self.image_path_var.get())
            if p.is_file():
                self.state["input_path"] = str(p)
                self.state["input_dir"]  = str(p.parent)
                self.state["input_file"] = p.name
                if full:
                    try:
                        size_gb = p.stat().st_size / (1024 ** 3)
                        self.image_status.configure(
                            text=f"✔  {p.name}  ({size_gb:.2f} GB)",
                            style="Success.TLabel")
                    except OSError as e:
                        self.image_status.configure(text=f"✘  {e}",
                                                    style="Error.TLabel")
                else:
                    self.image_status.configure(text=f"✔  {p.name}",
                                                style="Success.TLabel")
            else:
                self.state["input_path"] = None
                self.image_status.configure(text="", style="Muted.TLabel")

        elif mode == "folder":
            p = Path(self.folder_path_var.get())
            if p.is_dir():
                self.state["input_path"] = str(p)
                self.state["input_dir"]  = str(p.parent)
                self.state["input_file"] = p.name
                if full:
                    try:
                        n_files, total = 0, 0
                        for f in p.rglob("*"):
                            if f.is_file():
                                n_files += 1
                                try:
                                    total += f.stat().st_size
                                except OSError:
                                    pass
                        self.image_status.configure(
                            text=f"✔  {p.name}  ({n_files} Dateien, "
                                 f"{total / (1024**3):.2f} GB)",
                            style="Success.TLabel")
                    except (OSError, PermissionError) as e:
                        self.image_status.configure(text=f"✘  {e}",
                                                    style="Error.TLabel")
                else:
                    self.image_status.configure(
                        text=f"✔  {p.name}   (Enter drücken für Größe)",
                        style="Success.TLabel")
            else:
                self.state["input_path"] = None
                self.image_status.configure(text="", style="Muted.TLabel")

        elif mode == "batch":
            n_img = sum(1 for i in self.state["batch_items"] if i["type"] == "image")
            n_dir = sum(1 for i in self.state["batch_items"] if i["type"] == "folder")
            if not self.state["batch_items"]:
                self.image_status.configure(text="")
            else:
                parts = []
                if n_img: parts.append(f"{n_img} Image(s)")
                if n_dir: parts.append(f"{n_dir} Ordner")
                self.image_status.configure(
                    text=f"✔  {len(self.state['batch_items'])} Quelle(n) "
                         f"({', '.join(parts)})",
                    style="Success.TLabel")

    # ══════════════════════════════════════════════════════════
    #  Schritt 2: Ausgabe  (nur Image-Modi)
    # ══════════════════════════════════════════════════════════

    def _step_output(self):
        ttk.Label(self.content, text="Ausgabeort & Dateiname",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Hierhin werden die .plaso-Datei und die Exporte "
                       "gespeichert.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

        self._build_output_section(self.content)
        self._build_format_section(self.content,
            info_text="ℹ  Du kannst mehrere Formate gleichzeitig wählen. "
                      "Die .plaso-Datei wird einmal erzeugt – jedes weitere "
                      "Format wird daraus exportiert.")

        self.out_status = ttk.Label(self.content, text="",
                                    style="Muted.TLabel",
                                    wraplength=1100, justify="left")
        self.out_status.pack(anchor="w", pady=(12, 0))
        self._validate_out()

    # ══════════════════════════════════════════════════════════
    #  Schritt 3: BitLocker
    # ══════════════════════════════════════════════════════════

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
                  width=80, show="•").pack(fill="x", pady=(0, 4))
        ttk.Label(self.bitlocker_frame,
                  text="⚠  Der Schlüssel wird nur zur Laufzeit an Docker "
                       "übergeben und NICHT gespeichert oder geloggt.",
                  style="Warn.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(self.bitlocker_frame,
                  text="Beispiel: 123456-789012-345678-901234-567890-123456-789012-345678",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        self._toggle_bitlocker()

    def _toggle_bitlocker(self):
        if self.bitlocker_yes_var.get() == "yes":
            self.bitlocker_frame.pack(fill="x", pady=(15, 0))
        else:
            self.bitlocker_frame.pack_forget()

    # ══════════════════════════════════════════════════════════
    #  Schritt 4: Partition + VSS
    # ══════════════════════════════════════════════════════════

    def _step_partition(self):
        ttk.Label(self.content,
                  text="Partition & Volume Shadow Copies (VSS)",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Partition-Auswahl gilt nur für physische Images. "
                       "VSS-Stores enthalten historische Datei-Versionen – "
                       "für Windows-Forensik sehr wertvoll.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 15))

        part_frame = ttk.LabelFrame(self.content, text="Partition", padding=10)
        part_frame.pack(fill="x", pady=(0, 12))

        self.partition_mode_var = tk.StringVar(
            value="specific" if self.state["partitions_arg"] and
                  self.state["partitions_arg"][-1] != "all" else "all")
        ttk.Radiobutton(part_frame,
                        text="Alle Partitionen verarbeiten "
                             "(empfohlen bei Unsicherheit)",
                        variable=self.partition_mode_var, value="all",
                        command=self._toggle_partition).pack(anchor="w", pady=2)
        ttk.Radiobutton(part_frame,
                        text="Nur eine bestimmte Partition verarbeiten",
                        variable=self.partition_mode_var, value="specific",
                        command=self._toggle_partition).pack(anchor="w", pady=2)

        self.partition_num_frame = ttk.Frame(part_frame)
        ttk.Label(self.partition_num_frame,
                  text="Nummer der Partition (z. B. 2):").pack(
            side="left", padx=(20, 10))
        self.partition_num_var = tk.StringVar(value="2")
        ttk.Entry(self.partition_num_frame,
                  textvariable=self.partition_num_var,
                  width=10).pack(side="left")

        vss_frame = ttk.LabelFrame(self.content,
                                   text="Volume Shadow Copies (nur Images)",
                                   padding=10)
        vss_frame.pack(fill="x", pady=(0, 12))

        current_vss = self.state["vss_arg"][-1] if self.state["vss_arg"] else "skip"
        if current_vss == "all":
            initial_vss = "all"
        elif current_vss == "none":
            initial_vss = "none"
        elif current_vss == "skip":
            initial_vss = "skip"
        else:
            initial_vss = "specific"

        self.vss_mode_var = tk.StringVar(value=initial_vss)
        ttk.Radiobutton(vss_frame,
                        text="Keine VSS verarbeiten (--vss_stores none)",
                        variable=self.vss_mode_var, value="none",
                        command=self._toggle_vss).pack(anchor="w", pady=2)
        ttk.Radiobutton(vss_frame,
                        text="Nicht angeben – Plaso entscheidet automatisch",
                        variable=self.vss_mode_var, value="skip",
                        command=self._toggle_vss).pack(anchor="w", pady=2)
        ttk.Radiobutton(vss_frame,
                        text="Alle VSS-Stores verarbeiten (--vss_stores all)",
                        variable=self.vss_mode_var, value="all",
                        command=self._toggle_vss).pack(anchor="w", pady=2)
        ttk.Radiobutton(vss_frame,
                        text="Bestimmte VSS-Stores (z. B. 1,4,5)",
                        variable=self.vss_mode_var, value="specific",
                        command=self._toggle_vss).pack(anchor="w", pady=2)

        self.vss_specific_frame = ttk.Frame(vss_frame)
        ttk.Label(self.vss_specific_frame,
                  text="Store-Nummern (Komma-getrennt):").pack(
            side="left", padx=(20, 10))
        self.vss_specific_var = tk.StringVar(value="1")
        ttk.Entry(self.vss_specific_frame,
                  textvariable=self.vss_specific_var,
                  width=15).pack(side="left")

        self._toggle_partition()
        self._toggle_vss()

    def _toggle_partition(self):
        if self.partition_mode_var.get() == "specific":
            self.partition_num_frame.pack(fill="x", pady=(4, 0))
        else:
            self.partition_num_frame.pack_forget()

    def _toggle_vss(self):
        if self.vss_mode_var.get() == "specific":
            self.vss_specific_frame.pack(fill="x", pady=(4, 0))
        else:
            self.vss_specific_frame.pack_forget()

    # ══════════════════════════════════════════════════════════
    #  Schritt 5: Parser
    # ══════════════════════════════════════════════════════════

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

        ttk.Button(bar, text="Empfohlenes Windows-Set",
                   command=self._apply_recommended_windows_set).pack(
            side="left", padx=(12, 4))
        ttk.Button(bar, text="Alle abwählen",
                   command=self._deselect_all).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle erweitern",
                   command=lambda: self._expand_all(True)).pack(side="left", padx=4)
        ttk.Button(bar, text="Alle einklappen",
                   command=lambda: self._expand_all(False)).pack(side="left", padx=4)

        parser_hint = tk.Label(
            self.content,
            text=("ℹ  Nur einzelne Parser wählen (z. B. winevtx, winreg, mft). "
                  "Presets wie 'win10' sind KEINE einzelnen Parser. "
                  "Wenn keine Parser angegeben werden, verwendet Plaso "
                  "seine automatische Parser-Erkennung.\n"
                  "    ✅ Image + Triage-Ordner   |   "
                  "💾 Image oder Ordner mit angegebener Rohdatei   |   "
                  "📁 Nur Triage-Ordner"),
            bg="#fff8dc", fg="#664d03", justify="left",
            font=("Segoe UI", 9), padx=10, pady=6, anchor="w")
        parser_hint.pack(fill="x", pady=(0, 10))

        main = ttk.Frame(self.content)
        main.pack(fill="both", expand=True)

        tree_frame = ttk.Frame(main)
        tree_frame.pack(side="left", fill="both", expand=True)

        self.parser_tree = ttk.Treeview(
            tree_frame, columns=("check", "name", "desc"),
            show="tree headings", selectmode="none", height=18)
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

        panel = ttk.LabelFrame(main, text="✓ Ausgewählte Parser", padding=(6, 6))
        panel.pack(side="right", fill="y", padx=(12, 0))

        self.selected_tree = ttk.Treeview(
            panel, columns=("remove", "name"), show="headings",
            selectmode="none", height=22)
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

        if not self.expanded_parsers:
            for _, (_, parsers) in self.catalog.items():
                for name, _, _, plugins in parsers:
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

        def source_suffix(src):
            if isinstance(src, tuple):
                category, detail = src
            else:
                category, detail = src, None
            if category == "both":
                return "   —   ✅ Image + Triage-Ordner"
            if category == "image":
                if detail:
                    return f"   —   💾 Image oder Ordner mit {detail}"
                return "   —   💾 Image oder KAPE-Ordner"
            if category == "triage":
                return "   —   📁 Nur Triage-Ordner"
            return ""

        for cat_key, (cat_label, parsers) in self.catalog.items():
            visible = []
            for name, desc, source, plugins in parsers:
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
                visible.append((name, desc, source, plugins_shown))

            if not visible:
                continue

            cat_open = bool(search) or (cat_key in self.expanded_categories)
            cat_iid = self.parser_tree.insert(
                "", "end", text="",
                values=("", f"  {cat_label}", ""),
                tags=("category",), open=cat_open)
            self.parser_tree_map[cat_iid] = ("category", cat_key)

            for name, desc, source, plugins in visible:
                checked = name in self.state["selected_parsers"]
                mark = "☑" if checked else "☐"
                parser_open = bool(search) or (name in self.expanded_parsers)
                if plugins:
                    arrow = "▾" if parser_open else "▸"
                    display_name = f"  {arrow} {name}"
                else:
                    display_name = f"      {name}"
                display_desc = desc + source_suffix(source)

                main_iid = self.parser_tree.insert(
                    cat_iid, "end", text="",
                    values=(mark, display_name, display_desc),
                    tags=("selected",) if checked else (),
                    open=parser_open)
                self.parser_tree_map[main_iid] = ("main", name)

                for pl_name, pl_desc in plugins:
                    pl_checked = pl_name in self.state["selected_parsers"]
                    pl_mark = "☑" if pl_checked else "☐"
                    pl_iid = self.parser_tree.insert(
                        main_iid, "end", text="",
                        values=(pl_mark,
                                f"    └─ {pl_name.split('/')[-1]}",
                                pl_desc),
                        tags=("plugin", "selected") if pl_checked else ("plugin",))
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
                    for p_name, _, _, p_plugins in parsers:
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
                    for p_name, _, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].discard(pl_name)
        else:
            self.state["selected_parsers"].add(name)
            if kind == "main":
                for _, (_, parsers) in self.catalog.items():
                    for p_name, _, _, p_plugins in parsers:
                        if p_name == name:
                            for pl_name, _ in p_plugins:
                                self.state["selected_parsers"].add(pl_name)

        self._refresh_parser_tree()
        self._refresh_selected_panel()
        self._update_parser_count()

    def _expand_all(self, expand):
        if expand:
            for cat_key in self.catalog:
                self.expanded_categories.add(cat_key)
            for _, (_, parsers) in self.catalog.items():
                for name, _, _, plugins in parsers:
                    if plugins:
                        self.expanded_parsers.add(name)
        else:
            self.expanded_categories.clear()
            self.expanded_parsers.clear()
        self._refresh_parser_tree()

    def _apply_recommended_windows_set(self):
        preset = {"winevtx", "winreg", "prefetch",
                  "lnk", "recycle_bin", "winjob",
                  "chrome_cache", "firefox_cache2"}
        for _, (_, parsers) in self.catalog.items():
            for name, _, source, plugins in parsers:
                if name in preset:
                    for pl_name, _ in plugins:
                        preset.add(pl_name)
        if self.state.get("input_mode") == "folder":
            preset -= PHYSICAL_ONLY_PARSERS
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
            for p_name, _, _, p_plugins in parsers:
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
                text="Keine Auswahl – Plaso verwendet automatische Parser-Erkennung",
                style="Muted.TLabel")
        else:
            self.parser_count_lbl.configure(
                text=f"✔  {n} Parser ausgewählt", style="Success.TLabel")

    # ══════════════════════════════════════════════════════════
    #  Schritt 6: Optionen  (in beiden Modi vorhanden)
    # ══════════════════════════════════════════════════════════

    def _step_options(self):
        ttk.Label(self.content, text="Optionen",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(self.content,
                  text="Zusätzliche Filter und Optionen für den Export.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

        ttk.Label(self.content, text="Filterzeitraum",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(self.content,
                  text="Nur Ereignisse aus einem bestimmten Zeitraum exportieren. "
                       "Der Filter wirkt erst beim psort-Export – "
                       "die .plaso-Datei enthält weiterhin alle Ereignisse.\n"
                       "Die Eingabe erfolgt in UTC (Plaso-Standard).",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 8))

        self.time_filter_var = tk.BooleanVar(
            value=self.state["time_filter_enabled"])
        ttk.Checkbutton(self.content, text="Zeitfilter aktivieren",
                        variable=self.time_filter_var,
                        command=self._toggle_time_filter).pack(anchor="w", pady=(0, 10))

        self.time_frame = ttk.LabelFrame(self.content,
                                         text="Filterzeitraum (Eingabe in UTC)",
                                         padding=15)
        row1 = ttk.Frame(self.time_frame)
        row1.pack(fill="x", pady=(0, 10))
        ttk.Label(row1, text="Von:", width=6,
                  font=("Segoe UI", 10, "bold")).pack(side="left")
        self.time_from_var = tk.StringVar(
            value=self.state["time_from"] or "2024-01-01 00:00:00")
        ttk.Entry(row1, textvariable=self.time_from_var,
                  width=30, font=("Consolas", 10)).pack(side="left", padx=(5, 15))
        ttk.Label(row1, text="Format: YYYY-MM-DD HH:MM:SS (UTC)",
                  style="Muted.TLabel").pack(side="left")

        row2 = ttk.Frame(self.time_frame)
        row2.pack(fill="x", pady=(0, 10))
        ttk.Label(row2, text="Bis:", width=6,
                  font=("Segoe UI", 10, "bold")).pack(side="left")
        self.time_to_var = tk.StringVar(
            value=self.state["time_to"] or "2024-12-31 23:59:59")
        ttk.Entry(row2, textvariable=self.time_to_var,
                  width=30, font=("Consolas", 10)).pack(side="left", padx=(5, 15))
        ttk.Label(row2, text="Format: YYYY-MM-DD HH:MM:SS (UTC)",
                  style="Muted.TLabel").pack(side="left")

        ttk.Label(self.time_frame,
                  text="Beispiel: 2026-09-26 08:00:00 bis 2026-09-26 18:00:15",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        self._toggle_time_filter()

        # ── psort-Filter (Preset) ──────────────────────────────
        ttk.Label(self.content, text="psort-Filter (Preset)",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(25, 6))
        ttk.Label(self.content,
                  text="Wähle, welche Ereignisse exportiert werden sollen. "
                       "Der Filter wirkt nur beim Export – die .plaso-Datei "
                       "enthält weiterhin alle Ereignisse.\n"
                       "Der Filterausdruck wird im Log protokolliert.",
                  style="Muted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(0, 8))

        preset_container = ttk.Frame(self.content)
        preset_container.pack(fill="x", pady=(0, 8))

        self.filter_vars = {}
        for label, expression in PSORT_FILTER_PRESETS:
            var = tk.BooleanVar(value=(label in self.state["filter_presets"]))
            self.filter_vars[label] = var
            ttk.Checkbutton(
                preset_container, text=label, variable=var,
                command=self._on_filter_preset_change
            ).pack(anchor="w", pady=2)

        self.filter_preview_lbl = ttk.Label(
            self.content, text="", style="Muted.TLabel",
            wraplength=900, justify="left")
        self.filter_preview_lbl.pack(anchor="w", pady=(0, 8), fill="x")

        self.filter_custom_frame = ttk.LabelFrame(
            self.content, text="Eigener Filterausdruck", padding=10)
        ttk.Label(
            self.filter_custom_frame,
            text="psort-Filterausdruck (Syntax: data_type, parser, source, "
                 "date; Operatoren: is, contains, and, or, not, (), "
                 "Vergleiche)",
            style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        self.filter_custom_var = tk.StringVar(
            value=self.state.get("filter_custom", ""))
        custom_ent = ttk.Entry(self.filter_custom_frame,
                               textvariable=self.filter_custom_var,
                               font=("Consolas", 9))
        custom_ent.pack(fill="x", pady=(0, 4))
        custom_ent.bind("<KeyRelease>",
                        lambda e: self._update_filter_preview())
        ttk.Label(
            self.filter_custom_frame,
            text="Beispiel: data_type contains 'windows:registry:run' "
                 "and source contains 'NTUSER'",
            style="Muted.TLabel").pack(anchor="w")

        self._on_filter_preset_change()

    def _toggle_time_filter(self):
        if self.time_filter_var.get():
            self.time_frame.pack(fill="x", pady=(10, 0))
        else:
            self.time_frame.pack_forget()

    def _get_preset_filter_expression(self):
        if self.filter_vars.get("Alles (kein Filter)") and \
           self.filter_vars["Alles (kein Filter)"].get():
            return ""

        expressions = []
        for label, var in self.filter_vars.items():
            if not var.get():
                continue
            preset_expr = next(
                (e for l, e in PSORT_FILTER_PRESETS if l == label), "")
            if preset_expr == CUSTOM_FILTER_SENTINEL:
                custom = self.state.get("filter_custom", "").strip()
                if custom:
                    expressions.append(f"({custom})")
            elif preset_expr:
                expressions.append(f"({preset_expr})")

        if not expressions:
            return ""
        return " or ".join(expressions)

    def _get_combined_filter_expression(self):
        parts = []
        if self.state.get("time_filter_enabled"):
            tf = self.state.get("time_from")
            tt = self.state.get("time_to")
            if tf and tt:
                parts.append(f"date >= '{tf}' and date <= '{tt}'")
        preset_expr = self._get_preset_filter_expression()
        if preset_expr:
            parts.append(f"({preset_expr})")
        if not parts:
            return None
        return " and ".join(parts)

    def _on_filter_preset_change(self):
        all_label = "Alles (kein Filter)"
        all_var = self.filter_vars.get(all_label)

        if all_var and all_var.get():
            for label, var in self.filter_vars.items():
                if label != all_label:
                    var.set(False)
        else:
            any_other = any(var.get() for label, var in self.filter_vars.items()
                            if label != all_label)
            if any_other and all_var:
                all_var.set(False)

        self.state["filter_presets"] = {
            label for label, var in self.filter_vars.items() if var.get()
        }
        self.state["filter_custom"] = self.filter_custom_var.get()

        if self.filter_vars.get("Eigener Filter …") and \
           self.filter_vars["Eigener Filter …"].get():
            self.filter_custom_frame.pack(fill="x", pady=(5, 0))
        else:
            self.filter_custom_frame.pack_forget()

        self._update_filter_preview()

    def _update_filter_preview(self):
        self.state["filter_custom"] = self.filter_custom_var.get()
        expr = self._get_preset_filter_expression()

        if not expr:
            self.filter_preview_lbl.configure(
                text="✔  Kein Filter aktiv – alle Ereignisse werden exportiert.",
                style="Success.TLabel")
            return

        preview = expr if len(expr) <= 200 else expr[:197] + "…"
        self.filter_preview_lbl.configure(
            text=f"✔  Aktiver Filter:\n     {preview}",
            style="Success.TLabel")

    def _validate_filter_expression(self, expr: str):
        if not expr:
            return True, ""
        if expr.count("(") != expr.count(")"):
            return False, "Klammern sind nicht ausbalanciert."
        if expr.count("'") % 2 != 0:
            return False, "Anführungszeichen sind nicht ausbalanciert."
        return True, ""

    # ══════════════════════════════════════════════════════════
    #  Letzter Schritt: Ausführen
    # ══════════════════════════════════════════════════════════

    def _step_run(self):
        ttk.Label(self.content, text="Verarbeitung starten",
                  style="Title.TLabel").pack(anchor="w", pady=(5, 12))

        summary = ttk.LabelFrame(self.content, text="Zusammenfassung", padding=15)
        summary.pack(fill="x", pady=(0, 15))

        labels_by_value = {v: l for l, v, e, d in OUTPUT_FORMATS}
        selected_labels = [labels_by_value.get(v, v)
                           for v, e in self.state["selected_formats"]]
        fmt_label = ", ".join(selected_labels) if selected_labels else "?"

        use_existing = (self.state["input_mode"] == "plaso")
        mode = self.state["input_mode"]

        # Quell-Anzeige
        if use_existing:
            src = Path(self.state["existing_plaso_path"]).name \
                if self.state.get("existing_plaso_path") else "?"
            img_display = f"[.plaso] {src}"
        elif mode == "batch":
            n_img = sum(1 for i in self.state["batch_items"] if i["type"] == "image")
            n_dir = sum(1 for i in self.state["batch_items"] if i["type"] == "folder")
            parts = []
            if n_img: parts.append(f"{n_img} Image(s)")
            if n_dir: parts.append(f"{n_dir} Ordner")
            img_display = f"Batch: {', '.join(parts)}" if parts else "Batch: leer"
        elif mode == "folder":
            img_display = f"[Ordner] {self.state['input_path'] or '-'}"
        else:
            img_display = self.state["input_path"] or "-"

        # Ziel-Anzeige
        if mode == "batch" and not use_existing:
            out_display = (f"{self.state['out_dir']}\\<NN_quelle>\\"
                           f"{self.state['name']}<endung>  "
                           f"(Unterordner pro Quelle)"
                           if self.state["out_dir"] else "-")
        else:
            out_display = (f"{self.state['out_dir']}\\{self.state['name']}"
                           if self.state["out_dir"] else "-")

        if self.state["time_filter_enabled"]:
            tf_display = (f"{self.state['time_from']}  →  "
                          f"{self.state['time_to']}  (UTC)")
        else:
            tf_display = "inaktiv"

        if self.state["vss_arg"]:
            vss_display = self.state["vss_arg"][-1]
        else:
            vss_display = "auto (Plaso entscheidet)"

        preset_expr = self._get_preset_filter_expression()
        if not preset_expr:
            filter_display = "kein Filter (alle Events)"
        else:
            aktive = [l for l, v in self.filter_vars.items() if v.get()] \
                if hasattr(self, "filter_vars") else []
            filter_display = (" + ".join(aktive) if len(aktive) <= 2
                              else f"{len(aktive)} Presets kombiniert")

        parsers = self.state["selected_parsers"]
        physical_selected = parsers & PHYSICAL_ONLY_PARSERS
        folder_mode = (mode == "folder") or (
            mode == "batch" and any(i["type"] == "folder"
                                    for i in self.state["batch_items"]))

        if use_existing:
            pipeline_display = "psort (log2timeline übersprungen)"
            parser_display = "(irrelevant – .plaso enthält bereits alles)"
            partition_display = "(übersprungen)"
            vss_row_display = "(übersprungen)"
            bitlocker_display = "(übersprungen)"
        else:
            pipeline_display = "log2timeline → pinfo → psort"
            parser_display = (f"{len(parsers)} ausgewählt"
                              if parsers else "automatische Erkennung")
            partition_display = (self.state["partitions_arg"][-1]
                                 if self.state["partitions_arg"] else "auto")
            vss_row_display = vss_display
            bitlocker_display = ("aktiv"
                                 if self.state["credential_arg"] else "nein")

        rows = [
            ("Modus",       pipeline_display),
            ("Quelle",      img_display),
            ("Ausgabe",     out_display),
            ("Format",      fmt_label),
            ("Docker-Image", PLASO_DOCKER_IMAGE),
            ("BitLocker",   bitlocker_display),
            ("Partition",   partition_display),
            ("VSS",         vss_row_display),
            ("Parser",      parser_display),
            ("Zeitfilter",  tf_display),
            ("psort-Filter", filter_display),
            ("Zeitzone",    OUTPUT_TIMEZONE or "UTC (Standard)"),
        ]
        for k, v in rows:
            row = ttk.Frame(summary)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"{k}:", width=14,
                      font=("Segoe UI", 10, "bold")).pack(side="left")
            ttk.Label(row, text=str(v),
                      font=("Segoe UI", 10)).pack(side="left", padx=(5, 0))

        if use_existing:
            info = tk.Label(
                summary,
                text=("ℹ  Wiederverwendung aktiv: log2timeline wird "
                      "übersprungen.\n"
                      "    Die vorhandene .plaso-Datei wird read-only "
                      "gemountet und nur für psort verwendet."),
                bg="#e7f1fb", fg="#0b4a80", justify="left",
                font=("Segoe UI", 9), padx=10, pady=6, anchor="w")
            info.pack(fill="x", pady=(8, 0))

        if physical_selected and folder_mode and not use_existing:
            warn = tk.Label(
                summary,
                text=(f"⚠  Physische Parser ausgewählt, aber Ordner-Quelle aktiv:\n"
                      f"    {', '.join(sorted(physical_selected))}\n"
                      f"    Diese Parser benötigen ein physisches Image (E01/dd/raw)\n"
                      f"    ODER einen KAPE-Ordner mit den passenden Rohdateien\n"
                      f"    ($MFT, $UsnJrnl:$J, Bodyfile, …)."),
                bg="#fff3cd", fg="#856404", justify="left",
                font=("Segoe UI", 9), padx=10, pady=6, anchor="w")
            warn.pack(fill="x", pady=(8, 0))

        prog_frame = ttk.Frame(self.content)
        prog_frame.pack(fill="x", pady=(5, 10))
        self.progress = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.timer_lbl = ttk.Label(prog_frame, text="00:00:00",
                                   style="Timer.TLabel", width=12, anchor="e")
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

    # ══════════════════════════════════════════════════════════
    #  Verarbeitung
    # ══════════════════════════════════════════════════════════

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

        self.batch_results = []
        threading.Thread(target=self._run_pipeline, daemon=True).start()
        self.root.after(100, self._poll_log_queue)

    def _update_timer(self):
        if not self.timer_running:
            return
        elapsed = int(time.time() - self.process_start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
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

    # ══════════════════════════════════════════════════════════
    #  Preflight
    # ══════════════════════════════════════════════════════════

    def _check_docker_image_digest(self):
        if not PLASO_DOCKER_DIGEST:
            return True
        if "@sha256:" in PLASO_DOCKER_IMAGE:
            return True

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                ["docker", "inspect",
                 "--format={{index .RepoDigests 0}}",
                 PLASO_DOCKER_IMAGE],
                capture_output=True, text=True, timeout=10,
                creationflags=creationflags,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return True

        if result.returncode != 0 or not result.stdout.strip():
            return messagebox.askyesno(
                "Docker-Image nicht lokal vorhanden",
                f"Das Image '{PLASO_DOCKER_IMAGE}' ist nicht lokal vorhanden.\n\n"
                "Docker wird es beim Start automatisch herunterladen.\n\n"
                "⚠  Es kann dann NICHT geprüft werden, ob der heruntergeladene\n"
                "   Inhalt dem erwarteten Digest entspricht.\n\n"
                f"Erwarteter Digest:\n  {PLASO_DOCKER_DIGEST}\n\n"
                "Trotzdem fortfahren?")

        actual_full = result.stdout.strip()
        actual_digest = (actual_full.split("@", 1)[1]
                         if "@" in actual_full else actual_full)

        if actual_digest != PLASO_DOCKER_DIGEST:
            return messagebox.askyesno(
                "⚠  Image-Digest stimmt NICHT überein",
                f"Der Digest des lokalen Docker-Images weicht vom "
                f"erwarteten Wert ab!\n\n"
                f"Erwartet:\n  {PLASO_DOCKER_DIGEST}\n\n"
                f"Tatsächlich:\n  {actual_digest}\n\n"
                "Für forensische Reproduzierbarkeit ist dies ein "
                "ernstes Warnsignal.\n\n"
                "Trotzdem fortfahren? (NICHT empfohlen)")
        return True

    def _preflight_check(self):
        # 1. Docker verfügbar?
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True, text=True, timeout=5,
                creationflags=creationflags,
            )
            if result.returncode != 0:
                messagebox.showerror("Docker-Fehler",
                    "Docker scheint nicht zu laufen.\n\n"
                    "Bitte Docker Desktop starten und erneut versuchen.")
                return False
        except FileNotFoundError:
            messagebox.showerror("Docker nicht gefunden",
                "Der Befehl 'docker' wurde nicht gefunden.\n\n"
                "Bitte Docker Desktop installieren und starten.")
            return False
        except subprocess.TimeoutExpired:
            messagebox.showerror("Docker-Timeout",
                "Docker hat nicht innerhalb von 5 Sekunden geantwortet.\n\n"
                "Läuft Docker Desktop?")
            return False
        except Exception as e:
            messagebox.showerror("Docker-Fehler", f"Unerwarteter Fehler:\n{e}")
            return False

        # 2. Docker-Image-Digest prüfen
        if not self._check_docker_image_digest():
            self.log_queue.put(
                "Abbruch: Docker-Image-Digest-Prüfung fehlgeschlagen.\n")
            return False

        # 3. Quell-Validierung je Modus
        mode = self.state["input_mode"]
        if mode == "plaso":
            p = self.state.get("existing_plaso_path")
            if not p or not Path(p).is_file():
                messagebox.showerror("Input-Fehler",
                    "Die angegebene .plaso-Datei wurde nicht gefunden.")
                return False
        elif mode == "batch":
            if not self.state["batch_items"]:
                messagebox.showerror("Input-Fehler", "Keine Batch-Quellen.")
                return False
            for item in self.state["batch_items"]:
                if not Path(item["path"]).exists():
                    messagebox.showerror("Input-Fehler",
                        f"Quelle nicht gefunden:\n{item['path']}")
                    return False
        else:
            if not self.state["input_path"] or \
               not Path(self.state["input_path"]).exists():
                messagebox.showerror("Input-Fehler",
                    "Die Eingabequelle wurde nicht gefunden.")
                return False

        # 4. Output-Ordner
        out_dir = self.state["out_dir"]
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Output-Fehler",
                f"Ausgabeordner kann nicht erstellt werden:\n{e}")
            return False

        # 5. Konflikt-Check
        return self._preflight_check_overwrite()

    def _preflight_check_overwrite(self):
        """
        Prüft ALLE Zieldateien.
        Im .plaso-Modus wird NUR gegen die Export-Dateien geprüft –
        die vorhandene .plaso-Datei ist nie Ziel und wird nie gelöscht.
        """
        mode = self.state["input_mode"]
        targets = []

        if mode == "batch":
            items = self.state["batch_items"]
            used_names = set()
            for idx, item in enumerate(items, 1):
                p = Path(item["path"])
                base = p.name if item["type"] == "folder" else p.stem
                uniq = f"{idx:02d}_{base}"
                if uniq in used_names:
                    uniq = f"{idx:02d}_{base}_{idx}"
                used_names.add(uniq)
                targets.append((uniq, Path(self.state["out_dir"]) / uniq))
        else:
            targets.append((self.state["name"],
                            Path(self.state["out_dir"])))

        existing = []
        for base, out_dir in targets:
            # .plaso-Zieldatei NUR prüfen, wenn kein .plaso-Modus
            if mode != "plaso":
                plaso_target = out_dir / f"{base}.plaso"
                if plaso_target.exists():
                    existing.append(plaso_target)
            for _, ext in self.state["selected_formats"]:
                t = out_dir / f"{base}{ext}"
                if t.exists():
                    existing.append(t)

        if not existing:
            return True

        if len(existing) == 1:
            msg = (f"Die Datei existiert bereits:\n\n"
                   f"  {existing[0]}\n\n"
                   f"Möchtest du sie überschreiben?")
        else:
            liste = "\n".join(f"  • {t}" for t in existing[:20])
            more = (f"\n  … und {len(existing) - 20} weitere"
                    if len(existing) > 20 else "")
            msg = (f"{len(existing)} Datei(en) existieren bereits:\n\n"
                   f"{liste}{more}\n\nAlle überschreiben?")

        if not messagebox.askyesno("Datei(en) existieren bereits", msg):
            self.log_queue.put("Abbruch: Existierende Datei(en) bleiben erhalten.\n")
            return False

        for target in existing:
            try:
                target.unlink()
            except OSError as e:
                messagebox.showerror("Fehler",
                    f"Konnte '{target.name}' nicht löschen:\n{e}")
                return False
        return True

    # ══════════════════════════════════════════════════════════
    #  Pipeline
    # ══════════════════════════════════════════════════════════

    def _run_pipeline(self):
        try:
            mode = self.state["input_mode"]
            if mode == "plaso":
                self._run_reuse_existing()
            elif mode == "batch":
                self._run_batch()
            else:
                self._run_single()
        except Exception as e:
            self.log_queue.put(f"\n✘ Ausnahme: {type(e).__name__}: {e}\n")
            self.log_queue.put(("DONE", 1))

    # ─────────────────────────────────────────────────────────
    def _run_single(self):
        is_folder = (self.state["input_mode"] == "folder")

        if is_folder:
            mount_source = self.state["input_path"]
            input_arg = "/mnt/input"
        else:
            mount_source = self.state["input_dir"]
            input_arg = f"/mnt/input/{self.state['input_file']}"

        out_dir = self.state["out_dir"]
        name = self.state["name"]

        # 1. log2timeline
        cmd = self.builder.build_log2timeline(
            mount_source=mount_source,
            input_arg=input_arg,
            out_dir=out_dir,
            storage_name=name,
            is_folder=is_folder,
            credential_arg=self.state["credential_arg"],
            partitions_arg=self.state["partitions_arg"],
            vss_arg=self.state["vss_arg"],
            parsers=self.state["selected_parsers"],
        )
        self.log_queue.put("\n[1/3] log2timeline\n")
        rc = self.runner.run_cmd(cmd)
        if rc != 0:
            self.log_queue.put(f"✘ log2timeline fehlgeschlagen (rc={rc}).\n")
            self.log_queue.put(("DONE", rc))
            return

        # 2. pinfo
        plaso_file = Path(out_dir) / f"{name}.plaso"
        if plaso_file.exists():
            self.log_queue.put("\n[2/3] pinfo (optional, Info-Ausgabe)\n")
            pinfo_cmd = self.builder.build_pinfo(out_dir, name)
            pinfo_rc = self.runner.run_cmd(pinfo_cmd)
            if pinfo_rc != 0:
                self.log_queue.put(
                    "\n⚠  pinfo ist mit Fehler beendet (rc="
                    f"{pinfo_rc}).\n"
                    "   Das ist ein bekanntes Plaso-Problem (Warning-Counter-"
                    "Ausgabe).\n"
                    "   Die eigentliche Verarbeitung ist davon NICHT "
                    "betroffen.\n")
        else:
            self.log_queue.put(
                "⚠  .plaso-Datei nicht gefunden – pinfo wird übersprungen.\n")

        # 3. psort pro Format
        filter_expr = self._get_combined_filter_expression()

        if filter_expr:
            self.log_queue.put(
                f"\n[Filter] psort-Filterausdruck:\n  {filter_expr}\n")
        else:
            self.log_queue.put("\n[Filter] kein Filter aktiv (alle Events)\n")

        last_rc = 0
        for fmt, ext in self.state["selected_formats"]:
            out_name = name + ext
            self.log_queue.put(f"\n[3/3] psort → {out_name}\n")
            psort_cmd = self.builder.build_psort(
                out_dir=out_dir,
                storage_name=name,
                output_filename=out_name,
                fmt=fmt,
                filter_expression=filter_expr,
            )
            rc = self.runner.run_cmd(psort_cmd)
            if rc != 0:
                last_rc = rc
        self.log_queue.put(("DONE", last_rc))

    # ─────────────────────────────────────────────────────────
    def _run_reuse_existing(self):
        """Wiederverwendung: nur pinfo + psort, kein log2timeline."""
        plaso_path = Path(self.state["existing_plaso_path"])
        out_dir = self.state["out_dir"]
        name = self.state["name"]

        self.log_queue.put(
            "\n" + "═" * 70 + "\n"
            "WIEDERVERWENDUNG AKTIV\n"
            "log2timeline wird übersprungen – nur pinfo + psort laufen.\n"
            f"Quelle: {plaso_path}\n"
            f"Ziel:   {out_dir}\n"
            + "═" * 70 + "\n")

        try:
            self.log_queue.put("\n[Hash] Berechne SHA256 der .plaso-Datei …\n")
            digest = sha256_of_file(plaso_path)
            self.log_queue.put(
                f"[Hash] {plaso_path.name}\n"
                f"       SHA256: {digest}\n")
        except OSError as e:
            self.log_queue.put(f"⚠  Hash-Berechnung fehlgeschlagen: {e}\n")

        # 1. pinfo
        self.log_queue.put("\n[1/2] pinfo (optional)\n")
        pinfo_cmd = self.builder.build_pinfo_on_file(str(plaso_path))
        pinfo_rc = self.runner.run_cmd(pinfo_cmd)
        if pinfo_rc != 0:
            self.log_queue.put(
                f"⚠  pinfo rc={pinfo_rc} (bekanntes Plaso-Problem, "
                f"nicht kritisch)\n")

        # 2. psort pro Format
        filter_expr = self._get_combined_filter_expression()
        if filter_expr:
            self.log_queue.put(
                f"\n[Filter] psort-Filterausdruck:\n  {filter_expr}\n")
        else:
            self.log_queue.put("\n[Filter] kein Filter aktiv (alle Events)\n")

        last_rc = 0
        for fmt, ext in self.state["selected_formats"]:
            out_name = name + ext
            self.log_queue.put(f"\n[2/2] psort → {out_name}\n")
            psort_cmd = self.builder.build_psort_from_existing(
                plaso_path=str(plaso_path),
                out_dir=out_dir,
                output_filename=out_name,
                fmt=fmt,
                filter_expression=filter_expr,
            )
            rc = self.runner.run_cmd(psort_cmd)
            if rc != 0:
                last_rc = rc

        self.log_queue.put(
            "\n" + "═" * 70 + "\n"
            "WIEDERVERWENDUNG ABGESCHLOSSEN\n"
            + "═" * 70 + "\n")

        self.log_queue.put(("DONE", last_rc))

    # ─────────────────────────────────────────────────────────
    def _run_batch(self):
        items = self.state["batch_items"]
        total = len(items)
        last_rc = 0

        used_names = set()
        for idx, item in enumerate(items, 1):
            p = Path(item["path"])
            is_folder = (item["type"] == "folder")
            label = "Ordner" if is_folder else "Image"
            base = p.name if is_folder else p.stem
            uniq = f"{idx:02d}_{base}"
            if uniq in used_names:
                uniq = f"{idx:02d}_{base}_{idx}"
            used_names.add(uniq)

            item_out_dir = str(Path(self.state["out_dir"]) / uniq)
            try:
                Path(item_out_dir).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.batch_results.append((p.name, False, str(e)))
                last_rc = 1
                continue

            self.log_queue.put(
                f"\n{'═' * 70}\n"
                f"[{idx}/{total}] Verarbeite {label}: {p.name}\n"
                f"          Ausgabe: {item_out_dir}\n"
                f"{'═' * 70}\n\n")

            if is_folder:
                mount_source = str(p)
                input_arg = "/mnt/input"
            else:
                mount_source = str(p.parent)
                input_arg = f"/mnt/input/{p.name}"

            # 1. log2timeline
            cmd = self.builder.build_log2timeline(
                mount_source=mount_source,
                input_arg=input_arg,
                out_dir=item_out_dir,
                storage_name=uniq,
                is_folder=is_folder,
                credential_arg=self.state["credential_arg"],
                partitions_arg=self.state["partitions_arg"],
                vss_arg=self.state["vss_arg"],
                parsers=self.state["selected_parsers"],
            )
            rc = self.runner.run_cmd(cmd)
            if rc != 0:
                self.batch_results.append((p.name, False, f"log2timeline rc={rc}"))
                last_rc = rc
                self.log_queue.put(
                    f"\n✘ Fehler bei {p.name} (rc={rc}), weiter...\n")
                continue

            # 2. pinfo
            plaso_file = Path(item_out_dir) / f"{uniq}.plaso"
            if plaso_file.exists():
                self.log_queue.put("\n── pinfo (optional) ──\n")
                pinfo_cmd = self.builder.build_pinfo(item_out_dir, uniq)
                pinfo_rc = self.runner.run_cmd(pinfo_cmd)
                if pinfo_rc != 0:
                    self.log_queue.put(
                        f"⚠  pinfo rc={pinfo_rc} (bekanntes Plaso-Problem, "
                        f"nicht kritisch)\n")

            # 3. psort pro Format
            filter_expr = self._get_combined_filter_expression()
            item_rc = 0
            for fmt, ext in self.state["selected_formats"]:
                out_name = uniq + ext
                psort_cmd = self.builder.build_psort(
                    out_dir=item_out_dir,
                    storage_name=uniq,
                    output_filename=out_name,
                    fmt=fmt,
                    filter_expression=filter_expr,
                )
                rc = self.runner.run_cmd(psort_cmd)
                if rc != 0:
                    item_rc = rc

            if item_rc == 0:
                self.batch_results.append((p.name, True, ""))
            else:
                self.batch_results.append((p.name, False, f"psort rc={item_rc}"))
                last_rc = item_rc

        success = sum(1 for _, ok, _ in self.batch_results if ok)
        failed = sum(1 for _, ok, _ in self.batch_results if not ok)

        self.log_queue.put("\n" + "═" * 70 + "\n")
        self.log_queue.put("BATCH COMPLETED\n\n")
        self.log_queue.put(f"  Successful: {success}\n")
        self.log_queue.put(f"  Failed:     {failed}\n")

        if failed:
            self.log_queue.put("\nFailed items:\n")
            for name, ok, msg in self.batch_results:
                if not ok:
                    self.log_queue.put(f"  ✘ {name}\n")
                    self.log_queue.put(f"      Reason: {msg}\n")
        self.log_queue.put("═" * 70 + "\n")

        self.log_queue.put(("DONE", last_rc))

    # ─────────────────────────────────────────────────────────
    #  Aufräumen
    # ─────────────────────────────────────────────────────────

    def _on_close(self):
        if self.runner.process and self.runner.process.poll() is None:
            if not messagebox.askyesno(
                    "Bestätigung",
                    "Ein Prozess läuft noch. Wirklich beenden?"):
                return
            self.runner.terminate()
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

    if ":" not in PLASO_DOCKER_IMAGE and "@sha256:" not in PLASO_DOCKER_IMAGE:
        app.log_queue.put(
            "⚠  HINWEIS: Docker-Image ist nicht auf eine feste Version "
            "gepinnt.\n"
            f"   Aktuell: {PLASO_DOCKER_IMAGE}\n"
            "   Für reproduzierbare forensische Analysen sollte ein "
            "konkreter Tag oder SHA256-Digest gesetzt werden.\n\n")

    root.mainloop()
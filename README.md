# Plaso Docker Helper

Ein interaktiver Assistent zur einfachen Nutzung von [Plaso (log2timeline)](https://github.com/log2timeline/plaso) unter Windows 11 über Docker.

Zwei Varianten stehen zur Verfügung:

- **GUI:** `plaso_gui.py` – grafischer Wizard mit Tkinter
- **CLI:** `plaso_helper.py` – geführtes Terminal-Menü

---

## Features

- **7-Schritte-Wizard** – Image, Ausgabe, BitLocker, Partition, Parser, Optionen, Ausführen
- **BitLocker-Support** – Recovery Password, Benutzerpasswort, Startup Key, Key Data
- **Partitionsauswahl** – alle Partitionen oder eine bestimmte
- **Parser-Auswahl** mit Kategorien, Suche, Live-Status und Plugin-Parsern
- **6 Ausgabeformate** – CSV, JSON Lines, JSON, Bodyfile, SQLite, XLSX
- **Zeitfilter** – nur Ereignisse aus einem bestimmten Zeitraum exportieren
- **Batch-Modus** – mehrere Images in einem Durchlauf verarbeiten
- **Live-Timer** und Fortschrittsanzeige während der Verarbeitung
- **Überschreib-Schutz** – warnt vor beschädigten oder vorhandenen `.plaso`-Dateien
- **Batch-fähig** – mehrere Images nacheinander mit gemeinsamen Einstellungen

---

## Voraussetzungen

| Komponente | Version / Hinweis |
|------------|-------------------|
| Betriebssystem | Windows 10 oder 11 |
| Python | 3.10 oder neuer (nur für Quellcode-Nutzung) |
| Docker | Docker Desktop mit laufendem Daemon |
| Plaso-Image | `log2timeline/plaso` (siehe unten) |

Das Plaso-Image einmalig herunterladen:

```powershell
docker pull log2timeline/plaso
```

---

## Installation

### Option A: Fertige EXE (ohne Python)

Lade `PlasoHelper.exe` aus den [Releases](https://github.com/<USERNAME>/<REPO-NAME>/releases) herunter und starte sie per Doppelklick.

Voraussetzungen: Docker Desktop läuft, Plaso-Image ist gepullt.

### Option B: Aus dem Quellcode

```powershell
# Repository klonen
git clone https://github.com/kl-patrickstar/plaso-docker-helper.git
cd plaso-docker-helper

# Virtuelle Umgebung erstellen (optional, aber empfohlen)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Die GUI benötigt **keine externen Abhängigkeiten** – sie verwendet ausschließlich `tkinter` aus der Python-Standardbibliothek.

---

## Verwendung

### GUI (grafische Oberfläche)

```powershell
python plaso_gui.py
```

Der Wizard führt durch **7 Schritte**:

| Schritt | Beschreibung |
|---------|--------------|
| 1. Image | Einzelnes Image oder Batch-Modus für mehrere |
| 2. Ausgabe | Zielordner, Dateiname und Ausgabeformat |
| 3. BitLocker | Schlüssel für verschlüsselte Volumes (optional) |
| 4. Partition | Alle Partitionen oder eine bestimmte |
| 5. Parser | Kategorien, Suche, Presets, Plugin-Parser |
| 6. Optionen | Zeitfilter für den Export |
| 7. Ausführen | Live-Log, Timer und Fortschrittsanzeige |

### CLI (Kommandozeile)

```powershell
python plaso_helper.py
```

Interaktiv geführtes Menü im Terminal mit denselben Optionen.

---

## Details zu den Features

### Batch-Modus

Wenn du mehrere Images in einem Durchlauf verarbeiten willst:

1. Im Schritt **Image** die Checkbox *„Batch-Modus"* aktivieren
2. Über **„➕ Images hinzufügen"** mehrere Dateien per **Strg-Klick** oder **Shift-Klick** auswählen
3. Jedes Image wird nacheinander verarbeitet
4. Jedes bekommt seinen eigenen `.plaso`- und Ausgabedatei-Namen (basierend auf dem Image-Namen)

**Tipp:** Der Batch-Modus arbeitet alle Images mit denselben Einstellungen ab. Falls ein Image fehlschlägt, überspringt das Tool es und macht mit dem nächsten weiter.

### Ausgabeformate

| Format | Endung | Beschreibung |
|--------|--------|--------------|
| CSV (l2tcsv) | `.csv` | Standard für Excel / Timeline Explorer |
| JSON Lines | `.jsonl` | Eine JSON-Zeile pro Ereignis (Streaming-freundlich) |
| JSON | `.json` | Vollständiges JSON-Array |
| Bodyfile | `.bodyfile` | SleuthKit v3 bodyfile für `mactime` |
| SQLite | `.sqlite` | SQLite-Datenbank für eigene Abfragen |
| Dynamic (XLSX) | `.xlsx` | Optimiert für Timeline Explorer |

### Zeitfilter

Im Schritt **Optionen** kannst du einen Zeitraum festlegen:

- **Format:** `YYYY-MM-DD HH:MM:SS` (UTC)
- **Beispiel:** `2024-03-15 08:00:00` bis `2024-03-15 18:00:00` (ein Arbeitstag)
- Der Filter wirkt erst beim Export – die `.plaso`-Datei enthält weiterhin alle Ereignisse

Intern wird `psort --slice "<von>" "<bis>"` verwendet.

### Parser-Auswahl

Die Parser sind in Kategorien gruppiert:

- **Presets & Kombinationen** – z. B. `win10`, `webhist`
- **Windows-Kern** – Registry, EVTX, MFT, Prefetch, LNK, ...
- **Browser & Web** – Chrome, Firefox, Safari, Edge, IE
- **Mobile (iOS / Android)** – iMessage, WhatsApp, Android-Calls
- **macOS** – FSEvents, TCC, KnowledgeC
- **Linux** – Systemd, Bash, APT
- **Datenbanken & Formate** – SQLite, ESE, OLE, JSON-L
- **Windows-Anwendungen** – McAfee, Symantec, Trend Micro
- **Netzwerk, Server & Sonstiges** – Apache, AWS, PowerShell

Rechts im Fenster siehst du **alle ausgewählten Parser** mit `✕`-Button zum direkten Entfernen.

**Schnellauswahl:**
- **Empf. Win-Set** – lädt `win10, winevtx, winreg, mft, prefetch, usnjrnl, lnk, sqlite`
- **Alle abwählen** – leert die Auswahl
- **Suche** – filtert live nach Name und Beschreibung

---

## Beispiel-Workflow

| Schritt | Beispielwert |
|---------|--------------|
| Image | `C:\Cases\image.E01` |
| Ausgabeordner | `C:\Cases\output` |
| Dateiname | `timeline` |
| Format | CSV (l2tcsv) |
| BitLocker | nein |
| Partition | alle |
| Parser | `win10`, `winevtx`, `winreg`, `mft`, `prefetch`, `sqlite` |
| Zeitfilter | inaktiv |
| **Ergebnis** | `timeline.plaso` + `timeline.csv` |

---

## Ergebnis

Nach dem Durchlauf hast du zwei Dateien:

| Datei | Zweck |
|-------|-------|
| `timeline.plaso` | Rohdatenbank – jederzeit mit `psort` neu filterbar |
| `timeline.csv` | Lesbare Timeline für Excel oder Timeline Explorer |

**Empfohlenes Analyse-Tool:** [Timeline Explorer](https://ericzimmerman.github.io/) von Eric Zimmerman.

**Tipp:** Nach dem ersten Lauf kannst du die `.plaso`-Datei beliebig oft neu auswerten, ohne das Image erneut zu verarbeiten – z. B. mit anderen Formaten, anderen Zeitfiltern oder anderem Ausgabeort.

---

## EXE selbst bauen

Wenn du die GUI als eigenständige Windows-EXE verpacken willst:

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name PlasoHelper plaso_gui.py
```

Die fertige `PlasoHelper.exe` liegt dann im Ordner `dist/`.

**Optionale Parameter:**
- `--icon=icon.ico` – eigenes Icon hinzufügen
- `--clean` – Build-Cache leeren

---

## Projektstruktur

```
plaso-docker-helper/
├── plaso_gui.py        # Grafische Oberfläche (Tkinter)
├── plaso_helper.py     # Kommandozeilen-Version
├── README.md           # Diese Datei
└── .gitignore          # Git-Ausschlüsse
```

---

## Bekannte Einschränkungen

- Die Verarbeitung großer Images kann **mehrere Stunden dauern** – abhängig von Image-Größe und Parser-Auswahl.
- Die EXE benötigt ein installiertes **Docker Desktop** und das einmalig gepullte `log2timeline/plaso`-Image.
- Windows SmartScreen warnt möglicherweise beim Start der selbst gebauten EXE, weil sie nicht signiert ist. Klick auf **„Weitere Informationen" → „Trotzdem ausführen"**.
- Für die Analyse sehr großer Timelines (mehrere Millionen Ereignisse) ist **Timeline Explorer** oder **SQLite-Abfragen** deutlich schneller als Excel.

---

## Lizenz

MIT

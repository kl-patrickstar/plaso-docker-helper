# Plaso Docker Helper

Ein interaktiver Assistent zur einfachen Nutzung von [Plaso (log2timeline)](https://github.com/log2timeline/plaso) unter Windows 11 über Docker.

Zwei Varianten stehen zur Verfügung:

- **CLI:** `plaso_helper.py` – geführtes Terminal-Menü
- **GUI:** `plaso_gui.py` – grafischer Wizard mit Tkinter

---

## Features

- **Geführte Eingabe** für Image, Ausgabeordner und Dateiname
- **BitLocker-Support** – Recovery Password, Benutzerpasswort, Startup Key, Key Data
- **Partitionsauswahl** – alle Partitionen oder eine bestimmte
- **Parser-Auswahl** mit Kategorien, Suche, Live-Status und Plugins
- **Automatischer CSV-Export** via `psort` für Timeline Explorer
- **Live-Ausgabe** von `log2timeline` und `psort` in Echtzeit (GUI)

---

## Voraussetzungen

| Komponente | Version / Hinweis |
|------------|-------------------|
| Betriebssystem | Windows 10 oder 11 |
| Python | 3.10 oder neuer |
| Docker | Docker Desktop mit laufendem Daemon |
| Plaso-Image | `log2timeline/plaso` (siehe unten) |

Das Plaso-Image einmalig herunterladen:

```powershell
docker pull log2timeline/plaso
```

---

## Installation

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

Ein Wizard führt durch **6 Schritte**:

1. **Image** auswählen (`.E01`, `.dd`, `.raw`, `.vmdk`)
2. **Ausgabeordner** und Dateiname festlegen
3. **BitLocker**-Schlüssel (optional)
4. **Partition** auswählen
5. **Parser** auswählen (Kategorien, Suche, Presets)
6. **Ausführen** mit Live-Log und Fortschrittsanzeige

### CLI (Kommandozeile)

```powershell
python plaso_helper.py
```

Interaktiv geführtes Menü im Terminal mit denselben Optionen.

---

## Beispiel-Workflow

| Schritt | Beispielwert |
|---------|--------------|
| Image | `H:\Fälle\Fall_2\image.E01` |
| Ausgabeordner | `H:\Fälle\Fall_2\plaso` |
| Dateiname | `timeline` |
| Parser-Auswahl | `win10,winevtx,winreg,mft,prefetch,sqlite` |
| Ergebnis | `timeline.plaso` + `timeline.csv` |

---

## Ergebnis

Nach dem Durchlauf hast du zwei Dateien:

| Datei | Zweck |
|-------|-------|
| `timeline.plaso` | Rohdatenbank – jederzeit mit `psort` neu filterbar |
| `timeline.csv` | Lesbare Timeline für Excel oder Timeline Explorer |

**Empfohlenes Analyse-Tool:** [Timeline Explorer](https://ericzimmerman.github.io/) von Eric Zimmerman.

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

## Lizenz

MIT

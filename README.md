# DocuManager · Korrespondenzverwaltung

Lokale Anwendung für die eigene Korrespondenz mit Behörden, Finanzamt, Versicherungen und anderen Beteiligten.
Briefe, E-Mails, Bescheide, Entwürfe und Nachweise liegen pro Vorgang in einer durchsuchbaren Akte.
Die Anwendung läuft auf dem Mac, wird im Browser bedient und braucht keinen Cloud-Dienst.

## Stand

| Bereich | Stand |
|---|---|
| Vorgänge mit Bereich, Status und nächster Frist | produktiv in SQLite |
| Dokumentimport (PDF, JPEG, PNG, TIFF bis 25 MB), Original unverändert, Dubletten per SHA-256 | produktiv |
| Texterkennung mit PDFKit und Apple Vision, Titel aus Betreff oder Überschrift | produktiv, läuft als Warteschlange im Hintergrund; Bilderkennung am 23.11.2026 auf dem Mac bestätigt |
| Nativer macOS-Scandialog | produktiv, Test mit echtem Scanner offen |
| ChatGPT-Export importieren (Auswahl einzelner Unterhaltungen, wiederholbar) | produktiv |
| E-Mails aus Apple Mail übernehmen (Markierung „Erfasster Beleg“, mit Anlagen, ohne Doppelungen, letzter Abruf gespeichert) | neu, Test auf dem Mac offen |
| Automatische Drehung auf dem Kopf stehender Seiten (Ansichtsfassung, Original unverändert) | neu, Test auf dem Mac offen |
| Teilvorgänge, Chronik, Fristen mit Fundstelle und Verlauf, Kontakte mit Anschriftenverlauf, Versand, Referenzen, Bereiche, Schlagwörter, Papierkorb, Volltextsuche | Datenmodell und Schnittstellen ([docs/API.md](docs/API.md)) |
| Neue Oberfläche: Posteingang mit Absendererkennung, Vorgänge, Akte, Fristen, Archiv (nur Abgeschlossenes), Adressbuch, Chat-Notizen, Papierkorb | Etappe 3; bisherige Oberfläche unter `/alt` |
| Briefe mit Vorlagen und Druck, Fundstellen aus dem Text übernehmen, Abschlussprüfung, Aktenexport (ZIP mit Chronik.pdf), Datensicherung mit Prüfung | Etappe 3, Teil 2 |

Der Fahrplan steht in [docs/ETAPPEN.md](docs/ETAPPEN.md). Die Übergabe aus der ChatGPT-Entwicklung liegt in
[docs/Uebergabe_ChatGPT](docs/Uebergabe_ChatGPT).

## Voraussetzungen

- macOS 14 oder neuer, Apple Silicon (der mitgelieferte Finder-Starter ist arm64)
- Python 3.8 oder neuer
- Xcode-Kommandozeilenwerkzeuge für den Bau der Helfer: `xcode-select --install`

## Starten

Im Finder `Korrespondenz_Lokal/Korrespondenz.app` öffnen oder im Terminal:

```bash
cd Korrespondenz_Lokal
python3 -B app.py --open
```

Die Anwendung läuft danach unter http://127.0.0.1:8765. Beim ersten Start baut sie die Helfer für Texterkennung
und Scanner. Das dauert einige Sekunden.

## Prüfen

```bash
python3 -B Korrespondenz_Lokal/app.py --self-test
```

Der Selbsttest arbeitet mit synthetischen Daten in einem temporären Ordner und fasst echte Daten nicht an.
Die Prüfung auf dem Mac mit echter Texterkennung beschreibt [docs/TESTANLEITUNG_MAC.md](docs/TESTANLEITUNG_MAC.md).

## Daten

Alle Daten liegen in `Korrespondenz_Lokal/Daten/` und sind von Git ausgeschlossen.

| Inhalt | Ort |
|---|---|
| Datenbank | `Daten/Rechtsberatung.sqlite3` |
| Originale der Vorgangsdokumente | `Daten/Uploads/<sha256>.<endung>` |
| Anlagen aus ChatGPT-Exporten | `Daten/Chat_Originale/` |
| Automatische Sicherungen vor Schemaänderungen und Datensicherungen aus den Einstellungen | `Daten/Sicherungen/` |
| Aufrecht gedrehte Ansichtsfassungen (neu erzeugbar) | `Daten/Ansicht/` |
| Protokoll | `Daten/Logs/korrespondenz.log` und `Daten/Logs/scanner.log` |
| Scan-Zwischenablage | `Daten/Scan_Eingang/` |
| Gebaute Helfer | `Daten/Laufzeit/` |

Für eine manuelle Sicherung die Anwendung beenden und den ganzen Ordner `Daten/` kopieren.
Datenbank und Originale gehören zusammen.

## Aufbau

| Datei | Aufgabe |
|---|---|
| `Korrespondenz_Lokal/app.py` | HTTP-Dienst, SQLite mit Schema-Migrationen, Dokumentimport, OCR-Warteschlange, Scanner, Selbsttest |
| `Korrespondenz_Lokal/akte.py` | Datenmodell der Vorgangsakte, Suche, Papierkorb und zugehörige Schnittstellen |
| `Korrespondenz_Lokal/chat_sync.py` | Import von ChatGPT-Exporten |
| `Korrespondenz_Lokal/mail_import.py` | Übernahme markierter E-Mails aus Apple Mail |
| `Korrespondenz_Lokal/oberflaeche.html`, `oberflaeche.js`, `oberflaeche.css` | Neue Browseroberfläche |
| `Korrespondenz_Lokal/Korrespondenz_Rechtsberatung.html` | Bisherige Oberfläche unter `/alt` (Chat-Import, Rechtsberatung) |
| `Korrespondenz_Lokal/lokale_vorgaenge.js` | Vorgangsliste, Upload, Scan und Dokumentkarten für echte Daten |
| `Korrespondenz_Lokal/chat_notizen.js` | Ansicht der Chat-Notizen |
| `Korrespondenz_Lokal/ocr.swift` | PDFKit und Apple Vision, gibt seitenweisen Text als JSON aus |
| `Korrespondenz_Lokal/scanner.m` | Nativer Scandialog (ImageKit) |
| `Korrespondenz_Lokal/starter.m` | Quelltext des Finder-Starters |
| `Korrespondenz_Prototyp.html` | Eigenständiger Klickprototyp aus der ChatGPT-Entwicklung |
| `DATENBANKSCHEMA.sql` | Aktuelles Schema einer frischen Installation |
| `Testdaten/` | Synthetische Dateien für Selbsttest und Handtest |

Der Dienst hört nur auf `127.0.0.1`. Schreibzugriffe verlangen den Header `X-Korrespondenz: lokal`,
Host und Origin werden geprüft.

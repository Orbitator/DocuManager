# Stand und technische Entscheidungen

Stand 23. November 2026

Das Paket enthält den aktuellen Programmstand. Die bereinigte Kopie der Archivansicht startet leer. Identifizierende Namen aus den Beispielen wurden in den beiden HTML-Dateien durch Musterbezeichnungen ersetzt. Die SQLite-Bestandsdatei, Archivoriginale, Uploads, Chat-Anlagen, Scan-Dateien und erzeugte Laufzeithelfer samt Cache sind aus dem Paket genommen. Das vorhandene Finder-App-Bundle ist enthalten. Der Stylesheet-Code liegt inline in den HTML-Dateien.

## A. Getestet und noch offen

| Prüfumfang | Beobachtung |
|---|---|
| Echte Bestandsdaten | Die vorhandene SQLite-Datei bestand den Integritätstest. Die 81 importierten Archiv-Metadatensätze wurden gelesen. Ihre Filter und Quellenlinks wurden in einer simulierten Browserumgebung geprüft. In der Bestandsdatenbank waren keine archivierten Originale, produktiven Vorgänge, Dokumente oder importierten Chats verzeichnet. |
| Backend mit synthetischen Daten | Der integrierte Selbsttest prüft Anlegen und Wiederlesen, Bereich, Status, Fristenvalidierung, unveränderte Originalbytes, Dubletten, Titelbearbeitung, simulierte Scan-Dateiübergabe und wiederholbaren Chatimport. Ein separates synthetisches PDF mit Textebene lieferte den erwarteten Betreff und die Seitenangabe. |
| Browser mit synthetischen Daten | Desktop-DOM-Tests mit simuliertem Browser und simulierten HTTP-Antworten deckten u. a. kombinierte Filter, Sortierung, Friständerung, Chat-Auswahl und Notizsuche ab. Die HTML-Demofunktionen besitzen zusätzliche Selbsttests. |
| Native Funktionen | Die nativen Helfer und der Starter wurden kompiliert. Der signierte Starter konnte den Backend-Selbsttest ausführen. Der Finder-Start wurde aus der eingeschränkten Umgebung nicht bestätigt. Der lokale HTTP-Start scheiterte dort am Binden des Ports. |
| Noch offen | End-to-End-Test des entpackten Pakets im normalen Mac-Benutzerkontext mit Browser, Dateien aus einem realen Vorgang, echter Bild-OCR, angeschlossenem Scanner und einem tatsächlich exportierten ChatGPT-ZIP. |

### Reproduzierbare Prüfungen

Vom Paketstamm aus den Backend-Selbsttest starten:

```bash
python3 -B Korrespondenz_Lokal/app.py --self-test
```

Der im HTML enthaltene DEMO-Selbsttest startet mit `?selbsttest` in der URL und schreibt sein Ergebnis in das Attribut `data-selftest` des HTML-Wurzelelements. Für einen manuellen Import `Testdaten/PDF_Stellungnahme.pdf` oder `Testdaten/conversations.json` in der laufenden Anwendung auswählen. Bei einsatzbereiter Erkennung lautet der PDF-Titel „Stellungnahme zum Frontschaden“, Fundstelle Seite 1.

Der Bilderkennungstest kann mit dem vorhandenen Testbild separat ausgeführt werden. Aus dem Paketstamm:

```bash
ocr_test_dir=$(mktemp -d "${TMPDIR:-/tmp}/korrespondenz-ocr.XXXXXX")
swiftc -module-cache-path "$ocr_test_dir/cache" -O Korrespondenz_Lokal/ocr.swift -o "$ocr_test_dir/ocr"
python3 -B Korrespondenz_Lokal/app.py --self-test \
  --test-image Testdaten/OCR_Stellungnahme.png --ocr-binary "$ocr_test_dir/ocr"
```

## B. Apple Vision und der Pixelpufferfehler

Beim Bildtest meldete Vision zuerst `nilError`. Der spätere Versuch endete mit `com.apple.Vision Code=8: Failed to create CVPixelBuffer`. Begleitend erschien eine fehlgeschlagene `sysctlbyname`-Abfrage zu `kern.hv_vmm_present`. Die Ursache ist offen. Die Arbeitshypothese ist eine Einschränkung der isolierten Prozessumgebung bei der Vision- oder CoreVideo-Verarbeitung. Aus dem Log allein lässt sich weder diese Hypothese beweisen noch ein Bildformat-, System- oder Frameworkproblem ausschließen.

Der aktuelle Swift-Code versucht zunächst `VNRecognizeTextRequest` im Modus `.accurate` mit `CGImage`. Nach einem Fehler wechselt er auf `.fast`, wählt ab macOS 14 verfügbare CPU-Geräte für die Rechenstufen und übergibt einen selbst erzeugten BGRA-Pixelpuffer. Die CPU-Auswahl wurde dabei von einem unwirksamen Typvergleich auf den Enum-Fall `.cpu` korrigiert. Keiner dieser Schritte führte in der eingeschränkten Umgebung zu einem erfolgreichen Bildtest. Digitale PDFs mit ausreichend eingebettetem Text nutzen PDFKit als separaten, erfolgreich geprüften Pfad.

## C. Mindestversionen und getestete Versionen

| Komponente | Ableitung und Prüflage |
|---|---|
| macOS | Für den vollständigen Funktionsumfang mit nativen Fenstern ist **macOS 14** die aus dem Quellcode abgeleitete Untergrenze. `starter.m` und `scanner.m` rufen `NSApplication.activate` ohne Versionsprüfung auf. Diese Methode ist ab macOS 14 verfügbar. Der mitgelieferte Starter deklariert und linkt trotzdem ab 13.0. macOS 13 ist damit für diese Funktionen nicht belastbar unterstützt. |
| CPU | Der mitgelieferte Starter ist arm64, also für Apple Silicon. Ein Intel-Build ist nicht enthalten oder getestet. |
| Python | **Python 3.8** ist die aus der Syntax und verwendeten Standardbibliothek abgeleitete Untergrenze, unter anderem wegen Zuweisungsausdrücken und `Path.unlink(missing_ok=True)`. Geprüft wurde mit 3.12.1. |
| Xcode-Kommandozeilenwerkzeuge | Für den unveränderten Quellcode ist ein Toolset mit **macOS-14-SDK und Swift 5.9** der aus dem Code abgeleitete Einstieg, also die Generation der Xcode 15 Command Line Tools oder neuer. Grund sind die im Swift-Code referenzierten Vision/Core-ML-APIs und `NSApplication.activate`. Der Build mit dem ältesten Toolset wurde nicht geprüft. Erprobt auf dem Entwicklungsrechner waren CLT 26.6, Swift 6.3.3 und Apple Clang 21. |
| Tatsächliche Plattformprüfung | Die Entwicklungsumgebung meldete macOS 27.0 auf arm64. Der automatisch gebaute lokale OCR-Helfer trug laut Mach-O eine Mindestversion 28.0. Der Runtime-Build setzt kein eigenes Deployment-Ziel. Der Cache ist deshalb aus dem ZIP entfernt und der Helfer wird am Ziel neu gebaut. Der Swift- und Clang-Build im Zielkontext bleibt Teil des Praxistests. |

Quelle zur Zuordnung der SDK- und Swift-Versionen: [Apple · Xcode SDKs und Systemanforderungen](https://developer.apple.com/xcode/system-requirements).

## D. Offene Fehler, Provisorien und TODOs

- **Archivansicht.** Sie liest den eingebetteten HTML-Bestand. Neu angelegte oder aktualisierte SQLite-Archivdaten erscheinen dadurch nicht automatisch in der Ansicht. Der Server hat außerdem keine Route für die von dieser Ansicht vorgesehenen relativen Archiv-Originalpfade.
- **Frische Datenbank.** Beim Start legen `Store` und `ChatSync` sechs produktive Tabellen an. Die siebte Tabelle `archivdatei` stammt aus dem früheren Inventarimport. Auf einer leeren Installation fehlt sie bis zur manuellen Schema-Initialisierung. Der Chatimport kann ohne diese Tabelle laufen, die Archivverknüpfung entfällt dann. Das mitgelieferte vollständige Schema erzeugt alle sieben Tabellen.
- **Scan-Aufträge.** Die freigegebenen Scan-Dateien werden beim Statusabruf importiert. Auftragszustand und Vorschautoken liegen im Prozessspeicher. Wird der Browser vor dem Abruf geschlossen oder der Dienst neu gestartet, gibt es keinen automatischen Wiederanlauf für wartende Scans. Zurückgebliebene Dateien können noch in der Scan-Zwischenablage liegen.
- **Fehlerdiagnose.** HTTP-Standardlogs sind abgeschaltet. Scanner-Standardausgabe und Fehlerausgabe landen in `DEVNULL`. Bei OCR-Fehlern ist im Browser in der Regel nur ein generischer Status zu sehen. Das erschwert die Diagnose auf einem anderen Mac.
- **Weitere Grenzen.** Der Dienst verwendet einen einzelnen `HTTPServer`, daher blockieren längere Importe andere Anfragen. Die OCR- und Scanner-Builds nutzen die lokalen Compiler-Vorgaben ohne festes Deployment-Ziel. Das Starten der nativen App auf einer anderen macOS-Version sowie die Unterstützung von Bild-OCR und echter Scannerhardware bleiben ungeprüft.
- **Fachlicher Ausbau.** Teilvorgänge, Chronik, Adressbuch, Versandnachweis und Fristen mit Belegfundstellen laufen weiterhin im Demo-Zustand. Produktive Volltextsuche und OCR-Warteschlange, Backups, Archivverknüpfungen im Vorgang und ChatGPT-Live-Sync sind geplante Arbeit. Im geprüften Quellcode standen dazu keine eigens markierten `TODO`- oder `FIXME`-Kommentare.

## E. Speicherorte nach dem Start

Alle Pfade beginnen im ursprünglichen Projektordner, der `Korrespondenz_Lokal` enthält.

| Inhalt | Relativer Pfad |
|---|---|
| SQLite-Datenbank | `Korrespondenz_Lokal/Daten/Rechtsberatung.sqlite3` |
| Importierte Vorgangsdokumente | `Korrespondenz_Lokal/Daten/Uploads/<sha256>.<Endung>` |
| Aus ChatGPT-Exporten kopierte Anlagen | `Korrespondenz_Lokal/Daten/Chat_Originale/<sha256>` |
| Scan-Zwischenablage | `Korrespondenz_Lokal/Daten/Scan_Eingang/Scan-<zufälliger Name>/` |
| Frühere Ablage für Rechtsberatung-Originale | `Korrespondenz_Lokal/Daten/Originale/`, im Übergabepaket ausgelassen und ohne automatisch zugeführte Archivoriginale |
| Erzeugte OCR- und Scanner-Helfer | `Korrespondenz_Lokal/Daten/Laufzeit/korrespondenz-ocr` und `Korrespondenz_Lokal/Daten/Laufzeit/korrespondenz-scanner` |
| Swift-Modulcache | `Korrespondenz_Lokal/Daten/Laufzeit/SwiftCache/` |
| Logdateien | Es gibt keinen persistenten Logpfad. Der CLI-Start schreibt ins Terminal. Der Finder-Starter hält die jüngste Prozessausgabe im Speicher. |

## F. Schema und Startmigration

`DATENBANKSCHEMA.sql` ist aus `sqlite_schema` der vorhandenen Datenbank extrahiert. Primär- und Fremdschlüssel, `UNIQUE`, `CHECK` und der Index `archiv_typ` sind enthalten. SQLite erzeugt die zu Primärschlüsseln und Eindeutigkeitsregeln gehörenden `sqlite_autoindex_…`-Indizes selbst. `chat_anlage.archiv_id` bleibt eine fachliche Referenz ohne Datenbank-Fremdschlüssel.

Beim Start erzeugt `Korrespondenz_Lokal/app.py` in `Store.__init__` die Tabellen `vorgang`, `dokument` und `dokumentseite`. Danach prüft der Code `PRAGMA table_info(vorgang)` und ergänzt bei Bedarf `status` und `naechste_frist` per `ALTER TABLE`. `Store.connect()` aktiviert Fremdschlüssel pro Verbindung. Die drei Chat-Tabellen entstehen in `Korrespondenz_Lokal/chat_sync.py` in `ChatSync.__init__`. Die SQL-Datei eignet sich zur Initialisierung einer **leeren** Datenbank. Sie ist kein Upgrade-Skript für die Bestandsdatei.

## G. Technische Entscheidungen

Die Gründe beschreiben den erreichten Stand und die aus dem Code nachvollziehbaren Abwägungen. Eine formale Architekturbeschluss-Historie liegt nicht vor.

| Entscheidung | Begründung und Konsequenz |
|---|---|
| Python ohne Webframework | Standardbibliothek und SQLite ermöglichen einen kleinen lokalen Dienst ohne Python-Paketinstallation. Die Anwendung pflegt Routing, Validierung, Uploadlimits und Fehlerbehandlung selbst. |
| SQLite und getrennte Originaldateien | Vorgänge, OCR-Text und Metadaten sind relational abfragbar. Originale bleiben bytegetreu im Dateisystem. Bei Datensicherung müssen Datenbank und zugehörige Dateien zusammen gesichert werden. |
| Ein Dokumentdatensatz pro Vorgang | Das Datenmodell bildet Upload, fallbezogene Ablage und Duplikatprüfung mit einer direkten Fremdschlüsselbeziehung ab. Für gleiche Bytes können mehrere Vorgänge eigene Metadaten führen. Bei identischem Hash und gleicher Endung wird der physische Upload wiederverwendet. Gemeinsame Dokumentidentität oder Querverknüpfungen erfordern ein separates Dateimodell mit Zuordnungstabelle. |
| OCR in der HTTP-Anfrage | Der erste Importablauf liefert Dokument, Titel und Erkennungsstatus in einem Durchlauf, ohne Jobtabelle oder Worker. Lange OCR, asynchrone Vorbereitung des Helfers und umfangreiche Chatimporte können den Einzelserver blockieren. |
| PDFKit und Apple Vision als native Helfer | Vorhandene PDF-Texte und lokale Bilderkennung sind über macOS-Frameworks erreichbar. Der Prozessaufruf hält die Python-Anwendung frei von nativen Python-Abhängigkeiten. Die OCR- und Scan-Wege bleiben dadurch plattformgebunden. |
| Chatimport über Export und stabile IDs | Die App bietet eine explizite Auswahl aus dem Export und schreibt nur gewählte Unterhaltungen. Stabile IDs führen wiederholte Importe zusammen. Neue Inhalte erfordern einen neuen Export, und verfügbare Originale hängen vom Export beziehungsweise eindeutig erkannten Archivverweisen ab. |
| Lokaler Loopback-Betrieb | Der Dienst hört auf `127.0.0.1:8765` und prüft Host sowie bei Schreibzugriffen einen eigenen Header und, sofern vorhanden, Origin. Es gibt keine Benutzerverwaltung. Der bestehende Server ist für einen lokalen Einzelplatz ausgelegt. |

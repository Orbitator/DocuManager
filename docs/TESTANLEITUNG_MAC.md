# Testanleitung auf dem Mac · Etappe 1

Dauer etwa 15 Minuten. Die Schritte arbeiten zuerst mit einer Kopie, die echte Datenbank bleibt bis Schritt 5
unberührt.

## 1. Stand holen

Neuen Ordner anlegen, zum Beispiel `~/Projekte`, dann im Terminal:

```bash
cd ~/Projekte
```

```bash
git clone https://github.com/Orbitator/DocuManager.git
```

```bash
cd DocuManager
```

Solange Etappe 1 noch nicht in `main` übernommen ist, den Arbeitszweig auschecken:

```bash
git checkout claude/sleepy-brown-fydjld
```

## 2. Selbsttest

```bash
python3 -B Korrespondenz_Lokal/app.py --self-test
```

Erwartet: `Selbsttest erfolgreich.`

## 3. Bilderkennung mit Apple Vision

```bash
ocr_test_dir=$(mktemp -d "${TMPDIR:-/tmp}/korrespondenz-ocr.XXXXXX")
```

```bash
swiftc -O -target arm64-apple-macos14.0 -module-cache-path "$ocr_test_dir/cache" Korrespondenz_Lokal/ocr.swift -o "$ocr_test_dir/ocr"
```

```bash
python3 -B Korrespondenz_Lokal/app.py --self-test --test-image Testdaten/OCR_Stellungnahme.png --ocr-binary "$ocr_test_dir/ocr"
```

Erwartet: `Selbsttest erfolgreich einschließlich echter Bilderkennung.`
Falls der Pixelpuffer-Fehler erneut auftritt, bitte die komplette Ausgabe kopieren.

## 4. Anwendung mit leerem Datenbestand

```bash
cd Korrespondenz_Lokal
```

```bash
python3 -B app.py --open
```

Im Browser:

1. **Vorgänge** öffnen, „+ Neuer Vorgang“ anlegen.
2. `Testdaten/PDF_Stellungnahme.pdf` und `Testdaten/OCR_Stellungnahme.png` gemeinsam importieren.
   Erwartet: Beide Karten erscheinen sofort mit „⏳ Wartet auf Texterkennung“. Wenige Sekunden später zeigen
   sie den Titel „Stellungnahme zum Frontschaden“ und die Titelquelle mit Seite 1.
3. Während die Erkennung läuft, einen zweiten Vorgang anlegen. Die Anwendung muss sofort reagieren.
4. Bei einem Dokument „Titel bearbeiten“, dann „Text erneut erkennen“. Der eigene Titel muss bleiben.
5. „Dokument scannen“, falls ein Scanner angeschlossen ist.
6. Im Terminal mit Ctrl+C beenden. Das Protokoll liegt in `Daten/Logs/korrespondenz.log`.

## 5. Bestehende Datenbank übernehmen

Erst wenn Schritt 2 bis 4 funktionieren. Die bisherige Anwendung vorher beenden.

1. Im bisherigen Projektordner den Ordner `Korrespondenz_Lokal/Daten` komplett kopieren, zum Beispiel auf den
   Schreibtisch. Das ist die Sicherung.
2. Den Inhalt von `Daten` (Datenbank, `Uploads`, `Chat_Originale`) in `DocuManager/Korrespondenz_Lokal/Daten/`
   kopieren. Den Ordner `Laufzeit` nicht mitkopieren, die Helfer werden neu gebaut.
3. Anwendung starten. Beim ersten Start legt sie zusätzlich automatisch eine Sicherung in `Daten/Sicherungen/` an
   und aktualisiert das Schema auf Version 2.
4. Prüfen: Vorgänge, Chat-Notizen und Archivliste sind vollständig.

## 6. Neue Oberfläche (Etappe 3)

1. Unter **Einstellungen** bei „Eigene Angaben“ Ihren Namen und Ihre Anschrift eintragen und speichern.
2. Unter **Dokument importieren** zwei echte Schreiben auswählen. Sie erscheinen als Kacheln im **Posteingang**.
3. Eine Kachel anklicken. Rechts daneben stehen Titel, Datum und Absender. Prüfen, ob der Absender stimmt.
4. Einen Vorgang wählen oder „+ Neuer Vorgang …“ und **Zuordnen**. Die Akte öffnet sich mit dem Eingang
   in der Chronik und dem Original rechts.
5. **Archiv** öffnen und zwischen den Gruppierungen wechseln.

## Rückmeldung

Bitte mitteilen:

- Ausgabe von Schritt 2 und 3
- Ob Schritt 4 wie beschrieben funktioniert hat, sonst was stattdessen passiert ist
- Bei Fehlern die letzten 50 Zeilen aus `Daten/Logs/korrespondenz.log`

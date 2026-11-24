# Testanleitung auf dem Mac · Etappe 1

Dauer etwa 15 Minuten. Die Schritte arbeiten zuerst mit einer Kopie, die echte Datenbank bleibt bis Schritt 5
unberührt.

## 0. Als Programm installieren (ab Version 0.8)

1. ZIP herunterladen und entpacken. Falls Sie mit Ihren bisherigen Daten weiterarbeiten: den Ordner
   `Korrespondenz_Lokal/Daten` aus dem vorigen Download in den neuen Ordner `Korrespondenz_Lokal` kopieren.
2. Im neuen Ordner `Korrespondenz_Lokal` **DocuManager_Installieren.command** doppelklicken.
3. Erwartet: „Fertig.“, der Finder zeigt **DocuManager** unter Programme, auf die Frage „Jetzt starten?“ öffnet
   sich die Anwendung im Browser. Ab jetzt über Launchpad oder Spotlight starten; beenden über **Beenden** unten links.
4. Updates: neue ZIP entpacken, Installationsprogramm erneut doppelklicken. Ihre Daten liegen in `~/DocuManager/Daten`.

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
   und aktualisiert das Schema auf die aktuelle Version.
4. Prüfen: Vorgänge, Chat-Notizen und Archivliste sind vollständig.

## 6. Neue Oberfläche (Etappe 3)

1. Unter **Einstellungen** bei „Eigene Angaben“ Ihren Namen und Ihre Anschrift eintragen und speichern.
2. Unter **Dokument importieren** zwei echte Schreiben auswählen. Sie erscheinen als Kacheln im **Posteingang**.
3. Eine Kachel anklicken. Rechts daneben stehen Titel, Datum und Absender. Prüfen, ob der Absender stimmt.
4. Einen Vorgang wählen oder „+ Neuer Vorgang …“ und **Zuordnen**. Die Akte öffnet sich mit dem Eingang
   in der Chronik und dem Original rechts.
5. **Archiv** öffnen und zwischen den Gruppierungen wechseln.

## 7. Apple Mail

1. In Mail zwei E-Mails mit der Markierung „Erfasster Beleg“ (grau) versehen, eine davon mit PDF-Anlage.
2. In der Anwendung im **Posteingang** auf **„Aus Mail holen“** klicken.
3. Beim ersten Mal fragt macOS, ob Terminal bzw. Python „Mail“ steuern darf: **OK**.
   Falls die Frage nicht kommt oder abgelehnt wurde: Systemeinstellungen → Datenschutz & Sicherheit → Automation.
4. Erwartet: Die E-Mails erscheinen als Kacheln mit Betreff als Titel, Absender und Datum. Die PDF-Anlage
   erscheint als eigene Kachel. Ein zweiter Klick auf „Aus Mail holen“ holt nichts doppelt.
5. Unter **Einstellungen → Apple Mail** steht „Letzter Abruf: Datum, Uhrzeit (n neu)“.

## 8. Briefe, Fundstellen, Abschluss, Sicherung

1. Eine Akte öffnen, in der Chronik **Brief** klicken. Vorlage „Stellungnahme“ wählen. Rechts erscheint die
   Vorschau mit Ihrem Absender und der Anrede. **Entwurf anlegen**. Erwartet: Status „Schreiben verfassen“,
   der Brief erscheint als Entwurf. **Drucken oder PDF** öffnet ihn druckfertig.
2. Einen Eingang wählen, in der Vorschau auf **Text & Fundstellen** umschalten. Ein Datum mit der Maus markieren,
   im kleinen Menü **Als Frist**. Erwartet: Frist mit Fundstelle (Zitat, Seite).
3. Status des Vorgangs auf **Erledigt** setzen. Erwartet: Hinweis auf offene Frist und Entwurf.
   **Abbrechen** lässt den Status unverändert. Nach **Trotzdem abschließen** springt die Anwendung ins **Archiv**;
   der Vorgang steht nicht mehr unter **Vorgänge**, seine Dokumente stehen im Archiv.
4. **Exportieren** in der Akte: Es wird eine ZIP mit Chronik.pdf heruntergeladen.
5. **Einstellungen → Datensicherung → Sicherung erstellen**, danach **Prüfen**. Erwartet: „In Ordnung …“.

## 9. Fristen, Archiv ohne Vorgang, Vorgang ändern

1. Ein Schreiben mit Frist importieren (z. B. „… bis zum 16.12.2026“). In den Details im Posteingang steht unter
   **Fristen** die erkannte Frist mit Datum und Zitat. **Frist von Hand** ergänzt eine weitere. Zuordnen.
   Erwartet: Beide Fristen stehen in der Akte und unter **Fristen**.
2. Ein zweites Dokument mit **Ohne Vorgang ins Archiv** ablegen. Erwartet: Es steht im **Archiv** unter „Ohne Vorgang“.
3. In der Akte bei einem Dokument **Vorgang ändern** und einen anderen Vorgang wählen. Erwartet: Das Dokument
   steht danach im gewählten Vorgang.
4. Die Vorschau eines gescannten Bildes zeigt die ganze Seite, ohne zu scrollen.

## 10. Scanner

1. **Dokument importieren → Scannen …**. Erwartet: Nach einigen Sekunden steht Ihr Scanner in der Liste oben,
   auch wenn er nur im WLAN hängt.
2. Falls nicht: Unten links **„Digitale Bilder“ öffnen**, dort links den Scanner wählen und bei „Scannen nach“ den
   Ordner **DocuManager Scans** (in Ihrem Benutzerordner) einstellen. Scannen. Erwartet: Nach wenigen Sekunden erscheint der Scan
   im Posteingang. Den Ordner öffnet auch **Dokument importieren → Scan-Ordner öffnen**.
3. Im Scan-Dialog **Scan** drücken. Erwartet: keine Meldung „not writable“; nach „Scans übernehmen“ erscheint der
   Scan im Posteingang.
4. **„Digitale Bilder“ öffnen**: Das Scanfenster schließt sich, „Digitale Bilder“ kann den Scanner benutzen, DocuManager
   zeigt die Anleitung zum Ordner „DocuManager Scans“.
5. Bei Problemen den Inhalt von `~/DocuManager/Daten/Logs/scanner.log` schicken.

## 10a. Scannen ohne Dialog (ab 0.16)

1. Einmal **Dokument importieren → Scannen mit Einstellungen …**, Ihren Scanner wählen (wird gemerkt) und scannen.
   Erwartet: Der Scan wird nach wenigen Sekunden ohne „Scans übernehmen“ in den Posteingang übernommen.
2. Mehrere Blätter in den Einzug legen, **Dokument importieren → Scannen**. Erwartet: kleines Fenster „Scanne mit …“,
   danach ein PDF mit allen Seiten im Posteingang, ohne weitere Fragen.
3. Falls stattdessen der Dialog erscheint: Der Grund steht unten im Dialog. Bitte mitteilen, mit dem Inhalt von
   `~/DocuManager/Daten/Logs/scanner.log`.

## 11. Automatische Drehung

1. Einen Brief verkehrt herum (auf dem Kopf) scannen oder ein solches PDF importieren. Bereits vorhandene
   Scans werden nach dem ersten Start dieses Stands einmal automatisch neu geprüft (einige Minuten).
2. Warten, bis die Texterkennung fertig ist, dann das Dokument in der Akte oder im Posteingang öffnen.
3. Erwartet: Schon die Kachel im Posteingang zeigt das Dokument aufrecht. In der Akte steht daneben „automatisch gedreht“. „Original ungedreht“ zeigt die
   unveränderte Datei. Der erkannte Text (Text & Fundstellen) ist lesbar.
4. Falls die Texterkennung gar nicht mehr läuft: die letzten Zeilen aus `Daten/Logs/korrespondenz.log` schicken
   (der Helfer wird bei diesem Stand neu gebaut).

## 12. ChatGPT-Lesezeichen

1. **Einstellungen → ChatGPT-Lesezeichen**: Lesezeichenleiste einblenden (Safari: Darstellung → Favoritenleiste
   einblenden; Chrome: ⇧⌘B) und den Knopf **„→ DocuManager“** hineinziehen.
2. In Safari oder Chrome bei ChatGPT anmelden und einen Chat öffnen, in dem Sie eine Datei hochgeladen haben.
3. Das Lesezeichen anklicken. Erwartet: Unten rechts erscheint ein blauer Hinweis, ein DocuManager-Fenster öffnet sich
   mit Chat-Titel und Dateiliste.
4. Vorgang wählen, Dateien anhaken, **Übernehmen**. Erwartet: Die Dateien stehen als Dokumente im Vorgang.
5. Falls stattdessen eine Datei `….documanager.json` in Downloads landet: in das DocuManager-Fenster ziehen.
6. Bitte melden, was der blaue Hinweis anzeigt, falls etwas nicht klappt.

## 13. Claude-Analyse und Brief (ab 0.17)

1. Unter **console.anthropic.com** anmelden, Guthaben aufladen (z. B. 5 $), unter **API Keys** einen Schlüssel erzeugen
   und kopieren.
2. **Einstellungen → Claude (KI-Analyse)**: Schlüssel einfügen, **Speichern**. Erwartet: „Eingerichtet · Schlüssel endet
   auf …“.
3. Einen Vorgang mit einem Schreiben öffnen, den Eingang anklicken, in der Vorschau auf **Claude** klicken,
   **Zusammenfassen**. Erwartet: Nach einigen Sekunden steht die Zusammenfassung im Dialog.
4. Eine eigene Frage stellen (z. B. „Muss ich zahlen?“). Erwartet: Die Antwort bezieht sich auf die vorige.
5. **Antwort entwerfen** → **Als Brief übernehmen**. Erwartet: Briefdialog mit Betreff und Text von Claude, darüber
   Claudes Hinweise. Empfänger prüfen.
6. **Nach dem Speichern drucken** und **Als versendet in der Chronik erfassen** anhaken, **Entwurf anlegen**. Erwartet:
   Ein Fenster mit dem Brief öffnet sich samt Druckdialog; in der Chronik stehen Entwurf und „Versendet · Post“, der
   Status ist „Schreiben abgeschickt“.

## Rückmeldung

Bitte mitteilen:

- Ausgabe von Schritt 2 und 3
- Ob Schritt 4 wie beschrieben funktioniert hat, sonst was stattdessen passiert ist
- Bei Fehlern die letzten 50 Zeilen aus `Daten/Logs/korrespondenz.log`

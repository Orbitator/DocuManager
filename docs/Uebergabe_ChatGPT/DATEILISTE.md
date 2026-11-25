# Dateiliste

| Datei | Aufgabe |
|---|---|
| `Korrespondenz_Lokal/app.py` | Startet den lokalen HTTP-Dienst und enthält SQLite-Zugriffe, API, Dokumentimport, OCR-Aufruf, Scannersteuerung und den Backend-Selbsttest. |
| `Korrespondenz_Lokal/chat_sync.py` | Liest ChatGPT-Exporte, importiert ausgewählte Unterhaltungen mit ihren Anlagen und enthält den Import-Selbsttest. |
| `Korrespondenz_Lokal/Korrespondenz_Rechtsberatung.html` | Liefert die lokale Browseroberfläche mit CSS, Beispieldaten, leerem Archiv-Inventar und integriertem UI-Selbsttest. |
| `Korrespondenz_Lokal/lokale_vorgaenge.js` | Steuert Vorgangsliste, Filter, Status, Fristen, Upload und Scanstatus für SQLite-Vorgänge. |
| `Korrespondenz_Lokal/chat_notizen.js` | Zeigt Chat-Notizen und steuert Auswahl, Import, Suche und Zugriff auf Anlagen. |
| `Korrespondenz_Lokal/ocr.swift` | Nutzt PDFKit, ImageIO und Apple Vision für seitenweise Texterkennung und gibt JSON an Python zurück. |
| `Korrespondenz_Lokal/scanner.m` | Implementiert den nativen macOS-Scandialog und die Übergabe der Scan-Dateien. |
| `Korrespondenz_Lokal/starter.m` | Ist der Objective-C-Quellcode des nativen Finder-Starters. |
| `Korrespondenz_Lokal/Korrespondenz_Starten.command` | Startet den Python-Dienst mit offenem Terminal und fordert das Öffnen des Browsers an. |
| `Korrespondenz_Lokal/Korrespondenz.app/Contents/Info.plist` | Enthält App-Metadaten, Bundle-ID und den Namen des Starterprogramms. |
| `Korrespondenz_Lokal/Korrespondenz.app/Contents/MacOS/Korrespondenz` | Ist der vorhandene kompilierte arm64-Finder-Starter, der den Browser nach dem Start des Dienstes öffnet. |
| `Korrespondenz_Lokal/Korrespondenz.app/Contents/_CodeSignature/CodeResources` | Enthält die Signatur-Metadaten des mitgelieferten App-Bundles. |
| `Korrespondenz_Prototyp.html` | Ist der eigenständige Klickprototyp mit synthetischen Vorgängen, integriertem CSS, JavaScript und UI-Selbsttest. |
| `DATENBANKSCHEMA.sql` | Enthält das vollständige Schema des Bestands einschließlich Archiv-Tabelle und Index, ohne Datenzeilen. |
| `STAND_UND_ENTSCHEIDUNGEN.md` | Dokumentiert Tests, Mindestversionen, offene Probleme, Speicherorte und technische Entscheidungen. |
| `Testdaten/PDF_Stellungnahme.pdf` | Ist ein synthetisches PDF mit Textebene und definiertem Betreff zur Prüfung der Titelübernahme. |
| `Testdaten/OCR_Stellungnahme.png` | Ist ein synthetisches Testbild mit dem Betreff für den nativen Vision-Selbsttest. |
| `Testdaten/conversations.json` | Ist ein synthetischer ChatGPT-Export mit zwei Beiträgen und einer verzeichneten Anlage ohne lokale Kopie. |
| `DATEILISTE.md` | Beschreibt Aufgabe und Ablageort jeder Datei im Übergabepaket. |

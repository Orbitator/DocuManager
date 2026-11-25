# Hinweise für die Entwicklung

- Sprache der Oberfläche, Meldungen, Kommentare und Dokumentation: Deutsch.
- Keine Python-Pakete außerhalb der Standardbibliothek; native Funktionen nur über die Helfer
  `ocr.swift` und `scanner.m` (macOS 14, Mindestversion in `MIN_MACOS`).
- Fachliches Datenmodell und Schnittstellen der Akte in `akte.py` (`Akte`, `ROUTES`, `test_akte`).
  Die Prüfkriterien aus dem Konzept stehen in `test_akte` und dürfen nicht abgeschwächt werden.
- Schemaänderungen nur als neue Funktion in `MIGRATIONS` (app.py) mit erhöhtem `SCHEMA_VERSION`.
  Bestehende Migrationen nicht ändern. Danach `DATENBANKSCHEMA.sql` neu erzeugen.
- Originaldateien nie verändern. Echte Daten (`Korrespondenz_Lokal/Daten/`) nie committen.
- Vor jedem Commit: `python3 -B Korrespondenz_Lokal/app.py --self-test` und `node --check` für geänderte JS-Dateien.
- Apple Vision, PDFKit, Scanner und Finder-Starter lassen sich nur auf einem Mac prüfen. Für solche Änderungen
  die Testanleitung in `docs/TESTANLEITUNG_MAC.md` ergänzen.
- Fahrplan und Stand: `docs/ETAPPEN.md`.

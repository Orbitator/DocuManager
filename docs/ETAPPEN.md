# Fahrplan

Grundlage sind das Konzept vom 23.11.2026, die Übergabe aus der ChatGPT-Entwicklung und der
Klickprototyp aus der Claude-Sitzung (Vorlage für Oberfläche und Abläufe).

## Etappe 1 · Fundament (dieser Stand)

Keine neuen Fachfunktionen, nur Betriebssicherheit.

| Änderung | Warum |
|---|---|
| Server bedient Anfragen parallel (`ThreadingHTTPServer`) | Ein langer Import blockierte bisher die ganze Anwendung. |
| Texterkennung als Warteschlange im Hintergrund | Der Upload antwortet sofort. Der Titel folgt, sobald die Erkennung fertig ist. |
| Wiederanlauf | Nach einem Neustart setzt die Warteschlange unterbrochene Aufträge fort. |
| „Text erneut erkennen“ je Dokument | Fehlgeschlagene oder alte Erkennungen lassen sich wiederholen. Ein manuell gesetzter Titel bleibt erhalten. |
| Protokoll in `Daten/Logs/` | Fehler von Texterkennung, Scanner und Helferbau sind auf jedem Mac nachvollziehbar. Die Ursache eines OCR-Fehlers steht zusätzlich am Dokument. |
| Schemaversion (`PRAGMA user_version`) mit geordneten Migrationen | Eine frische Installation erhält alle Tabellen, auch `archivdatei`. |
| Automatische Sicherung vor jeder Schemaänderung | Der bestehende Bestand wird vor dem Update nach `Daten/Sicherungen/` kopiert. |
| Helfer mit fester Mindestversion macOS 14 | Früher gebaute Helfer trugen die Mindestversion des Entwicklungsrechners. Sie werden beim nächsten Start automatisch neu gebaut. |
| Erweiterter Selbsttest | Prüft Update eines Altbestands samt Sicherung, Warteschlange, Wiederanlauf, Fehlerübernahme, Protokoll und Parallelbetrieb. |

**Geprüft auf dem Mac (23.11.2026):** Selbsttest erfolgreich, Bilderkennung mit Apple Vision erfolgreich
(Testbild `Testdaten/OCR_Stellungnahme.png`). Der Pixelpuffer-Fehler aus der Übergabe trat nur in der
eingeschränkten Entwicklungsumgebung auf.

## Etappe 2 · Datenmodell aus dem Prototyp (umgesetzt, Schemaversion 3)

Neues Modul `Korrespondenz_Lokal/akte.py`, Schnittstellen in [API.md](API.md). Die Oberfläche folgt in Etappe 3;
bis dahin sind die neuen Daten über die Schnittstellen und den Selbsttest prüfbar.

Bestehendes Verhalten bleibt: Vorgabestatus „Schreiben verfassen“, bisherige Schnittstellen, Dubletten im
selben Vorgang. Neu ist, dass dieselbe Datei in einem zweiten Vorgang verknüpft statt erneut angelegt wird.
Der Bestand wird beim ersten Start übernommen (Dokumentzuordnungen, Bereiche, Suchindex), vorher entsteht
automatisch eine Sicherung.

Der Selbsttest prüft die Kriterien aus dem Konzept:

| Kriterium | Prüfung |
|---|---|
| 1. Schadennummer aus einem Scan führt zur Akte und zum Original | Suche nach „KFZ-2026-1842“, „KFZ 2026 1842“ und „kfz2026“ findet Vorgang, Dokument und Seite |
| 2. Gutachten in zwei Teilvorgängen, kein zweites Exemplar | ein Dokument, ein Eintrag in beiden Teilvorgängen, erneuter Import in einen anderen Vorgang verknüpft |
| 3. Eingang, Entwurf, versendete Fassung und Nachweis chronologisch | Reihenfolge der Chronik, Entwurf verweist auf die versendete Fassung, Nachweis auf den Versand |
| 4. Zwei Teilvorgänge mit eigener Zuständigkeit, Status und Fristen | getrennte Werte und getrennte offene Fristen |
| 5. Empfänger in zwei Vorgängen, alte Anschrift bleibt nach Änderung sichtbar | Versand speichert die Anschrift, Kennzeichen „Anschrift geändert“, Versand an abgelaufene Anschrift wird abgelehnt |

Bestandteile:

- Teilvorgänge mit eigenem Status, Zuständigkeit und nächstem Schritt
- Chronik-Einträge: Eingang, Ausgang, Entwurf, Versandnachweis, Telefonat, Notiz, Entscheidung, Chat-Notiz,
  fehlendes Original; Ereignisdatum und Erfassungsdatum getrennt
- Fristen, Wiedervorlagen und Aufgaben mit Fundstelle (Dokument, Seite, Zitat), Zuständigkeit und Verlauf
- Kontakte mit Abteilungen, Kontaktwegen und Anschriften mit Gültigkeitszeitraum
- Versand mit gespeicherter Anschrift und Nachweis
- Referenzen (Aktenzeichen, Schadennummer) je Vorgang, Bereiche und Schlagwörter als Tabellen
- Datei einmal gespeichert, Dokument mit mehreren Vorgängen verknüpfbar
- Papierkorb über Löschzeitpunkt statt sofortigem Löschen
- Volltextsuche mit SQLite FTS5 über Dokumentseiten, Notizen und Chat-Notizen
- Status ergänzt um „Offen“, „Wartet auf Antwort“ und „Erledigt“

## Etappe 3 · Eine Oberfläche (Teil 1 umgesetzt, Schemaversion 4)

Neue Oberfläche unter http://127.0.0.1:8765 (`oberflaeche.html`, `oberflaeche.js`, `oberflaeche.css`).
Die bisherige Oberfläche bleibt unter `/alt` erreichbar (Chat-Import, Rechtsberatung).

Umgesetzt: Übersicht, Posteingang (Kacheln, Details neben dem Dokument, Vorschläge für Titel, Datum,
Absender und Vorgang, Zuordnen oder neuer Vorgang), Vorgänge (Filter, sortierbare Spalten), Vorgangsakte
(Teilvorgänge, Chronik mit Typfilter, Vorschau des Originals, Einträge, Antwort-Entwurf, Versand, Fristen,
Beteiligte, Referenzen, Schlagwörter), Fristen, Archiv (gruppiert nach Vorgang, Bereich, Absender oder Jahr,
filterbar, sortierbar), Adressbuch (Anschriftenverlauf, Dublettenhinweis), Papierkorb, Einstellungen
(Bereiche, eigene Angaben für die Absendererkennung), Volltextsuche, Import per Datei, Ziehen und Scan.

Absendererkennung: Absenderzeile über der Anschrift, Behörde oder Gericht im Kopf, Organisation im
Briefkopf, Grußformel. Eigene Angaben werden nie vorgeschlagen. Unbekannte Absender werden beim
Zuordnen als Kontakt mit Anschrift angelegt.

Offen für Teil 2: Briefvorlagen mit Vorschau, Markieren von Text in der Vorschau, Chat-Notizen in der
neuen Oberfläche, Abschlussprüfung beim Status „Erledigt“, Aktenexport.

Die Trennung zwischen „Vorgänge“ (echte Daten) und „Beispiele“ (Demo) entfällt. Die Ansichten aus dem
Prototyp arbeiten mit echten Daten: Übersicht, Posteingang, Vorgangsakte mit Chronik und Vorschau,
Fristen, Adressbuch, Chat-Notizen, Papierkorb, Einstellungen.

## Etappe 4 · Restfunktionen aus dem Konzept

- Vollständige Datensicherung (Datenbank und Originale) mit geprüfter Wiederherstellung
- Aktenexport als ZIP mit Chronik als PDF
- E-Mail-Import (.eml) mit Anlagen
- Briefvorlagen nach DIN 5008 mit Versand-Workflow
- Chat-Notizen mit Vorgängen verknüpfen, erwähnte Originale prüfen
- Kalender-Abo (iCal) für Fristen bei geschlossener Anwendung

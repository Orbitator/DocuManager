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

## Etappe 3 · Eine Oberfläche (umgesetzt, Schemaversion 7)

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

Apple Mail (Schemaversion 5, `mail_import.py`): „Aus Mail holen“ übernimmt alle E-Mails mit der eingestellten
Markierung (Vorgabe Grau, beim Anwender „Erfasster Beleg“) über die macOS-Automatisierung in den Posteingang:
die E-Mail als Dokument mit Kopf und Text, PDF- und Bildanlagen als eigene Dokumente. Absender, Datum und
Betreff kommen aus dem Mailkopf. Beim Zuordnen wandern die Anlagen mit. Die Message-ID verhindert Doppelungen,
die Markierung in Mail bleibt unverändert. Beim ersten Abruf fragt macOS nach der Erlaubnis, Mail zu steuern.

Teil 2 (umgesetzt, Schemaversion 7):

- Briefe: Vorlagen (Stellungnahme, Fristverlängerung, Erinnerung, Eingangsbestätigung, frei) mit
  persönlicher Anrede, Empfänger aus der aktuellen Anschrift, Live-Vorschau nach DIN 5008, Drucken oder PDF.
  Ein neuer Entwurf setzt den Status auf „Schreiben verfassen“.
- Text und Fundstellen: In der Vorschau zwischen Original und erkanntem Text wechseln. Markierten Text oder
  vorgeschlagene Fundstellen als Frist (mit Dokument, Seite, Zitat), Aktenzeichen, Dokumentdatum oder Notiz übernehmen.
- Chat-Notizen als eigener Menüpunkt; importierte ChatGPT-Unterhaltungen lassen sich in Vorgänge übernehmen.
- Abschlussprüfung bei „Erledigt“: offene Fristen, nicht versendete Entwürfe, fehlende Originale, ungeprüfte Chats.
- Archiv: Dokumente werden erst archiviert, wenn ihr Vorgang oder alle ihre Teilvorgänge auf „Erledigt“ stehen.
  Ein erledigter Vorgang verschwindet aus „Vorgänge“, der Übersicht, allen Auswahllisten und den Vorschlägen
  im Posteingang; nach dem Abschluss springt die Anwendung ins Archiv. Chronik, Briefe und Fristen werden dabei
  nicht vernichtet: Über ein archiviertes Dokument lässt sich die Akte weiterhin öffnen und bei Bedarf
  wieder aufnehmen (Status ändern).
- Scannen: Der Scan-Dialog sucht auch Netzwerkscanner (Bonjour/AirScan) und bietet „Digitale Bilder“ als Ausweg.
  Zusätzlich überwacht die Anwendung den Ordner `~/DocuManager Scans`: Was die Scanner-Software dort
  ablegt, kommt nach wenigen Sekunden in den Posteingang und wird nach „Übernommen“ verschoben.
- Fristen: Beim Zuordnen schlägt der Posteingang erkannte Fristen vor („bis zum 16.12.2026“, „spätestens am …“,
  „zahlbar bis …“, „innerhalb von 14 Tagen“ / „binnen eines Monats“ ab Dokumentdatum) mit Titel aus dem Satz
  (Stellungnahme, Zahlung, Widerspruch, Unterlagen, Rückmeldung) und Zitat. Fristen lassen sich dort auch von Hand
  ergänzen. Erkannte Fristen werden als verbindliche Frist mit Fundstelle eingetragen, von Hand gesetzte als
  Wiedervorlage. In der Akte zeigt „Text & Fundstellen“ die erkannten Fristen mit „Als Frist übernehmen“;
  „Frist“ im Kopf der Akte und „Neue Frist“ in der Fristenansicht legen Fristen von Hand an (`fristen_erkennen`).
- Ohne Vorgang ins Archiv: Ein Dokument aus dem Posteingang kann direkt archiviert werden (interner, stets
  erledigter Vorgang „Ohne Vorgang“, `system='ablage'`, in keiner Vorgangsliste).
- Vorgang ändern: Ein Dokument samt Chronik-Eintrag (und Mail-Anlagen) lässt sich in jeden bestehenden Vorgang
  verschieben, auch in einen erledigten oder zurück ins Archiv ohne Vorgang (`dokument_verschieben`).
- Vorschau: Bilder werden vollständig ins Fenster eingepasst, PDFs als ganze Seite geöffnet.
- Bedienung (0.8): „Heute“-Knopf an jedem Datumsfeld; je Dokumentzeile (Chronik, Dokumente, Archiv) zwei kleine
  Knöpfe „verschieben“ und „löschen“ (`dokument_entfernen`: bei mehreren Vorgängen nur die Verknüpfung lösen, sonst
  Papierkorb); „Vorgang ändern“ bietet „+ Neuer Vorgang …“; kompakte Werkzeugzeile der Vorschau mit Details per
  Info-Knopf; „Dokument importieren“ nur in Posteingang und Archiv. Im Archiv wird direkt abgelegt; nach der
  Texterkennung werden Titel, Datum und Absender ergänzt (`ablage_nachtragen`). „Bisherige Ansicht“ entfällt im Menü
  (ChatGPT-Export-Import über Chat-Notizen).
- Fehlerbehebung 0.8.2 (Schemaversion 9): „Zuordnen“ scheiterte mit „Speichern fehlgeschlagen“, wenn dieselbe Datei
  schon einmal im Vorgang lag und im Papierkorb war. Ursache war die alte Regel UNIQUE(vorgang_id, sha256) in
  `dokument`; `migrate_9` baut die Tabelle ohne sie neu (Zugehörigkeit regelt `dokument_vorgang`). Der Scan-Ordner
  liegt jetzt unter `~/DocuManager Scans` (nicht in „Dokumente“, das macOS für Programme gesondert schützt).
  Fehlermeldungen beim Speichern nennen die Ursache.
- 0.16.1 (Schemaversion 14): Direkt in einem Vorgang abgelegte Dokumente („+ Dokument“, Ziehen auf die Akte) bekommen
  sofort einen Chronik-Eintrag „Eingang“ (`direkt_eintrag`, Kennzeichen `quelle = DIREKT_ABGELEGT`); nach der
  Texterkennung werden Titel, Datum und bekannter Absender nachgetragen (`direkt_nachtragen`), solange der Eintrag nicht
  von Hand bearbeitet wurde. `migrate_14` legt die fehlenden Einträge für bereits abgelegte Dokumente an.
- 0.17.0: **Claude-Analyse** (`claude_ki.py`). Schaltfläche „Claude“ in der Dokumentvorschau und im Chronik-Kopf öffnet
  einen Dialog mit Zusammenfassen, Fristen & Pflichten, Prüfen & Einschätzen, Antwort entwerfen und freien Fragen
  (Folgefragen behalten den Verlauf). Grundlage: Text des gewählten Dokuments, gekürzte Texte der übrigen Dokumente,
  Chronik, Beteiligte, Referenzen, offene Fristen und Eigene Angaben. Der Antwortentwurf kommt als strukturierte
  Antwort (Betreff, Brieftext, Hinweise) und lässt sich mit „Als Brief übernehmen“ in den Briefdialog übernehmen;
  jede Antwort kann als Notiz in die Chronik. Der Briefdialog bietet „Nach dem Speichern drucken“ (Druckdialog öffnet
  sich selbst, `?drucken=1`) und „Als versendet in der Chronik erfassen“ (Versandart, Datum → Eintrag „Versendet“,
  Status „Schreiben abgeschickt“). Zugangsschlüssel unter Einstellungen → Claude, gespeichert in
  `Daten/claude_schluessel` (nur für den Benutzer lesbar, nicht in der Datensicherung). Netzaufrufe nur auf Anfrage.
- 0.17.1: Claude bekommt bei jeder Anfrage die **ganze Akte** in zeitlicher Reihenfolge: jeder Chronik-Eintrag mit
  Volltext des Dokuments, eigene versendete Briefe (mit Versandart, Datum, Empfänger) und Entwürfe im Wortlaut, Notizen,
  Telefonate, Chat-Notizen, Teilvorgänge; dazu Dokumente ohne Eintrag. Eigene Schreiben gelten als verbindlich, der
  Antwortentwurf muss sich auf den bisherigen Schriftverkehr beziehen. Erst über 600 000 Zeichen wird gekürzt, und nur
  ältere fremde Dokumente (auf 3 000 Zeichen); das gewählte Schreiben und eigene Schreiben bleiben vollständig. Unter
  jeder Antwort steht, was berücksichtigt wurde, und ob etwas gekürzt war oder ohne erkannten Text fehlte.
- 0.17.2: Druckfertiger Brief nach DIN 5008 Form B (`BRIEF_MASSE` in export.py): Absender oben rechts, Rücksendezeile
  bei 49 mm, Empfängeranschrift ab 55 mm (im Sichtfenster DIN lang/C5/C4, 45–90 mm), Informationsblock rechts,
  Betreff bei 100 mm, Falzmarken bei 105/210 mm und Lochmarke bei 148,5 mm, Raum für die Unterschrift; Folgeseiten mit
  oberem Rand. Claude liefert den Brieftext ohne Markdown, von der Anrede bis zum Namen; Reste werden entfernt.
- 0.17.3: Claude direkt im Briefdialog: „Antwort entwerfen“ (bzw. „Schreiben entwerfen“ ohne Bezugsschreiben) und
  „Text überarbeiten“, jeweils mit optionaler Vorgabe; Grundlage ist die ganze Akte, der Empfänger aus dem Dialog und
  beim Überarbeiten der eigene Entwurf. Aufgaben `schreiben` und `ueberarbeiten` mit strukturierter Antwort.
- 0.18.0: Zweistufiger Ablauf im Briefdialog. **1 · Analysieren & bewerten** (Aufgabe `bewerten`, `BEWERTUNG_SCHEMA`):
  Zusammenfassung, rechtliche Bewertung mit Normen, Fristen, Risiken, fehlende Angaben und 2–4 Handlungsoptionen mit
  Vor- und Nachteilen, eine davon empfohlen; als Notiz in die Chronik übernehmbar. **2 · Antwort entwerfen** ist erst
  danach frei und setzt die gewählte Option (oder eine eigene Linie aus der Vorgabe) auf Grundlage dieser Bewertung um.
  Briefdialog neu aufgeteilt: fast bildschirmfüllend, links kompakte Felder (Vorlage/Datum, Zeichen/Betreff in einer
  Zeile), rechts große Vorschau in echter A4-Aufteilung (Anschrift bei 55 mm, Betreff bei 100 mm, Falzmarken,
  Seitenende), vergrößer- und verkleinerbar.
- 0.18.1: Kosten gesenkt. Zwischenspeicher-Merker am Ende der Akte statt am Ende der Anfrage: Folgeanfragen zum selben
  Vorgang binnen 5 Minuten lesen die Akte zu einem Zwanzigstel des Preises (vorher wurde bei jeder Anfrage nur neu
  geschrieben). Denktiefe je Aufgabe (`AUFWAND`): Zusammenfassen und Fristen niedrig, alles andere mittel. Einstellung
  „Qualität und Kosten“ (Gründlich = Standard, Ausgewogen, Sparsam; `STUFEN`). Unter jeder Antwort stehen die Kosten der
  Anfrage und ob die Akte aus dem Zwischenspeicher kam.
- 0.19.0: **Gesetzestexte** (`gesetze.py`). Zitierte Vorschriften aus Bundesgesetzen (BGB, ZPO, GG, VwVfG, AO, VVG,
  SGB I–XII u. a., Liste `GESETZE`) werden in Bewertungen und Antworten anklickbar; ein Seitenfenster zeigt den
  amtlichen Wortlaut von gesetze-im-internet.de, der zitierte Absatz ist hervorgehoben. Abgerufene Vorschriften liegen
  in `Daten/Gesetze/` und werden nach 30 Tagen erneuert; ohne Netz gilt der gespeicherte Stand. **Zitate prüfen**
  schickt nur den Text und den Wortlaut der zitierten Vorschriften (nicht die Akte) an Claude und meldet je Vorschrift
  passt / teilweise / passt nicht / unklar mit Begründung (ca. 1 Cent). Rechtsprechung und Landesrecht sind nicht enthalten.
- 0.19.1 (Schemaversion 15): Jede Antwort von Claude (Analysen, Bewertungen, Entwürfe, Fragen, Zitatprüfungen) wird in
  der Tabelle `ki_ergebnis` gespeichert (`migrate_15`) und ist damit Teil der Datenbank, der Datensicherung und bleibt bei
  Updates erhalten. Der Claude-Dialog zeigt den gespeicherten Verlauf mit Datum, Folgefragen knüpfen daran an; der
  Briefdialog lädt die letzte Bewertung und bietet frühere Entwürfe zur Übernahme an. Briefschrift 10,5 pt (Druck und
  Vorschau).
- 0.16: Scannen ohne Dialog. „Scannen“ scannt sofort mit dem zuletzt benutzten Scanner (`Daten/scanner.json`):
  Einzug wenn vorhanden, sonst Glas; beidseitig, wenn möglich; 300 dpi Farbe. Die Seiten werden mit PDFKit zu einem
  komprimierten PDF zusammengefügt (leere Rückseiten fallen weg) und landen im Posteingang bzw. Archiv. Nur ein kleines
  Fortschrittsfenster; bei Problemen öffnet sich der Dialog. „Scannen mit Einstellungen …“ öffnet den Dialog, der jetzt
  ebenfalls automatisch übernimmt. Lässt sich der neue Helfer nicht bauen, wird `scanner_alt.m` verwendet.
- 0.15.3: Scannen repariert. Der Scan-Dialog schrieb in einen versteckten Programmordner mit Rechten 0700; der
  Scan-Dienst von macOS meldete „The selected folder is not writable“. Zwischenablage jetzt `~/Pictures/DocuManager
  Scans/Scan-…` (0755), danach Übernahme und Aufräumen wie bisher. „Digitale Bilder öffnen“ gibt den Scanner frei und
  schließt das Scanfenster (sonst „wird von einem anderen Programm verwendet“); DocuManager zeigt die Anleitung.
- 0.15.2: Posteingang-Kacheln zeigen das Dokumentdatum (aus dem Text, sonst Erstellungsdatum der Datei; Quelle als
  Hinweis beim Darüberfahren). Nur ohne beides erscheint „importiert …“.
- 0.15.1: Posteingang-Details mit Auswahl **Empfänger** in der Zeile von Dokumentdatum und Absender (zulässige
  Empfänger, erkannter Empfänger, „+ Neuer Empfänger …“ ergänzt die Liste). Beim Zuordnen wird die Wahl gespeichert;
  eine Änderung gegenüber der Erkennung gilt als von Hand gesetzt.
- 0.15: Dokumente kombinieren. Dritter Knopf auf den Posteingang-Kacheln startet die Auswahl; Dokumente in der
  gewünschten Reihenfolge anklicken (nummeriert), „Zu einem PDF kombinieren“. Das PDF entsteht im Browser mit
  pdf-lib (lokal unter `pdflib/`, MIT): PDF-Seiten werden übernommen, Bilder auf A4 eingepasst, Drehungen
  berücksichtigt. Das neue Dokument läuft durch die Texterkennung, die Teile kommen in den Papierkorb; „Rückgängig“
  in der Meldung stellt sie wieder her. Nur PDFs und Bilder lassen sich kombinieren.
- 0.14.1: Posteingang-Kacheln mit zwei kleinen Knöpfen im Vorschaubild: Lupe (bildschirmfüllende Seitenansicht) und
  Papierkorb (ohne Rückfrage, Meldung mit „Rückgängig“). Die Kachel ist dafür kein `<button>` mehr, sondern ein
  per Maus und Tastatur bedienbares Element mit `role="button"`.
- 0.14: ChatGPT-Lesezeichen „→ DocuManager“ (`chatgpt_lesezeichen.js`, eingerichtet unter Einstellungen). Es läuft in
  der angemeldeten ChatGPT-Seite (Safari oder Chrome, nicht in der ChatGPT-App), liest den geöffneten Chat und dessen
  hochgeladene Dateien über die Schnittstelle der Seite und übergibt alles per postMessage an das DocuManager-Fenster
  `#chatempfang`. Dort Vorgang (oder Posteingang) wählen, Dateien anhaken, optional Chatverlauf als Chat-Notiz.
  Bilder in WebP/GIF/HEIC werden als PNG übernommen. Ist die direkte Übergabe nicht möglich, speichert das Lesezeichen
  `…documanager.json` in Downloads; die Datei lässt sich in DocuManager ziehen oder über Chat-Notizen einlesen.
  Hinweis: Die ChatGPT-Schnittstelle ist nicht öffentlich dokumentiert und kann sich ändern.
- 0.13: Filter in Vorgänge, Archiv, Chronik und Fristen wahlweise als Schaltflächen untereinander oder als
  Ausklappmenüs in einer Zeile (`filterBlock()`); umgeschaltet über das kleine Symbol am Ende der Filter, gespeichert
  in der Datenbank (`einstellung` „oberflaeche“, GET/POST `/api/oberflaeche`) und damit dauerhaft.
- 0.12.1: Fehler behoben – im Archiv (ebenso Fristen-Filter, Posteingang-Details, Adressbuch-Suche) zeichneten
  Filterklicks nur den Ansichtsinhalt neu und verloren dabei Suche und Import aus der Kopfzeile; jeder weitere Klick
  brach danach ab. Alle Teil-Neuzeichnungen laufen jetzt über `zeichne()`, das die Kopfzeilenwerkzeuge erhält.
- 0.12 (Schemaversion 13): Priorität je Vorgang (keine, hoch, sehr hoch; `vorgang.prioritaet`), nur in der
  Vorgangsliste als Spalte, sortier- und gruppierbar, gesetzt im Dialog „Vorgang bearbeiten“. Vorgangsliste
  gruppierbar nach Bereich, Status, Priorität und Empfänger (Empfänger der Dokumente des Vorgangs). Suche als Symbol
  in der Kopfzeile jeder Ansicht neben deren Knöpfen; ein Klick öffnet das Eingabefeld. Die eigene Kopfleiste
  entfällt.
- 0.11 (Schemaversion 12): Archiv mit vollem Import-Menü (Datei, Scan, Apple Mail landen direkt im Archiv;
  Scan-Ordner weiter über den Posteingang). Ankreuzfeld „nur erledigte Vorgänge“ entfernt. „Einem Vorgang
  zuordnen …“ im Archiv-Dialog holt Dokumente in laufende Vorgänge zurück. Empfänger je Dokument
  (`empfaenger_erkennen`: zulässige Empfänger aus den Einstellungen, sonst Anschriftenfeld über „PLZ Ort“, bei
  E-Mails „An:“; von Hand änderbar, `dokument.empfaenger_quelle='manuell'` bleibt erhalten); Gruppieren nach
  Empfänger. Dialoge mit eigener Hintergrundfarbe (`--dialog`), größere Zeilenknöpfe im Archiv.
- 0.10 (Schemaversion 11):
  - Dateitypen Word (.docx, Text direkt aus der Datei, Ansicht als HTML über macOS-textutil oder eigenen Umsetzer)
    und E-Mail (.eml, über den Mail-Import mit Anlagen); Dateityp-Symbole (PDF, BILD, MAIL, WORD) in Vorgangsliste,
    Chronik, Dokumenten-Reiter und Archiv.
  - Dokumentdatum: Steht im Text kein Datum, wird das Erstellungsdatum der Datei vorgeschlagen (PDF-Metadaten, EXIF,
    Word-Eigenschaften, sonst Änderungsdatum laut Browser; `dokument.datei_datum`).
  - Seitenansicht mit pdf.js (lokal unter `pdfjs/`, Apache-2.0): eine A4-Seite füllt die Fensterhöhe, ab zwei Seiten
    zwei nebeneinander.
  - Adressbuch: Kontakte umbenennen (`kontakt_aendern`). Posteingang: „+ Neuer Kontakt …“ beim Absender.
  - Chat-Notizen: ChatGPT-Export (.zip/.json) direkt importieren, Unterhaltungen auswählen.
  - Archiv: Filter in zwei Zeilen (Gruppieren + Bereich; Typ + Jahr + Suche). Einstellungen: Bereiche sortieren
    (`bereich.reihenfolge`), eigene Eintragsarten verwalten (`eintrag.typ`, Grundart „notiz“).
  - Chronik: Einträge bearbeiten mit Art, Beteiligtem und Dokument (zuweisen oder hochladen); ein fehlendes
    Original wird beim Zuweisen zum Eingang.
- 0.9 (Schemaversion 10): Mehrere Bereiche je Vorgang (`vorgang_bereich`, erster = Hauptbereich in `vorgang.bereich`)
  und je Dokument (`dokument_bereich`, leer = Bereiche des Vorgangs); weitere Kontakte je Dokument
  (`dokument_kontakt`); Beteiligte im Dialog „Vorgang bearbeiten“ setzen, auch direkt aus der Vorgangsliste.
  Archiv: Filter und Gruppierung nach Typ (Eingang, Versendet, Entwurf, Versandnachweis), Dokumente mit mehreren
  Bereichen erscheinen in jeder Bereichsgruppe. Vorschau: Drehen um je 90° (`dokument_drehen`, gespeichert in
  `dokument.drehung_manuell`, gilt auch für Betrachter und Vorschaubild; Original unverändert). Datumsfelder mit
  „Heute“ einheitlich in einer Zeile.
- 0.8.3: Archiv – Klick auf eine Zeile öffnet „Dokument bearbeiten“ (Titel, Dateiname, Dokumentdatum, Absender;
  `dokument_aendern`, Original bleibt unverändert), das Dateisymbol vor dem Namen öffnet das Dokument im Betrachter.
  Akte – „Referenz“ steht neben „Eintrag“ im Kopf der Chronik, der Filter „Fehlende Originale“ entfällt.
  Brief – Auswahl „Kontakt“ (Beteiligte zuerst, dann Adressbuch); die Anschrift wird aus dem Kontakt übernommen
  (Name, z. Hd. Ansprechpartner, aktuelle Anschrift), Anrede und Zeichen passen sich an.
- Fristen werden nur noch bei der Formulierung „bis zum <Datum>“ (auch „bis spätestens zum“) vorgeschlagen.
- Datensicherung: immer nur eine Sicherungsdatei; Wiederherstellen in den Einstellungen (Datei laden oder aus der
  Liste) bei laufender Anwendung über die SQLite-Sicherungsschnittstelle (`wiederherstellen_laufend`), die bisherige
  Datenbank bleibt als Kopie erhalten.
- Programm ohne Terminal: `DocuManager_Installieren.command` installiert nach `~/DocuManager` und erzeugt
  `DocuManager.app` (Startskript, Symbol aus `icon.svg`); „Beenden“ in der Seitenleiste (`POST /api/beenden`).
- Kacheln im Posteingang zeigen ein echtes Vorschaubild der ersten Seite, aufrecht gedreht (auf dem Mac mit `sips`,
  zwischengespeichert in `Daten/Vorschau/`).
- Aktenexport als ZIP mit Chronik.pdf, akte.json und ausgewählten Originalen.
- Datensicherung unter Einstellungen: erstellen, prüfen, herunterladen; Wiederherstellen im Terminal mit
  `python3 app.py --wiederherstellen <Datei.zip>`.
- Apple Mail: Zeitpunkt und Ergebnis des letzten Abrufs werden gespeichert und angezeigt. Neben der
  Message-ID verhindert ein Fingerabdruck der E-Mail, dass dieselbe E-Mail aus einem zweiten Postfach erneut
  übernommen wird. Ein reiner Zeitfilter wäre unsicher: Eine ältere E-Mail, die erst später markiert wird, ginge verloren.
- Automatische Drehung (Schemaversion 7, 8): Apple Vision liest auch Text, der auf dem Kopf steht. Die Lage
  ergibt sich deshalb aus der Leserichtung der Zeilen im Bild (vom ersten zum letzten Zeichen); bei unklarer
  Richtung werden die Lagen verglichen. Eine gedrehte Seite wird aufrecht erneut gelesen, damit Zeilenfolge und
  Titel stimmen. Unter `Daten/Ansicht/` entsteht eine aufrechte Ansichtsfassung (einseitige Bilder als JPEG, sonst
  PDF). Das Original bleibt unverändert und ist über „Original ungedreht“ erreichbar. Schemaversion 8 lässt
  vorhandene Scans einmalig im Hintergrund neu prüfen; scheitert das, bleibt der bisherige Text erhalten.

Die Trennung zwischen „Vorgänge“ (echte Daten) und „Beispiele“ (Demo) entfällt. Die Ansichten aus dem
Prototyp arbeiten mit echten Daten: Übersicht, Posteingang, Vorgangsakte mit Chronik und Vorschau,
Fristen, Adressbuch, Chat-Notizen, Papierkorb, Einstellungen.

## Etappe 4 · Restfunktionen aus dem Konzept

- Datensicherung zeitgesteuert und auf externes Ziel (NAS, Datenträger)
- E-Mail-Import per .eml-Datei (zusätzlich zu Apple Mail)
- Kalender-Abo (iCal) für Fristen bei geschlossener Anwendung

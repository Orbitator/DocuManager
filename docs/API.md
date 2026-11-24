# Schnittstellen der Vorgangsakte (Etappe 2)

Basis: `http://127.0.0.1:8765`. Schreibzugriffe (POST) brauchen den Header `X-Korrespondenz: lokal`
und einen JSON-Körper. Fehler kommen als `{"error": "…"}` mit Status 400 (Eingabe) oder 404 (nicht gefunden).
Die bisherigen Schnittstellen (`/api/cases`, Dokumente, Scan, Chat) bleiben unverändert.

## Lesen

| Pfad | Inhalt |
|---|---|
| GET `/api/akte/{id}` | Vollständige Akte: Vorgang, Teilvorgänge, Schlagwörter, Beteiligte, Referenzen, Dokumente, Chronik (mit Teilvorgängen, Versand, „nacherfasst“), Fristen mit Verlauf |
| GET `/api/akte/{id}/offen?teil={teilvorgang}` | Was vor dem Abschluss offen ist: Fristen, nicht versendete Entwürfe, fehlende Originale, ungeprüfte Chat-Notizen |
| POST `/api/akte/{id}` | Vorgang ändern: `titel`, `prioritaet` (keine, hoch, sehr hoch), `bereich` oder `bereiche` (Liste, erster = Hauptbereich), `kontakte` (Beteiligte), `status`, `zustaendig`, `naechster_schritt`, `beschreibung` |
| GET `/api/bereiche` | Bereiche mit Anzahl der Vorgänge |
| GET `/api/kontakte` | Kontakte mit Abteilungen, Anschriften (aktuelle zuerst, mit Gültigkeit und Verwendung) und Vorgängen |
| GET `/api/kontakte/dubletten?name=…` | Mögliche Dubletten vor dem Anlegen |
| GET `/api/suche?q=…` | Volltextsuche über Dokumentseiten, Chronik, Referenzen und Titel, mit Textausschnitt und Seite |
| GET `/api/papierkorb` | Gelöschte Vorgänge, Dokumente, Einträge, Fristen und Kontakte |
| GET `/api/posteingang` | Noch nicht zugeordnete Dokumente mit Seiten und Vorschlägen (Datum, Absender, Referenz, Vorgänge) |
| GET `/api/archiv` | Archivierte Dokumente: nur aus Vorgängen auf „Erledigt“ oder deren Teilvorgänge alle erledigt sind; mit Vorgang, Bereich, Absender, Datum und Größe |
| GET `/api/fristen` | Alle Fristen, Wiedervorlagen und Aufgaben |
| GET `/api/einstellungen` | Eigene Angaben für die Absendererkennung |
| GET `/api/mail` | Markierungsfarbe, Anzahl übernommener E-Mails, `letzter_abruf` (`zeit`, `neu`, `bereits_vorhanden`) |
| GET `/api/documents/{id}/original` | Original zur Anzeige; lag eine Seite gedreht, die aufrecht gedrehte Ansichtsfassung. `?fassung=original` liefert immer die unveränderte Datei |
| GET `/api/documents/{id}/vorschaubild` | JPEG der ersten Seite, aufrecht gedreht (404, wenn keins erzeugt werden kann) |
| GET `/api/scanordner` | Pfad des überwachten Scan-Ordners und letzte Übernahme; POST `/api/scanordner/oeffnen` öffnet ihn im Finder |
| GET `/api/documents/{id}/pages` | Erkannter Text je Seite mit `methode` und `drehung` (0, 90, 180, 270) |
| GET `/api/eintraege/{id}/brief` | Brief eines Entwurfs als druckfertige Seite nach DIN 5008; `?drucken=1` öffnet den Druckdialog |
| GET `/api/akte/{id}/export?docs=alle\|1,2` | Akte als ZIP: Chronik.pdf, akte.json, ausgewählte Originale |
| GET `/api/chatnotizen` | Alle Chat-Notizen mit Vorgang, Quelle und Prüfstatus |
| GET `/api/sicherungen` | Vorhandene Datensicherungen; `/api/sicherungen/{name}` lädt eine herunter |

## Ändern

| Pfad | Körper |
|---|---|
| POST `/api/akte/{id}` | beliebige von `titel`, `beschreibung`, `bereich`, `status`, `zustaendig`, `naechster_schritt` |
| POST `/api/akte/{id}/schlagwoerter` | `{"namen": ["Auto", "2026"]}` (ersetzt die Liste) |
| POST `/api/akte/{id}/teilvorgaenge` | `name`, optional `status`, `zustaendig`, `naechster_schritt` |
| POST `/api/teilvorgaenge/{id}` | Felder wie beim Anlegen |
| POST `/api/teilvorgaenge/{id}/entfernen` | – (nur ohne eigene Einträge und Fristen) |
| POST `/api/akte/{id}/beteiligte` | `kontakt_id`, `rolle` |
| POST `/api/akte/{id}/beteiligte/{kontakt}/entfernen` | – |
| POST `/api/akte/{id}/referenzen` | `bezeichnung`, `wert`, optional `kontakt_id` |
| POST `/api/referenzen/{id}/entfernen` | – |
| POST `/api/akte/{id}/eintraege` | `art` (eingang, ausgang, entwurf, nachweis, telefonat, notiz, entscheidung, chat, fehlt), `titel`, `datum`, optional `teile`, `richtung` (von, an, mit), `kontakt_id`, `dokument_id`, `bezug_id`, `text`, `quelle`, `geprueft` |
| POST `/api/eintraege/{id}` | `titel`, `datum`, `text`, `kontakt_id`, `geprueft`, `teile`, `auch_in_vorgang` |
| GET `/api/claude` | Ob Claude eingerichtet ist (`eingerichtet`, `endung` des Schlüssels) |
| POST `/api/gesetze` | `text` → `vorschriften` [{`gesetz`, `norm`, `absatz`, `titel`, `absaetze`, `url`, `fehler`}] |
| POST `/api/claude/zitate` | `text` → `pruefungen` [{`vorschrift`, `ergebnis`, `begruendung`}], `vorschriften`, `kosten_usd` |
| POST `/api/claude/verlauf` | `vorgang_id`, optional `dokument_id`, `aufgabe` → `ergebnisse` (neueste zuerst; `frage`, `antwort`, `daten`, `kontext`, `zitate`, `erstellt_am`) |
| POST `/api/claude/ergebnisse/{id}/loeschen` | gespeichertes Ergebnis entfernen |
| POST `/api/claude/stufe` | `stufe` (gruendlich, ausgewogen, sparsam) |
| POST `/api/claude/schluessel` | `schluessel` (leer = entfernen); Ablage in `Daten/claude_schluessel` |
| POST `/api/claude/fragen` | `vorgang_id`, `dokument_id` (optional), `verlauf` [{`rolle`: user/assistant, `text`}], `aufgabe` (frage, zusammenfassen, fristen, pruefen, bewerten, antwort, schreiben, ueberarbeiten), optional `anweisung`, `entwurf`, `empfaenger`, `bewertung` (Text), `option`; bei `bewerten` zusätzlich `bewertung` (zusammenfassung, rechtliche_bewertung, fristen, risiken, fehlende_angaben, optionen) → `text`, `kontext` (`eintraege`, `eigene_schreiben`, `dokumente`, `ohne_text`, `gekuerzt`); bei `antwort` zusätzlich `betreff`, `brieftext`, `hinweise` |
| POST `/api/eintraege/{id}/versand` | `art` (Post, Einschreiben, E-Mail, Fax, Persönlich, Online-Portal), `datum`, `sendungsnummer`, `anschrift_id` oder `empfaenger`, `nachweis_dokument_id` |
| POST `/api/akte/{id}/fristen` | `art` (frist, wiedervorlage, aufgabe), `titel`, `faellig_am`, optional `teilvorgang_id`, `zustaendig`, `quelle_dokument_id`, `quelle_seite`, `quelle_zitat`. Eine verbindliche Frist braucht eine Fundstelle oder ein Zitat. |
| POST `/api/fristen/{id}` | `faellig_am` (mit `grund`, wird im Verlauf festgehalten), `zustaendig`, `titel`, `erledigt` |
| POST `/api/bereiche` | `name` |
| POST `/api/bereiche/umbenennen` | `alt`, `neu` (Vorgänge werden mitgeändert) |
| POST `/api/bereiche/entfernen` | `name` (nur ohne Vorgänge) |
| POST `/api/kontakte` | `name`, `kurzname`, `typ`, `notiz`, `abteilungen: [{name, ansprechpartner, email, telefon, anschrift, gueltig_von}]` |
| POST `/api/kontakte/{id}/abteilungen` | wie eine Abteilung oben |
| POST `/api/abteilungen/{id}/anschrift` | `zeilen`, `gueltig_von`. Die bisherige Anschrift endet am Vortag und bleibt für frühere Schreiben erhalten. |
| POST `/api/documents/{id}/verknuepfen` | `vorgang_id` |
| POST `/api/posteingang/dokumente` | Rohe Datei, Header `X-Dateiname`; landet im Posteingang |
| POST `/api/posteingang/scan` | Öffnet den Scan-Dialog; Scans landen im Posteingang |
| POST `/api/posteingang/{id}/zuordnen` | `vorgang_id` oder `ablage: true` (ohne Vorgang ins Archiv), optional `empfaenger`, `teile`, `titel`, `datum`, `kontakt_id` oder `neuer_absender` (`name`, `anschrift`), `fristen: [{titel, faellig_am, seite, zitat, art}]` |
| POST `/api/dokumente/{id}/verschieben` | `von_vorgang_id` und `vorgang_id` oder `ablage: true`; verschiebt Dokument, Chronik-Eintrag und Mail-Anlagen |
| GET `/api/dokumente/{id}/fristen` | Im Text erkannte Fristen mit Datum, Titel, Seite und Zitat |
| POST `/api/einstellungen` | `eigene_angaben` (eine Angabe pro Zeile) |
| POST `/api/mail/abholen` | Holt bis zu 25 neue markierte E-Mails aus Apple Mail; `weitere` zeigt, ob noch mehr vorliegen. Bereits übernommene werden über Message-ID und Fingerabdruck der E-Mail erkannt und nicht erneut angelegt; Zeitpunkt und Ergebnis des Abrufs werden gespeichert |
| POST `/api/akte/{id}/chatnotiz` | `titel`, `text`, `quelle`, `datum`; antwortet mit `fehlend` (im Text erwähnte Schreiben ohne Original) |
| POST `/api/sicherungen` | Erstellt eine Sicherung und prüft sie sofort |
| POST `/api/sicherungen/wiederherstellen` | Körper: Sicherungsdatei (.zip); prüft und stellt bei laufender Anwendung wieder her |
| POST `/api/sicherungen/{name}/wiederherstellen` | Stellt eine vorhandene Sicherung wieder her |
| POST `/api/archiv/dokumente` | Körper: Datei, Kopf `X-Dateiname`; legt direkt im Archiv ab, Texterkennung wie im Posteingang |
| POST `/api/dokumente/{id}/entfernen` | `vorgang_id`; löst die Verknüpfung oder legt das Dokument in den Papierkorb |
| POST `/api/dokumente/{id}/aendern` | `titel`, `dateiname`, `datum`, `kontakt_id`, `bereiche` (Liste, leer = vom Vorgang), `kontakte` (weitere) – jeweils optional |
| POST `/api/dokumente/{id}/drehen` | `grad` 90, −90 oder 180; Anzeige drehen, Original bleibt unverändert |
| POST `/api/kontakte/{id}` | `name`, `kurzname`, `typ`, `notiz` |
| POST `/api/bereiche/reihenfolge` | `namen`: alle Bereiche in neuer Reihenfolge |
| GET/POST `/api/eintragsarten` | eigene Eintragsarten lesen / `name` anlegen; POST `/api/eintragsarten/entfernen` |
| POST `/api/eintraege/{id}` | zusätzlich `art`, `typ`, `dokument_id`, `kontakt_id` |
| GET `/api/documents/{id}/html` | Word-Dokument als lesbare HTML-Seite |
| POST `/api/chat/preview`, `/api/chat/import` | ChatGPT-Export lesen (Körper: Datei) und ausgewählte Unterhaltungen übernehmen |
| GET/POST `/api/empfaenger` | zulässige Empfänger lesen / `empfaenger` (Liste) setzen; ordnet nicht von Hand gesetzte Empfänger neu zu |
| POST `/api/archiv/scan` | Scan-Dialog; Scans landen direkt im Archiv |
| POST `/api/mail/abholen` mit `{"ziel": "archiv"}` | E-Mails samt Anlagen direkt im Archiv ablegen |
| GET/POST `/api/oberflaeche` | Oberflächen-Einstellungen, z. B. `filteransicht`: chips oder menue |
| POST `/api/beenden` | Beendet die Anwendung |
| POST `/api/sicherungen/{name}/pruefen` | Prüft Vollständigkeit, Prüfsummen und Datenbank, ohne etwas zu ändern |
| POST `/api/mail/markierung` | `markierung` 0–6 (Rot, Orange, Gelb, Grün, Blau, Violett, Grau) |
| POST `/api/{typ}/{id}/loeschen` | Papierkorb; `typ` = vorgang, dokument, eintrag, frist, kontakt |
| POST `/api/{typ}/{id}/wiederherstellen` | aus dem Papierkorb zurück |
| POST `/api/{eintrag,frist}/{id}/endgueltig` | endgültig entfernen (nur aus dem Papierkorb) |

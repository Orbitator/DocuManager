# Schnittstellen der Vorgangsakte (Etappe 2)

Basis: `http://127.0.0.1:8765`. Schreibzugriffe (POST) brauchen den Header `X-Korrespondenz: lokal`
und einen JSON-Körper. Fehler kommen als `{"error": "…"}` mit Status 400 (Eingabe) oder 404 (nicht gefunden).
Die bisherigen Schnittstellen (`/api/cases`, Dokumente, Scan, Chat) bleiben unverändert.

## Lesen

| Pfad | Inhalt |
|---|---|
| GET `/api/akte/{id}` | Vollständige Akte: Vorgang, Teilvorgänge, Schlagwörter, Beteiligte, Referenzen, Dokumente, Chronik (mit Teilvorgängen, Versand, „nacherfasst“), Fristen mit Verlauf |
| GET `/api/akte/{id}/offen?teil={teilvorgang}` | Was vor dem Abschluss offen ist: Fristen, nicht versendete Entwürfe, fehlende Originale, ungeprüfte Chat-Notizen |
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
| GET `/api/documents/{id}/pages` | Erkannter Text je Seite mit `methode` und `drehung` (0, 90, 180, 270) |
| GET `/api/eintraege/{id}/brief` | Brief eines Entwurfs als druckfertige Seite nach DIN 5008 |
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
| POST `/api/posteingang/{id}/zuordnen` | `vorgang_id`, optional `teile`, `titel`, `datum`, `kontakt_id` oder `neuer_absender` (`name`, `anschrift`) |
| POST `/api/einstellungen` | `eigene_angaben` (eine Angabe pro Zeile) |
| POST `/api/mail/abholen` | Holt bis zu 25 neue markierte E-Mails aus Apple Mail; `weitere` zeigt, ob noch mehr vorliegen. Bereits übernommene werden über Message-ID und Fingerabdruck der E-Mail erkannt und nicht erneut angelegt; Zeitpunkt und Ergebnis des Abrufs werden gespeichert |
| POST `/api/akte/{id}/chatnotiz` | `titel`, `text`, `quelle`, `datum`; antwortet mit `fehlend` (im Text erwähnte Schreiben ohne Original) |
| POST `/api/sicherungen` | Erstellt eine Sicherung und prüft sie sofort |
| POST `/api/sicherungen/{name}/pruefen` | Prüft Vollständigkeit, Prüfsummen und Datenbank, ohne etwas zu ändern |
| POST `/api/mail/markierung` | `markierung` 0–6 (Rot, Orange, Gelb, Grün, Blau, Violett, Grau) |
| POST `/api/{typ}/{id}/loeschen` | Papierkorb; `typ` = vorgang, dokument, eintrag, frist, kontakt |
| POST `/api/{typ}/{id}/wiederherstellen` | aus dem Papierkorb zurück |
| POST `/api/{eintrag,frist}/{id}/endgueltig` | endgültig entfernen (nur aus dem Papierkorb) |

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
| POST `/api/{typ}/{id}/loeschen` | Papierkorb; `typ` = vorgang, dokument, eintrag, frist, kontakt |
| POST `/api/{typ}/{id}/wiederherstellen` | aus dem Papierkorb zurück |
| POST `/api/{eintrag,frist}/{id}/endgueltig` | endgültig entfernen (nur aus dem Papierkorb) |

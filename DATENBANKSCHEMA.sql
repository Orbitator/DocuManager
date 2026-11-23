-- SQLite-Schema der Korrespondenzverwaltung, Schemaversion 2 (PRAGMA user_version).
-- Erzeugt aus einer frischen Installation. Ausschließlich Struktur, keine Daten.
-- Maßgeblich sind die Migrationen in Korrespondenz_Lokal/app.py (MIGRATIONS) und ChatSync.__init__.
-- Fremdschlüssel müssen pro Verbindung aktiviert werden.
PRAGMA foreign_keys = ON;

CREATE TABLE vorgang(
            id INTEGER PRIMARY KEY, titel TEXT NOT NULL, bereich TEXT NOT NULL,
            beschreibung TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Schreiben verfassen',
            naechste_frist TEXT,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE dokument(
            id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
            dateiname TEXT NOT NULL, titel TEXT NOT NULL, titel_seite INTEGER,
            titel_quelle TEXT NOT NULL, mime TEXT NOT NULL, dateipfad TEXT NOT NULL,
            sha256 TEXT NOT NULL, ocr_status TEXT NOT NULL,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ocr_fehler TEXT, ocr_aktualisiert_am TEXT,
            UNIQUE(vorgang_id, sha256)
        );

CREATE TABLE dokumentseite(
            dokument_id INTEGER NOT NULL REFERENCES dokument(id), nummer INTEGER NOT NULL,
            methode TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(dokument_id, nummer)
        );

CREATE TABLE archivdatei(
            id TEXT PRIMARY KEY, datei_id TEXT NOT NULL, dateiname TEXT NOT NULL,
            mime_typ TEXT NOT NULL, groesse_bytes INTEGER NOT NULL CHECK(groesse_bytes >= 0),
            archiviert_am TEXT NOT NULL, lokaler_pfad TEXT, sha256 TEXT
        );

CREATE TABLE chat_thread(
                    id TEXT PRIMARY KEY, titel TEXT NOT NULL, stand REAL, importiert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

CREATE TABLE chat_notiz(
                    thread_id TEXT NOT NULL REFERENCES chat_thread(id), id TEXT NOT NULL,
                    rolle TEXT NOT NULL, text TEXT NOT NULL, datum REAL, alternativ INTEGER NOT NULL,
                    PRIMARY KEY(thread_id,id)
                );

CREATE TABLE chat_anlage(
                    id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL, notiz_id TEXT NOT NULL,
                    schluessel TEXT NOT NULL, datei_id TEXT NOT NULL, name TEXT NOT NULL,
                    archiv_id TEXT, sha256 TEXT,
                    FOREIGN KEY(thread_id,notiz_id) REFERENCES chat_notiz(thread_id,id),
                    UNIQUE(thread_id,notiz_id,schluessel)
                );

CREATE INDEX archiv_typ ON archivdatei(mime_typ);

PRAGMA user_version = 2;

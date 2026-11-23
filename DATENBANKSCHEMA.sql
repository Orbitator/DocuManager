-- SQLite-Schema der Korrespondenzverwaltung, Schemaversion 12 (PRAGMA user_version).
-- Erzeugt aus einer frischen Installation. Ausschließlich Struktur, keine Daten.
-- Maßgeblich sind die Migrationen in app.py (MIGRATIONS), akte.py (migrate_3, migrate_4, migrate_6), mail_import.py
-- (migrate_5) und ChatSync.__init__. Fremdschlüssel müssen pro Verbindung aktiviert werden.
PRAGMA foreign_keys = ON;

CREATE TABLE anschrift(
    id INTEGER PRIMARY KEY, abteilung_id INTEGER NOT NULL REFERENCES kontakt_abteilung(id),
    zeilen TEXT NOT NULL, gueltig_von TEXT NOT NULL, gueltig_bis TEXT
);

CREATE TABLE archivdatei(
            id TEXT PRIMARY KEY, datei_id TEXT NOT NULL, dateiname TEXT NOT NULL,
            mime_typ TEXT NOT NULL, groesse_bytes INTEGER NOT NULL CHECK(groesse_bytes >= 0),
            archiviert_am TEXT NOT NULL, lokaler_pfad TEXT, sha256 TEXT
        );

CREATE TABLE bereich(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
, reihenfolge INTEGER);

CREATE TABLE beteiligter(
    vorgang_id INTEGER NOT NULL REFERENCES vorgang(id), kontakt_id INTEGER NOT NULL REFERENCES kontakt(id),
    rolle TEXT NOT NULL DEFAULT '', PRIMARY KEY(vorgang_id, kontakt_id)
);

CREATE TABLE chat_anlage(
                    id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL, notiz_id TEXT NOT NULL,
                    schluessel TEXT NOT NULL, datei_id TEXT NOT NULL, name TEXT NOT NULL,
                    archiv_id TEXT, sha256 TEXT,
                    FOREIGN KEY(thread_id,notiz_id) REFERENCES chat_notiz(thread_id,id),
                    UNIQUE(thread_id,notiz_id,schluessel)
                );

CREATE TABLE chat_notiz(
                    thread_id TEXT NOT NULL REFERENCES chat_thread(id), id TEXT NOT NULL,
                    rolle TEXT NOT NULL, text TEXT NOT NULL, datum REAL, alternativ INTEGER NOT NULL,
                    PRIMARY KEY(thread_id,id)
                );

CREATE TABLE chat_thread(
                    id TEXT PRIMARY KEY, titel TEXT NOT NULL, stand REAL, importiert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

CREATE TABLE "dokument"(
            id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
            dateiname TEXT NOT NULL, titel TEXT NOT NULL, titel_seite INTEGER,
            titel_quelle TEXT NOT NULL, mime TEXT NOT NULL, dateipfad TEXT NOT NULL,
            sha256 TEXT NOT NULL, ocr_status TEXT NOT NULL,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ocr_fehler TEXT, ocr_aktualisiert_am TEXT, geloescht_am TEXT, dokument_datum TEXT, ansicht TEXT
        , drehung_manuell INTEGER NOT NULL DEFAULT 0, datei_datum TEXT, empfaenger TEXT, empfaenger_quelle TEXT);

CREATE TABLE dokument_bereich(dokument_id INTEGER NOT NULL REFERENCES dokument(id),
            bereich TEXT NOT NULL, PRIMARY KEY(dokument_id, bereich));

CREATE TABLE dokument_kontakt(dokument_id INTEGER NOT NULL REFERENCES dokument(id),
            kontakt_id INTEGER NOT NULL REFERENCES kontakt(id), PRIMARY KEY(dokument_id, kontakt_id));

CREATE TABLE dokument_vorgang(
    dokument_id INTEGER NOT NULL REFERENCES dokument(id), vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    verknuepft_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(dokument_id, vorgang_id)
);

CREATE TABLE dokumentseite(
            dokument_id INTEGER NOT NULL REFERENCES dokument(id), nummer INTEGER NOT NULL,
            methode TEXT NOT NULL, text TEXT NOT NULL, drehung INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(dokument_id, nummer)
        );

CREATE TABLE einstellung(schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);

CREATE TABLE eintrag(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    art TEXT NOT NULL CHECK(art IN ('eingang','ausgang','entwurf','nachweis','telefonat','notiz','entscheidung','chat','fehlt')),
    titel TEXT NOT NULL, ereignis_datum TEXT NOT NULL,
    erfasst_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    richtung TEXT CHECK(richtung IS NULL OR richtung IN ('von','an','mit')),
    kontakt_id INTEGER REFERENCES kontakt(id), dokument_id INTEGER REFERENCES dokument(id),
    bezug_id INTEGER REFERENCES eintrag(id), text TEXT, quelle TEXT,
    geprueft INTEGER NOT NULL DEFAULT 0, versendet_als INTEGER REFERENCES eintrag(id),
    geloescht_am TEXT
, brief TEXT, typ TEXT);

CREATE TABLE eintrag_teil(
    eintrag_id INTEGER NOT NULL REFERENCES eintrag(id), teilvorgang_id INTEGER NOT NULL REFERENCES teilvorgang(id),
    PRIMARY KEY(eintrag_id, teilvorgang_id)
);

CREATE TABLE frist(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    teilvorgang_id INTEGER REFERENCES teilvorgang(id),
    art TEXT NOT NULL CHECK(art IN ('frist','wiedervorlage','aufgabe')),
    titel TEXT NOT NULL, faellig_am TEXT NOT NULL, zustaendig TEXT,
    quelle_dokument_id INTEGER REFERENCES dokument(id), quelle_seite INTEGER, quelle_zitat TEXT,
    erledigt_am TEXT, angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geloescht_am TEXT,
    CHECK(art <> 'frist' OR quelle_dokument_id IS NOT NULL OR quelle_zitat IS NOT NULL)
);

CREATE TABLE frist_verlauf(
    id INTEGER PRIMARY KEY, frist_id INTEGER NOT NULL REFERENCES frist(id),
    faellig_alt TEXT NOT NULL, faellig_neu TEXT NOT NULL, grund TEXT,
    geaendert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kontakt(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, kurzname TEXT, typ TEXT, notiz TEXT,
    angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geloescht_am TEXT
);

CREATE TABLE kontakt_abteilung(
    id INTEGER PRIMARY KEY, kontakt_id INTEGER NOT NULL REFERENCES kontakt(id),
    name TEXT NOT NULL DEFAULT '', ansprechpartner TEXT, email TEXT, telefon TEXT
);

CREATE TABLE mail_anlage(
    message_id TEXT NOT NULL REFERENCES mail_import(message_id), dokument_id INTEGER NOT NULL REFERENCES dokument(id),
    PRIMARY KEY(message_id, dokument_id)
);

CREATE TABLE mail_import(
    message_id TEXT PRIMARY KEY, dokument_id INTEGER NOT NULL REFERENCES dokument(id),
    betreff TEXT, absender TEXT, postfach TEXT, importiert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE referenz(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    bezeichnung TEXT NOT NULL, wert TEXT NOT NULL, kontakt_id INTEGER REFERENCES kontakt(id),
    UNIQUE(vorgang_id, wert)
);

CREATE TABLE schlagwort(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE VIRTUAL TABLE suche USING fts5(
            art UNINDEXED, ref_id UNINDEXED, seite UNINDEXED, text, tokenize='unicode61 remove_diacritics 2');

CREATE TABLE teilvorgang(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Offen', zustaendig TEXT, naechster_schritt TEXT,
    reihenfolge INTEGER NOT NULL DEFAULT 0, angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE versand(
    eintrag_id INTEGER PRIMARY KEY REFERENCES eintrag(id), art TEXT NOT NULL, datum TEXT NOT NULL,
    sendungsnummer TEXT, anschrift_id INTEGER REFERENCES anschrift(id), empfaenger TEXT NOT NULL,
    nachweis_dokument_id INTEGER REFERENCES dokument(id)
);

CREATE TABLE vorgang(
            id INTEGER PRIMARY KEY, titel TEXT NOT NULL, bereich TEXT NOT NULL,
            beschreibung TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Schreiben verfassen',
            naechste_frist TEXT,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        , zustaendig TEXT, naechster_schritt TEXT, geloescht_am TEXT, system TEXT);

CREATE TABLE vorgang_bereich(vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
            bereich TEXT NOT NULL, PRIMARY KEY(vorgang_id, bereich));

CREATE TABLE vorgang_schlagwort(
    vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    schlagwort_id INTEGER NOT NULL REFERENCES schlagwort(id),
    PRIMARY KEY(vorgang_id, schlagwort_id)
);

CREATE INDEX archiv_typ ON archivdatei(mime_typ);

CREATE INDEX dokument_sha256 ON dokument(sha256);

CREATE INDEX dokument_vorgang_vorgang ON dokument_vorgang(vorgang_id);

CREATE INDEX eintrag_vorgang ON eintrag(vorgang_id);

CREATE INDEX frist_faellig ON frist(faellig_am);

CREATE INDEX referenz_wert ON referenz(wert);

CREATE TRIGGER suche_dokument_ai AFTER INSERT ON dokument BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('dokument',NEW.id,NULL,NEW.titel||' '||NEW.dateiname); END;

CREATE TRIGGER suche_dokument_au AFTER UPDATE OF titel ON dokument BEGIN
  DELETE FROM suche WHERE art='dokument' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('dokument',NEW.id,NULL,NEW.titel||' '||NEW.dateiname); END;

CREATE TRIGGER suche_eintrag_ai AFTER INSERT ON eintrag BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('eintrag',NEW.id,NULL,NEW.titel||' '||ifnull(NEW.text,'')); END;

CREATE TRIGGER suche_eintrag_au AFTER UPDATE OF titel,text ON eintrag BEGIN
  DELETE FROM suche WHERE art='eintrag' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('eintrag',NEW.id,NULL,NEW.titel||' '||ifnull(NEW.text,'')); END;

CREATE TRIGGER suche_referenz_ad AFTER DELETE ON referenz BEGIN
  DELETE FROM suche WHERE art='referenz' AND ref_id=OLD.id; END;

CREATE TRIGGER suche_referenz_ai AFTER INSERT ON referenz BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('referenz',NEW.id,NULL,NEW.bezeichnung||' '||NEW.wert); END;

CREATE TRIGGER suche_seite_ad AFTER DELETE ON dokumentseite BEGIN
  DELETE FROM suche WHERE art='seite' AND ref_id=OLD.dokument_id AND seite=OLD.nummer; END;

CREATE TRIGGER suche_seite_ai AFTER INSERT ON dokumentseite BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('seite',NEW.dokument_id,NEW.nummer,NEW.text); END;

CREATE TRIGGER suche_vorgang_ai AFTER INSERT ON vorgang BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('vorgang',NEW.id,NULL,NEW.titel||' '||NEW.beschreibung); END;

CREATE TRIGGER suche_vorgang_au AFTER UPDATE OF titel,beschreibung ON vorgang BEGIN
  DELETE FROM suche WHERE art='vorgang' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('vorgang',NEW.id,NULL,NEW.titel||' '||NEW.beschreibung); END;

PRAGMA user_version = 12;

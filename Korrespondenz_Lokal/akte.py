"""Fachliches Datenmodell der Vorgangsakte (Etappe 2).

Teilvorgänge, Chronik, Fristen mit Fundstelle und Verlauf, Kontakte mit Anschriftenverlauf,
Versand mit gespeicherter Anschrift, Referenzen, Bereiche, Schlagwörter, Papierkorb und Volltextsuche.
Alle Daten liegen in derselben SQLite-Datei wie Vorgänge und Dokumente.
"""
import re
import sqlite3
from contextlib import closing
from datetime import date, timedelta

STATUSES = ("Schreiben verfassen", "Recherchieren", "Schreiben abgeschickt",
            "Offen", "Wartet auf Antwort", "Erledigt")
DEFAULT_GROUPS = ("Rechtliche Angelegenheiten", "Finanzamt und Steuern", "Versicherungen", "Anderes")
EINTRAG_ARTEN = ("eingang", "ausgang", "entwurf", "nachweis", "telefonat", "notiz", "entscheidung", "chat", "fehlt")
RICHTUNGEN = ("von", "an", "mit")
FRIST_ARTEN = ("frist", "wiedervorlage", "aufgabe")
VERSAND_ARTEN = ("Post", "Einschreiben", "E-Mail", "Fax", "Persönlich", "Online-Portal")

SCHEMA_3 = f"""
CREATE TABLE IF NOT EXISTS bereich(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS schlagwort(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS vorgang_schlagwort(
    vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    schlagwort_id INTEGER NOT NULL REFERENCES schlagwort(id),
    PRIMARY KEY(vorgang_id, schlagwort_id)
);
CREATE TABLE IF NOT EXISTS teilvorgang(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Offen', zustaendig TEXT, naechster_schritt TEXT,
    reihenfolge INTEGER NOT NULL DEFAULT 0, angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kontakt(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, kurzname TEXT, typ TEXT, notiz TEXT,
    angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geloescht_am TEXT
);
CREATE TABLE IF NOT EXISTS kontakt_abteilung(
    id INTEGER PRIMARY KEY, kontakt_id INTEGER NOT NULL REFERENCES kontakt(id),
    name TEXT NOT NULL DEFAULT '', ansprechpartner TEXT, email TEXT, telefon TEXT
);
CREATE TABLE IF NOT EXISTS anschrift(
    id INTEGER PRIMARY KEY, abteilung_id INTEGER NOT NULL REFERENCES kontakt_abteilung(id),
    zeilen TEXT NOT NULL, gueltig_von TEXT NOT NULL, gueltig_bis TEXT
);
CREATE TABLE IF NOT EXISTS beteiligter(
    vorgang_id INTEGER NOT NULL REFERENCES vorgang(id), kontakt_id INTEGER NOT NULL REFERENCES kontakt(id),
    rolle TEXT NOT NULL DEFAULT '', PRIMARY KEY(vorgang_id, kontakt_id)
);
CREATE TABLE IF NOT EXISTS referenz(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    bezeichnung TEXT NOT NULL, wert TEXT NOT NULL, kontakt_id INTEGER REFERENCES kontakt(id),
    UNIQUE(vorgang_id, wert)
);
CREATE TABLE IF NOT EXISTS dokument_vorgang(
    dokument_id INTEGER NOT NULL REFERENCES dokument(id), vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    verknuepft_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(dokument_id, vorgang_id)
);
CREATE TABLE IF NOT EXISTS eintrag(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    art TEXT NOT NULL CHECK(art IN ({",".join(repr(a) for a in EINTRAG_ARTEN)})),
    titel TEXT NOT NULL, ereignis_datum TEXT NOT NULL,
    erfasst_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    richtung TEXT CHECK(richtung IS NULL OR richtung IN ('von','an','mit')),
    kontakt_id INTEGER REFERENCES kontakt(id), dokument_id INTEGER REFERENCES dokument(id),
    bezug_id INTEGER REFERENCES eintrag(id), text TEXT, quelle TEXT,
    geprueft INTEGER NOT NULL DEFAULT 0, versendet_als INTEGER REFERENCES eintrag(id),
    geloescht_am TEXT
);
CREATE TABLE IF NOT EXISTS eintrag_teil(
    eintrag_id INTEGER NOT NULL REFERENCES eintrag(id), teilvorgang_id INTEGER NOT NULL REFERENCES teilvorgang(id),
    PRIMARY KEY(eintrag_id, teilvorgang_id)
);
CREATE TABLE IF NOT EXISTS versand(
    eintrag_id INTEGER PRIMARY KEY REFERENCES eintrag(id), art TEXT NOT NULL, datum TEXT NOT NULL,
    sendungsnummer TEXT, anschrift_id INTEGER REFERENCES anschrift(id), empfaenger TEXT NOT NULL,
    nachweis_dokument_id INTEGER REFERENCES dokument(id)
);
CREATE TABLE IF NOT EXISTS frist(
    id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
    teilvorgang_id INTEGER REFERENCES teilvorgang(id),
    art TEXT NOT NULL CHECK(art IN ('frist','wiedervorlage','aufgabe')),
    titel TEXT NOT NULL, faellig_am TEXT NOT NULL, zustaendig TEXT,
    quelle_dokument_id INTEGER REFERENCES dokument(id), quelle_seite INTEGER, quelle_zitat TEXT,
    erledigt_am TEXT, angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geloescht_am TEXT,
    CHECK(art <> 'frist' OR quelle_dokument_id IS NOT NULL OR quelle_zitat IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS frist_verlauf(
    id INTEGER PRIMARY KEY, frist_id INTEGER NOT NULL REFERENCES frist(id),
    faellig_alt TEXT NOT NULL, faellig_neu TEXT NOT NULL, grund TEXT,
    geaendert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS eintrag_vorgang ON eintrag(vorgang_id);
CREATE INDEX IF NOT EXISTS frist_faellig ON frist(faellig_am);
CREATE INDEX IF NOT EXISTS dokument_vorgang_vorgang ON dokument_vorgang(vorgang_id);
CREATE INDEX IF NOT EXISTS referenz_wert ON referenz(wert);
"""

# Suchindex: Seiten, Einträge, Referenzen, Vorgangs- und Dokumenttitel. Trigger halten ihn aktuell.
SEARCH_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS suche_seite_ai AFTER INSERT ON dokumentseite BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('seite',NEW.dokument_id,NEW.nummer,NEW.text); END;
CREATE TRIGGER IF NOT EXISTS suche_seite_ad AFTER DELETE ON dokumentseite BEGIN
  DELETE FROM suche WHERE art='seite' AND ref_id=OLD.dokument_id AND seite=OLD.nummer; END;
CREATE TRIGGER IF NOT EXISTS suche_eintrag_ai AFTER INSERT ON eintrag BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('eintrag',NEW.id,NULL,NEW.titel||' '||ifnull(NEW.text,'')); END;
CREATE TRIGGER IF NOT EXISTS suche_eintrag_au AFTER UPDATE OF titel,text ON eintrag BEGIN
  DELETE FROM suche WHERE art='eintrag' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('eintrag',NEW.id,NULL,NEW.titel||' '||ifnull(NEW.text,'')); END;
CREATE TRIGGER IF NOT EXISTS suche_referenz_ai AFTER INSERT ON referenz BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('referenz',NEW.id,NULL,NEW.bezeichnung||' '||NEW.wert); END;
CREATE TRIGGER IF NOT EXISTS suche_referenz_ad AFTER DELETE ON referenz BEGIN
  DELETE FROM suche WHERE art='referenz' AND ref_id=OLD.id; END;
CREATE TRIGGER IF NOT EXISTS suche_vorgang_ai AFTER INSERT ON vorgang BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('vorgang',NEW.id,NULL,NEW.titel||' '||NEW.beschreibung); END;
CREATE TRIGGER IF NOT EXISTS suche_vorgang_au AFTER UPDATE OF titel,beschreibung ON vorgang BEGIN
  DELETE FROM suche WHERE art='vorgang' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('vorgang',NEW.id,NULL,NEW.titel||' '||NEW.beschreibung); END;
CREATE TRIGGER IF NOT EXISTS suche_dokument_ai AFTER INSERT ON dokument BEGIN
  INSERT INTO suche(art,ref_id,seite,text) VALUES('dokument',NEW.id,NULL,NEW.titel||' '||NEW.dateiname); END;
CREATE TRIGGER IF NOT EXISTS suche_dokument_au AFTER UPDATE OF titel ON dokument BEGIN
  DELETE FROM suche WHERE art='dokument' AND ref_id=OLD.id;
  INSERT INTO suche(art,ref_id,seite,text) VALUES('dokument',NEW.id,NULL,NEW.titel||' '||NEW.dateiname); END;
"""


def _columns(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def migrate_3(db):
    """Datenmodell der Vorgangsakte. Übernimmt Bereiche und Dokumentzuordnungen aus dem Bestand."""
    db.executescript(SCHEMA_3)
    for table, column in (("vorgang", "zustaendig"), ("vorgang", "naechster_schritt"),
                          ("vorgang", "geloescht_am"), ("dokument", "geloescht_am")):
        if column not in _columns(db, table):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    db.executemany("INSERT OR IGNORE INTO bereich(name) VALUES(?)", ((g,) for g in DEFAULT_GROUPS))
    db.execute("INSERT OR IGNORE INTO bereich(name) SELECT DISTINCT bereich FROM vorgang WHERE trim(bereich)<>''")
    db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) SELECT id,vorgang_id FROM dokument")
    try:
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS suche USING fts5(
            art UNINDEXED, ref_id UNINDEXED, seite UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')""")
    except sqlite3.OperationalError:  # SQLite ohne FTS5: einfache Tabelle, Suche per LIKE
        db.execute("CREATE TABLE IF NOT EXISTS suche(art TEXT, ref_id INTEGER, seite INTEGER, text TEXT)")
    db.executescript(SEARCH_TRIGGERS)
    db.execute("DELETE FROM suche")
    db.execute("INSERT INTO suche(art,ref_id,seite,text) SELECT 'seite',dokument_id,nummer,text FROM dokumentseite")
    db.execute("INSERT INTO suche(art,ref_id,seite,text) SELECT 'vorgang',id,NULL,titel||' '||beschreibung FROM vorgang")
    db.execute("INSERT INTO suche(art,ref_id,seite,text) SELECT 'dokument',id,NULL,titel||' '||dateiname FROM dokument")


# --- Prüfhilfen ---------------------------------------------------------------------------
def _text(value, label, limit, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label}: ungültige Eingabe.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} fehlt.")
    if len(value) > limit:
        raise ValueError(f"{label} ist zu lang (höchstens {limit} Zeichen).")
    return value or None


def _date(value, label, required=True):
    if value in (None, ""):
        if required:
            raise ValueError(f"{label} fehlt.")
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label}: bitte ein gültiges Datum angeben.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{label}: bitte ein gültiges Datum angeben.") from error


def _choice(value, allowed, label):
    if value not in allowed:
        raise ValueError(f"{label}: bitte einen Wert aus der Liste wählen.")
    return value


def _id(value, label):
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label}: ungültige Angabe.")
    return value


class Akte:
    def __init__(self, store, today=None):
        self.store = store
        self.today = today or (lambda: date.today().isoformat())

    def connect(self):
        return self.store.connect()

    # --- Bereiche und Schlagwörter --------------------------------------------------------
    def bereiche(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute("""SELECT b.name, count(v.id) AS vorgaenge FROM bereich b
                LEFT JOIN vorgang v ON v.bereich=b.name COLLATE NOCASE AND v.geloescht_am IS NULL
                GROUP BY b.id ORDER BY b.id""")]

    def bereich_namen(self):
        return [b["name"] for b in self.bereiche()]

    def bereich_anlegen(self, name):
        name = _text(name, "Bereich", 80, True)
        with closing(self.connect()) as db, db:
            try:
                db.execute("INSERT INTO bereich(name) VALUES(?)", (name,))
            except sqlite3.IntegrityError:
                raise ValueError("Diesen Bereich gibt es schon.") from None
        return name

    def bereich_umbenennen(self, alt, neu):
        neu = _text(neu, "Bereich", 80, True)
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE bereich SET name=? WHERE name=?", (neu, alt)).rowcount:
                raise ValueError("Bereich nicht gefunden.")
            db.execute("UPDATE vorgang SET bereich=? WHERE bereich=?", (neu, alt))

    def bereich_entfernen(self, name):
        with closing(self.connect()) as db, db:
            if db.execute("SELECT 1 FROM vorgang WHERE bereich=? AND geloescht_am IS NULL", (name,)).fetchone():
                raise ValueError("Der Bereich enthält noch Vorgänge.")
            if not db.execute("DELETE FROM bereich WHERE name=?", (name,)).rowcount:
                raise ValueError("Bereich nicht gefunden.")

    def schlagwoerter_setzen(self, vorgang_id, namen):
        if not isinstance(namen, list) or len(namen) > 30:
            raise ValueError("Schlagwörter: ungültige Liste.")
        eindeutig = {}
        for n in namen:  # „Auto“ und „auto“ gelten als dasselbe Schlagwort
            n = _text(n, "Schlagwort", 40, True)
            eindeutig.setdefault(n.lower(), n)
        namen = list(eindeutig.values())
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            db.execute("DELETE FROM vorgang_schlagwort WHERE vorgang_id=?", (vorgang_id,))
            for name in namen:
                db.execute("INSERT OR IGNORE INTO schlagwort(name) VALUES(?)", (name,))
                sid = db.execute("SELECT id FROM schlagwort WHERE name=?", (name,)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO vorgang_schlagwort VALUES(?,?)", (vorgang_id, sid))
        return namen

    # --- Vorgang ---------------------------------------------------------------------------
    def _vorgang(self, db, vorgang_id, deleted_ok=False):
        row = db.execute("SELECT * FROM vorgang WHERE id=?", (vorgang_id,)).fetchone()
        if not row or (row["geloescht_am"] and not deleted_ok):
            raise ValueError("Vorgang nicht gefunden.")
        return row

    def vorgang_aendern(self, vorgang_id, data):
        felder = {}
        if "titel" in data:
            felder["titel"] = _text(data["titel"], "Titel", 160, True)
        if "beschreibung" in data:
            felder["beschreibung"] = _text(data["beschreibung"], "Beschreibung", 4000) or ""
        if "zustaendig" in data:
            felder["zustaendig"] = _text(data["zustaendig"], "Zuständig", 80)
        if "naechster_schritt" in data:
            felder["naechster_schritt"] = _text(data["naechster_schritt"], "Nächster Schritt", 300)
        if "bereich" in data:
            if data["bereich"] not in self.bereich_namen():
                raise ValueError("Wähle einen Bereich aus der Liste.")
            felder["bereich"] = data["bereich"]
        if "status" in data:
            felder["status"] = _choice(data["status"], STATUSES, "Status")
        if not felder:
            raise ValueError("Keine Änderung angegeben.")
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            db.execute(f"UPDATE vorgang SET {','.join(k + '=?' for k in felder)} WHERE id=?",
                       (*felder.values(), vorgang_id))

    def akte(self, vorgang_id):
        """Die vollständige Vorgangsakte in einem Abruf."""
        with closing(self.connect()) as db:
            v = dict(self._vorgang(db, vorgang_id))
            q = lambda sql, *a: [dict(r) for r in db.execute(sql, a)]
            v["teilvorgaenge"] = q("SELECT * FROM teilvorgang WHERE vorgang_id=? ORDER BY reihenfolge,id", vorgang_id)
            v["schlagwoerter"] = [r["name"] for r in q("""SELECT s.name FROM vorgang_schlagwort vs
                JOIN schlagwort s ON s.id=vs.schlagwort_id WHERE vs.vorgang_id=? ORDER BY s.name""", vorgang_id)]
            v["beteiligte"] = q("""SELECT b.kontakt_id, b.rolle, k.name, k.kurzname, k.typ FROM beteiligter b
                JOIN kontakt k ON k.id=b.kontakt_id WHERE b.vorgang_id=? ORDER BY k.name""", vorgang_id)
            v["referenzen"] = q("SELECT * FROM referenz WHERE vorgang_id=? ORDER BY id", vorgang_id)
            v["dokumente"] = q("""SELECT d.id,d.titel,d.dateiname,d.titel_seite,d.titel_quelle,d.ocr_status,d.mime,
                d.angelegt_am,(SELECT count(*) FROM dokument_vorgang x WHERE x.dokument_id=d.id) AS vorgaenge
                FROM dokument d JOIN dokument_vorgang dv ON dv.dokument_id=d.id
                WHERE dv.vorgang_id=? AND d.geloescht_am IS NULL ORDER BY d.id DESC""", vorgang_id)
            eintraege = q("""SELECT * FROM eintrag WHERE vorgang_id=? AND geloescht_am IS NULL
                ORDER BY ereignis_datum DESC, id DESC""", vorgang_id)
            for e in eintraege:
                e["teile"] = [r["teilvorgang_id"] for r in q(
                    "SELECT teilvorgang_id FROM eintrag_teil WHERE eintrag_id=? ORDER BY teilvorgang_id", e["id"])]
                e["nacherfasst"] = e["ereignis_datum"] < e["erfasst_am"][:10]
                versand = q("SELECT * FROM versand WHERE eintrag_id=?", e["id"])
                e["versand"] = versand[0] if versand else None
                if e["versand"] and e["versand"]["anschrift_id"]:
                    aktuell = db.execute("""SELECT a2.zeilen FROM anschrift a1 JOIN anschrift a2
                        ON a2.abteilung_id=a1.abteilung_id AND a2.gueltig_bis IS NULL WHERE a1.id=?""",
                                         (e["versand"]["anschrift_id"],)).fetchone()
                    e["versand"]["anschrift_geaendert"] = bool(aktuell and aktuell[0] != e["versand"]["empfaenger"])
            v["eintraege"] = eintraege
            fristen = q("""SELECT * FROM frist WHERE vorgang_id=? AND geloescht_am IS NULL
                ORDER BY erledigt_am IS NOT NULL, faellig_am""", vorgang_id)
            for f in fristen:
                f["verlauf"] = q("SELECT faellig_alt,faellig_neu,grund,geaendert_am FROM frist_verlauf "
                                 "WHERE frist_id=? ORDER BY id", f["id"])
            v["fristen"] = fristen
            return v

    # --- Teilvorgänge --------------------------------------------------------------------
    def teilvorgang_anlegen(self, vorgang_id, data):
        name = _text(data.get("name"), "Name", 120, True)
        status = _choice(data.get("status", "Offen"), STATUSES, "Status")
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            nr = db.execute("SELECT ifnull(max(reihenfolge),0)+1 FROM teilvorgang WHERE vorgang_id=?",
                            (vorgang_id,)).fetchone()[0]
            return db.execute("""INSERT INTO teilvorgang(vorgang_id,name,status,zustaendig,naechster_schritt,reihenfolge)
                VALUES(?,?,?,?,?,?)""", (vorgang_id, name, status, _text(data.get("zustaendig"), "Zuständig", 80),
                                         _text(data.get("naechster_schritt"), "Nächster Schritt", 300), nr)).lastrowid

    def teilvorgang_aendern(self, teil_id, data):
        felder = {}
        if "name" in data:
            felder["name"] = _text(data["name"], "Name", 120, True)
        if "status" in data:
            felder["status"] = _choice(data["status"], STATUSES, "Status")
        if "zustaendig" in data:
            felder["zustaendig"] = _text(data["zustaendig"], "Zuständig", 80)
        if "naechster_schritt" in data:
            felder["naechster_schritt"] = _text(data["naechster_schritt"], "Nächster Schritt", 300)
        if not felder:
            raise ValueError("Keine Änderung angegeben.")
        with closing(self.connect()) as db, db:
            if not db.execute(f"UPDATE teilvorgang SET {','.join(k + '=?' for k in felder)} WHERE id=?",
                              (*felder.values(), teil_id)).rowcount:
                raise ValueError("Teilvorgang nicht gefunden.")

    def teilvorgang_entfernen(self, teil_id):
        """Nur möglich, solange kein Eintrag und keine Frist ausschließlich zu diesem Teilvorgang gehört."""
        with closing(self.connect()) as db, db:
            allein = db.execute("""SELECT 1 FROM eintrag_teil et JOIN eintrag e ON e.id=et.eintrag_id
                WHERE et.teilvorgang_id=? AND e.geloescht_am IS NULL AND
                (SELECT count(*) FROM eintrag_teil x WHERE x.eintrag_id=et.eintrag_id)=1""", (teil_id,)).fetchone()
            frist = db.execute("SELECT 1 FROM frist WHERE teilvorgang_id=? AND geloescht_am IS NULL",
                               (teil_id,)).fetchone()
            if allein or frist:
                raise ValueError("Der Teilvorgang enthält noch eigene Einträge oder Fristen.")
            db.execute("DELETE FROM eintrag_teil WHERE teilvorgang_id=?", (teil_id,))
            if not db.execute("DELETE FROM teilvorgang WHERE id=?", (teil_id,)).rowcount:
                raise ValueError("Teilvorgang nicht gefunden.")

    def _teile(self, db, vorgang_id, teile):
        if teile in (None, []):
            return []
        if not isinstance(teile, list) or not all(isinstance(t, int) and not isinstance(t, bool) for t in teile):
            raise ValueError("Teilvorgänge: ungültige Angabe.")
        gueltig = {r[0] for r in db.execute("SELECT id FROM teilvorgang WHERE vorgang_id=?", (vorgang_id,))}
        if not set(teile) <= gueltig:
            raise ValueError("Teilvorgang gehört nicht zu diesem Vorgang.")
        return sorted(set(teile))

    # --- Kontakte ------------------------------------------------------------------------
    def kontakte(self):
        with closing(self.connect()) as db:
            kontakte = [dict(r) for r in db.execute(
                "SELECT * FROM kontakt WHERE geloescht_am IS NULL ORDER BY name COLLATE NOCASE")]
            for k in kontakte:
                k["abteilungen"] = [dict(r) for r in db.execute(
                    "SELECT * FROM kontakt_abteilung WHERE kontakt_id=? ORDER BY id", (k["id"],))]
                for a in k["abteilungen"]:
                    a["anschriften"] = [dict(r) for r in db.execute("""SELECT a.*,
                        (SELECT count(*) FROM versand v WHERE v.anschrift_id=a.id) AS verwendet
                        FROM anschrift a WHERE abteilung_id=? ORDER BY gueltig_bis IS NOT NULL, gueltig_von DESC""",
                        (a["id"],))]
                k["vorgaenge"] = [dict(r) for r in db.execute("""SELECT v.id,v.titel,b.rolle FROM beteiligter b
                    JOIN vorgang v ON v.id=b.vorgang_id WHERE b.kontakt_id=? AND v.geloescht_am IS NULL""", (k["id"],))]
            return kontakte

    def moegliche_dubletten(self, name):
        name = (name or "").strip().lower()
        woerter = [w for w in re.split(r"[\s\-]+", name) if len(w) >= 4]
        if len(name) < 3:
            return []
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute("SELECT id,name FROM kontakt WHERE geloescht_am IS NULL")
                    if name in r["name"].lower() or any(w in r["name"].lower() for w in woerter)]

    def kontakt_anlegen(self, data):
        name = _text(data.get("name"), "Name", 160, True)
        with closing(self.connect()) as db, db:
            kid = db.execute("INSERT INTO kontakt(name,kurzname,typ,notiz) VALUES(?,?,?,?)",
                             (name, _text(data.get("kurzname"), "Kurzname", 80), _text(data.get("typ"), "Typ", 60),
                              _text(data.get("notiz"), "Notiz", 2000))).lastrowid
            for abt in data.get("abteilungen") or [{}]:
                self._abteilung(db, kid, abt)
            return kid

    def _abteilung(self, db, kontakt_id, abt):
        aid = db.execute("""INSERT INTO kontakt_abteilung(kontakt_id,name,ansprechpartner,email,telefon)
            VALUES(?,?,?,?,?)""", (kontakt_id, _text(abt.get("name"), "Abteilung", 120) or "",
                                   _text(abt.get("ansprechpartner"), "Ansprechpartner", 120),
                                   _text(abt.get("email"), "E-Mail", 160), _text(abt.get("telefon"), "Telefon", 60))).lastrowid
        if abt.get("anschrift"):
            db.execute("INSERT INTO anschrift(abteilung_id,zeilen,gueltig_von) VALUES(?,?,?)",
                       (aid, _text(abt["anschrift"], "Anschrift", 500, True),
                        _date(abt.get("gueltig_von"), "Gültig ab", False) or self.today()))
        return aid

    def abteilung_anlegen(self, kontakt_id, data):
        with closing(self.connect()) as db, db:
            if not db.execute("SELECT 1 FROM kontakt WHERE id=?", (kontakt_id,)).fetchone():
                raise ValueError("Kontakt nicht gefunden.")
            return self._abteilung(db, kontakt_id, data)

    def anschrift_aendern(self, abteilung_id, zeilen, gueltig_von=None):
        """Neue Anschrift ab einem Datum. Die bisherige endet am Vortag und bleibt für frühere Schreiben sichtbar."""
        zeilen = _text(zeilen, "Anschrift", 500, True)
        von = _date(gueltig_von, "Gültig ab", False) or self.today()
        with closing(self.connect()) as db, db:
            if not db.execute("SELECT 1 FROM kontakt_abteilung WHERE id=?", (abteilung_id,)).fetchone():
                raise ValueError("Abteilung nicht gefunden.")
            bis = (date.fromisoformat(von) - timedelta(days=1)).isoformat()
            db.execute("UPDATE anschrift SET gueltig_bis=? WHERE abteilung_id=? AND gueltig_bis IS NULL",
                       (bis, abteilung_id))
            return db.execute("INSERT INTO anschrift(abteilung_id,zeilen,gueltig_von) VALUES(?,?,?)",
                              (abteilung_id, zeilen, von)).lastrowid

    def beteiligter_setzen(self, vorgang_id, kontakt_id, rolle=""):
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            if not db.execute("SELECT 1 FROM kontakt WHERE id=? AND geloescht_am IS NULL", (kontakt_id,)).fetchone():
                raise ValueError("Kontakt nicht gefunden.")
            db.execute("INSERT OR REPLACE INTO beteiligter(vorgang_id,kontakt_id,rolle) VALUES(?,?,?)",
                       (vorgang_id, kontakt_id, _text(rolle, "Rolle", 120) or ""))

    def beteiligter_entfernen(self, vorgang_id, kontakt_id):
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM beteiligter WHERE vorgang_id=? AND kontakt_id=?", (vorgang_id, kontakt_id))

    def referenz_anlegen(self, vorgang_id, data):
        bezeichnung = _text(data.get("bezeichnung"), "Bezeichnung", 60) or "Aktenzeichen"
        wert = _text(data.get("wert"), "Nummer", 120, True)
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            try:
                return db.execute("INSERT INTO referenz(vorgang_id,bezeichnung,wert,kontakt_id) VALUES(?,?,?,?)",
                                  (vorgang_id, bezeichnung, wert, _id(data.get("kontakt_id"), "Kontakt"))).lastrowid
            except sqlite3.IntegrityError:
                raise ValueError("Diese Referenz ist bereits hinterlegt.") from None

    def referenz_entfernen(self, referenz_id):
        with closing(self.connect()) as db, db:
            if not db.execute("DELETE FROM referenz WHERE id=?", (referenz_id,)).rowcount:
                raise ValueError("Referenz nicht gefunden.")

    # --- Chronik ---------------------------------------------------------------------------
    def eintrag_anlegen(self, vorgang_id, data):
        art = _choice(data.get("art"), EINTRAG_ARTEN, "Art")
        titel = _text(data.get("titel"), "Titel", 200, True)
        datum = _date(data.get("datum"), "Ereignisdatum", False) or self.today()
        richtung = data.get("richtung")
        if richtung is not None:
            _choice(richtung, RICHTUNGEN, "Richtung")
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            teile = self._teile(db, vorgang_id, data.get("teile"))
            dok = _id(data.get("dokument_id"), "Dokument")
            if dok and not db.execute("SELECT 1 FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?",
                                      (dok, vorgang_id)).fetchone():
                raise ValueError("Das Dokument ist diesem Vorgang nicht zugeordnet.")
            eid = db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,richtung,kontakt_id,
                dokument_id,bezug_id,text,quelle,geprueft) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (vorgang_id, art, titel, datum, richtung, _id(data.get("kontakt_id"), "Kontakt"), dok,
                 _id(data.get("bezug_id"), "Bezug"), _text(data.get("text"), "Text", 20000),
                 _text(data.get("quelle"), "Quelle", 300), 1 if data.get("geprueft") else 0)).lastrowid
            db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((eid, t) for t in teile))
            return eid

    def eintrag_aendern(self, eintrag_id, data):
        with closing(self.connect()) as db, db:
            e = db.execute("SELECT * FROM eintrag WHERE id=? AND geloescht_am IS NULL", (eintrag_id,)).fetchone()
            if not e:
                raise ValueError("Eintrag nicht gefunden.")
            felder = {}
            if "titel" in data:
                felder["titel"] = _text(data["titel"], "Titel", 200, True)
            if "datum" in data:
                felder["ereignis_datum"] = _date(data["datum"], "Ereignisdatum")
            if "text" in data:
                felder["text"] = _text(data["text"], "Text", 20000)
            if "kontakt_id" in data:
                felder["kontakt_id"] = _id(data["kontakt_id"], "Kontakt")
            if "geprueft" in data:
                felder["geprueft"] = 1 if data["geprueft"] else 0
            if felder:
                db.execute(f"UPDATE eintrag SET {','.join(k + '=?' for k in felder)} WHERE id=?",
                           (*felder.values(), eintrag_id))
            if "teile" in data:
                teile = self._teile(db, e["vorgang_id"], data["teile"])
                db.execute("DELETE FROM eintrag_teil WHERE eintrag_id=?", (eintrag_id,))
                db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((eintrag_id, t) for t in teile))
            if "auch_in_vorgang" in data:  # Dokument zusätzlich in einem anderen Vorgang zeigen
                ziel = _id(data["auch_in_vorgang"], "Vorgang")
                self._vorgang(db, ziel)
                if not e["dokument_id"]:
                    raise ValueError("Nur Einträge mit Dokument lassen sich verknüpfen.")
                db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)",
                           (e["dokument_id"], ziel))
                db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,richtung,dokument_id,text,quelle)
                    VALUES(?,?,?,?,?,?,?,?)""", (ziel, e["art"], e["titel"], e["ereignis_datum"], e["richtung"],
                                                 e["dokument_id"], e["text"], e["quelle"]))

    def versand_erfassen(self, entwurf_id, data):
        """Erfasst den Versand eines Entwurfs. Die verwendete Anschrift wird als Text festgehalten."""
        art = _choice(data.get("art"), VERSAND_ARTEN, "Versandart")
        datum = _date(data.get("datum"), "Versanddatum", False) or self.today()
        with closing(self.connect()) as db, db:
            e = db.execute("SELECT * FROM eintrag WHERE id=? AND geloescht_am IS NULL", (entwurf_id,)).fetchone()
            if not e or e["art"] != "entwurf":
                raise ValueError("Nur ein Entwurf lässt sich versenden.")
            if e["versendet_als"]:
                raise ValueError("Dieser Entwurf ist bereits versendet.")
            anschrift_id = _id(data.get("anschrift_id"), "Anschrift")
            if anschrift_id:
                row = db.execute("SELECT zeilen,gueltig_bis FROM anschrift WHERE id=?", (anschrift_id,)).fetchone()
                if not row:
                    raise ValueError("Anschrift nicht gefunden.")
                if row["gueltig_bis"] and row["gueltig_bis"] < datum:
                    raise ValueError("Diese Anschrift ist nicht mehr gültig.")
                empfaenger = row["zeilen"]
            else:
                empfaenger = _text(data.get("empfaenger"), "Empfänger", 500, True)
            nachweis = _id(data.get("nachweis_dokument_id"), "Nachweis")
            aus = db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,richtung,kontakt_id,dokument_id,
                bezug_id,text) VALUES(?,?,?,?,?,?,?,?,?)""",
                (e["vorgang_id"], "ausgang", _text(data.get("titel"), "Titel", 200) or e["titel"], datum, "an",
                 e["kontakt_id"], e["dokument_id"], e["bezug_id"], e["text"])).lastrowid
            teile = [r[0] for r in db.execute("SELECT teilvorgang_id FROM eintrag_teil WHERE eintrag_id=?", (entwurf_id,))]
            db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((aus, t) for t in teile))
            db.execute("""INSERT INTO versand(eintrag_id,art,datum,sendungsnummer,anschrift_id,empfaenger,
                nachweis_dokument_id) VALUES(?,?,?,?,?,?,?)""",
                (aus, art, datum, _text(data.get("sendungsnummer"), "Sendungsnummer", 80), anschrift_id,
                 empfaenger, nachweis))
            db.execute("UPDATE eintrag SET versendet_als=? WHERE id=?", (aus, entwurf_id))
            if teile:
                db.executemany("UPDATE teilvorgang SET status='Schreiben abgeschickt' WHERE id=? AND status<>'Erledigt'",
                               ((t,) for t in teile))
            else:
                db.execute("UPDATE vorgang SET status='Schreiben abgeschickt' WHERE id=? AND status<>'Erledigt'",
                           (e["vorgang_id"],))
            return aus

    # --- Fristen ---------------------------------------------------------------------------
    def frist_anlegen(self, vorgang_id, data):
        art = _choice(data.get("art"), FRIST_ARTEN, "Art")
        titel = _text(data.get("titel"), "Titel", 200, True)
        faellig = _date(data.get("faellig_am"), "Fällig am")
        quelle_dok = _id(data.get("quelle_dokument_id"), "Fundstelle")
        zitat = _text(data.get("quelle_zitat"), "Fundstelle", 500)
        if art == "frist" and not (quelle_dok or zitat):
            raise ValueError("Eine verbindliche Frist braucht eine Fundstelle oder einen Quellenvermerk.")
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            teil = data.get("teilvorgang_id")
            if teil is not None:
                self._teile(db, vorgang_id, [teil])
            return db.execute("""INSERT INTO frist(vorgang_id,teilvorgang_id,art,titel,faellig_am,zustaendig,
                quelle_dokument_id,quelle_seite,quelle_zitat) VALUES(?,?,?,?,?,?,?,?,?)""",
                (vorgang_id, teil, art, titel, faellig, _text(data.get("zustaendig"), "Zuständig", 80),
                 quelle_dok, _id(data.get("quelle_seite"), "Seite"), zitat)).lastrowid

    def frist_aendern(self, frist_id, data):
        with closing(self.connect()) as db, db:
            f = db.execute("SELECT * FROM frist WHERE id=? AND geloescht_am IS NULL", (frist_id,)).fetchone()
            if not f:
                raise ValueError("Frist nicht gefunden.")
            if "faellig_am" in data:  # Verschieben: das bisherige Datum bleibt im Verlauf nachvollziehbar
                neu = _date(data["faellig_am"], "Fällig am")
                if neu != f["faellig_am"]:
                    db.execute("INSERT INTO frist_verlauf(frist_id,faellig_alt,faellig_neu,grund) VALUES(?,?,?,?)",
                               (frist_id, f["faellig_am"], neu, _text(data.get("grund"), "Grund", 300)))
                    db.execute("UPDATE frist SET faellig_am=? WHERE id=?", (neu, frist_id))
            if "zustaendig" in data:
                db.execute("UPDATE frist SET zustaendig=? WHERE id=?",
                           (_text(data["zustaendig"], "Zuständig", 80), frist_id))
            if "titel" in data:
                db.execute("UPDATE frist SET titel=? WHERE id=?", (_text(data["titel"], "Titel", 200, True), frist_id))
            if "erledigt" in data:
                db.execute("UPDATE frist SET erledigt_am=? WHERE id=?",
                           (self.today() if data["erledigt"] else None, frist_id))

    def offene_punkte(self, vorgang_id, teil_id=None):
        """Was vor dem Abschluss noch offen ist: Fristen, nicht versendete Entwürfe, fehlende Originale, Chats."""
        teil_filter = "" if teil_id is None else " AND id IN (SELECT eintrag_id FROM eintrag_teil WHERE teilvorgang_id=?)"
        args = (vorgang_id,) if teil_id is None else (vorgang_id, teil_id)
        with closing(self.connect()) as db:
            fristen = [dict(r) for r in db.execute(
                "SELECT id,art,titel,faellig_am FROM frist WHERE vorgang_id=? AND erledigt_am IS NULL "
                "AND geloescht_am IS NULL" + ("" if teil_id is None else " AND teilvorgang_id=?"), args)]
            def eintraege(bedingung):
                return [dict(r) for r in db.execute(
                    "SELECT id,titel FROM eintrag WHERE vorgang_id=? AND geloescht_am IS NULL AND "
                    + bedingung + teil_filter, args)]
            return {"fristen": fristen,
                    "entwuerfe": eintraege("art='entwurf' AND versendet_als IS NULL"),
                    "fehlende_originale": eintraege("art='fehlt'"),
                    "ungepruefte_chats": eintraege("art='chat' AND geprueft=0")}

    # --- Dokumente -------------------------------------------------------------------------
    def dokument_verknuepfen(self, dokument_id, vorgang_id):
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            if not db.execute("SELECT 1 FROM dokument WHERE id=? AND geloescht_am IS NULL", (dokument_id,)).fetchone():
                raise ValueError("Dokument nicht gefunden.")
            db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)",
                       (dokument_id, vorgang_id))

    # --- Papierkorb ------------------------------------------------------------------------
    TABELLEN = {"vorgang": "vorgang", "dokument": "dokument", "eintrag": "eintrag", "frist": "frist",
                "kontakt": "kontakt"}

    def loeschen(self, typ, objekt_id):
        tabelle = self.TABELLEN.get(typ)
        if not tabelle:
            raise ValueError("Unbekannter Typ.")
        with closing(self.connect()) as db, db:
            if not db.execute(f"UPDATE {tabelle} SET geloescht_am=CURRENT_TIMESTAMP WHERE id=? AND geloescht_am IS NULL",
                              (objekt_id,)).rowcount:
                raise ValueError("Nicht gefunden oder bereits im Papierkorb.")

    def wiederherstellen(self, typ, objekt_id):
        tabelle = self.TABELLEN.get(typ)
        if not tabelle:
            raise ValueError("Unbekannter Typ.")
        with closing(self.connect()) as db, db:
            if tabelle in ("eintrag", "frist"):
                row = db.execute(f"SELECT vorgang_id FROM {tabelle} WHERE id=?", (objekt_id,)).fetchone()
                if row and db.execute("SELECT geloescht_am FROM vorgang WHERE id=?", (row[0],)).fetchone()[0]:
                    raise ValueError("Der zugehörige Vorgang liegt im Papierkorb. Bitte zuerst den Vorgang wiederherstellen.")
            if not db.execute(f"UPDATE {tabelle} SET geloescht_am=NULL WHERE id=? AND geloescht_am IS NOT NULL",
                              (objekt_id,)).rowcount:
                raise ValueError("Nicht im Papierkorb gefunden.")

    def papierkorb(self):
        with closing(self.connect()) as db:
            teile = []
            for typ, sql in (("vorgang", "SELECT id, titel AS bezeichnung, geloescht_am, NULL AS vorgang FROM vorgang"),
                             ("dokument", "SELECT id, titel, geloescht_am, NULL FROM dokument"),
                             ("eintrag", "SELECT e.id, e.titel, e.geloescht_am, v.titel FROM eintrag e "
                                         "JOIN vorgang v ON v.id=e.vorgang_id"),
                             ("frist", "SELECT f.id, f.titel, f.geloescht_am, v.titel FROM frist f "
                                       "JOIN vorgang v ON v.id=f.vorgang_id"),
                             ("kontakt", "SELECT id, name, geloescht_am, NULL FROM kontakt")):
                alias = "e." if typ == "eintrag" else "f." if typ == "frist" else ""
                for r in db.execute(sql + f" WHERE {alias}geloescht_am IS NOT NULL"):
                    teile.append({"typ": typ, "id": r[0], "bezeichnung": r[1], "geloescht_am": r[2], "vorgang": r[3]})
            return sorted(teile, key=lambda t: t["geloescht_am"], reverse=True)

    def endgueltig_loeschen(self, typ, objekt_id):
        """Entfernt einen Eintrag oder eine Frist aus dem Papierkorb. Vorgänge und Dokumente bleiben
        bis zur vollständigen Datensicherung (Etappe 4) im Papierkorb erhalten."""
        if typ not in ("eintrag", "frist"):
            raise ValueError("Vorgänge, Dokumente und Kontakte bleiben vorerst im Papierkorb erhalten.")
        with closing(self.connect()) as db, db:
            row = db.execute(f"SELECT geloescht_am FROM {typ} WHERE id=?", (objekt_id,)).fetchone()
            if not row or not row[0]:
                raise ValueError("Nicht im Papierkorb gefunden.")
            if typ == "eintrag":
                db.execute("UPDATE eintrag SET bezug_id=NULL WHERE bezug_id=?", (objekt_id,))
                db.execute("UPDATE eintrag SET versendet_als=NULL WHERE versendet_als=?", (objekt_id,))
                db.execute("DELETE FROM eintrag_teil WHERE eintrag_id=?", (objekt_id,))
                db.execute("DELETE FROM versand WHERE eintrag_id=?", (objekt_id,))
                db.execute("DELETE FROM suche WHERE art='eintrag' AND ref_id=?", (objekt_id,))
                db.execute("DELETE FROM eintrag WHERE id=?", (objekt_id,))
            else:
                db.execute("DELETE FROM frist_verlauf WHERE frist_id=?", (objekt_id,))
                db.execute("DELETE FROM frist WHERE id=?", (objekt_id,))

    # --- Suche -----------------------------------------------------------------------------
    def suche(self, begriff, limit=30):
        """Volltextsuche über Dokumentseiten, Chronik, Referenzen und Titel.

        Referenzen werden zusätzlich ohne Leerzeichen und Bindestriche verglichen, damit
        „KFZ 2026 1842“ auch „KFZ-2026-1842“ findet (Idee aus Tender AI)."""
        begriff = (begriff or "").strip()
        if len(begriff) < 2:
            return []
        woerter = re.findall(r"\w+", begriff)
        if not woerter:
            return []
        flach = re.sub(r"[\s\-_/.]+", "", begriff).lower()
        with closing(self.connect()) as db:
            fts = "fts5" in (db.execute("SELECT sql FROM sqlite_master WHERE name='suche'").fetchone()[0] or "").lower()
            if fts:
                ausdruck = " ".join('"' + w.replace('"', '') + '"*' for w in woerter)
                treffer = db.execute("""SELECT art,ref_id,seite,snippet(suche,3,'[',']','…',12) AS ausschnitt
                    FROM suche WHERE suche MATCH ? ORDER BY rank LIMIT ?""", (ausdruck, limit * 3)).fetchall()
            else:
                treffer = db.execute("""SELECT art,ref_id,seite,substr(text,1,160) AS ausschnitt FROM suche
                    WHERE text LIKE ? LIMIT ?""", ("%" + begriff + "%", limit * 3)).fetchall()
            ergebnis, gesehen = [], set()
            flach_ref = db.execute("""SELECT 'referenz',id,NULL,bezeichnung||' '||wert FROM referenz
                WHERE replace(replace(replace(replace(lower(wert),' ',''),'-',''),'/',''),'.','') LIKE ?""",
                                   ("%" + flach + "%",)).fetchall() if len(flach) >= 4 else []
            for art, ref, seite, ausschnitt in list(flach_ref) + list(treffer):
                ziel = self._trefferziel(db, art, ref)
                if not ziel:
                    continue
                schluessel = (art, ref, seite)
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                ergebnis.append({**ziel, "art": art, "seite": seite, "ausschnitt": ausschnitt})
                if len(ergebnis) >= limit:
                    break
            return ergebnis

    def _trefferziel(self, db, art, ref):
        if art in ("seite", "dokument"):
            row = db.execute("""SELECT d.id AS dokument_id, d.titel, dv.vorgang_id, v.titel AS vorgang
                FROM dokument d JOIN dokument_vorgang dv ON dv.dokument_id=d.id JOIN vorgang v ON v.id=dv.vorgang_id
                WHERE d.id=? AND d.geloescht_am IS NULL AND v.geloescht_am IS NULL ORDER BY dv.vorgang_id LIMIT 1""",
                             (ref,)).fetchone()
        elif art == "eintrag":
            row = db.execute("""SELECT e.dokument_id, e.titel, e.vorgang_id, v.titel AS vorgang, e.id AS eintrag_id
                FROM eintrag e JOIN vorgang v ON v.id=e.vorgang_id
                WHERE e.id=? AND e.geloescht_am IS NULL AND v.geloescht_am IS NULL""", (ref,)).fetchone()
        elif art == "referenz":
            row = db.execute("""SELECT NULL AS dokument_id, r.bezeichnung||' '||r.wert AS titel, r.vorgang_id,
                v.titel AS vorgang FROM referenz r JOIN vorgang v ON v.id=r.vorgang_id
                WHERE r.id=? AND v.geloescht_am IS NULL""", (ref,)).fetchone()
        else:
            row = db.execute("""SELECT NULL AS dokument_id, titel, id AS vorgang_id, titel AS vorgang FROM vorgang
                WHERE id=? AND geloescht_am IS NULL""", (ref,)).fetchone()
        return dict(row) if row else None


# --- HTTP-Schnittstelle -------------------------------------------------------------------
def _route_table():
    i = int
    return [
        ("GET", r"/api/akte/(\d+)", lambda a, m, d: a.akte(i(m[1]))),
        ("GET", r"/api/akte/(\d+)/offen", lambda a, m, d: a.offene_punkte(i(m[1]), i(d["teil"]) if str(d.get("teil", "")).isdigit() else None)),
        ("GET", r"/api/bereiche", lambda a, m, d: {"bereiche": a.bereiche()}),
        ("GET", r"/api/kontakte", lambda a, m, d: {"kontakte": a.kontakte()}),
        ("GET", r"/api/kontakte/dubletten", lambda a, m, d: {"dubletten": a.moegliche_dubletten(d.get("name"))}),
        ("GET", r"/api/papierkorb", lambda a, m, d: {"eintraege": a.papierkorb()}),
        ("GET", r"/api/suche", lambda a, m, d: {"treffer": a.suche(d.get("q"))}),
        ("POST", r"/api/akte/(\d+)", lambda a, m, d: a.vorgang_aendern(i(m[1]), d)),
        ("POST", r"/api/akte/(\d+)/schlagwoerter", lambda a, m, d: {"schlagwoerter": a.schlagwoerter_setzen(i(m[1]), d.get("namen"))}),
        ("POST", r"/api/akte/(\d+)/teilvorgaenge", lambda a, m, d: {"id": a.teilvorgang_anlegen(i(m[1]), d)}),
        ("POST", r"/api/teilvorgaenge/(\d+)", lambda a, m, d: a.teilvorgang_aendern(i(m[1]), d)),
        ("POST", r"/api/teilvorgaenge/(\d+)/entfernen", lambda a, m, d: a.teilvorgang_entfernen(i(m[1]))),
        ("POST", r"/api/akte/(\d+)/beteiligte", lambda a, m, d: a.beteiligter_setzen(i(m[1]), d.get("kontakt_id"), d.get("rolle", ""))),
        ("POST", r"/api/akte/(\d+)/beteiligte/(\d+)/entfernen", lambda a, m, d: a.beteiligter_entfernen(i(m[1]), i(m[2]))),
        ("POST", r"/api/akte/(\d+)/referenzen", lambda a, m, d: {"id": a.referenz_anlegen(i(m[1]), d)}),
        ("POST", r"/api/referenzen/(\d+)/entfernen", lambda a, m, d: a.referenz_entfernen(i(m[1]))),
        ("POST", r"/api/akte/(\d+)/eintraege", lambda a, m, d: {"id": a.eintrag_anlegen(i(m[1]), d)}),
        ("POST", r"/api/eintraege/(\d+)", lambda a, m, d: a.eintrag_aendern(i(m[1]), d)),
        ("POST", r"/api/eintraege/(\d+)/versand", lambda a, m, d: {"id": a.versand_erfassen(i(m[1]), d)}),
        ("POST", r"/api/akte/(\d+)/fristen", lambda a, m, d: {"id": a.frist_anlegen(i(m[1]), d)}),
        ("POST", r"/api/fristen/(\d+)", lambda a, m, d: a.frist_aendern(i(m[1]), d)),
        ("POST", r"/api/bereiche", lambda a, m, d: {"name": a.bereich_anlegen(d.get("name"))}),
        ("POST", r"/api/bereiche/umbenennen", lambda a, m, d: a.bereich_umbenennen(d.get("alt"), d.get("neu"))),
        ("POST", r"/api/bereiche/entfernen", lambda a, m, d: a.bereich_entfernen(d.get("name"))),
        ("POST", r"/api/kontakte", lambda a, m, d: {"id": a.kontakt_anlegen(d)}),
        ("POST", r"/api/kontakte/(\d+)/abteilungen", lambda a, m, d: {"id": a.abteilung_anlegen(i(m[1]), d)}),
        ("POST", r"/api/abteilungen/(\d+)/anschrift", lambda a, m, d: {"id": a.anschrift_aendern(i(m[1]), d.get("zeilen"), d.get("gueltig_von"))}),
        ("POST", r"/api/documents/(\d+)/verknuepfen", lambda a, m, d: a.dokument_verknuepfen(i(m[1]), d.get("vorgang_id"))),
        ("POST", r"/api/(vorgang|dokument|eintrag|frist|kontakt)/(\d+)/loeschen", lambda a, m, d: a.loeschen(m[1], i(m[2]))),
        ("POST", r"/api/(vorgang|dokument|eintrag|frist|kontakt)/(\d+)/wiederherstellen", lambda a, m, d: a.wiederherstellen(m[1], i(m[2]))),
        ("POST", r"/api/(eintrag|frist)/(\d+)/endgueltig", lambda a, m, d: a.endgueltig_loeschen(m[1], i(m[2]))),
    ]


ROUTES = [(method, re.compile(pattern), handler) for method, pattern, handler in _route_table()]


def route_akte(akte, method, path, data):
    """Gibt (Antwort, Status) zurück oder None, wenn der Pfad nicht zur Akte gehört."""
    for m, pattern, handler in ROUTES:
        if m == method and (match := pattern.fullmatch(path)):
            result = handler(akte, match, data or {})
            return (result if result is not None else {"ok": True}), (201 if method == "POST" and isinstance(result, dict)
                                                                      and "id" in result else 200)
    return None


# --- Selbsttest: Prüfkriterien aus dem Konzept ---------------------------------------------
def test_akte(store):
    from contextlib import closing as _closing
    heute = "2026-11-23"
    akte = Akte(store, today=lambda: heute)

    # Bereiche und Status
    assert "Versicherungen" in akte.bereich_namen()
    akte.bereich_anlegen("Wohnen")
    try:
        akte.bereich_anlegen("wohnen")
    except ValueError:
        pass
    else:
        raise AssertionError("Doppelter Bereich wurde angelegt.")
    kia = store.create_case("Kia-Schadenabwicklung", "Versicherungen", "")
    uni = store.create_case("Unitask", "Anderes", "")
    akte.bereich_umbenennen("Anderes", "Verträge")
    assert akte.akte(uni)["bereich"] == "Verträge"
    try:
        akte.bereich_entfernen("Verträge")
    except ValueError:
        pass
    else:
        raise AssertionError("Bereich mit Vorgängen wurde entfernt.")
    akte.schlagwoerter_setzen(kia, ["Auto", "2026", "auto"])
    assert akte.akte(kia)["schlagwoerter"] == ["2026", "Auto"]

    # Kriterium 4: Zwei Teilvorgänge mit eigener Zuständigkeit, eigenem Status und eigenen Fristen
    front = akte.teilvorgang_anlegen(kia, {"name": "Frontschaden", "status": "Wartet auf Antwort", "zustaendig": "Ich"})
    heck = akte.teilvorgang_anlegen(kia, {"name": "Heckschaden", "status": "Recherchieren", "zustaendig": "Werkstatt"})
    a = akte.akte(kia)
    assert [(t["name"], t["status"], t["zustaendig"]) for t in a["teilvorgaenge"]] == [
        ("Frontschaden", "Wartet auf Antwort", "Ich"), ("Heckschaden", "Recherchieren", "Werkstatt")]

    # Kontakte, Beteiligte, Referenzen
    vers = akte.kontakt_anlegen({"name": "Allsicher Versicherung AG", "kurzname": "Allsicher", "typ": "Versicherung",
                                 "abteilungen": [{"name": "Kfz-Schaden", "ansprechpartner": "Frau Berger",
                                                  "anschrift": "Allsicher Versicherung AG\nPostfach 10 20 30\n50442 Köln",
                                                  "gueltig_von": "2019-01-01"}]})
    assert akte.moegliche_dubletten("Allsicher")[0]["id"] == vers
    abt = akte.kontakte()[0]["abteilungen"][0]
    alte_anschrift = abt["anschriften"][0]["id"]
    akte.beteiligter_setzen(kia, vers, "Haftpflichtversicherung")
    akte.beteiligter_setzen(uni, vers, "Versicherung des Gegners")  # Kriterium 5: in zwei Vorgängen wählbar
    assert {v["id"] for v in akte.kontakte()[0]["vorgaenge"]} == {kia, uni}
    akte.referenz_anlegen(kia, {"bezeichnung": "Schaden-Nr.", "wert": "KFZ-2026-1842", "kontakt_id": vers})
    try:
        akte.referenz_anlegen(kia, {"wert": "KFZ-2026-1842"})
    except ValueError:
        pass
    else:
        raise AssertionError("Doppelte Referenz wurde angelegt.")

    # Kriterium 2: Gutachten in zwei Teilvorgängen, erneuter Import ohne zweite Kopie
    gutachten = b"%PDF-1.4\nGutachten L-26-0931"
    doc, neu = store.import_document(kia, "Gutachten.pdf", gutachten)
    with _closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)",
                   (doc, 1, "ocr", "Kfz-Gutachten Nr. L-26-0931 zur Schaden-Nr. KFZ-2026-1842, Frontschaden"))
    e_gut = akte.eintrag_anlegen(kia, {"art": "eingang", "titel": "Gutachten", "datum": "2026-11-10",
                                       "dokument_id": doc, "teile": [front, heck], "richtung": "von"})
    assert store.import_document(kia, "Gutachten_Kopie.pdf", gutachten) == (doc, False)
    assert store.import_document(uni, "Gutachten.pdf", gutachten) == (doc, False)  # verknüpft statt kopiert
    with _closing(store.connect()) as db:
        assert db.execute("SELECT count(*) FROM dokument WHERE sha256=(SELECT sha256 FROM dokument WHERE id=?)",
                          (doc,)).fetchone()[0] == 1
    assert len(list(store.uploads.glob("*.pdf"))) >= 1
    assert [d["id"] for d in akte.akte(uni)["dokumente"]] == [doc]
    assert akte.akte(kia)["eintraege"][0]["teile"] == sorted([front, heck])

    # Kriterium 1: Schadennummer aus eingescanntem Schreiben führt über die Suche zur Akte und Seite
    for frage in ("KFZ-2026-1842", "KFZ 2026 1842", "kfz2026", "Frontschaden"):
        treffer = akte.suche(frage)
        assert any(t["vorgang_id"] == kia for t in treffer), (frage, treffer)
    seite = [t for t in akte.suche("L-26-0931") if t["art"] == "seite"][0]
    assert seite["dokument_id"] == doc and seite["seite"] == 1 and "[" in seite["ausschnitt"]

    # Kriterium 3: Eingang, Antwortentwurf, versendete Fassung und Versandnachweis chronologisch
    e_brief = akte.eintrag_anlegen(kia, {"art": "eingang", "titel": "Schreiben der Versicherung", "datum": "2026-11-18",
                                         "teile": [front], "kontakt_id": vers, "richtung": "von"})
    entwurf = akte.eintrag_anlegen(kia, {"art": "entwurf", "titel": "Stellungnahme", "datum": "2026-11-20",
                                         "teile": [front], "kontakt_id": vers, "richtung": "an", "bezug_id": e_brief})
    # Kriterium 5: Adressänderung nach dem ersten Versand
    alt_versand = akte.eintrag_anlegen(kia, {"art": "entwurf", "titel": "Schadensmeldung", "datum": "2026-10-09",
                                             "teile": [front, heck], "kontakt_id": vers})
    akte.versand_erfassen(alt_versand, {"art": "Einschreiben", "datum": "2026-10-09", "sendungsnummer": "RR 4471 2093 5DE",
                                        "anschrift_id": alte_anschrift})
    neue_anschrift = akte.anschrift_aendern(abt["id"], "Allsicher Versicherung AG\nRheinuferstraße 12\n50668 Köln",
                                            "2026-11-01")
    try:
        akte.versand_erfassen(entwurf, {"art": "Post", "datum": heute, "anschrift_id": alte_anschrift})
    except ValueError:
        pass
    else:
        raise AssertionError("Versand an eine abgelaufene Anschrift wurde angenommen.")
    ausgang = akte.versand_erfassen(entwurf, {"art": "Post", "datum": heute, "anschrift_id": neue_anschrift})
    nachweis = akte.eintrag_anlegen(kia, {"art": "nachweis", "titel": "Einlieferungsbeleg", "datum": heute,
                                          "teile": [front], "bezug_id": ausgang})
    try:
        akte.versand_erfassen(entwurf, {"art": "Post", "anschrift_id": neue_anschrift})
    except ValueError:
        pass
    else:
        raise AssertionError("Ein Entwurf wurde doppelt versendet.")
    a = akte.akte(kia)
    chronik = [(e["ereignis_datum"], e["art"]) for e in a["eintraege"] if front in e["teile"]][::-1]
    assert chronik == [("2026-10-09", "entwurf"), ("2026-10-09", "ausgang"), ("2026-11-10", "eingang"),
                       ("2026-11-18", "eingang"), ("2026-11-20", "entwurf"), (heute, "ausgang"),
                       (heute, "nachweis")], chronik
    by_id = {e["id"]: e for e in a["eintraege"]}
    assert by_id[entwurf]["versendet_als"] == ausgang and by_id[nachweis]["bezug_id"] == ausgang
    erster = [e for e in a["eintraege"] if e["versand"] and e["versand"]["datum"] == "2026-10-09"][0]
    assert "Postfach 10 20 30" in erster["versand"]["empfaenger"] and erster["versand"]["anschrift_geaendert"]
    assert not by_id[ausgang]["versand"]["anschrift_geaendert"]
    anschriften = akte.kontakte()[0]["abteilungen"][0]["anschriften"]
    assert anschriften[0]["gueltig_bis"] is None and anschriften[1]["gueltig_bis"] == "2026-10-31"
    assert anschriften[1]["verwendet"] == 1
    assert {t["id"]: t["status"] for t in a["teilvorgaenge"]}[front] == "Schreiben abgeschickt"
    assert by_id[e_gut]["nacherfasst"]  # Ereignis 10.11., erfasst heute

    # Fristen: verbindliche Frist nur mit Fundstelle, Verschieben mit Verlauf, getrennt je Teilvorgang
    try:
        akte.frist_anlegen(kia, {"art": "frist", "titel": "Stellungnahme", "faellig_am": "2026-12-16"})
    except ValueError:
        pass
    else:
        raise AssertionError("Frist ohne Fundstelle wurde angenommen.")
    f1 = akte.frist_anlegen(kia, {"art": "frist", "titel": "Stellungnahme", "faellig_am": "2026-12-16", "teilvorgang_id": front,
                                  "quelle_dokument_id": doc, "quelle_seite": 1, "quelle_zitat": "bis zum 16.12.2026"})
    akte.frist_anlegen(kia, {"art": "aufgabe", "titel": "Fotos senden", "faellig_am": "2026-11-25",
                             "teilvorgang_id": heck, "zustaendig": "Werkstatt"})
    akte.frist_aendern(f1, {"faellig_am": "2026-12-30", "grund": "Verlängerung bestätigt"})
    f = [x for x in akte.akte(kia)["fristen"] if x["id"] == f1][0]
    assert f["faellig_am"] == "2026-12-30" and f["verlauf"][0]["faellig_alt"] == "2026-12-16"
    offen = akte.offene_punkte(kia, front)
    assert [x["id"] for x in offen["fristen"]] == [f1] and not offen["entwuerfe"]
    assert len(akte.offene_punkte(kia, heck)["fristen"]) == 1

    # Teilvorgang mit eigenen Einträgen lässt sich nicht entfernen
    try:
        akte.teilvorgang_entfernen(front)
    except ValueError:
        pass
    else:
        raise AssertionError("Teilvorgang mit Einträgen wurde entfernt.")

    # Papierkorb: Vorgang löschen, verschwindet aus Liste und Suche, Wiederherstellung
    akte.loeschen("vorgang", uni)
    assert uni not in [c["id"] for c in store.list_cases()]
    assert all(t["vorgang_id"] != uni for t in akte.suche("Unitask"))
    assert any(p["typ"] == "vorgang" and p["id"] == uni for p in akte.papierkorb())
    akte.wiederherstellen("vorgang", uni)
    assert uni in [c["id"] for c in store.list_cases()]
    akte.loeschen("eintrag", nachweis)
    assert nachweis not in {e["id"] for e in akte.akte(kia)["eintraege"]}
    akte.endgueltig_loeschen("eintrag", nachweis)
    assert not any(p["id"] == nachweis and p["typ"] == "eintrag" for p in akte.papierkorb())

    # HTTP-Anbindung
    result, status = route_akte(akte, "GET", f"/api/akte/{kia}", None)
    assert status == 200 and result["titel"] == "Kia-Schadenabwicklung"
    result, status = route_akte(akte, "POST", f"/api/akte/{kia}/referenzen", {"wert": "KV-778812-3"})
    assert status == 201 and result["id"]
    assert route_akte(akte, "GET", "/api/unbekannt", None) is None
    result, _ = route_akte(akte, "GET", "/api/suche", {"q": "KV 778812"})
    assert result["treffer"][0]["vorgang_id"] == kia

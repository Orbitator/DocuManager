"""Fachliches Datenmodell der Vorgangsakte (Etappe 2).

Teilvorgänge, Chronik, Fristen mit Fundstelle und Verlauf, Kontakte mit Anschriftenverlauf,
Versand mit gespeicherter Anschrift, Referenzen, Bereiche, Schlagwörter, Papierkorb und Volltextsuche.
Alle Daten liegen in derselben SQLite-Datei wie Vorgänge und Dokumente.
"""
import json
import os
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


def migrate_4(db):
    """Posteingang: ein interner Vorgang trägt noch nicht zugeordnete Dokumente. Dokumentdatum je Dokument."""
    for table, column in (("vorgang", "system"), ("dokument", "dokument_datum")):
        if column not in _columns(db, table):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    db.execute("CREATE TABLE IF NOT EXISTS einstellung(schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL)")
    if not db.execute("SELECT 1 FROM vorgang WHERE system='posteingang'").fetchone():
        db.execute("""INSERT INTO vorgang(titel,bereich,beschreibung,status,system)
            VALUES('Posteingang','Anderes','Interner Vorgang für noch nicht zugeordnete Dokumente','Offen','posteingang')""")
    db.execute("DELETE FROM suche WHERE art='vorgang' AND ref_id=(SELECT id FROM vorgang WHERE system='posteingang')")


def migrate_6(db):
    """Briefangaben eines Entwurfs (Empfänger, Betreff, Zeichen, Anlagen) als JSON am Eintrag."""
    if "brief" not in _columns(db, "eintrag"):
        db.execute("ALTER TABLE eintrag ADD COLUMN brief TEXT")


def _brief(value):
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("Briefangaben: ungültig.")
    erlaubt = {"empfaenger": 600, "betreff": 300, "zeichen": 120, "bezug_datum": 20, "datum": 20}
    brief = {k: _text(value.get(k), k, n) for k, n in erlaubt.items() if value.get(k)}
    anlagen = value.get("anlagen") or []
    if not isinstance(anlagen, list) or len(anlagen) > 30:
        raise ValueError("Anlagen: ungültige Liste.")
    brief["anlagen"] = [_text(a, "Anlage", 200, True) for a in anlagen]
    return json.dumps(brief, ensure_ascii=False)


# --- Vorschläge für den Posteingang ------------------------------------------------------
MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
          "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}
_DATUM = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})\b")
_DATUM_LANG = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(MONATE) + r")\s+(\d{4})\b", re.I)
_KEIN_DOKUMENTDATUM = re.compile(r"\b(bis|frist|fällig|zahlbar|spätestens|vom)\b", re.I)
_ALLGEMEIN = {"versicherung", "gmbh", "steuerberatung", "ingenieurbüro", "autohaus", "finanzamt", "kanzlei",
              "köln", "berlin", "mitte", "solutions"}
_REF_LABEL = re.compile(r"(aktenzeichen|az\.|ihr zeichen|unser zeichen|schaden-?\s?(?:nummer|nr\.?)|"
                        r"kunden-?\s?(?:nummer|nr\.?)|rechnungs-?\s?(?:nummer|nr\.?)|vertrags-?\s?(?:nummer|nr\.?)|"
                        r"versicherungs-?\s?(?:nummer|nr\.?)|steuer-?\s?(?:nummer|nr\.?)|HR[AB])\s*[:.]?\s*"
                        r"([A-Z0-9][A-Z0-9/.\-]{2,24})", re.I)


def flach(text):
    """Ohne Leerraum, Bindestriche und Trennzeichen – gleicht OCR-Eigenheiten aus (Idee aus Tender AI)."""
    return re.sub(r"[\s\u00ad\-_–/.]+", "", (text or "").lower())


def daten_in(zeile):
    gefunden = []
    for t, m, j in _DATUM.findall(zeile):
        j = "20" + j if len(j) == 2 else j
        try:
            gefunden.append(date(int(j), int(m), int(t)).isoformat())
        except ValueError:
            pass
    for t, mon, j in _DATUM_LANG.findall(zeile):
        try:
            gefunden.append(date(int(j), MONATE[mon.lower()], int(t)).isoformat())
        except ValueError:
            pass
    return gefunden


# --- Fristen aus dem Text ------------------------------------------------------------------
_DATUM_TEIL = r"(\d{1,2}\.\s?\d{1,2}\.\s?(?:\d{4}|\d{2})|\d{1,2}\.\s*(?:" + "|".join(MONATE) + r")\s+\d{4})"
# Nur die eindeutige Formulierung „bis zum <Datum>“ (auch „bis spätestens zum“, „spätestens bis zum“) gilt als Frist.
# Beliebige Datumsangaben im Text werden bewusst nicht vorgeschlagen.
_FRIST_ABSOLUT = re.compile(r"\b(?:spätestens\s+)?bis\s+(?:spätestens\s+)?zum\s+" + _DATUM_TEIL, re.I)
_ZAHLWORT = {"einem": 1, "einer": 1, "eines": 1, "ein": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
             "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "zwölf": 12, "vierzehn": 14, "einundzwanzig": 21,
             "dreißig": 30}
_FRIST_RELATIV = re.compile(
    r"\b(?:innerhalb|binnen)\s+(?:von\s+|der\s+nächsten\s+)?(\d{1,3}|" + "|".join(_ZAHLWORT) + r")\s+"
    r"(tag\w*|woche\w*|monat\w*)", re.I)
_FRIST_THEMA = (("Stellungnahme", r"stellungnahme|äußern|stellung\s+nehmen"),
                ("Zahlung", r"zahl|überweis|begleich|betrag|ausgleich"),
                ("Widerspruch", r"widerspruch|einspruch|klage|rechtsbehelf"),
                ("Unterlagen einreichen", r"einreich|vorleg|nachreich|übersend|zusend|unterlagen|nachweis"),
                ("Rückmeldung", r"rückmeld|antwort|mitteil|bestätig|melden"))


def _plus(start, menge, einheit):
    einheit = einheit.lower()
    if einheit.startswith("tag"):
        return start + timedelta(days=menge)
    if einheit.startswith("woche"):
        return start + timedelta(weeks=menge)
    monat = start.month - 1 + menge
    jahr, monat = start.year + monat // 12, monat % 12 + 1
    for tag in (start.day, 30, 29, 28):
        try:
            return date(jahr, monat, tag)
        except ValueError:
            continue


def fristen_erkennen(seiten, dokument_datum=None, heute=None):
    """Erkennt Fristen der Form „bis zum 16.12.2026“ (auch „bis spätestens zum …“). Liefert Vorschläge mit Datum,
    Titel, Seite und Zitat. Vergangene Daten und alle anderen Datumsangaben werden übergangen."""
    basis = date.fromisoformat(dokument_datum) if dokument_datum else date.fromisoformat(heute or date.today().isoformat())
    gefunden, gesehen = [], set()
    for seite in seiten:
        text = re.sub(r"\s+", " ", seite.get("text") or "")
        for m, daten in [(m, daten_in(m.group(1))) for m in _FRIST_ABSOLUT.finditer(text)]:
            if not daten or daten[0] < basis.isoformat() or daten[0] in gesehen:
                continue
            gesehen.add(daten[0])
            punkt = text.rfind(". ", 0, m.start())
            anfang = max(punkt + 2 if punkt >= 0 else 0, m.start() - 160)
            ende = text.find(". ", m.end())
            ende = min(ende + 1 if ende >= 0 else len(text), m.end() + 160)
            zitat = text[anfang:ende].strip()
            umfeld = text[max(0, m.start() - 160):m.end() + 60].lower()
            titel = next((t for bereich in (zitat.lower(), umfeld) for t, muster in _FRIST_THEMA
                          if re.search(muster, bereich)), "Frist")
            gefunden.append({"faellig_am": daten[0], "titel": titel, "seite": seite.get("nummer") or 1,
                             "zitat": zitat[:480], "relativ": False})
    return sorted(gefunden, key=lambda f: f["faellig_am"])[:6]


_PLZ_ORT = re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][\wäöüß\-.]+")
_TRENNER = re.compile(r"\s+[·•|–]\s+|\s+-\s+|\s{3,}|,\s+")
_BEHOERDE = re.compile(
    r"\b(Amtsgericht|Landgericht|Oberlandesgericht|Sozialgericht|Arbeitsgericht|Verwaltungsgericht|Finanzgericht|"
    r"Registergericht|Finanzamt|Hauptzollamt|Jobcenter|Familienkasse|Bürgeramt|Standesamt|Ordnungsamt|"
    r"Straßenverkehrsamt|Landratsamt|Stadtverwaltung|Gemeindeverwaltung)(?:e?s)?\s+"
    r"([A-ZÄÖÜ][\wäöüß]+(?:[- ](?:an der |am |im )?[A-ZÄÖÜ][\wäöüß]+)?)")
_ORGANISATION = re.compile(
    r"\b(GmbH|AG|KG|OHG|e\.\s?V\.|eG|mbH|SE|Versicherung|Bank|Sparkasse|Kasse|Kanzlei|Rechtsanw|Steuerberat|"
    r"Notar|Verwaltung|Stadtwerke|Werke|Verlag|Institut|Universität|Klinik|Praxis|Hausverwaltung|Vermietung|Amt)\b", re.I)
_GRUSS = re.compile(r"^(mit freundlichen grüßen|freundliche grüße|mit besten grüßen|hochachtungsvoll|viele grüße)", re.I)


_ANREDE_ZEILE = re.compile(r"^(firma|herrn?|frau|an|eheleute|familie)\.?$", re.I)
_STRASSE = re.compile(r"^\d|\b(str(aße|asse|\.)|weg|platz|allee|ring|gasse|damm|ufer|chaussee)\b|\s\d+\s?[a-z]?$", re.I)


def empfaenger_erkennen(text, zulaessig=()):
    """Empfänger eines Schreibens. Zuerst die in den Einstellungen hinterlegten zulässigen Empfänger (wer zuerst im
    Kopf des Schreibens steht), sonst der Name im Anschriftenfeld über „PLZ Ort“, bei E-Mails die Zeile „An:“."""
    zeilen = [re.sub(r"\s+", " ", z).strip() for z in (text or "").splitlines() if z.strip()][:40]
    kopf = flach("\n".join(zeilen))
    treffer = sorted((kopf.find(flach(z)), z) for z in zulaessig if len(flach(z)) >= 4 and flach(z) in kopf)
    if treffer:
        return treffer[0][1]
    m = re.search(r"^An:\s*(.+)$", text or "", re.M)
    if m:
        name = re.sub(r"\s*<[^>]+>", "", m[1]).split(",")[0].strip().strip('"')
        return (name or m[1].strip())[:160]
    for i, z in enumerate(zeilen):
        if not re.match(r"^\d{5}\s+[A-ZÄÖÜ]", z) or re.search(r"[,·|]", z):
            continue
        block = []
        for j in range(i - 1, max(-1, i - 7), -1):
            vor = zeilen[j]
            if re.search(r"[·|]|,\s*\d{5}", vor) or _DATUM.search(vor):
                break  # Absenderzeile oder Datum beendet das Anschriftenfeld
            block.insert(0, vor)
        namen = [b for b in block if not _STRASSE.search(b) and not _ANREDE_ZEILE.match(b)
                 and not b.lower().startswith(("z.h", "z. h", "zh.", "zu händen", "postfach"))]
        if namen:
            return re.sub(r"^(Herrn?|Frau|Firma)\s+", "", namen[0])[:160]
    return None


def absender_erkennen(text, eigene=()):
    """Sucht den Absender dort, wo er in einem Schreiben steht: Absenderzeile über der Anschrift,
    Behörde oder Gericht im Briefkopf, Organisation in der ersten Zeile, Name unter der Grußformel.
    Eigene Angaben (Einstellungen) werden nie als Absender vorgeschlagen."""
    zeilen = [re.sub(r"\s+", " ", z).strip() for z in (text or "").splitlines() if z.strip()]
    eigen = [flach(e) for e in eigene if len(flach(e)) >= 4]
    ist_eigen = lambda z: any(e in flach(z) for e in eigen)
    if zeilen and (m := re.match(r"^Von:\s*(.+?)(?:\s*<([^>]+)>)?$", zeilen[0])):  # übernommene E-Mail
        if not ist_eigen(zeilen[0]):
            return {"name": m[1].strip(), "anschrift": None, "quelle": "E-Mail-Absender", "email": m[2] or
                    (m[1] if "@" in m[1] else None)}
    for z in zeilen[:15]:  # DIN-5008-Absenderzeile: „Firma · Straße 1 · 12345 Ort“
        if _PLZ_ORT.search(z) and _TRENNER.search(z) and len(z) <= 160 and not ist_eigen(z):
            teile = [t.strip() for t in _TRENNER.split(z) if t.strip()]
            if len(teile) >= 2 and not re.match(r"^\d", teile[0]) and not _PLZ_ORT.search(teile[0]):
                return {"name": teile[0], "anschrift": "\n".join(teile), "quelle": "Absenderzeile"}
    for z in zeilen[:20]:  # Behörde oder Gericht, auch im Genitiv („des Amtsgerichts Rostock“)
        m = _BEHOERDE.search(z)
        if m and not ist_eigen(z):
            return {"name": f"{m[1]} {m[2]}", "anschrift": None, "quelle": "Behörde im Briefkopf"}
    for i, z in enumerate(zeilen[:6]):  # Organisation im Briefkopf, Anschrift aus den Folgezeilen
        if _ORGANISATION.search(z) and len(z) <= 90 and not ist_eigen(z) and not re.match(r"^(betreff|ihr|unser)", z, re.I):
            anschrift = [z]
            for f in zeilen[i + 1:i + 4]:
                anschrift.append(f)
                if _PLZ_ORT.search(f):
                    break
            return {"name": z, "anschrift": "\n".join(anschrift) if _PLZ_ORT.search(anschrift[-1]) else None,
                    "quelle": "Briefkopf"}
    for i, z in enumerate(zeilen):  # Unter der Grußformel
        if _GRUSS.match(z):
            for f in zeilen[i + 1:i + 4]:
                if _ORGANISATION.search(f) and not ist_eigen(f):
                    return {"name": f, "anschrift": None, "quelle": "Grußformel"}
    return None


def dokumentdatum(text):
    """Datum des Schreibens, nicht eine darin genannte Frist."""
    zeilen = [re.sub(r"\s+", " ", z).strip() for z in text.splitlines() if z.strip()]
    for z in zeilen[:30]:
        if _KEIN_DOKUMENTDATUM.search(z):
            continue
        d = daten_in(z)
        if d and (len(z) < 45 or re.match(r"datum", z, re.I) or re.search(r",\s*(den\s*)?\d", z)):
            return d[0], "Datumszeile"
    for z in zeilen:
        if not re.search(r"\b(bis|frist|fällig|zahlbar|spätestens)\b", z, re.I) and daten_in(z):
            return daten_in(z)[0], "erstes Datum im Text"
    return None, None


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
                LEFT JOIN vorgang v ON v.bereich=b.name COLLATE NOCASE AND v.geloescht_am IS NULL AND v.system IS NULL
                GROUP BY b.id ORDER BY coalesce(b.reihenfolge, b.id), b.id""")]

    def bereiche_sortieren(self, namen):
        """Neue Reihenfolge der Bereiche (vollständige Liste der Namen)."""
        if not isinstance(namen, list) or sorted(namen) != sorted(self.bereich_namen()):
            raise ValueError("Bitte alle Bereiche in der neuen Reihenfolge angeben.")
        with closing(self.connect()) as db, db:
            db.executemany("UPDATE bereich SET reihenfolge=? WHERE name=?", ((i, n) for i, n in enumerate(namen, 1)))
        return {"ok": True}

    def bereich_namen(self):
        return [b["name"] for b in self.bereiche()]

    def bereich_anlegen(self, name):
        name = _text(name, "Bereich", 80, True)
        with closing(self.connect()) as db, db:
            try:
                db.execute("INSERT INTO bereich(name,reihenfolge) VALUES(?,(SELECT coalesce(max(reihenfolge),0)+1 FROM bereich))", (name,))
            except sqlite3.IntegrityError:
                raise ValueError("Diesen Bereich gibt es schon.") from None
        return name

    def bereich_umbenennen(self, alt, neu):
        neu = _text(neu, "Bereich", 80, True)
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE bereich SET name=? WHERE name=?", (neu, alt)).rowcount:
                raise ValueError("Bereich nicht gefunden.")
            db.execute("UPDATE vorgang SET bereich=? WHERE bereich=?", (neu, alt))
            for tabelle in ("vorgang_bereich", "dokument_bereich"):
                db.execute(f"UPDATE OR IGNORE {tabelle} SET bereich=? WHERE bereich=?", (neu, alt))
                db.execute(f"DELETE FROM {tabelle} WHERE bereich=?", (alt,))

    def bereich_entfernen(self, name):
        with closing(self.connect()) as db, db:
            if db.execute("SELECT 1 FROM vorgang WHERE bereich=? AND geloescht_am IS NULL AND system IS NULL",
                          (name,)).fetchone():
                raise ValueError("Der Bereich enthält noch Vorgänge.")
            if not db.execute("DELETE FROM bereich WHERE name=?", (name,)).rowcount:
                raise ValueError("Bereich nicht gefunden.")
            db.execute("DELETE FROM vorgang_bereich WHERE bereich=?", (name,))
            db.execute("DELETE FROM dokument_bereich WHERE bereich=?", (name,))

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
        if not row or row["system"] or (row["geloescht_am"] and not deleted_ok):
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
        if "prioritaet" in data:
            felder["prioritaet"] = _choice(data["prioritaet"] or "keine", ("keine", "hoch", "sehr hoch"), "Priorität")
        bereiche = self._bereiche(data["bereiche"], True) if "bereiche" in data else None
        if bereiche:
            felder["bereich"] = bereiche[0]  # erster = Hauptbereich (Listen, Gruppierung)
        kontakte = self._kontakt_ids(data["kontakte"]) if "kontakte" in data else None
        if not felder and kontakte is None:
            raise ValueError("Keine Änderung angegeben.")
        with closing(self.connect()) as db, db:
            self._vorgang(db, vorgang_id)
            if felder:
                db.execute(f"UPDATE vorgang SET {','.join(k + '=?' for k in felder)} WHERE id=?",
                           (*felder.values(), vorgang_id))
            if bereiche is not None or "bereich" in felder:
                db.execute("DELETE FROM vorgang_bereich WHERE vorgang_id=?", (vorgang_id,))
                db.executemany("INSERT OR IGNORE INTO vorgang_bereich(vorgang_id,bereich) VALUES(?,?)",
                               ((vorgang_id, b) for b in (bereiche or [felder["bereich"]])))
            if kontakte is not None:  # Beteiligte: fehlende hinzufügen, abgewählte entfernen
                vorhanden = {r[0] for r in db.execute("SELECT kontakt_id FROM beteiligter WHERE vorgang_id=?", (vorgang_id,))}
                for k in kontakte:
                    if k not in vorhanden:
                        db.execute("INSERT INTO beteiligter(vorgang_id,kontakt_id,rolle) VALUES(?,?,'')", (vorgang_id, k))
                for k in vorhanden - set(kontakte):
                    db.execute("DELETE FROM beteiligter WHERE vorgang_id=? AND kontakt_id=?", (vorgang_id, k))

    def _bereiche(self, werte, pflicht):
        if not isinstance(werte, list):
            raise ValueError("Bereiche: ungültige Liste.")
        namen, gueltig = [], set(self.bereich_namen())
        for b in werte:
            if b not in gueltig:
                raise ValueError(f"Unbekannter Bereich: {b}")
            if b not in namen:
                namen.append(b)
        if pflicht and not namen:
            raise ValueError("Bitte mindestens einen Bereich wählen.")
        return namen

    def _kontakt_ids(self, werte):
        if not isinstance(werte, list):
            raise ValueError("Kontakte: ungültige Liste.")
        ids = []
        with closing(self.connect()) as db:
            for w in werte:
                k = _id(w, "Kontakt")
                if not k or not db.execute("SELECT 1 FROM kontakt WHERE id=? AND geloescht_am IS NULL", (k,)).fetchone():
                    raise ValueError("Kontakt nicht gefunden.")
                if k not in ids:
                    ids.append(k)
        return ids

    def akte(self, vorgang_id):
        """Die vollständige Vorgangsakte in einem Abruf."""
        with closing(self.connect()) as db:
            v = dict(self._vorgang(db, vorgang_id))
            q = lambda sql, *a: [dict(r) for r in db.execute(sql, a)]
            v["teilvorgaenge"] = q("SELECT * FROM teilvorgang WHERE vorgang_id=? ORDER BY reihenfolge,id", vorgang_id)
            v["bereiche"] = [v["bereich"]] + [r["bereich"] for r in q(
                "SELECT bereich FROM vorgang_bereich WHERE vorgang_id=? AND bereich<>? ORDER BY bereich", vorgang_id, v["bereich"])]
            v["schlagwoerter"] = [r["name"] for r in q("""SELECT s.name FROM vorgang_schlagwort vs
                JOIN schlagwort s ON s.id=vs.schlagwort_id WHERE vs.vorgang_id=? ORDER BY s.name""", vorgang_id)]
            v["beteiligte"] = q("""SELECT b.kontakt_id, b.rolle, k.name, k.kurzname, k.typ FROM beteiligter b
                JOIN kontakt k ON k.id=b.kontakt_id WHERE b.vorgang_id=? ORDER BY k.name""", vorgang_id)
            v["referenzen"] = q("SELECT * FROM referenz WHERE vorgang_id=? ORDER BY id", vorgang_id)
            v["dokumente"] = q("""SELECT d.id,d.titel,d.dateiname,d.titel_seite,d.titel_quelle,d.ocr_status,d.mime,
                (d.ansicht IS NOT NULL) AS gedreht, d.drehung_manuell,
                d.angelegt_am,(SELECT count(*) FROM dokument_vorgang x WHERE x.dokument_id=d.id) AS vorgaenge
                FROM dokument d JOIN dokument_vorgang dv ON dv.dokument_id=d.id
                WHERE dv.vorgang_id=? AND d.geloescht_am IS NULL ORDER BY d.id DESC""", vorgang_id)
            eintraege = q("""SELECT * FROM eintrag WHERE vorgang_id=? AND geloescht_am IS NULL
                ORDER BY ereignis_datum DESC, id DESC""", vorgang_id)
            for e in eintraege:
                e["brief"] = json.loads(e["brief"]) if e.get("brief") else None
                e["teile"] = [r["teilvorgang_id"] for r in q(
                    "SELECT teilvorgang_id FROM eintrag_teil WHERE eintrag_id=? ORDER BY teilvorgang_id", e["id"])]
                # Nacherfasst: Telefonat, Notiz o. Ä. später eingetragen. Ein Brief ist naturgemäß älter als sein Eingang.
                e["nacherfasst"] = not e["dokument_id"] and e["ereignis_datum"] < e["erfasst_am"][:10]
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

    def kontakt_aendern(self, kontakt_id, data):
        """Name, Kurzname, Art und Notiz eines Kontakts ändern."""
        felder = {}
        if "name" in data:
            felder["name"] = _text(data.get("name"), "Name", 160, True)
        for feld, label, laenge in (("kurzname", "Kurzname", 80), ("typ", "Art", 60), ("notiz", "Notiz", 2000)):
            if feld in data:
                felder[feld] = _text(data.get(feld), label, laenge)
        if not felder:
            raise ValueError("Keine Änderung angegeben.")
        with closing(self.connect()) as db, db:
            if not db.execute(f"UPDATE kontakt SET {','.join(k + '=?' for k in felder)} WHERE id=? AND geloescht_am IS NULL",
                              (*felder.values(), kontakt_id)).rowcount:
                raise ValueError("Kontakt nicht gefunden.")
        return {"ok": True}

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
    def eintragsarten(self):
        """Eigene Eintragsarten (z. B. „Besprechung“, „Ortstermin“). Sie werden wie Notizen geführt."""
        with closing(self.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='eintrag_arten'").fetchone()
        return json.loads(row[0]) if row else []

    def eintragsart_anlegen(self, name):
        name = _text(name, "Art", 40, True)
        eingebaut = {"eingang", "versendet", "ausgang", "entwurf", "versandnachweis", "telefonat", "notiz", "entscheidung",
                     "chat-notiz", "chat", "original fehlt"}
        arten = self.eintragsarten()
        if name.lower() in eingebaut or name.lower() in (a.lower() for a in arten):
            raise ValueError("Diese Art gibt es schon.")
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('eintrag_arten',?)",
                       (json.dumps(arten + [name], ensure_ascii=False),))
        return name

    def eintragsart_entfernen(self, name):
        """Entfernt die Art aus der Auswahl; bestehende Einträge behalten ihre Bezeichnung."""
        arten = [a for a in self.eintragsarten() if a != name]
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('eintrag_arten',?)",
                       (json.dumps(arten, ensure_ascii=False),))
        return {"ok": True}

    def _typ(self, wert):
        if not wert:
            return None
        if wert not in self.eintragsarten():
            raise ValueError("Unbekannte Eintragsart.")
        return wert

    def eintrag_anlegen(self, vorgang_id, data):
        typ = self._typ(data.get("typ"))
        art = _choice(data.get("art") or ("notiz" if typ else None), EINTRAG_ARTEN, "Art")
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
                dokument_id,bezug_id,text,quelle,geprueft,brief,typ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (vorgang_id, art, titel, datum, richtung, _id(data.get("kontakt_id"), "Kontakt"), dok,
                 _id(data.get("bezug_id"), "Bezug"), _text(data.get("text"), "Text", 20000),
                 _text(data.get("quelle"), "Quelle", 300), 1 if data.get("geprueft") else 0,
                 _brief(data.get("brief")), typ)).lastrowid
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
            if "brief" in data:
                felder["brief"] = _brief(data["brief"])
            if "typ" in data:
                felder["typ"] = self._typ(data["typ"])
            if "art" in data:  # nur zwischen Arten ohne eigene Abläufe (Brief, Versand, Chat bleiben, wie sie sind)
                frei = ("eingang", "ausgang", "telefonat", "notiz", "entscheidung", "fehlt")
                if e["art"] not in frei:
                    raise ValueError("Die Art dieses Eintrags lässt sich nicht ändern.")
                felder["art"] = _choice(data["art"], frei, "Art")
            if "dokument_id" in data:  # Dokument zuweisen oder lösen; es muss zum Vorgang gehören
                dok = _id(data["dokument_id"], "Dokument")
                if dok and not db.execute("SELECT 1 FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?",
                                          (dok, e["vorgang_id"])).fetchone():
                    raise ValueError("Das Dokument gehört nicht zu diesem Vorgang.")
                felder["dokument_id"] = dok
                if dok and e["art"] == "fehlt" and "art" not in data:  # fehlendes Original ist jetzt da
                    felder["art"] = "eingang"
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
                bezug_id,text,brief) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (e["vorgang_id"], "ausgang", _text(data.get("titel"), "Titel", 200) or e["titel"], datum, "an",
                 e["kontakt_id"], e["dokument_id"], e["bezug_id"], e["text"], e["brief"])).lastrowid
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
            for typ, sql in (("vorgang", "SELECT id, titel AS bezeichnung, geloescht_am, NULL AS vorgang FROM vorgang "
                                         "WHERE system IS NULL AND 1"),
                             ("dokument", "SELECT id, titel, geloescht_am, NULL FROM dokument"),
                             ("eintrag", "SELECT e.id, e.titel, e.geloescht_am, v.titel FROM eintrag e "
                                         "JOIN vorgang v ON v.id=e.vorgang_id"),
                             ("frist", "SELECT f.id, f.titel, f.geloescht_am, v.titel FROM frist f "
                                       "JOIN vorgang v ON v.id=f.vorgang_id"),
                             ("kontakt", "SELECT id, name, geloescht_am, NULL FROM kontakt")):
                alias = "e." if typ == "eintrag" else "f." if typ == "frist" else ""
                verbinder = " AND " if " WHERE " in sql else " WHERE "
                for r in db.execute(sql + f"{verbinder}{alias}geloescht_am IS NOT NULL"):
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

    # --- Posteingang ------------------------------------------------------------------------
    def posteingang(self):
        """Noch nicht zugeordnete Dokumente mit Vorschlägen für Datum, Absender, Referenz und Vorgang."""
        with closing(self.connect()) as db:
            rows = [dict(r) for r in db.execute("""SELECT d.id,d.titel,d.titel_quelle,d.titel_seite,d.dateiname,d.mime,
                d.dateipfad,d.ocr_status,d.ocr_fehler,d.angelegt_am,d.dokument_datum,d.datei_datum,d.drehung_manuell FROM dokument d
                JOIN vorgang v ON v.id=d.vorgang_id AND v.system='posteingang'
                WHERE d.geloescht_am IS NULL ORDER BY d.id DESC""")]
            for r in rows:
                datei = self.store.uploads / r.pop("dateipfad")
                r["groesse"] = datei.stat().st_size if datei.is_file() else None
                seiten = [dict(s) for s in db.execute(
                    "SELECT nummer,methode,text FROM dokumentseite WHERE dokument_id=? ORDER BY nummer", (r["id"],))]
                r["seiten"] = seiten
                r["vorschlag"] = self._vorschlag(db, "\n".join(s["text"] for s in seiten))
                if not r["vorschlag"]["datum"] and r["datei_datum"]:  # kein Datum im Text: Erstellungsdatum der Datei
                    r["vorschlag"]["datum"], r["vorschlag"]["datum_quelle"] = r["datei_datum"], "Erstellungsdatum der Datei"
                r["vorschlag"]["fristen"] = fristen_erkennen(seiten, r["vorschlag"]["datum"], self.today())
            return rows

    def oberflaeche(self):
        """Einstellungen der Oberfläche, z. B. Darstellung der Filter (chips = untereinander, menue = Ausklappmenüs)."""
        with closing(self.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='oberflaeche'").fetchone()
        return {"filteransicht": "chips", **(json.loads(row[0]) if row else {})}

    def oberflaeche_setzen(self, data):
        werte = self.oberflaeche()
        if "filteransicht" in data:
            werte["filteransicht"] = _choice(data["filteransicht"], ("chips", "menue"), "Filteransicht")
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('oberflaeche',?)", (json.dumps(werte),))
        return werte

    def empfaenger_liste(self):
        with closing(self.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='empfaenger'").fetchone()
        return json.loads(row[0]) if row else []

    def empfaenger_setzen(self, namen):
        if not isinstance(namen, list):
            raise ValueError("Empfänger: ungültige Liste.")
        liste = []
        for n in namen:
            n = _text(n, "Empfänger", 160)
            if n and n not in liste:
                liste.append(n)
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('empfaenger',?)", (json.dumps(liste, ensure_ascii=False),))
            # Dokumente ohne bisher passenden Empfänger neu zuordnen (von Hand gesetzte bleiben)
            for d in db.execute("""SELECT d.id, group_concat(s.text, char(10)) AS text FROM dokument d
                JOIN dokumentseite s ON s.dokument_id=d.id AND s.nummer=1 WHERE coalesce(d.empfaenger_quelle,'')<>'manuell'
                GROUP BY d.id""").fetchall():
                db.execute("UPDATE dokument SET empfaenger=? WHERE id=?", (empfaenger_erkennen(d["text"], liste), d["id"]))
        return {"empfaenger": liste}

    def eigene_angaben(self):
        with closing(self.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='eigene_angaben'").fetchone()
            return row[0] if row else ""

    def eigene_angaben_setzen(self, wert):
        wert = _text(wert, "Eigene Angaben", 1000) or ""
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('eigene_angaben',?)", (wert,))

    def _vorschlag(self, db, text):
        datum, datum_quelle = dokumentdatum(text)
        eigene = (db.execute("SELECT wert FROM einstellung WHERE schluessel='eigene_angaben'").fetchone() or [""])[0]
        absender = absender_erkennen(text, eigene.splitlines())
        if absender:
            # Ein erkannter Absender entscheidet. Bekannte Kontakte werden über den Namen zugeordnet.
            name = flach(absender["name"])
            absender["kontakt"] = None
            domain = (absender.get("email") or "").split("@")[-1].lower() if absender.get("email") else ""
            for k in db.execute("SELECT id,name,kurzname FROM kontakt WHERE geloescht_am IS NULL"):
                namen = [flach(k["name"]), flach(k["kurzname"] or "")]
                mails = [r[0].lower() for r in db.execute(
                    "SELECT email FROM kontakt_abteilung WHERE kontakt_id=? AND email LIKE '%@%'", (k["id"],))]
                if any(len(n) >= 4 and (n in name or name in n) for n in namen) or \
                        (domain and any(m.endswith("@" + domain) for m in mails)):
                    absender["kontakt"] = dict(k)
                    break
            return self._vorschlag_mit(db, text, datum, datum_quelle, absender["kontakt"], absender)
        unten, kopf = text.lower(), "\n".join(text.splitlines()[:15]).lower()
        ganz, kopf_flach = flach(text), flach(kopf)
        bester, punkte = None, 0
        for k in db.execute("SELECT id,name,kurzname FROM kontakt WHERE geloescht_am IS NULL"):
            p = 5 if k["name"].lower() in unten or flach(k["name"]) in ganz else 0
            for w in re.split(r"[\s\-]+", (k["name"] + " " + (k["kurzname"] or "")).lower()):
                if len(w) >= 4 and w not in _ALLGEMEIN:
                    p += 3 if (w in kopf or flach(w) in kopf_flach) else 1 if w in unten else 0
            for (mail,) in db.execute("SELECT email FROM kontakt_abteilung WHERE kontakt_id=? AND email LIKE '%@%'",
                                      (k["id"],)):
                if mail.split("@", 1)[1].lower() in unten:
                    p += 4
            if p > punkte:
                bester, punkte = k, p
        kontakt = dict(bester) if bester and punkte >= 3 else None
        return self._vorschlag_mit(db, text, datum, datum_quelle, kontakt, None)

    def _vorschlag_mit(self, db, text, datum, datum_quelle, kontakt, absender):
        ganz = flach(text)
        vorschlaege, gesehen = [], set()
        for r in db.execute("""SELECT r.bezeichnung,r.wert,r.vorgang_id,v.titel FROM referenz r JOIN vorgang v
            ON v.id=r.vorgang_id WHERE v.geloescht_am IS NULL AND v.system IS NULL AND v.status<>'Erledigt'"""):
            if len(flach(r["wert"])) >= 4 and flach(r["wert"]) in ganz and r["vorgang_id"] not in gesehen:
                gesehen.add(r["vorgang_id"])
                vorschlaege.append({"vorgang_id": r["vorgang_id"], "titel": r["titel"],
                                    "grund": f"{r['bezeichnung']} {r['wert']} im Text"})
        if kontakt:
            for r in db.execute("""SELECT v.id,v.titel FROM beteiligter b JOIN vorgang v ON v.id=b.vorgang_id
                WHERE b.kontakt_id=? AND v.geloescht_am IS NULL AND v.status<>'Erledigt' ORDER BY v.id DESC""", (kontakt["id"],)):
                if r["id"] not in gesehen:
                    gesehen.add(r["id"])
                    vorschlaege.append({"vorgang_id": r["id"], "titel": r["titel"],
                                        "grund": f"{kontakt['kurzname'] or kontakt['name']} ist beteiligt"})
        referenz = next(((m[0], m[1].rstrip(".-")) for m in _REF_LABEL.findall(text) if re.search(r"\d", m[1])), None)
        return {"datum": datum, "datum_quelle": datum_quelle, "kontakt": kontakt, "absender": absender,
                "referenz": {"bezeichnung": referenz[0], "wert": referenz[1]} if referenz else None,
                "vorgaenge": vorschlaege[:4]}

    def zuordnen(self, dokument_id, data):
        """Ordnet ein Dokument aus dem Posteingang einem Vorgang zu und legt den Eingang in der Chronik an."""
        ablage = bool(data.get("ablage"))  # direkt ins Archiv, ohne Vorgang
        vorgang_id = None if ablage else _id(data.get("vorgang_id"), "Vorgang")
        if not vorgang_id and not ablage:
            raise ValueError("Bitte einen Vorgang wählen.")
        fristen = []
        for f in data.get("fristen") or []:  # beim Zuordnen übernommene Fristen (erkannt oder von Hand)
            if not isinstance(f, dict):
                raise ValueError("Fristen: ungültige Angabe.")
            fristen.append({"art": f.get("art") or "frist", "titel": _text(f.get("titel"), "Frist", 200, True),
                            "faellig_am": _date(f.get("faellig_am"), "Frist"), "quelle_seite": f.get("seite"),
                            "quelle_zitat": _text(f.get("zitat"), "Fundstelle", 500) or "Beim Zuordnen festgelegt"})
        if ablage and fristen:
            raise ValueError("Fristen lassen sich nur in einem Vorgang führen. Bitte einen Vorgang wählen.")
        with closing(self.connect()) as db, db:
            d = db.execute("""SELECT d.* FROM dokument d JOIN vorgang v ON v.id=d.vorgang_id AND v.system='posteingang'
                WHERE d.id=? AND d.geloescht_am IS NULL""", (dokument_id,)).fetchone()
            if not d:
                raise ValueError("Das Dokument liegt nicht im Posteingang.")
            if ablage:
                vorgang_id = self._ablage(db)
                teile = []
            else:
                self._vorgang(db, vorgang_id)
                teile = self._teile(db, vorgang_id, data.get("teile"))
            titel = _text(data.get("titel"), "Titel", 160) or d["titel"]
            datum = _date(data.get("datum"), "Dokumentdatum", False)
            kontakt = _id(data.get("kontakt_id"), "Absender")
            neu = data.get("neuer_absender")
            if neu and not kontakt:  # Erkannten Absender als Kontakt im Adressbuch anlegen
                if not isinstance(neu, dict):
                    raise ValueError("Absender: ungültige Angabe.")
                kontakt = db.execute("INSERT INTO kontakt(name) VALUES(?)",
                                     (_text(neu.get("name"), "Absender", 160, True),)).lastrowid
                self._abteilung(db, kontakt, {"anschrift": neu.get("anschrift")})
            db.execute("UPDATE dokument SET vorgang_id=?, dokument_datum=? WHERE id=?", (vorgang_id, datum, dokument_id))
            if titel != d["titel"]:
                db.execute("UPDATE dokument SET titel=?, titel_seite=NULL, titel_quelle='Manuell' WHERE id=?",
                           (titel, dokument_id))
            db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)",
                       (dokument_id, vorgang_id))
            if kontakt and not db.execute("SELECT 1 FROM beteiligter WHERE vorgang_id=? AND kontakt_id=?",
                                          (vorgang_id, kontakt)).fetchone():
                db.execute("INSERT INTO beteiligter(vorgang_id,kontakt_id,rolle) VALUES(?,?,'')", (vorgang_id, kontakt))
            eid = db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,richtung,kontakt_id,dokument_id)
                VALUES(?,?,?,?,?,?,?)""", (vorgang_id, "eingang", titel, datum or self.today(),
                                           "von" if kontakt else None, kontakt, dokument_id)).lastrowid
            db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((eid, t) for t in teile))
            try:  # Anlagen einer übernommenen E-Mail wandern mit, sofern sie noch im Posteingang liegen
                anlagen = db.execute("""SELECT d.id, d.titel FROM mail_anlage ma
                    JOIN mail_import mi ON mi.message_id=ma.message_id JOIN dokument d ON d.id=ma.dokument_id
                    JOIN vorgang v ON v.id=d.vorgang_id AND v.system='posteingang'
                    WHERE mi.dokument_id=? AND d.geloescht_am IS NULL""", (dokument_id,)).fetchall()
            except sqlite3.OperationalError:
                anlagen = []
            for a in anlagen:
                db.execute("UPDATE dokument SET vorgang_id=? WHERE id=?", (vorgang_id, a["id"]))
                db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)", (a["id"], vorgang_id))
                aid = db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,richtung,kontakt_id,dokument_id,
                    bezug_id) VALUES(?,?,?,?,?,?,?,?)""", (vorgang_id, "eingang", a["titel"], datum or self.today(),
                                                         "von" if kontakt else None, kontakt, a["id"], eid)).lastrowid
                db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((aid, t) for t in teile))
        for f in fristen:
            self.frist_anlegen(vorgang_id, {**f, "quelle_dokument_id": dokument_id,
                                            "teilvorgang_id": teile[0] if len(teile) == 1 else None})
        return eid

    def dokument_entfernen(self, dokument_id, vorgang_id):
        """Entfernt ein Dokument aus einem Vorgang. Gehört es noch zu weiteren Vorgängen, wird nur die Verknüpfung
        gelöst; sonst kommt es samt Chronik-Eintrag in den Papierkorb."""
        with closing(self.connect()) as db, db:
            if not db.execute("SELECT 1 FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?", (dokument_id, vorgang_id)).fetchone():
                raise ValueError("Das Dokument gehört nicht zu diesem Vorgang.")
            weitere = db.execute("SELECT vorgang_id FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id<>?",
                                 (dokument_id, vorgang_id)).fetchall()
            db.execute("""UPDATE eintrag SET geloescht_am=CURRENT_TIMESTAMP WHERE dokument_id=? AND vorgang_id=?
                AND geloescht_am IS NULL""", (dokument_id, vorgang_id))
            if weitere:
                db.execute("DELETE FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?", (dokument_id, vorgang_id))
                db.execute("UPDATE dokument SET vorgang_id=? WHERE id=? AND vorgang_id=?", (weitere[0][0], dokument_id, vorgang_id))
                return {"papierkorb": False}
            db.execute("UPDATE dokument SET geloescht_am=CURRENT_TIMESTAMP WHERE id=?", (dokument_id,))
            return {"papierkorb": True}

    def posteingang_id_von(self, dokument_id):
        """True, wenn das Dokument (noch) im Posteingang liegt."""
        with closing(self.connect()) as db:
            return bool(db.execute("""SELECT 1 FROM dokument d JOIN vorgang v ON v.id=d.vorgang_id AND v.system='posteingang'
                WHERE d.id=? AND d.geloescht_am IS NULL""", (dokument_id,)).fetchone())

    def ablage_nachtragen(self, dokument_id):
        """Nach der Texterkennung: Bei direkt archivierten Dokumenten Datum, Titel und Absender aus dem Text übernehmen."""
        with closing(self.connect()) as db, db:
            e = db.execute("""SELECT e.id, e.kontakt_id, d.dokument_datum, d.datei_datum, d.titel FROM eintrag e
                JOIN vorgang v ON v.id=e.vorgang_id AND v.system='ablage' JOIN dokument d ON d.id=e.dokument_id
                WHERE e.dokument_id=? AND e.geloescht_am IS NULL""", (dokument_id,)).fetchone()
            if not e:
                return
            text = "\n".join(r[0] for r in db.execute(
                "SELECT text FROM dokumentseite WHERE dokument_id=? ORDER BY nummer", (dokument_id,)))
            if not text.strip():
                return
            v = self._vorschlag(db, text)
            if not v["datum"]:
                v["datum"] = e["datei_datum"]
            db.execute("UPDATE eintrag SET titel=? WHERE id=?", (e["titel"], e["id"]))
            if v["datum"] and not e["dokument_datum"]:
                db.execute("UPDATE dokument SET dokument_datum=? WHERE id=?", (v["datum"], dokument_id))
                db.execute("UPDATE eintrag SET ereignis_datum=? WHERE id=?", (v["datum"], e["id"]))
            if not e["kontakt_id"]:
                kontakt = v["kontakt"]["id"] if v.get("kontakt") else None
                if not kontakt and v.get("absender"):
                    kontakt = db.execute("INSERT INTO kontakt(name) VALUES(?)", (v["absender"]["name"][:160],)).lastrowid
                    self._abteilung(db, kontakt, {"anschrift": v["absender"].get("anschrift")})
                if kontakt:
                    db.execute("UPDATE eintrag SET kontakt_id=?, richtung='von' WHERE id=?", (kontakt, e["id"]))

    def dokument_aendern(self, dokument_id, data):
        """Titel, Dateiname, Dokumentdatum und Absender eines Dokuments ändern (z. B. im Archiv).
        Chronik-Einträge des Dokuments werden mitgeführt; die Originaldatei bleibt unverändert."""
        with closing(self.connect()) as db, db:
            d = db.execute("SELECT * FROM dokument WHERE id=? AND geloescht_am IS NULL", (dokument_id,)).fetchone()
            if not d:
                raise ValueError("Dokument nicht gefunden.")
            if "titel" in data:
                titel = _text(data.get("titel"), "Titel", 160, True)
                if titel != d["titel"]:
                    db.execute("UPDATE dokument SET titel=?, titel_seite=NULL, titel_quelle='Manuell' WHERE id=?", (titel, dokument_id))
                    db.execute("UPDATE eintrag SET titel=? WHERE dokument_id=? AND titel=?", (titel, dokument_id, d["titel"]))
            if "dateiname" in data:
                name = _text(data.get("dateiname"), "Dateiname", 200, True)
                if any(c in name for c in "/\\:") or any(ord(c) < 32 for c in name):
                    raise ValueError("Der Dateiname darf keine Schrägstriche oder Doppelpunkte enthalten.")
                endung = os.path.splitext(d["dateiname"])[1]
                if endung and not name.lower().endswith(endung.lower()):
                    name += endung
                db.execute("UPDATE dokument SET dateiname=? WHERE id=?", (name, dokument_id))
            if "datum" in data:
                datum = _date(data.get("datum"), "Dokumentdatum", False)
                db.execute("UPDATE dokument SET dokument_datum=? WHERE id=?", (datum, dokument_id))
                if datum:
                    db.execute("UPDATE eintrag SET ereignis_datum=? WHERE dokument_id=? AND art='eingang'", (datum, dokument_id))
            if "empfaenger" in data:
                db.execute("UPDATE dokument SET empfaenger=?, empfaenger_quelle='manuell' WHERE id=?",
                           (_text(data.get("empfaenger"), "Empfänger", 160), dokument_id))
            if "bereiche" in data:  # leer = Bereiche des Vorgangs gelten
                bereiche = self._bereiche(data["bereiche"], False)
                db.execute("DELETE FROM dokument_bereich WHERE dokument_id=?", (dokument_id,))
                db.executemany("INSERT INTO dokument_bereich(dokument_id,bereich) VALUES(?,?)", ((dokument_id, b) for b in bereiche))
            if "kontakte" in data:  # weitere Kontakte zusätzlich zum Absender
                kontakte = self._kontakt_ids(data["kontakte"])
                db.execute("DELETE FROM dokument_kontakt WHERE dokument_id=?", (dokument_id,))
                db.executemany("INSERT INTO dokument_kontakt(dokument_id,kontakt_id) VALUES(?,?)", ((dokument_id, k) for k in kontakte))
            if "kontakt_id" in data:
                kontakt = _id(data.get("kontakt_id"), "Absender")
                if kontakt and not db.execute("SELECT 1 FROM kontakt WHERE id=?", (kontakt,)).fetchone():
                    raise ValueError("Absender nicht gefunden.")
                db.execute("UPDATE eintrag SET kontakt_id=?, richtung=? WHERE dokument_id=? AND art='eingang'",
                           (kontakt, "von" if kontakt else None, dokument_id))
        return {"ok": True}

    def dokument_drehen(self, dokument_id, data):
        """Dreht die Anzeige eines Dokuments von Hand um 90° (rechts) oder −90° (links). Das Original bleibt unverändert."""
        grad = data.get("grad")
        if grad not in (90, -90, 180):
            raise ValueError("Drehung: 90, −90 oder 180 Grad.")
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE dokument SET drehung_manuell=(drehung_manuell+?+360)%360 WHERE id=?",
                              (grad, dokument_id)).rowcount:
                raise ValueError("Dokument nicht gefunden.")
            return {"drehung": db.execute("SELECT drehung_manuell FROM dokument WHERE id=?", (dokument_id,)).fetchone()[0]}

    def dokument_fristen(self, dokument_id):
        """Im Text eines Dokuments erkannte Fristen, gerechnet ab Dokumentdatum."""
        with closing(self.connect()) as db:
            d = db.execute("SELECT dokument_datum FROM dokument WHERE id=?", (dokument_id,)).fetchone()
            if not d:
                raise ValueError("Dokument nicht gefunden.")
            seiten = [dict(r) for r in db.execute("SELECT nummer,text FROM dokumentseite WHERE dokument_id=? ORDER BY nummer",
                                                  (dokument_id,))]
        datum = d["dokument_datum"] or dokumentdatum("\n".join(s["text"] for s in seiten))[0]
        return fristen_erkennen(seiten, datum, self.today())

    def _ablage(self, db):
        """Interner, stets erledigter Vorgang für Dokumente, die ohne Vorgang ins Archiv gehen."""
        row = db.execute("SELECT id FROM vorgang WHERE system='ablage'").fetchone()
        if row:
            return row[0]
        vid = db.execute("""INSERT INTO vorgang(titel,bereich,beschreibung,status,system)
            VALUES('Ohne Vorgang','Anderes','Direkt archivierte Dokumente','Erledigt','ablage')""").lastrowid
        db.execute("DELETE FROM suche WHERE art='vorgang' AND ref_id=?", (vid,))
        return vid

    def dokument_verschieben(self, dokument_id, data):
        """Hängt ein Dokument samt Chronik-Eintrag (und mitgekommenen Mail-Anlagen) in einen anderen Vorgang um.
        Ziel ist ein bestehender Vorgang, auch ein erledigter, oder mit `ablage` das Archiv ohne Vorgang."""
        von = _id(data.get("von_vorgang_id"), "Bisheriger Vorgang")
        with closing(self.connect()) as db, db:
            if data.get("ablage"):
                nach = self._ablage(db)
            else:
                nach = _id(data.get("vorgang_id"), "Vorgang")
                if not nach:
                    raise ValueError("Bitte einen Vorgang wählen.")
                self._vorgang(db, nach)
            if not db.execute("SELECT 1 FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?", (dokument_id, von)).fetchone():
                raise ValueError("Das Dokument gehört nicht zu diesem Vorgang.")
            if nach == von:
                return {"vorgang_id": nach}
            eintraege = [r[0] for r in db.execute(
                "SELECT id FROM eintrag WHERE dokument_id=? AND vorgang_id=? AND geloescht_am IS NULL", (dokument_id, von))]
            anlagen = [(r[0], r[1]) for r in db.execute(f"""SELECT id, dokument_id FROM eintrag WHERE vorgang_id=?
                AND dokument_id IS NOT NULL AND geloescht_am IS NULL AND bezug_id IN ({",".join("?" * len(eintraege)) or "NULL"})""",
                (von, *eintraege))]
            dokumente = {dokument_id} | {d for _, d in anlagen}
            bewegt = eintraege + [e for e, _ in anlagen]
            for d in dokumente:
                db.execute("DELETE FROM dokument_vorgang WHERE dokument_id=? AND vorgang_id=?", (d, von))
                db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)", (d, nach))
                db.execute("UPDATE dokument SET vorgang_id=? WHERE id=? AND vorgang_id=?", (nach, d, von))
            marken = ",".join("?" * len(bewegt)) or "NULL"
            # Verweise zwischen bewegten und verbliebenen Einträgen lösen; Teilvorgänge gelten nur im alten Vorgang
            db.execute(f"UPDATE eintrag SET bezug_id=NULL WHERE vorgang_id=? AND bezug_id IN ({marken})", (von, *bewegt))
            db.execute(f"""UPDATE eintrag SET bezug_id=NULL WHERE id IN ({marken})
                AND bezug_id NOT IN ({marken})""", (*bewegt, *bewegt))
            db.execute(f"DELETE FROM eintrag_teil WHERE eintrag_id IN ({marken})", bewegt)
            db.execute(f"UPDATE eintrag SET vorgang_id=? WHERE id IN ({marken})", (nach, *bewegt))
            for (kontakt,) in db.execute(f"SELECT DISTINCT kontakt_id FROM eintrag WHERE id IN ({marken}) AND kontakt_id IS NOT NULL",
                                         bewegt).fetchall():
                if not db.execute("SELECT 1 FROM beteiligter WHERE vorgang_id=? AND kontakt_id=?", (nach, kontakt)).fetchone():
                    db.execute("INSERT INTO beteiligter(vorgang_id,kontakt_id,rolle) VALUES(?,?,'')", (nach, kontakt))
            if not eintraege:  # nur verknüpft, ohne eigenen Eintrag: im Ziel sichtbar machen
                d = db.execute("SELECT titel, dokument_datum, angelegt_am FROM dokument WHERE id=?", (dokument_id,)).fetchone()
                db.execute("INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,dokument_id) VALUES(?,?,?,?,?)",
                           (nach, "eingang", d["titel"], d["dokument_datum"] or d["angelegt_am"][:10], dokument_id))
            ziel = db.execute("SELECT status, system FROM vorgang WHERE id=?", (nach,)).fetchone()
            return {"vorgang_id": nach, "archiviert": ziel["status"] == "Erledigt", "ablage": ziel["system"] == "ablage"}

    def archiv(self):
        """Archivierte Dokumente mit Vorgang, Bereich, Absender und Daten – Grundlage der Archivansicht.

        Archiviert ist ein Dokument erst, wenn es abgeschlossen ist: Der Vorgang steht auf „Erledigt“, oder alle
        Teilvorgänge, denen das Dokument zugeordnet ist, stehen auf „Erledigt“. Wird ein Vorgang wieder
        geöffnet, verlässt das Dokument das Archiv und ist wieder in der Akte in Arbeit."""
        with closing(self.connect()) as db:
            rows = [dict(r) for r in db.execute("""
                SELECT d.id, d.titel, d.dateiname, d.mime, d.dateipfad, d.ocr_status, d.angelegt_am, d.dokument_datum,
                       dv.vorgang_id, v.titel AS vorgang, v.system, (d.ansicht IS NOT NULL) AS gedreht, d.drehung_manuell, d.empfaenger, v.bereich, v.status AS vorgang_status,
                       (SELECT count(*) FROM dokumentseite s WHERE s.dokument_id=d.id) AS seiten,
                       (SELECT e.art FROM eintrag e WHERE e.dokument_id=d.id AND e.vorgang_id=dv.vorgang_id
                          AND e.geloescht_am IS NULL ORDER BY e.id LIMIT 1) AS art,
                       (SELECT e.typ FROM eintrag e WHERE e.dokument_id=d.id AND e.vorgang_id=dv.vorgang_id
                          AND e.geloescht_am IS NULL ORDER BY e.id LIMIT 1) AS typ,
                       (SELECT k.name FROM eintrag e JOIN kontakt k ON k.id=e.kontakt_id WHERE e.dokument_id=d.id
                          AND e.geloescht_am IS NULL ORDER BY e.id LIMIT 1) AS absender,
                       (SELECT e.kontakt_id FROM eintrag e WHERE e.dokument_id=d.id AND e.kontakt_id IS NOT NULL
                          AND e.geloescht_am IS NULL ORDER BY e.id LIMIT 1) AS kontakt_id,
                       (SELECT min(e.ereignis_datum) FROM eintrag e WHERE e.dokument_id=d.id AND e.geloescht_am IS NULL)
                          AS ereignis_datum
                FROM dokument d JOIN dokument_vorgang dv ON dv.dokument_id=d.id JOIN vorgang v ON v.id=dv.vorgang_id
                WHERE d.geloescht_am IS NULL AND v.geloescht_am IS NULL AND (v.system IS NULL OR v.system='ablage')
                  AND (v.status='Erledigt' OR (
                    EXISTS (SELECT 1 FROM eintrag e JOIN eintrag_teil et ON et.eintrag_id=e.id
                            WHERE e.dokument_id=d.id AND e.vorgang_id=v.id AND e.geloescht_am IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM eintrag e JOIN eintrag_teil et ON et.eintrag_id=e.id
                            JOIN teilvorgang t ON t.id=et.teilvorgang_id
                            WHERE e.dokument_id=d.id AND e.vorgang_id=v.id AND e.geloescht_am IS NULL AND t.status<>'Erledigt')))
                ORDER BY d.id DESC""")]
            eigene, vorgang_b, kontakte = {}, {}, {}
            for r in db.execute("SELECT dokument_id, bereich FROM dokument_bereich ORDER BY bereich"):
                eigene.setdefault(r[0], []).append(r[1])
            for r in db.execute("SELECT vorgang_id, bereich FROM vorgang_bereich ORDER BY bereich"):
                vorgang_b.setdefault(r[0], []).append(r[1])
            for r in db.execute("""SELECT dk.dokument_id, k.id, k.name FROM dokument_kontakt dk JOIN kontakt k ON k.id=dk.kontakt_id
                ORDER BY k.name"""):
                kontakte.setdefault(r[0], []).append({"id": r[1], "name": r[2]})
            for r in rows:
                datei = self.store.uploads / r.pop("dateipfad")
                r["groesse"] = datei.stat().st_size if datei.is_file() else None
                r["datum"] = r["dokument_datum"] or r["ereignis_datum"] or r["angelegt_am"][:10]
                r["eigene_bereiche"] = eigene.get(r["id"], [])
                r["bereiche"] = r["eigene_bereiche"] or ([r["bereich"]] + [b for b in vorgang_b.get(r["vorgang_id"], []) if b != r["bereich"]])
                r["kontakte"] = kontakte.get(r["id"], [])
            return rows

    def chat_notiz(self, vorgang_id, data):
        """Chat-Notiz mit Quellenhinweis. Im Text erwähnte Schreiben ohne Original werden als fehlend vermerkt."""
        text = _text(data.get("text"), "Text", 20000, True)
        eid = self.eintrag_anlegen(vorgang_id, {**data, "art": "chat", "text": text,
                                                "quelle": data.get("quelle") or "Chat", "geprueft": False})
        fehlend = 0
        with closing(self.connect()) as db, db:
            teile = [r[0] for r in db.execute("SELECT teilvorgang_id FROM eintrag_teil WHERE eintrag_id=?", (eid,))]
            for art, tag in re.findall(r"(Schreiben|Brief|Bescheid|E-Mail|Mail|Rechnung|Gutachten|Bestätigung|Kündigung\w*)"
                                       r"\s+vom\s+(\d{1,2}\.\d{1,2}\.\d{4})", text, re.I):
                d = daten_in(tag)
                if not d or db.execute("""SELECT 1 FROM eintrag WHERE vorgang_id=? AND ereignis_datum=? AND geloescht_am IS NULL
                    AND (dokument_id IS NOT NULL OR art='fehlt')""", (vorgang_id, d[0])).fetchone():
                    continue
                fid = db.execute("""INSERT INTO eintrag(vorgang_id,art,titel,ereignis_datum,text,bezug_id)
                    VALUES(?,?,?,?,?,?)""", (vorgang_id, "fehlt", f"{art} vom {tag}", d[0],
                                             "Erwähnt in einer Chat-Notiz. Das Original ist nicht in der Akte.", eid)).lastrowid
                db.executemany("INSERT INTO eintrag_teil VALUES(?,?)", ((fid, t) for t in teile))
                fehlend += 1
        return {"id": eid, "fehlend": fehlend}

    def chat_notizen(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute("""SELECT e.id,e.vorgang_id,v.titel AS vorgang,e.titel,e.ereignis_datum,
                e.quelle,e.geprueft,substr(e.text,1,240) AS auszug FROM eintrag e JOIN vorgang v ON v.id=e.vorgang_id
                WHERE e.art='chat' AND e.geloescht_am IS NULL AND v.geloescht_am IS NULL
                ORDER BY e.ereignis_datum DESC, e.id DESC""")]

    def fristen_alle(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute("""SELECT f.*, v.titel AS vorgang, t.name AS teilvorgang
                FROM frist f JOIN vorgang v ON v.id=f.vorgang_id LEFT JOIN teilvorgang t ON t.id=f.teilvorgang_id
                WHERE f.geloescht_am IS NULL AND v.geloescht_am IS NULL
                ORDER BY f.erledigt_am IS NOT NULL, f.faellig_am""")]

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
                WHERE id=? AND geloescht_am IS NULL AND system IS NULL""", (ref,)).fetchone()
        return dict(row) if row else None


# --- HTTP-Schnittstelle -------------------------------------------------------------------
def _route_table():
    i = int
    return [
        ("GET", r"/api/akte/(\d+)", lambda a, m, d: a.akte(i(m[1]))),
        ("GET", r"/api/akte/(\d+)/offen", lambda a, m, d: a.offene_punkte(i(m[1]), i(d["teil"]) if str(d.get("teil", "")).isdigit() else None)),
        ("GET", r"/api/bereiche", lambda a, m, d: {"bereiche": a.bereiche()}),
        ("GET", r"/api/eintragsarten", lambda a, m, d: {"arten": a.eintragsarten()}),
        ("GET", r"/api/empfaenger", lambda a, m, d: {"empfaenger": a.empfaenger_liste()}),
        ("GET", r"/api/oberflaeche", lambda a, m, d: a.oberflaeche()),
        ("GET", r"/api/kontakte", lambda a, m, d: {"kontakte": a.kontakte()}),
        ("GET", r"/api/kontakte/dubletten", lambda a, m, d: {"dubletten": a.moegliche_dubletten(d.get("name"))}),
        ("GET", r"/api/papierkorb", lambda a, m, d: {"eintraege": a.papierkorb()}),
        ("GET", r"/api/suche", lambda a, m, d: {"treffer": a.suche(d.get("q"))}),
        ("GET", r"/api/posteingang", lambda a, m, d: {"dokumente": a.posteingang()}),
        ("GET", r"/api/fristen", lambda a, m, d: {"fristen": a.fristen_alle()}),
        ("GET", r"/api/archiv", lambda a, m, d: {"dokumente": a.archiv()}),
        ("GET", r"/api/chatnotizen", lambda a, m, d: {"notizen": a.chat_notizen()}),
        ("POST", r"/api/akte/(\d+)/chatnotiz", lambda a, m, d: a.chat_notiz(i(m[1]), d)),
        ("GET", r"/api/einstellungen", lambda a, m, d: {"eigene_angaben": a.eigene_angaben()}),
        ("POST", r"/api/einstellungen", lambda a, m, d: a.eigene_angaben_setzen(d.get("eigene_angaben"))),
        ("POST", r"/api/posteingang/(\d+)/zuordnen", lambda a, m, d: {"id": a.zuordnen(i(m[1]), d)}),
        ("POST", r"/api/dokumente/(\d+)/verschieben", lambda a, m, d: a.dokument_verschieben(i(m[1]), d)),
        ("POST", r"/api/dokumente/(\d+)/aendern", lambda a, m, d: a.dokument_aendern(i(m[1]), d)),
        ("POST", r"/api/dokumente/(\d+)/drehen", lambda a, m, d: a.dokument_drehen(i(m[1]), d)),
        ("POST", r"/api/dokumente/(\d+)/entfernen", lambda a, m, d: a.dokument_entfernen(i(m[1]), _id(d.get("vorgang_id"), "Vorgang"))),
        ("GET", r"/api/dokumente/(\d+)/fristen", lambda a, m, d: {"fristen": a.dokument_fristen(i(m[1]))}),
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
        ("POST", r"/api/bereiche/reihenfolge", lambda a, m, d: a.bereiche_sortieren(d.get("namen"))),
        ("POST", r"/api/eintragsarten", lambda a, m, d: {"name": a.eintragsart_anlegen(d.get("name"))}),
        ("POST", r"/api/empfaenger", lambda a, m, d: a.empfaenger_setzen(d.get("empfaenger"))),
        ("POST", r"/api/oberflaeche", lambda a, m, d: a.oberflaeche_setzen(d)),
        ("POST", r"/api/eintragsarten/entfernen", lambda a, m, d: a.eintragsart_entfernen(d.get("name"))),
        ("POST", r"/api/kontakte", lambda a, m, d: {"id": a.kontakt_anlegen(d)}),
        ("POST", r"/api/kontakte/(\d+)/abteilungen", lambda a, m, d: {"id": a.abteilung_anlegen(i(m[1]), d)}),
        ("POST", r"/api/kontakte/(\d+)", lambda a, m, d: a.kontakt_aendern(i(m[1]), d)),
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
    assert not by_id[e_gut]["nacherfasst"]  # Schreiben mit Dokument gelten nicht als nacherfasst
    tel = akte.eintrag_anlegen(kia, {"art": "telefonat", "titel": "Telefonat", "datum": "2026-10-14", "teile": [heck]})
    assert [e for e in akte.akte(kia)["eintraege"] if e["id"] == tel][0]["nacherfasst"]

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


def test_posteingang(store):
    """Posteingang: Import ohne Vorgang, Vorschläge, Zuordnung mit Chronik-Eintrag."""
    from contextlib import closing as _closing
    akte = Akte(store, today=lambda: "2026-11-23")
    vorgang = store.create_case("Unitask – Rechnungsklärung", "Versicherungen", "")
    teil = akte.teilvorgang_anlegen(vorgang, {"name": "Rechnung"})
    kontakt = akte.kontakt_anlegen({"name": "Unitask GmbH", "kurzname": "Unitask",
                                    "abteilungen": [{"email": "buchhaltung@unitask.example"}]})
    akte.beteiligter_setzen(vorgang, kontakt, "Vertragspartner")
    akte.referenz_anlegen(vorgang, {"bezeichnung": "Kundennr.", "wert": "UT-30418"})
    raw = b"%PDF-1.4\nPosteingang-Test"
    doc, neu = store.import_document(None, "Rechnung_korrigiert.pdf", raw)
    assert neu and store.import_document(None, "Kopie.pdf", raw) == (doc, False)
    assert doc not in [d["id"] for c in store.list_cases() for d in store.case_documents(c["id"])]
    assert all(c["titel"] != "Posteingang" for c in store.list_cases())
    with _closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)", (doc, 1, "pdf",
                   "Unitask GmbH · Friedrichstraße 140\nKundennummer: UT 30418\nBerlin, 22.11.2026\n"
                   "Betreff: Korrigierte Rechnung\nGuten Tag,\nzahlbar bis 06.12.2026."))
    eingang = akte.posteingang()
    assert [e["id"] for e in eingang] == [doc] and eingang[0]["groesse"] == len(raw)
    v = eingang[0]["vorschlag"]
    assert v["datum"] == "2026-11-22" and v["datum_quelle"] == "Datumszeile", v
    assert v["kontakt"]["id"] == kontakt, v
    assert v["vorgaenge"][0]["vorgang_id"] == vorgang and "UT-30418" in v["vorgaenge"][0]["grund"], v
    try:
        akte.zuordnen(doc, {})
    except ValueError:
        pass
    else:
        raise AssertionError("Zuordnung ohne Vorgang wurde angenommen.")
    eintrag = akte.zuordnen(doc, {"vorgang_id": vorgang, "teile": [teil], "titel": "Korrigierte Rechnung",
                                  "datum": v["datum"], "kontakt_id": kontakt})
    assert akte.posteingang() == []
    a = akte.akte(vorgang)
    assert [d["id"] for d in a["dokumente"]] == [doc] and a["dokumente"][0]["titel"] == "Korrigierte Rechnung"
    e = [x for x in a["eintraege"] if x["id"] == eintrag][0]
    assert e["art"] == "eingang" and e["ereignis_datum"] == "2026-11-22" and e["teile"] == [teil]
    assert any(t["dokument_id"] == doc for t in akte.suche("Korrigierte Rechnung"))
    try:
        akte.zuordnen(doc, {"vorgang_id": vorgang})
    except ValueError:
        pass
    else:
        raise AssertionError("Bereits zugeordnetes Dokument wurde erneut zugeordnet.")
    f = akte.frist_anlegen(vorgang, {"art": "wiedervorlage", "titel": "Nachfassen", "faellig_am": "2026-12-03"})
    assert any(x["id"] == f and x["vorgang"] == "Unitask – Rechnungsklärung" for x in akte.fristen_alle())
    assert dokumentdatum("Ihr Schreiben vom 02.11.2026\nKöln, den 18. November 2026") == ("2026-11-18", "Datumszeile")


def test_absender(store):
    """Der Absender kommt aus dem Briefkopf, nicht aus einer beliebigen Erwähnung im Text."""
    store = type(store)(store.data / "Absendertest", store.ocr)  # eigene, leere Datenbank
    akte = Akte(store, today=lambda: "2026-11-23")
    akte.eigene_angaben_setzen("A. Mustermann\nLindenweg 4\n50733 Köln")
    hr = ("Handelsregister B des Amtsgerichts Rostock\nAbteilung B\nAusdruck\nNummer der Firma: HRB 11893\n"
          "1. Anzahl der bisherigen Eintragungen\n2. a) Firma: unitask solutions GmbH\nb) Sitz: Rostock")
    assert absender_erkennen(hr)["name"] == "Amtsgericht Rostock"
    brief = ("Allsicher Versicherung AG · Rheinuferstraße 12 · 50668 Köln\nA. Mustermann\nLindenweg 4\n"
             "50733 Köln\nKöln, 18.11.2026\nIhr Schadenfall\nSehr geehrte Damen und Herren,\n"
             "die Unitask GmbH hat uns informiert.")
    a = absender_erkennen(brief, ["A. Mustermann", "Lindenweg 4"])
    assert a["name"] == "Allsicher Versicherung AG" and "50668 Köln" in a["anschrift"], a
    eigener = "A. Mustermann · Lindenweg 4 · 50733 Köln\nUnitask GmbH\nFriedrichstraße 140\n10117 Berlin\nWiderspruch"
    a = absender_erkennen(eigener, ["A. Mustermann"])
    assert a is None or "Mustermann" not in a["name"], a
    kopf = "Stadtwerke Rostock AG\nSchmarler Damm 5\n18069 Rostock\nIhre Jahresabrechnung"
    a = absender_erkennen(kopf)
    assert a["name"] == "Stadtwerke Rostock AG" and a["anschrift"].endswith("18069 Rostock"), a

    # Posteingang: bekannter Kontakt wird über den Absendernamen erkannt, Erwähnungen zählen nicht
    vorgang = store.create_case("Kia-Schaden", "Versicherungen", "")
    allsicher = akte.kontakt_anlegen({"name": "Allsicher Versicherung AG", "kurzname": "Allsicher"})
    unitask = akte.kontakt_anlegen({"name": "Unitask Solutions GmbH", "kurzname": "Unitask"})
    akte.beteiligter_setzen(vorgang, allsicher, "Versicherung")
    from contextlib import closing as _closing
    doc, _ = store.import_document(None, "Schreiben.pdf", b"%PDF-1.4\nAbsendertest")
    with _closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)", (doc, 1, "ocr", brief))
    v = [d for d in akte.posteingang() if d["id"] == doc][0]["vorschlag"]
    assert v["kontakt"]["id"] == allsicher and v["absender"]["quelle"] == "Absenderzeile", v
    assert v["vorgaenge"][0]["vorgang_id"] == vorgang

    # Unbekannter Absender: wird beim Zuordnen als neuer Kontakt mit Anschrift angelegt
    doc2, _ = store.import_document(None, "Registerauszug.pdf", b"%PDF-1.4\nRegister")
    with _closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)", (doc2, 1, "pdf", hr))
    v = [d for d in akte.posteingang() if d["id"] == doc2][0]["vorschlag"]
    assert v["absender"]["name"] == "Amtsgericht Rostock" and v["kontakt"] is None, v
    assert v["kontakt"] is None or v["kontakt"]["id"] != unitask
    akte.zuordnen(doc2, {"vorgang_id": vorgang, "neuer_absender": {"name": "Amtsgericht Rostock",
                                                                     "anschrift": "Amtsgericht Rostock\nZochstraße 13\n18057 Rostock"}})
    neu = [k for k in akte.kontakte() if k["name"] == "Amtsgericht Rostock"][0]
    assert neu["abteilungen"][0]["anschriften"][0]["zeilen"].endswith("18057 Rostock")
    assert any(b["kontakt_id"] == neu["id"] for b in akte.akte(vorgang)["beteiligte"])


def test_archiv(store):
    """Archiv: nur Dokumente abgeschlossener Vorgänge oder Teilvorgänge, je Vorgang eine Zeile, mit Absender und Datum."""
    store = type(store)(store.data / "Archivtest", store.ocr)
    akte = Akte(store, today=lambda: "2026-11-23")
    a = store.create_case("Kia-Schaden", "Versicherungen", "")
    b = store.create_case("Steuer 2025", "Finanzamt und Steuern", "")
    k = akte.kontakt_anlegen({"name": "Allsicher Versicherung AG"})
    doc, _ = store.import_document(a, "Gutachten.pdf", b"%PDF-1.4\nArchiv")
    akte.eintrag_anlegen(a, {"art": "eingang", "titel": "Gutachten", "datum": "2026-11-10", "dokument_id": doc,
                             "kontakt_id": k, "richtung": "von"})
    store.import_document(b, "Gutachten.pdf", b"%PDF-1.4\nArchiv")  # verknüpft
    inbox, _ = store.import_document(None, "Neu.pdf", b"%PDF-1.4\nNoch im Posteingang")
    assert akte.archiv() == []  # Vorgänge noch in Arbeit: nichts archiviert
    akte.vorgang_aendern(a, {"status": "Erledigt"})
    assert [r["vorgang"] for r in akte.archiv()] == ["Kia-Schaden"]
    akte.vorgang_aendern(b, {"status": "Erledigt"})
    rows = akte.archiv()
    assert sorted(r["vorgang"] for r in rows) == ["Kia-Schaden", "Steuer 2025"]
    assert all(r["id"] == doc for r in rows) and inbox not in [r["id"] for r in rows]
    kia = [r for r in rows if r["vorgang_id"] == a][0]
    assert kia["absender"] == "Allsicher Versicherung AG" and kia["datum"] == "2026-11-10" and kia["art"] == "eingang"
    akte.vorgang_aendern(a, {"status": "Offen"})  # wieder geöffnet: verlässt das Archiv
    assert [r["vorgang"] for r in akte.archiv()] == ["Steuer 2025"]
    # Teilvorgänge: archiviert, sobald alle Teilvorgänge des Dokuments erledigt sind
    c = store.create_case("Haus", "Versicherungen", "")
    t1 = akte.teilvorgang_anlegen(c, {"name": "Dach"})
    t2 = akte.teilvorgang_anlegen(c, {"name": "Heizung"})
    d2, _ = store.import_document(c, "Angebot.pdf", b"%PDF-1.4\nDach")
    akte.eintrag_anlegen(c, {"art": "eingang", "titel": "Angebot Dach", "datum": "2026-11-11", "dokument_id": d2, "teile": [t1]})
    d3, _ = store.import_document(c, "Wartung.pdf", b"%PDF-1.4\nHeizung")
    akte.eintrag_anlegen(c, {"art": "eingang", "titel": "Wartung", "datum": "2026-11-12", "dokument_id": d3, "teile": [t2]})
    akte.teilvorgang_aendern(t1, {"status": "Erledigt"})
    haus = [r["id"] for r in akte.archiv() if r["vorgang"] == "Haus"]
    assert haus == [d2], haus
    akte.loeschen("dokument", doc)
    assert [r["vorgang"] for r in akte.archiv()] == ["Haus"]


def test_fristen_ablage(store):  # noqa: C901
    """Fristen aus dem Text, direkte Ablage ins Archiv, Dokument in anderen Vorgang verschieben."""
    seiten = [{"nummer": 1, "text": "Ihr Schreiben vom 10.08.2026\nWir bitten um Ihre Stellungnahme bis zum 16.12.2026.\n"
                                    "Bitte überweisen Sie den Betrag bis spätestens zum 2. Dezember 2026. Termin am 20.12.2026. "
                                    "Der Betrag ist innerhalb von 14 Tagen zu überweisen. Zahlbar bis 05.12.2026. Frist bis zum 01.01.2020."}]
    f = fristen_erkennen(seiten, "2026-11-18")
    # Nur „bis zum <Datum>“: weder „Termin am …“, „zahlbar bis …“, relative Angaben noch vergangene Daten
    assert [(x["faellig_am"], x["titel"]) for x in f] == [("2026-12-02", "Zahlung"), ("2026-12-16", "Stellungnahme")], f
    assert "16.12.2026" in f[1]["zitat"] and f[1]["seite"] == 1
    assert fristen_erkennen([{"nummer": 1, "text": "Ihr Schreiben vom 10.08.2026 und Rechnung vom 12.12.2026"}], "2026-08-01") == []

    store = type(store)(store.data / "Ablagetest", store.ocr)
    akte = Akte(store, today=lambda: "2026-11-23")
    a = store.create_case("Kia-Schaden", "Versicherungen", "")
    b = store.create_case("Steuer 2025", "Versicherungen", "")
    # Direkt ins Archiv
    d1, _ = store.import_document(None, "Werbung.pdf", b"%PDF-1.4\nAblage")
    akte.zuordnen(d1, {"ablage": True, "titel": "Info-Schreiben"})
    zeilen = akte.archiv()
    assert [(r["id"], r["vorgang"], r["system"]) for r in zeilen] == [(d1, "Ohne Vorgang", "ablage")], zeilen
    assert all(c["titel"] != "Ohne Vorgang" for c in store.list_cases())
    try:
        akte.zuordnen(store.import_document(None, "x.pdf", b"%PDF-1.4\nx")[0], {"ablage": True, "fristen": [
            {"titel": "Frist", "faellig_am": "2026-12-01"}]})
        raise AssertionError("Fristen ohne Vorgang dürfen nicht angelegt werden")
    except ValueError:
        pass
    # Zuordnen mit erkannter und manueller Frist
    d2, _ = store.import_document(None, "Brief.pdf", b"%PDF-1.4\nBrief")
    akte.zuordnen(d2, {"vorgang_id": a, "fristen": [
        {"titel": "Stellungnahme", "faellig_am": "2026-12-16", "seite": 1, "zitat": "Stellungnahme bis zum 16.12.2026"},
        {"titel": "Selbst gesetzt", "faellig_am": "2026-12-01", "art": "wiedervorlage"}]})
    fr = akte.akte(a)["fristen"]
    assert sorted((x["titel"], x["quelle_dokument_id"]) for x in fr) == [("Selbst gesetzt", d2), ("Stellungnahme", d2)]
    # Verschieben: Dokument samt Eintrag in einen anderen Vorgang, aus der Ablage in einen Vorgang
    akte.dokument_verschieben(d2, {"von_vorgang_id": a, "vorgang_id": b})
    assert [e["dokument_id"] for e in akte.akte(a)["eintraege"]] == [] and akte.akte(a)["dokumente"] == []
    assert [e["dokument_id"] for e in akte.akte(b)["eintraege"]] == [d2]
    ablage = zeilen[0]["vorgang_id"]
    r = akte.dokument_verschieben(d1, {"von_vorgang_id": ablage, "vorgang_id": a})
    assert r == {"vorgang_id": a, "archiviert": False, "ablage": False} and akte.archiv() == []
    assert [d["id"] for d in akte.akte(a)["dokumente"]] == [d1]
    r = akte.dokument_verschieben(d1, {"von_vorgang_id": a, "ablage": True})
    assert r["ablage"] and [x["id"] for x in akte.archiv()] == [d1]
    # Entfernen: mehrfach verknüpft -> nur Verknüpfung lösen; sonst Papierkorb
    store.import_document(a, "Brief.pdf", b"%PDF-1.4\nBrief")  # d2 zusätzlich in a verknüpft
    assert akte.dokument_entfernen(d2, a) == {"papierkorb": False}
    assert [d["id"] for d in akte.akte(b)["dokumente"]] == [d2] and akte.akte(a)["dokumente"] == []
    assert akte.dokument_entfernen(d2, b) == {"papierkorb": True}
    assert akte.akte(b)["dokumente"] == [] and any(t["id"] == d2 for t in akte.papierkorb() if t["typ"] == "dokument")
    # Gelöscht und dieselbe Datei erneut importiert: Zuordnen zum selben Vorgang muss gehen
    d4, _ = store.import_document(None, "Wiederholt.pdf", b"%PDF-1.4\nWiederholt")
    akte.zuordnen(d4, {"vorgang_id": a})
    akte.dokument_entfernen(d4, a)
    d5, neu5 = store.import_document(None, "Wiederholt.pdf", b"%PDF-1.4\nWiederholt")
    assert neu5 and d5 != d4
    akte.zuordnen(d5, {"vorgang_id": a})
    assert [d["id"] for d in akte.akte(a)["dokumente"]] == [d5]
    # Im Archiv bearbeiten: Titel, Dateiname (Endung bleibt), Datum, Absender
    k = akte.kontakt_anlegen({"name": "Finanzamt Rostock"})
    akte.dokument_aendern(d1, {"titel": "Info Stadtwerke", "dateiname": "Stadtwerke-Info", "datum": "2026-10-01", "kontakt_id": k})
    z = [x for x in akte.archiv() if x["id"] == d1][0]
    assert (z["titel"], z["dateiname"], z["datum"], z["absender"], z["kontakt_id"]) == (
        "Info Stadtwerke", "Stadtwerke-Info.pdf", "2026-10-01", "Finanzamt Rostock", k), z
    # Eintrag bearbeiten: Dokument zuweisen, fehlendes Original wird zum Eingang
    dz, _ = store.import_document(b, "Nachgereicht.pdf", b"%PDF-1.4\nNachgereicht")
    ef = akte.eintrag_anlegen(b, {"art": "fehlt", "titel": "Bescheid vom 01.10.2026", "datum": "2026-10-01"})
    akte.eintrag_aendern(ef, {"dokument_id": dz})
    e_f = [e for e in akte.akte(b)["eintraege"] if e["id"] == ef][0]
    assert (e_f["art"], e_f["dokument_id"]) == ("eingang", dz)
    try:
        akte.eintrag_aendern(ef, {"dokument_id": d1})  # gehört nicht zu Vorgang b
        raise AssertionError("Fremdes Dokument darf nicht zugewiesen werden")
    except ValueError:
        pass
    # Empfänger: Anschriftenfeld, E-Mail-Kopf, zulässige Empfänger aus den Einstellungen
    brief = ("Amt Rostocker Heide, Eichenallee 20 a, 18182 Gelbensande\nFirma\nOrbit Cross media e.K.\n"
             "z.H. Herr Sven Muster\nZum Süderholz 7\n18182 Bentwisch\nIhr Schreiben vom 10.08.2026")
    assert empfaenger_erkennen(brief) == "Orbit Cross media e.K.", empfaenger_erkennen(brief)
    assert empfaenger_erkennen("Von: Bank\nAn: Max Muster <max@x.example>\nBetreff: Auszug") == "Max Muster"
    assert empfaenger_erkennen(brief, ["Sven Muster", "Orbit Cross media e.K."]) == "Orbit Cross media e.K."
    assert empfaenger_erkennen("Herrn\nSven Muster\nWeg 1\n18182 Bentwisch", ["Orbit Cross media e.K.", "Sven Muster"]) == "Sven Muster"
    assert akte.empfaenger_setzen(["Orbit Cross media e.K.", "", "Orbit Cross media e.K."]) == {"empfaenger": ["Orbit Cross media e.K."]}
    akte.dokument_aendern(d1, {"empfaenger": "Privat"})
    assert [x for x in akte.archiv() if x["id"] == d1][0]["empfaenger"] == "Privat"
    akte.empfaenger_setzen([])
    assert [x for x in akte.archiv() if x["id"] == d1][0]["empfaenger"] == "Privat"  # von Hand gesetzt bleibt
    # Priorität je Vorgang; Empfänger je Vorgang in der Liste
    akte.vorgang_aendern(b, {"prioritaet": "sehr hoch"})
    fall = [c for c in store.list_cases() if c["id"] == b][0]
    assert fall["prioritaet"] == "sehr hoch" and "empfaenger" in fall
    try:
        akte.vorgang_aendern(b, {"prioritaet": "dringend"})
        raise AssertionError("Unbekannte Priorität muss abgelehnt werden")
    except ValueError:
        pass
    # Darstellung der Filter wird gespeichert
    assert akte.oberflaeche() == {"filteransicht": "chips"}
    assert akte.oberflaeche_setzen({"filteransicht": "menue"})["filteransicht"] == "menue"
    assert akte.oberflaeche()["filteransicht"] == "menue"
    akte.oberflaeche_setzen({"filteransicht": "chips"})
    # Eigene Eintragsart
    assert akte.eintragsart_anlegen("Ortstermin") == "Ortstermin"
    try:
        akte.eintragsart_anlegen("ortstermin")
        raise AssertionError("Doppelte Art muss abgelehnt werden")
    except ValueError:
        pass
    eo = akte.eintrag_anlegen(b, {"typ": "Ortstermin", "titel": "Besichtigung", "datum": "2026-11-20"})
    e_ort = [e for e in akte.akte(b)["eintraege"] if e["id"] == eo][0]
    assert (e_ort["art"], e_ort["typ"]) == ("notiz", "Ortstermin")
    akte.eintragsart_entfernen("Ortstermin")
    assert akte.eintragsarten() == [] and [e for e in akte.akte(b)["eintraege"] if e["id"] == eo][0]["typ"] == "Ortstermin"
    # Kontakt umbenennen; Bereiche sortieren
    akte.kontakt_aendern(k, {"name": "Finanzamt Rostock-Land", "kurzname": "FA Rostock"})
    assert [x for x in akte.kontakte() if x["id"] == k][0]["name"] == "Finanzamt Rostock-Land"
    alt = store.groups()
    akte.bereiche_sortieren(list(reversed(alt)))
    assert store.groups() == list(reversed(alt)) and akte.bereich_namen() == list(reversed(alt))
    akte.bereiche_sortieren(alt)
    # Mehrere Bereiche und weitere Kontakte am Dokument; Drehung von Hand
    k2 = akte.kontakt_anlegen({"name": "Steuerbüro Nord"})
    namen = store.groups()
    akte.dokument_aendern(d1, {"bereiche": namen[:2], "kontakte": [k2]})
    z = [x for x in akte.archiv() if x["id"] == d1][0]
    assert z["bereiche"] == sorted(namen[:2]) and [c["name"] for c in z["kontakte"]] == ["Steuerbüro Nord"], z
    assert akte.dokument_drehen(d1, {"grad": -90}) == {"drehung": 270}
    assert akte.dokument_drehen(d1, {"grad": 90}) == {"drehung": 0}
    # Vorgang: mehrere Bereiche, Beteiligte setzen
    akte.vorgang_aendern(a, {"bereiche": [namen[1], namen[0]], "kontakte": [k, k2]})
    va = akte.akte(a)
    assert va["bereich"] == namen[1] and va["bereiche"] == [namen[1], namen[0]], va["bereiche"]
    assert sorted(x["kontakt_id"] for x in va["beteiligte"]) == sorted([k, k2])
    assert [c for c in store.list_cases() if c["id"] == a][0]["bereiche"] == [namen[1], namen[0]]
    akte.vorgang_aendern(a, {"kontakte": [k2]})
    assert [x["kontakt_id"] for x in akte.akte(a)["beteiligte"]] == [k2]
    try:
        akte.vorgang_aendern(a, {"bereiche": []})
        raise AssertionError("Ein Vorgang braucht mindestens einen Bereich")
    except ValueError:
        pass
    try:
        akte.dokument_aendern(d1, {"dateiname": "../boese.pdf"})
        raise AssertionError("Pfadangaben im Dateinamen müssen abgelehnt werden")
    except ValueError:
        pass
    # Direkt archiviert: Datum, Absender und Titel werden nach der Texterkennung nachgetragen
    d3, _ = store.import_document(None, "Scan_0007.pdf", b"%PDF-1.4\nNachtrag")
    akte.zuordnen(d3, {"ablage": True})
    with closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)", (d3, 1, "ocr",
                   "Stadtwerke Musterstadt GmbH · Hafenweg 3 · 18055 Rostock\nHerrn Max Muster\nRostock, 12.11.2026\nJahresabrechnung"))
        db.execute("UPDATE dokument SET titel='Jahresabrechnung', titel_quelle='Überschrift' WHERE id=?", (d3,))
    akte.ablage_nachtragen(d3)
    z = [x for x in akte.archiv() if x["id"] == d3][0]
    assert z["datum"] == "2026-11-12" and z["absender"] and "Stadtwerke" in z["absender"] and z["titel"] == "Jahresabrechnung", z


def test_chatnotiz(store):
    store = type(store)(store.data / "Chattest", store.ocr)
    akte = Akte(store, today=lambda: "2026-11-23")
    v = store.create_case("Unitask", "Versicherungen", "")
    r = akte.chat_notiz(v, {"titel": "Einschätzung", "text": "Die Kündigung vom 14.10.2026 ist wirksam. Siehe E-Mail vom 05.10.2026.",
                            "quelle": "ChatGPT-Verlauf „Unitask“"})
    a = akte.akte(v)
    assert r["fehlend"] == 2 and sorted(e["titel"] for e in a["eintraege"] if e["art"] == "fehlt") == [
        "E-Mail vom 05.10.2026", "Kündigung vom 14.10.2026"]
    assert akte.chat_notiz(v, {"titel": "Nochmal", "text": "Kündigung vom 14.10.2026"})["fehlend"] == 0
    assert akte.chat_notizen()[0]["geprueft"] == 0

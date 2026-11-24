#!/usr/bin/env python3
"""Lokale Korrespondenzverwaltung. Startet ausschließlich auf diesem Mac."""
import argparse
import hashlib
import io
import json
import logging
import logging.handlers
import os
import platform
import queue
import re
import shutil
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from contextlib import closing
from datetime import date
from email.utils import encode_rfc2231
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import parse_qsl, unquote, urlsplit

from akte import (Akte, fristen_erkennen, empfaenger_erkennen, ROUTES as AKTE_ROUTES, STATUSES, migrate_3, migrate_4, migrate_6, route_akte, test_absender, test_fristen_ablage,
                  test_akte, test_archiv, test_chatnotiz, test_posteingang)
from export import (akte_zip, brief_html, sicherung_erstellen, sicherung_pruefen, test_export, wiederherstellen,
                    wiederherstellen_laufend)
from chat_sync import ChatSync, MAX_EXPORT, test_chat_sync
from mail_import import MailImport, migrate_5, test_mail

ROOT = Path(__file__).resolve().parent
PORT = 8765
APP_VERSION = "DocuManager 0.13 · Filter wahlweise als Ausklappmenüs"
MAX_UPLOAD = 25 * 1024 * 1024
MIN_MACOS = "14.0"
SCHEMA_VERSION = 13
OCR_WAITING = "Wartet auf Texterkennung"
# Scan-Ordner für Scanner-Software und „Digitale Bilder“: Dateien darin kommen automatisch in den Posteingang.
# Bewusst nicht unter „Dokumente“: Diesen Ordner schützt macOS, ein über Launchpad gestartetes Programm bräuchte
# dafür eine eigene Erlaubnis.
SCAN_ORDNER = Path.home() / "DocuManager Scans"
OCR_RUNNING = "Texterkennung läuft"
log = logging.getLogger("korrespondenz")
# Die ersten drei Werte und die Vorgabe „Schreiben verfassen“ stammen aus dem bisherigen Stand und bleiben gleich.
CASE_STATUSES = STATUSES
DEFAULT_STATUS = "Schreiben verfassen"
TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
HEADING = re.compile(r"bescheid|widerspruch|einspruch|mahnung|rechnung|kündigung|schaden|"
                     r"zahlungsaufforderung|stellungnahme|anforderung|rückfrage|mitteilung|"
                     r"ordnungs(?:geld|widrigkeit)|entscheidung|aufforderung", re.IGNORECASE)
REFERENCE = re.compile(r"^(?:aktenzeichen|schadennummer|schaden-?\s?nr|kunden-?\s?(?:nr|nummer)|"
                       r"rechnungs-?\s?(?:nr|nummer)|vertrags-?\s?(?:nr|nummer)|versicherungs-?\s?(?:nr|nummer)|"
                       r"referenz|zeichen|datum|seite|"
                       r"telefon|kontakt|e-mail|telefonisch|iban|steuer(?:nr|nummer)|"
                       r"sehr geehrte|guten tag|mit freundlichen|deutschland|"
                       r"(?:ihr|unser)\s+(?:zeichen|schreiben|kontakt)|"
                       r"finanzamt|amtsgericht|landgericht|bundesamt|musterstraße)\b", re.IGNORECASE)
SUBJECT = re.compile(r"^(?:betreff|subject)\s*(?::\s*(.*))?$", re.IGNORECASE)


DOCUMENT_TYPES = (  # Dokumentarten ohne Betreffzeile, die sich am Inhalt eindeutig erkennen lassen
    (re.compile(r"handelsregister", re.I), re.compile(r"\b(HR[AB])\s*(\d{2,7})\b"), "Handelsregisterauszug {0} {1}"),
)


def select_title(pages):
    """Gibt einen erkannten Titel mit Fundstelle zurück."""
    if pages:
        first = "\n".join(row["text"] for row in pages[0]["lines"][:30])
        if not any(SUBJECT.fullmatch(re.sub(r"\s+", " ", row["text"]).strip()) for row in pages[0]["lines"][:24]):
            for marker, number, template in DOCUMENT_TYPES:
                found = number.search(first)
                if marker.search(first) and found:
                    return template.format(*found.groups()), pages[0]["number"], "Dokumentart"
    for page in pages[:2]:
        lines = [(re.sub(r"\s+", " ", row["text"]).strip(), row)
                 for row in page["lines"][:24]]
        for i, (text, _) in enumerate(lines):
            subject = SUBJECT.fullmatch(text)
            if subject:
                following = lines[i + 1][0] if i + 1 < len(lines) else ""
                explicit = (subject.group(1) or following).strip()
                if len(explicit) >= 4 and not REFERENCE.match(explicit):
                    return explicit[:160], page["number"], "Betreff"
        candidates = []
        for i, (text, box) in enumerate(lines):
            if not 7 <= len(text) <= 130 or REFERENCE.match(text) or len(re.findall(r"[A-Za-zÄÖÜäöüß]", text)) < 5:
                continue
            if re.search(r"@|https?://|^\d|\b(?:straße|strasse|str\.|gmbh|ag|kg)\b", text, re.I):
                continue
            if HEADING.search(text):
                candidates.append((100 - i + float(box.get("height", 0)) * 30, text))
        if candidates:
            return max(candidates)[1], page["number"], "Überschrift"
    return "", None, ""


def file_type(name, raw):
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES:
        raise ValueError("Erlaubt sind PDF, JPEG, PNG, TIFF, Word (.docx) und E-Mail (.eml).")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if "word/document.xml" not in z.namelist():
                    raise ValueError("Die Datei ist kein Word-Dokument (.docx).")
        except zipfile.BadZipFile:
            raise ValueError("Die Datei ist kein Word-Dokument (.docx).") from None
        return suffix
    signatures = {".pdf": b"%PDF-", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff",
                  ".png": b"\x89PNG\r\n\x1a\n",
                  ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*")}
    if not raw.startswith(signatures[suffix]):
        raise ValueError("Der Dateiinhalt passt nicht zur Endung.")
    return suffix


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_absaetze(raw):
    """Absätze eines Word-Dokuments als (Formatvorlage, Text), nur mit der Standardbibliothek."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
    absaetze = []
    for p in wurzel.iter(_W + "p"):
        stil = p.find(f"{_W}pPr/{_W}pStyle")
        teile = []
        for el in p.iter():
            if el.tag == _W + "t":
                teile.append(el.text or "")
            elif el.tag == _W + "tab":
                teile.append("\t")
            elif el.tag in (_W + "br", _W + "cr"):
                teile.append("\n")
        absaetze.append((stil.get(_W + "val") if stil is not None else "", "".join(teile)))
    return absaetze


def docx_text(raw):
    return "\n".join(t for _, t in docx_absaetze(raw)).strip()


def docx_html(raw, titel):
    """Lesbare HTML-Ansicht eines Word-Dokuments (Ersatz, wenn macOS-textutil fehlt)."""
    import html as h
    zeilen = []
    for stil, text in docx_absaetze(raw):
        if not text.strip():
            zeilen.append("<p>&nbsp;</p>")
        elif re.match(r"(?i)(heading|überschrift|titel|title)", stil):
            zeilen.append(f"<h2>{h.escape(text)}</h2>")
        else:
            zeilen.append("<p>" + h.escape(text).replace("\n", "<br>").replace("\t", "&emsp;") + "</p>")
    return ("<!doctype html><meta charset='utf-8'><title>" + h.escape(titel) + "</title><style>body{font:15px/1.5 Georgia,serif;"
            "max-width:21cm;margin:24px auto;padding:2cm;background:#fff;color:#111;box-shadow:0 0 0 1px #ddd}"
            "p{margin:0 0 .6em}h2{font-size:1.2em}</style>" + "".join(zeilen))


def datei_erstellt(raw, suffix):
    """Erstellungsdatum aus den Daten der Datei: PDF-Metadaten, EXIF bei Fotos und Scans, Word-Eigenschaften."""
    try:
        if suffix == ".pdf":
            m = re.search(rb"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})", raw) or re.search(
                rb"<xmp:CreateDate>(\d{4})-(\d{2})-(\d{2})", raw)
        elif suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                kern = z.read("docProps/core.xml") if "docProps/core.xml" in z.namelist() else b""
            m = re.search(rb"<dcterms:created[^>]*>(\d{4})-(\d{2})-(\d{2})", kern)
        elif suffix in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            m = re.search(rb"(\d{4}):(\d{2}):(\d{2}) \d{2}:\d{2}:\d{2}", raw[:256 * 1024])
        else:
            m = None
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except (ValueError, zipfile.BadZipFile, KeyError):
        pass
    return None


def case_due_date(value):
    if value in ("", None):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Gib die Frist als gültiges Datum ein.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("Gib die Frist als gültiges Datum ein.") from error


def setup_logging(folder):
    """Schreibt das Protokoll nach Daten/Logs/korrespondenz.log (5 Dateien zu je 1 MB)."""
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(folder / "korrespondenz.log", maxBytes=1_000_000,
                                                   backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
    for old in log.handlers[:]:
        log.removeHandler(old)
        old.close()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    return folder / "korrespondenz.log"


def columns_of(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def migrate_1(db):
    """Grundschema, auch für Bestände aus früheren Ständen ohne Status und Frist."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vorgang(
            id INTEGER PRIMARY KEY, titel TEXT NOT NULL, bereich TEXT NOT NULL,
            beschreibung TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Schreiben verfassen',
            naechste_frist TEXT,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS dokument(
            id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
            dateiname TEXT NOT NULL, titel TEXT NOT NULL, titel_seite INTEGER,
            titel_quelle TEXT NOT NULL, mime TEXT NOT NULL, dateipfad TEXT NOT NULL,
            sha256 TEXT NOT NULL, ocr_status TEXT NOT NULL,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(vorgang_id, sha256)
        );
        CREATE TABLE IF NOT EXISTS dokumentseite(
            dokument_id INTEGER NOT NULL REFERENCES dokument(id), nummer INTEGER NOT NULL,
            methode TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(dokument_id, nummer)
        );
        CREATE TABLE IF NOT EXISTS archivdatei(
            id TEXT PRIMARY KEY, datei_id TEXT NOT NULL, dateiname TEXT NOT NULL,
            mime_typ TEXT NOT NULL, groesse_bytes INTEGER NOT NULL CHECK(groesse_bytes >= 0),
            archiviert_am TEXT NOT NULL, lokaler_pfad TEXT, sha256 TEXT
        );
        CREATE INDEX IF NOT EXISTS archiv_typ ON archivdatei(mime_typ);
    """)
    columns = columns_of(db, "vorgang")
    if "status" not in columns:
        db.execute("ALTER TABLE vorgang ADD COLUMN status TEXT NOT NULL DEFAULT 'Schreiben verfassen'")
    if "naechste_frist" not in columns:
        db.execute("ALTER TABLE vorgang ADD COLUMN naechste_frist TEXT")


def migrate_2(db):
    """Texterkennung als Warteschlange: Fehlertext und Zeitpunkt je Dokument."""
    columns = columns_of(db, "dokument")
    if "ocr_fehler" not in columns:
        db.execute("ALTER TABLE dokument ADD COLUMN ocr_fehler TEXT")
    if "ocr_aktualisiert_am" not in columns:
        db.execute("ALTER TABLE dokument ADD COLUMN ocr_aktualisiert_am TEXT")


def migrate_7(db):
    """Automatische Drehung: Lage je Seite und eine aufrecht gedrehte Ansichtsfassung (das Original bleibt unverändert)."""
    if "ansicht" not in columns_of(db, "dokument"):
        db.execute("ALTER TABLE dokument ADD COLUMN ansicht TEXT")
    if "drehung" not in columns_of(db, "dokumentseite"):
        db.execute("ALTER TABLE dokumentseite ADD COLUMN drehung INTEGER NOT NULL DEFAULT 0")


def migrate_8(db):
    """Einmalig: Dokumente mit Texterkennung erneut prüfen lassen, damit auf dem Kopf liegende Scans aus der Zeit
    vor der verbesserten Lageerkennung aufrecht angezeigt werden. Vorhandener Text bleibt bei einem Fehler erhalten."""
    db.execute("""UPDATE dokument SET ocr_status=? WHERE geloescht_am IS NULL AND mime<>'message/rfc822'
        AND id IN (SELECT dokument_id FROM dokumentseite WHERE methode='ocr')""", (OCR_WAITING,))


def migrate_9(db):
    """Entfernt die Regel UNIQUE(vorgang_id, sha256) aus `dokument`. Sie stammt aus der Zeit, als ein Dokument nur zu
    einem Vorgang gehörte. Ein Dokument im Papierkorb blockierte damit das Zuordnen derselben, neu importierten Datei.
    Die Zugehörigkeit regelt `dokument_vorgang` (Primärschlüssel verhindert Doppelungen je Vorgang).
    Neuaufbau der Tabelle nach dem SQLite-Verfahren: Fremdschlüssel währenddessen aus, danach Prüfung."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='dokument'").fetchone()[0]
    if "UNIQUE(vorgang_id, sha256)" not in sql.replace(" ", "").replace("UNIQUE(vorgang_id,sha256)", "UNIQUE(vorgang_id, sha256)"):
        return
    db.execute("PRAGMA foreign_keys=OFF")  # wirkt nur außerhalb einer Transaktion; hier ist noch keine offen
    trigger = [r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='dokument'")]
    neu = re.sub(r",\s*UNIQUE\s*\(\s*vorgang_id\s*,\s*sha256\s*\)", "", sql)
    neu = re.sub(r"^CREATE TABLE\s+\"?dokument\"?\s*\(", "CREATE TABLE dokument_neu(", neu)
    spalten = ",".join(r[1] for r in db.execute("PRAGMA table_info(dokument)"))
    db.execute(neu)
    db.execute(f"INSERT INTO dokument_neu({spalten}) SELECT {spalten} FROM dokument")
    db.execute("DROP TABLE dokument")
    db.execute("ALTER TABLE dokument_neu RENAME TO dokument")
    for t in trigger:
        db.execute(t)
    db.execute("CREATE INDEX IF NOT EXISTS dokument_sha256 ON dokument(sha256)")
    fehler = db.execute("PRAGMA foreign_key_check").fetchall()
    if fehler:
        raise sqlite3.IntegrityError(f"Fremdschlüssel nach dem Umbau verletzt: {fehler[:3]}")


def migrate_10(db):
    """Mehrere Bereiche je Vorgang und je Dokument, weitere Kontakte je Dokument, Drehung von Hand."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vorgang_bereich(vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
            bereich TEXT NOT NULL, PRIMARY KEY(vorgang_id, bereich));
        CREATE TABLE IF NOT EXISTS dokument_bereich(dokument_id INTEGER NOT NULL REFERENCES dokument(id),
            bereich TEXT NOT NULL, PRIMARY KEY(dokument_id, bereich));
        CREATE TABLE IF NOT EXISTS dokument_kontakt(dokument_id INTEGER NOT NULL REFERENCES dokument(id),
            kontakt_id INTEGER NOT NULL REFERENCES kontakt(id), PRIMARY KEY(dokument_id, kontakt_id));
    """)
    if "drehung_manuell" not in columns_of(db, "dokument"):
        db.execute("ALTER TABLE dokument ADD COLUMN drehung_manuell INTEGER NOT NULL DEFAULT 0")
    db.execute("INSERT OR IGNORE INTO vorgang_bereich(vorgang_id,bereich) SELECT id,bereich FROM vorgang WHERE system IS NULL")


def migrate_11(db):
    """Erstellungsdatum der Datei (PDF-Metadaten, EXIF, Word) als Vorschlag für das Dokumentdatum."""
    if "datei_datum" not in columns_of(db, "dokument"):
        db.execute("ALTER TABLE dokument ADD COLUMN datei_datum TEXT")
    if "typ" not in columns_of(db, "eintrag"):  # eigene Eintragsart (Name); die Grundart bleibt z. B. „notiz“
        db.execute("ALTER TABLE eintrag ADD COLUMN typ TEXT")
    if "reihenfolge" not in columns_of(db, "bereich"):  # Bereiche in den Einstellungen sortierbar
        db.execute("ALTER TABLE bereich ADD COLUMN reihenfolge INTEGER")
        db.execute("UPDATE bereich SET reihenfolge=id")


def migrate_12(db):
    """Empfänger je Dokument (aus Anschriftenfeld oder E-Mail-Kopf erkannt, von Hand änderbar)."""
    for spalte in ("empfaenger", "empfaenger_quelle"):
        if spalte not in columns_of(db, "dokument"):
            db.execute(f"ALTER TABLE dokument ADD COLUMN {spalte} TEXT")
    for d in db.execute("SELECT dokument_id, text FROM dokumentseite WHERE nummer=1").fetchall():
        db.execute("UPDATE dokument SET empfaenger=? WHERE id=? AND empfaenger IS NULL", (empfaenger_erkennen(d[1]), d[0]))


def migrate_13(db):
    """Priorität je Vorgang: keine, hoch, sehr hoch."""
    if "prioritaet" not in columns_of(db, "vorgang"):
        db.execute("ALTER TABLE vorgang ADD COLUMN prioritaet TEXT NOT NULL DEFAULT 'keine'")


MIGRATIONS = ((1, migrate_1), (2, migrate_2), (3, migrate_3), (4, migrate_4), (5, migrate_5), (6, migrate_6),
              (7, migrate_7), (8, migrate_8), (9, migrate_9), (10, migrate_10), (11, migrate_11), (12, migrate_12),
              (13, migrate_13))


class Store:
    def __init__(self, data, ocr):
        self.data = data
        self.ocr = ocr
        self.ocr_ready = Event()
        self.ocr_ready.set()
        self.queue = queue.Queue()
        self.worker = None
        self.nach_texterkennung = None
        self.uploads = data / "Uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.ansicht = data / "Ansicht"  # aufrecht gedrehte Fassungen zur Anzeige, jederzeit neu erzeugbar
        self.migrate()

    @property
    def database(self):
        return self.data / "Rechtsberatung.sqlite3"

    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def migrate(self):
        """Spielt fehlende Schemaschritte ein. Vorher wird ein bestehender Bestand gesichert."""
        with closing(self.connect()) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Die Datenbank stammt aus einer neueren Programmversion. "
                                   "Bitte die aktuelle Version der Anwendung verwenden.")
            if version == SCHEMA_VERSION:
                return
            has_data = db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] > 0
        if has_data:
            target = self.backup("vor-schema-v" + str(SCHEMA_VERSION))
            log.info("Sicherung vor Schemaänderung: %s", target)
        with closing(self.connect()) as db:
            for number, step in MIGRATIONS:
                if number > version:
                    with db:
                        step(db)
                        db.execute(f"PRAGMA user_version={number}")
                    log.info("Datenbankschema auf Version %s gebracht.", number)

    def backup(self, label):
        """Konsistente Kopie der Datenbank nach Daten/Sicherungen/."""
        folder = self.data / "Sicherungen"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{time.strftime('%Y-%m-%d_%H%M%S')}_{label}.sqlite3"
        counter = 1
        while target.exists():
            counter += 1
            target = folder / f"{time.strftime('%Y-%m-%d_%H%M%S')}_{label}_{counter}.sqlite3"
        with closing(self.connect()) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
        return target

    def list_cases(self):
        with closing(self.connect()) as db:
            faelle = [dict(row) for row in db.execute("""SELECT v.*, (SELECT count(*) FROM dokument_vorgang dv
                JOIN dokument d ON d.id=dv.dokument_id WHERE dv.vorgang_id=v.id AND d.geloescht_am IS NULL) AS dokumente
                FROM vorgang v WHERE v.geloescht_am IS NULL AND v.system IS NULL ORDER BY v.id DESC""")]
            try:
                weitere = {}
                for r in db.execute("SELECT vorgang_id, bereich FROM vorgang_bereich"):
                    weitere.setdefault(r[0], []).append(r[1])
            except sqlite3.OperationalError:
                weitere = {}
            typen = {}
            for r in db.execute("""SELECT dv.vorgang_id, d.mime, count(*) FROM dokument_vorgang dv JOIN dokument d
                ON d.id=dv.dokument_id WHERE d.geloescht_am IS NULL GROUP BY dv.vorgang_id, d.mime"""):
                typen.setdefault(r[0], {})[r[1]] = r[2]
            empfaenger = {}
            try:
                for r in db.execute("""SELECT dv.vorgang_id, d.empfaenger, count(*) AS n FROM dokument_vorgang dv
                    JOIN dokument d ON d.id=dv.dokument_id WHERE d.geloescht_am IS NULL AND d.empfaenger IS NOT NULL
                    GROUP BY dv.vorgang_id, d.empfaenger ORDER BY n DESC"""):
                    empfaenger.setdefault(r[0], []).append(r[1])
            except sqlite3.OperationalError:
                pass
            for f in faelle:  # Hauptbereich zuerst, weitere danach
                f["empfaenger"] = empfaenger.get(f["id"], [])
                f["bereiche"] = [f["bereich"]] + sorted(b for b in weitere.get(f["id"], []) if b != f["bereich"])
                f["typen"] = typen.get(f["id"], {})
            return faelle

    def groups(self):
        with closing(self.connect()) as db:
            return [row["name"] for row in db.execute("SELECT name FROM bereich ORDER BY coalesce(reihenfolge, id), id")]

    def create_case(self, title, group, description, status=DEFAULT_STATUS, due=None):
        title = title.strip()
        group = group.strip() or "Anderes"
        if not title or len(title) > 160 or len(description) > 4000:
            raise ValueError("Prüfe Titel und Beschreibung.")
        if group not in self.groups():
            raise ValueError("Wähle einen Bereich aus der Liste.")
        if status not in CASE_STATUSES:
            raise ValueError("Wähle einen Status aus der Liste.")
        with closing(self.connect()) as db, db:
            return db.execute("INSERT INTO vorgang(titel,bereich,beschreibung,status,naechste_frist) VALUES(?,?,?,?,?)",
                              (title, group, description.strip(), status, case_due_date(due))).lastrowid

    def change_case_status(self, case_id, status):
        if status not in CASE_STATUSES:
            raise ValueError("Wähle einen Status aus der Liste.")
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE vorgang SET status=? WHERE id=?", (status, case_id)).rowcount:
                raise ValueError("Vorgang nicht gefunden.")

    def change_case_group(self, case_id, group):
        if group not in self.groups():
            raise ValueError("Wähle einen Bereich aus der Liste.")
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE vorgang SET bereich=? WHERE id=?", (group, case_id)).rowcount:
                raise ValueError("Vorgang nicht gefunden.")

    def change_case_due_date(self, case_id, due):
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE vorgang SET naechste_frist=? WHERE id=?",
                              (case_due_date(due), case_id)).rowcount:
                raise ValueError("Vorgang nicht gefunden.")

    def case_documents(self, case_id):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""SELECT d.id,d.titel,d.dateiname,d.titel_seite,
                    d.titel_quelle,d.ocr_status,d.ocr_fehler,d.mime,d.angelegt_am FROM dokument d
                    JOIN dokument_vorgang dv ON dv.dokument_id=d.id
                    WHERE dv.vorgang_id=? AND d.geloescht_am IS NULL ORDER BY d.id DESC""", (case_id,))]

    def document(self, document_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM dokument WHERE id=?", (document_id,)).fetchone()
            return dict(row) if row else None

    def pages(self, document_id):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""SELECT nummer,methode,text,drehung FROM dokumentseite
                    WHERE dokument_id=? ORDER BY nummer""", (document_id,))]

    def vorschaubild(self, document_id):
        """Kleines JPEG der ersten Seite, aufrecht gedreht. None, wenn keins erzeugt werden kann.
        Auf dem Mac mit `sips` (PDF, JPEG, PNG, TIFF); sonst nur für unveränderte JPEG/PNG das Original."""
        row = self.document(document_id)
        if not row or row["mime"] == "message/rfc822":
            return None
        with closing(self.connect()) as db:
            seite = db.execute("SELECT drehung FROM dokumentseite WHERE dokument_id=? ORDER BY nummer LIMIT 1",
                               (document_id,)).fetchone()
        drehung = ((int(seite[0]) if seite else 0) + int(row["drehung_manuell"] or 0)) % 360
        original = self.uploads / row["dateipfad"]
        if not original.is_file():
            return None
        ziel = self.data / "Vorschau" / f"{row['sha256']}-{drehung}.jpg"
        if ziel.is_file():
            return ziel.read_bytes()
        if row["mime"] == TYPES[".docx"]:  # Word: Vorschaubild über Quick Look (nur macOS)
            if not Path("/usr/bin/qlmanage").exists():
                return None
            ziel.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    subprocess.run(["/usr/bin/qlmanage", "-t", "-s", "520", "-o", tmp, str(original)], capture_output=True, timeout=60)
                    bild = next(Path(tmp).glob("*.png"), None)
                    if bild:
                        ziel.write_bytes(bild.read_bytes())
                        return ziel.read_bytes()
                except (subprocess.SubprocessError, OSError):
                    pass
            return None
        sips = Path("/usr/bin/sips")
        if not sips.exists():
            return original.read_bytes() if drehung == 0 and row["mime"] in ("image/jpeg", "image/png") else None
        ziel.parent.mkdir(exist_ok=True)
        stage = ziel.with_suffix(".tmp.jpg")
        befehl = [str(sips), "-s", "format", "jpeg", "-s", "formatOptions", "70", "-Z", "520"]
        if drehung:
            befehl += ["-r", str(drehung)]  # sips dreht im Uhrzeigersinn
        try:
            subprocess.run(befehl + [str(original), "--out", str(stage)], capture_output=True, timeout=60, check=True)
            os.replace(stage, ziel)
            return ziel.read_bytes()
        except (subprocess.SubprocessError, OSError) as error:
            log.warning("Vorschaubild für Dokument %s nicht erzeugt: %s", document_id, error)
            stage.unlink(missing_ok=True)
            return None

    def rename_document(self, document_id, title):
        title = title.strip()
        if not 1 <= len(title) <= 160:
            raise ValueError("Der Titel muss 1 bis 160 Zeichen lang sein.")
        with closing(self.connect()) as db, db:
            changed = db.execute("UPDATE dokument SET titel=?,titel_seite=NULL,titel_quelle='Manuell' WHERE id=?",
                                 (title, document_id)).rowcount
        if not changed:
            raise ValueError("Dokument nicht gefunden.")

    def read_ocr(self, path, suffix, ansicht=None):
        """Gibt Seiten, Status und gegebenenfalls einen Fehlertext für das Protokoll zurück.
        Mit `ansicht` schreibt der Helfer eine aufrecht gedrehte Fassung dorthin, falls Seiten gedreht lagen."""
        self.ocr_ready.wait(timeout=165)
        if not self.ocr or not self.ocr.is_file():
            return [], "OCR nicht verfügbar", "OCR-Helfer fehlt oder konnte nicht gebaut werden."
        try:
            run = subprocess.run([str(self.ocr), "pdf" if suffix == ".pdf" else "image", str(path)]
                                 + ([str(ansicht)] if ansicht else []), check=True, capture_output=True, timeout=150)
            result = json.loads(run.stdout)
            pages = result["pages"]
            issues = "; ".join(map(str, result.get("issues") or []))[:2000] or None
            if not pages:
                return [], "Kein Text erkannt", issues
            if issues:
                return pages, "Text teilweise erkannt", issues
            return pages, ("OCR abgeschlossen" if any(p["method"] == "ocr" for p in pages)
                           else "PDF-Text übernommen"), None
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode("utf-8", "replace").strip()[-2000:]
            if "tooManyPages" in detail:
                return [], "Texterkennung übersprungen: mehr als 40 Seiten", detail
            return [], "Texterkennung fehlgeschlagen", detail or f"Exit-Code {error.returncode}"
        except subprocess.TimeoutExpired:
            return [], "Texterkennung fehlgeschlagen", "Zeitüberschreitung nach 150 Sekunden."
        except (OSError, ValueError, KeyError) as error:
            return [], "Texterkennung fehlgeschlagen", f"{type(error).__name__}: {error}"

    # --- Warteschlange der Texterkennung -------------------------------------------------
    def pending_documents(self):
        with closing(self.connect()) as db:
            return [row["id"] for row in db.execute(
                "SELECT id FROM dokument WHERE ocr_status IN (?,?) ORDER BY id", (OCR_WAITING, OCR_RUNNING))]

    def start_worker(self):
        """Startet die Texterkennung im Hintergrund und nimmt unterbrochene Aufträge wieder auf."""
        pending = self.pending_documents()
        for doc_id in pending:
            self.queue.put(doc_id)
        if pending:
            log.info("Texterkennung: %s unterbrochene Aufträge werden fortgesetzt.", len(pending))
        self.worker = Thread(target=self._work, name="Texterkennung", daemon=True)
        self.worker.start()

    def _work(self):
        while True:
            doc_id = self.queue.get()
            try:
                self.process_document(doc_id)
            except Exception:  # Ein Fehler darf die Warteschlange nicht beenden.
                log.exception("Texterkennung für Dokument %s abgebrochen.", doc_id)
                self._set_ocr_result(doc_id, [], "Texterkennung fehlgeschlagen", "Interner Fehler, siehe Protokoll.")
            finally:
                self.queue.task_done()

    def process_pending(self):
        """Arbeitet alle wartenden Aufträge sofort ab (für Selbsttest und Notfall)."""
        for doc_id in self.pending_documents():
            self.process_document(doc_id)

    def process_document(self, doc_id):
        row = self.document(doc_id)
        if not row or row["ocr_status"] not in (OCR_WAITING, OCR_RUNNING):
            return
        with closing(self.connect()) as db, db:
            db.execute("UPDATE dokument SET ocr_status=? WHERE id=?", (OCR_RUNNING, doc_id))
        started = time.monotonic()
        if Path(row["dateipfad"]).suffix == ".docx":  # Word: Text direkt aus der Datei, keine Bilderkennung
            try:
                text = docx_text((self.uploads / row["dateipfad"]).read_bytes())
                seiten = [{"number": 1, "method": "docx", "text": text, "lines": [{"text": z} for z in text.splitlines() if z.strip()]}]
                self._set_ocr_result(doc_id, seiten if text else [], "Text übernommen" if text else "Kein Text erkannt", None)
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                self._set_ocr_result(doc_id, [], "Texterkennung fehlgeschlagen", str(error))
            if self.nach_texterkennung:
                self.nach_texterkennung(doc_id)
            return
        self.ansicht.mkdir(exist_ok=True)
        stage = self.ansicht / f"{doc_id}.tmp"
        stage.unlink(missing_ok=True)
        pages, status, error = self.read_ocr(self.uploads / row["dateipfad"], Path(row["dateipfad"]).suffix, stage)
        ansicht = None
        if stage.is_file() and stage.stat().st_size and any(p.get("rotation") for p in pages):
            kopf = stage.read_bytes()[:4]
            endung = ".pdf" if kopf.startswith(b"%PDF") else ".jpg" if kopf.startswith(b"\xff\xd8") else None
            if endung:
                ansicht = row["sha256"] + endung
                os.replace(stage, self.ansicht / ansicht)
        stage.unlink(missing_ok=True)
        self._set_ocr_result(doc_id, pages, status, error, ansicht)
        log.info("Dokument %s: %s nach %.1f s%s", doc_id, status, time.monotonic() - started,
                 f" ({error})" if error else "")
        if self.nach_texterkennung:  # z. B. Datum und Absender bei direkt archivierten Dokumenten nachtragen
            try:
                self.nach_texterkennung(doc_id)
            except Exception:
                log.exception("Nachbearbeitung nach der Texterkennung für Dokument %s fehlgeschlagen.", doc_id)

    def _set_ocr_result(self, doc_id, pages, status, error, ansicht=None):
        title, page, source = select_title(pages)
        with closing(self.connect()) as db, db:
            if pages:  # Empfänger erkennen, sofern nicht von Hand gesetzt
                liste = db.execute("SELECT wert FROM einstellung WHERE schluessel='empfaenger'").fetchone()
                db.execute("""UPDATE dokument SET empfaenger=? WHERE id=? AND coalesce(empfaenger_quelle,'')<>'manuell'""",
                           (empfaenger_erkennen(pages[0].get("text", ""), json.loads(liste[0]) if liste else []), doc_id))
            if not pages and db.execute("SELECT 1 FROM dokumentseite WHERE dokument_id=?", (doc_id,)).fetchone():
                # Eine fehlgeschlagene erneute Erkennung darf vorhandenen Text nicht löschen.
                db.execute("UPDATE dokument SET ocr_status=?, ocr_fehler=?, ocr_aktualisiert_am=CURRENT_TIMESTAMP WHERE id=?",
                           ("Erneute Erkennung fehlgeschlagen, bisheriger Text bleibt", error or status, doc_id))
                return
            db.execute("DELETE FROM dokumentseite WHERE dokument_id=?", (doc_id,))
            db.executemany("INSERT INTO dokumentseite(dokument_id,nummer,methode,text,drehung) VALUES(?,?,?,?,?)",
                           ((doc_id, p["number"], p["method"], p["text"], int(p.get("rotation") or 0) % 360) for p in pages))
            db.execute("""UPDATE dokument SET ocr_status=?, ocr_fehler=?, ocr_aktualisiert_am=CURRENT_TIMESTAMP, ansicht=?
                          WHERE id=?""", (status, error, ansicht, doc_id))
            if title:  # Ein manuell gesetzter Titel bleibt unangetastet.
                db.execute("""UPDATE dokument SET titel=?, titel_seite=?, titel_quelle=?
                              WHERE id=? AND titel_quelle='Dateiname'""", (title, page, source, doc_id))

    def retry_ocr(self, doc_id):
        row = self.document(doc_id)
        if row and row["mime"] == "message/rfc822":
            raise ValueError("Bei einer E-Mail liegt der Text bereits vor.")
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE dokument SET ocr_status=?, ocr_fehler=NULL WHERE id=?",
                              (OCR_WAITING, doc_id)).rowcount:
                raise ValueError("Dokument nicht gefunden.")
        if self.worker:
            self.queue.put(doc_id)

    def inbox_id(self, db):
        """Interner Vorgang, der noch nicht zugeordnete Dokumente des Posteingangs trägt."""
        return db.execute("SELECT id FROM vorgang WHERE system='posteingang'").fetchone()[0]

    def import_document(self, case_id, name, raw, geaendert=None):
        """Legt ein Original ab. Ohne Vorgang (case_id=None) landet es im Posteingang.
        `geaendert` (Änderungsdatum der Datei laut Browser) dient als Ersatz, wenn die Datei kein Erstellungsdatum trägt."""
        name = unicodedata.normalize("NFC", name)
        if not name or len(name) > 240 or any(c in name for c in "/\\") or any(ord(c) < 32 for c in name):
            raise ValueError("Ungültiger Dateiname.")
        suffix = file_type(name, raw)
        digest = hashlib.sha256(raw).hexdigest()
        inbox = case_id is None
        with closing(self.connect()) as db:
            if inbox:
                case_id = self.inbox_id(db)
                same = db.execute("SELECT id FROM dokument WHERE sha256=? AND geloescht_am IS NULL ORDER BY id",
                                  (digest,)).fetchone()
                if same:  # Identische Datei liegt schon vor: keine zweite Kopie im Posteingang
                    return same["id"], False
            row = db.execute("SELECT geloescht_am, system FROM vorgang WHERE id=?", (case_id,)).fetchone()
            if not row or row["geloescht_am"] or (row["system"] and not inbox):
                raise ValueError("Vorgang nicht gefunden.")
            existing = db.execute("""SELECT d.id FROM dokument d JOIN dokument_vorgang dv ON dv.dokument_id=d.id
                WHERE dv.vorgang_id=? AND d.sha256=?""", (case_id, digest)).fetchone()
            if existing:
                return existing["id"], False
            # Dieselbe Datei aus einem anderen Vorgang: verknüpfen statt ein zweites Dokument anzulegen.
            elsewhere = db.execute("SELECT id FROM dokument WHERE sha256=? AND geloescht_am IS NULL ORDER BY id",
                                   (digest,)).fetchone()
            if elsewhere:
                with db:
                    db.execute("INSERT OR IGNORE INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)",
                               (elsewhere["id"], case_id))
                log.info("Dokument %s zusätzlich mit Vorgang %s verknüpft.", elsewhere["id"], case_id)
                return elsewhere["id"], False
        path = self.uploads / (digest + suffix)
        if not path.is_file():
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.uploads, delete=False) as stage:
                temporary = Path(stage.name)
                try:
                    stage.write(raw)
                    stage.close()
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        # Das Original ist gespeichert. Titel und Text folgen aus der Warteschlange,
        # damit der Upload sofort antwortet und andere Anfragen nicht warten müssen.
        with closing(self.connect()) as db, db:
            erstellt = datei_erstellt(raw, suffix) or (geaendert if geaendert and re.fullmatch(r"\d{4}-\d{2}-\d{2}", geaendert) else None)
            doc_id = db.execute("""INSERT INTO dokument(vorgang_id,dateiname,titel,titel_seite,titel_quelle,mime,
                dateipfad,sha256,ocr_status,datei_datum) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (case_id, name, Path(name).stem[:160], None, "Dateiname", TYPES[suffix], path.name, digest,
                 OCR_WAITING, erstellt)).lastrowid
            if not inbox:
                db.execute("INSERT INTO dokument_vorgang(dokument_id,vorgang_id) VALUES(?,?)", (doc_id, case_id))
        log.info("Dokument %s %s abgelegt (%s Bytes).", doc_id,
                 "im Posteingang" if inbox else f"in Vorgang {case_id}", len(raw))
        if self.worker:
            self.queue.put(doc_id)
        return doc_id, True


class Scanner:
    def __init__(self, store):
        self.store = store
        self.job = None
        self.ins_archiv = None
        self.lock = Lock()  # Der Server bedient Anfragen parallel; ein Scanauftrag zur Zeit.

    def start(self, case_id, archiv=False):
        with self.lock:
            return self._start(case_id, archiv)

    def finish(self, job_id):
        with self.lock:
            return self._finish(job_id)

    def _start(self, case_id, archiv=False):
        if self.job and self.job["result"] is None:
            self._finish(self.job["id"])
            if self.job["result"] is None:
                # Ein früheres Scanfenster läuft noch, ist aber womöglich nicht sichtbar: schließen und neu öffnen.
                log.info("Vorheriger Scandialog läuft noch und wird für einen neuen Versuch beendet.")
                self.job["process"].terminate()
                try:
                    self.job["process"].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.job["process"].kill()
                self._finish(self.job["id"])
        if case_id is not None and not any(item["id"] == case_id for item in self.store.list_cases()):
            raise ValueError("Vorgang nicht gefunden.")
        binary = build_scanner()
        if not binary:
            raise ValueError("Der macOS-Scandialog konnte nicht gestartet werden.")
        inbox = self.store.data / "Scan_Eingang"
        inbox.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="Scan-", dir=inbox))
        logs = self.store.data / "Logs"
        logs.mkdir(parents=True, exist_ok=True)
        output = open(logs / "scanner.log", "ab")  # Ausgabe des Scandialogs für die Fehlersuche
        try:
            process = subprocess.Popen([str(binary), str(folder), str(SCAN_ORDNER)], stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT)
        except OSError:
            output.close()
            folder.rmdir()
            raise
        self.job = {"id": secrets.token_hex(16), "case": case_id, "archiv": archiv, "folder": folder,
                    "process": process, "result": None, "output": output}
        log.info("Scandialog für Vorgang %s geöffnet (%s).", case_id, folder.name)
        return self.job["id"]

    def _finish(self, job_id):
        job = self.job
        if not job or job["id"] != job_id:
            raise ValueError("Scanvorgang nicht gefunden.")
        if job["result"] is not None:
            return job["result"]
        code = job["process"].poll()
        if code is None:
            return {"state": "open"}
        if job.get("output"):
            job["output"].close()
        log.info("Scandialog beendet mit Code %s.", code)
        folder = job["folder"]
        manifest = folder / "scan-result.json"
        if not manifest.is_file():
            job["result"] = {"state": "cancelled" if code == 0 else "error", "imported": 0}
            if code == 0:
                shutil.rmtree(folder)
            return job["result"]
        imported = duplicates = 0
        errors = []
        try:
            names = json.loads(manifest.read_bytes())
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise ValueError
            for name in dict.fromkeys(names):
                file = folder / name
                try:
                    if not name or Path(name).name != name or file.is_symlink() or not file.is_file():
                        raise ValueError("Scan-Datei fehlt.")
                    if file.stat().st_size > MAX_UPLOAD:
                        raise ValueError("Die Scan-Datei ist größer als 25 MB.")
                    doc_id, created = self.store.import_document(job["case"], name, file.read_bytes())
                    if created and job.get("archiv") and self.ins_archiv:
                        self.ins_archiv(doc_id)
                    if created:
                        imported += 1
                    else:
                        duplicates += 1
                except (ValueError, OSError, sqlite3.Error) as error:
                    errors.append(name + ": " + (str(error) if isinstance(error, ValueError) else "Import fehlgeschlagen."))
        except (OSError, ValueError):
            errors.append("Die Scanliste konnte nicht gelesen werden.")
        if errors:
            log.warning("Scanimport mit Fehlern: %s", " | ".join(errors))
            errors.append("Die Scan-Dateien liegen weiterhin im lokalen Ordner Daten/Scan_Eingang/" + folder.name + ".")
        else:
            shutil.rmtree(folder)
        job["result"] = {"state": "done", "imported": imported, "duplicates": duplicates, "errors": errors}
        return job["result"]

    def stop(self):
        if self.job and self.job["process"].poll() is None:
            self.job["process"].terminate()
        if self.job and self.job.get("output"):
            self.job["output"].close()



class Handler(BaseHTTPRequestHandler):
    store = None
    akte = None
    mail = None
    mail_lock = Lock()
    restore_lock = Lock()
    server_ref = None
    scanordner = None
    scanner = None
    chat = None
    host = f"127.0.0.1:{PORT}"
    chat_lock = Lock()

    def log_message(self, format, *args):
        log.info("HTTP " + format, *args)

    def send_bytes(self, status, mime, body, disposition=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if disposition:
            if "filename*=" in disposition and "filename=" not in disposition:  # Ersatzname für ältere Browser
                art, _, kodiert = disposition.partition("; filename*=")
                einfach = re.sub(r"[^A-Za-z0-9._ -]+", "_", unquote(kodiert.split("''", 1)[-1]))
                disposition = f'{art}; filename="{einfach}"; filename*={kodiert}'
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value, status=200):
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(value, ensure_ascii=False).encode())

    def ins_archiv(self, doc_id):
        if self.akte.posteingang_id_von(doc_id):
            self.akte.zuordnen(doc_id, {"ablage": True})
            self.akte.ablage_nachtragen(doc_id)

    def ablegen(self, vorgang):
        """Nimmt eine hochgeladene Datei an. E-Mails (.eml) laufen über den Mail-Import (mit Anlagen), alle anderen
        Dateien über die normale Ablage. Mit `vorgang` wird eine E-Mail anschließend dem Vorgang zugeordnet."""
        name = unquote(self.headers.get("X-Dateiname", ""), errors="strict")
        raw = self.read_body(MAX_UPLOAD)
        geaendert = self.headers.get("X-Datei-Datum") or None
        if Path(name).suffix.lower() != ".eml":
            return self.store.import_document(vorgang, name, raw, geaendert)
        neu = self.mail.uebernehmen(raw, None, "Datei")
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT id FROM dokument WHERE sha256=? AND mime='message/rfc822' ORDER BY id",
                             (hashlib.sha256(raw).hexdigest(),)).fetchone()
        if not row:
            raise ValueError("Die E-Mail konnte nicht gelesen werden.")
        if vorgang and neu:
            self.akte.zuordnen(row[0], {"vorgang_id": vorgang})
        return row[0], neu

    def read_body(self, limit):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= limit:
            raise ValueError("Datei oder Eingabe ist leer oder zu groß. Maximal " + str(limit // (1024 * 1024)) + " MB."
                             if limit >= 1024 * 1024 else "Die Eingabe ist leer oder zu groß.")
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise ValueError("Übertragung unvollständig.")
        return raw

    def permitted(self):
        if self.headers.get("Host") != self.host:
            self.send_json({"error": "Die Anwendung ist nur über die lokale Adresse erreichbar."}, 403)
            return False
        return True

    def do_GET(self):
        if not self.permitted():
            return
        path = urlsplit(self.path).path
        static = {"/": ("oberflaeche.html", "text/html; charset=utf-8"),
                  "/oberflaeche.js": ("oberflaeche.js", "text/javascript; charset=utf-8"),
                  "/oberflaeche.css": ("oberflaeche.css", "text/css; charset=utf-8"),
                  "/alt": ("Korrespondenz_Rechtsberatung.html", "text/html; charset=utf-8"),
                  "/lokale_vorgaenge.js": ("lokale_vorgaenge.js", "text/javascript; charset=utf-8"),
                  "/chat_notizen.js": ("chat_notizen.js", "text/javascript; charset=utf-8"),
                  "/pdfjs/pdf.min.js": ("pdfjs/pdf.min.js", "text/javascript; charset=utf-8"),
                  "/pdfjs/pdf.worker.min.js": ("pdfjs/pdf.worker.min.js", "text/javascript; charset=utf-8")}
        if path in static:
            name, mime = static[path]
            self.send_bytes(200, mime, (ROOT / name).read_bytes())
        elif path == "/api/cases":
            self.send_json({"cases": self.store.list_cases(), "statuses": CASE_STATUSES, "groups": self.store.groups(),
                            "ocr": bool(self.store.ocr and self.store.ocr.is_file()),
                            "ocr_loading": not self.store.ocr_ready.is_set(), "version": APP_VERSION})
        elif path == "/api/scanordner":
            ordner = self.scanordner.ordner if self.scanordner else SCAN_ORDNER
            self.send_json({"pfad": str(ordner), "zuletzt": self.scanordner.zuletzt if self.scanordner else None})
        elif path == "/api/mail":
            self.send_json(self.mail.status())
        elif match := re.fullmatch(r"/api/akte/(\d+)/export", path):
            query = dict(parse_qsl(urlsplit(self.path).query))
            auswahl = None if query.get("docs", "alle") == "alle" else {int(x) for x in query["docs"].split(",") if x.isdigit()}
            try:
                a = self.akte.akte(int(match[1]))
            except ValueError as error:
                self.send_json({"error": str(error)}, 404)
                return
            name, inhalt = akte_zip(self.store, self.akte, a, auswahl)
            self.send_bytes(200, "application/zip", inhalt, "attachment; filename*=" + encode_rfc2231(name, "utf-8"))
        elif match := re.fullmatch(r"/api/eintraege/(\d+)/brief", path):
            eintrag = None
            with closing(self.store.connect()) as db:
                row = db.execute("SELECT vorgang_id FROM eintrag WHERE id=?", (int(match[1]),)).fetchone()
            if row:
                eintrag = next((e for e in self.akte.akte(row[0])["eintraege"] if e["id"] == int(match[1])), None)
            if not eintrag:
                self.send_json({"error": "Eintrag nicht gefunden."}, 404)
            else:
                self.send_bytes(200, "text/html; charset=utf-8", brief_html(eintrag, self.akte.eigene_angaben()).encode())
        elif path == "/api/sicherungen":
            ordner = self.store.data / "Sicherungen"
            liste = sorted(ordner.glob("Korrespondenz-Sicherung_*.zip"), reverse=True) if ordner.is_dir() else []
            self.send_json({"sicherungen": [{"name": p.name, "groesse": p.stat().st_size} for p in liste[:20]]})
        elif match := re.fullmatch(r"/api/sicherungen/(Korrespondenz-Sicherung_[0-9_-]+\.zip)", path):
            datei = self.store.data / "Sicherungen" / match[1]
            if not datei.is_file():
                self.send_json({"error": "Sicherung nicht gefunden."}, 404)
            else:
                self.send_bytes(200, "application/zip", datei.read_bytes(), "attachment; filename=" + match[1])
        elif path == "/api/chat/threads":
            self.send_json({"threads": self.chat.threads()})
        elif match := re.fullmatch(r"/api/chat/threads/([A-Za-z0-9_-]{1,160})", path):
            self.send_json({"notes": self.chat.notes(match[1])})
        elif match := re.fullmatch(r"/api/chat/originals/(\d+)", path):
            original = self.chat.original(int(match[1]))
            if original is None:
                self.send_json({"error": "Das Original ist lokal nicht verfügbar."}, 404)
            else:
                name, body = original
                self.send_bytes(200, "application/octet-stream", body,
                                "attachment; filename*=" + encode_rfc2231(name, "utf-8"))
        elif match := re.fullmatch(r"/api/cases/(\d+)/documents", path):
            self.send_json({"documents": self.store.case_documents(int(match[1]))})
        elif match := re.fullmatch(r"/api/documents/(\d+)/html", path):  # Word-Dokument lesbar anzeigen
            row = self.store.document(int(match[1]))
            if not row or row["mime"] != TYPES[".docx"]:
                self.send_json({"error": "Kein Word-Dokument."}, 404)
            else:
                datei = self.store.uploads / row["dateipfad"]
                inhalt = None
                if Path("/usr/bin/textutil").exists():
                    lauf = subprocess.run(["/usr/bin/textutil", "-convert", "html", "-stdout", str(datei)], capture_output=True, timeout=60)
                    inhalt = lauf.stdout if lauf.returncode == 0 and lauf.stdout else None
                if inhalt is None:
                    inhalt = docx_html(datei.read_bytes(), row["titel"]).encode("utf-8")
                self.send_bytes(200, "text/html; charset=utf-8", inhalt)
        elif match := re.fullmatch(r"/api/documents/(\d+)/vorschaubild", path):
            bild = self.store.vorschaubild(int(match[1]))
            if bild is None:
                self.send_json({"error": "Kein Vorschaubild."}, 404)
            else:
                self.send_bytes(200, "image/jpeg" if bild[:2] == b"\xff\xd8" else "image/png", bild)
        elif match := re.fullmatch(r"/api/documents/(\d+)/(original|pages)", path):
            doc_id = int(match[1])
            row = self.store.document(doc_id)
            if row is None:
                self.send_json({"error": "Dokument nicht gefunden."}, 404)
            elif match[2] == "pages":
                self.send_json({"pages": self.store.pages(doc_id)})
            else:
                file = self.store.uploads / row["dateipfad"]
                ansicht = self.store.ansicht / row["ansicht"] if row["ansicht"] else None
                unveraendert = dict(parse_qsl(urlsplit(self.path).query)).get("fassung") == "original"
                if ansicht and ansicht.is_file() and not unveraendert:  # aufrecht gedrehte Ansichtsfassung
                    name = Path(row["dateiname"]).stem + " (gedreht)" + ansicht.suffix
                    mime = "application/pdf" if ansicht.suffix == ".pdf" else "image/jpeg"
                    self.send_bytes(200, mime, ansicht.read_bytes(), "inline; filename*=" + encode_rfc2231(name, "utf-8"))
                elif not file.is_file():
                    self.send_json({"error": "Das Original fehlt."}, 404)
                else:
                    encoded = encode_rfc2231(row["dateiname"], "utf-8")
                    self.send_bytes(200, row["mime"], file.read_bytes(), "inline; filename*=" + encoded)
        else:
            try:
                found = route_akte(self.akte, "GET", path, dict(parse_qsl(urlsplit(self.path).query)))
            except ValueError as error:
                self.send_json({"error": str(error)}, 404)
                return
            if found is None:
                self.send_json({"error": "Seite nicht gefunden."}, 404)
            else:
                self.send_json(*found)

    def do_POST(self):
        if not self.permitted():
            return
        if self.headers.get("X-Korrespondenz") != "lokal" or self.headers.get("Origin") not in {None, "http://" + self.host}:
            self.send_json({"error": "Unzulässige Anfrage."}, 403)
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/chat/preview":
                body = self.read_body(MAX_EXPORT)
                with self.chat_lock:
                    self.send_json(self.chat.preview(body))
            elif path == "/api/chat/import":
                data = json.loads(self.read_body(24000))
                with self.chat_lock:
                    self.send_json(self.chat.import_selected(data["token"], data["threads"]))
            elif path == "/api/cases":
                data = json.loads(self.read_body(24000))
                case_id = self.store.create_case(data["title"], data.get("group", ""), data.get("description", ""),
                                                 data.get("status", DEFAULT_STATUS), data.get("due"))
                self.send_json({"id": case_id}, 201)
            elif match := re.fullmatch(r"/api/cases/(\d+)/due", path):
                self.store.change_case_due_date(int(match[1]), json.loads(self.read_body(4000))["due"])
                self.send_json({"ok": True})
            elif match := re.fullmatch(r"/api/cases/(\d+)/group", path):
                self.store.change_case_group(int(match[1]), json.loads(self.read_body(4000))["group"])
                self.send_json({"ok": True})
            elif match := re.fullmatch(r"/api/cases/(\d+)/status", path):
                self.store.change_case_status(int(match[1]), json.loads(self.read_body(4000))["status"])
                self.send_json({"ok": True})
            elif path == "/api/posteingang/dokumente":
                doc_id, created = self.ablegen(None)
                self.send_json({"id": doc_id, "created": created}, 201 if created else 200)
            elif path == "/api/sicherungen":
                ziel = sicherung_erstellen(self.store)
                log.info("Sicherung erstellt: %s", ziel)
                self.send_json({"name": ziel.name, "groesse": ziel.stat().st_size, "pruefung": sicherung_pruefen(ziel)}, 201)
            elif match := re.fullmatch(r"/api/sicherungen/(Korrespondenz-Sicherung_[0-9_-]+\.zip)/pruefen", path):
                self.send_json(sicherung_pruefen(self.store.data / "Sicherungen" / match[1]))
            elif path == "/api/sicherungen/wiederherstellen":  # hochgeladene Sicherungsdatei
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8 * 1024 ** 3:
                    raise ValueError("Die Sicherungsdatei ist leer oder zu groß.")
                with tempfile.NamedTemporaryFile(suffix=".zip", dir=self.store.data, delete=False) as stage:
                    rest = size
                    while rest:
                        block = self.rfile.read(min(rest, 1024 * 1024))
                        if not block:
                            break
                        stage.write(block)
                        rest -= len(block)
                try:
                    if rest:
                        raise ValueError("Übertragung unvollständig.")
                    with self.restore_lock:
                        pruefung = wiederherstellen_laufend(self.store, Path(stage.name))
                finally:
                    Path(stage.name).unlink(missing_ok=True)
                log.info("Sicherung wiederhergestellt (hochgeladen).")
                self.send_json(pruefung)
            elif match := re.fullmatch(r"/api/sicherungen/(Korrespondenz-Sicherung_[0-9_-]+\.zip)/wiederherstellen", path):
                with self.restore_lock:
                    pruefung = wiederherstellen_laufend(self.store, self.store.data / "Sicherungen" / match[1])
                log.info("Sicherung %s wiederhergestellt.", match[1])
                self.send_json(pruefung)
            elif path == "/api/archiv/dokumente":  # direkt ins Archiv, Texterkennung läuft wie im Posteingang
                doc_id, created = self.ablegen(None)
                row = self.store.document(doc_id)
                if created or (row and self.akte.posteingang_id_von(doc_id)):
                    self.akte.zuordnen(doc_id, {"ablage": True})
                    self.akte.ablage_nachtragen(doc_id)
                self.send_json({"id": doc_id, "created": created}, 201 if created else 200)
            elif path == "/api/mail/abholen":
                ziel = json.loads(self.read_body(4000)).get("ziel") if self.headers.get("Content-Length", "0") != "0" else None
                with self.mail_lock:  # ein Abruf zur Zeit
                    ergebnis = self.mail.abholen()
                if ziel == "archiv":  # im Archiv geholt: E-Mails samt Anlagen direkt ablegen
                    for doc_id in ergebnis.get("ids", []):
                        self.ins_archiv(doc_id)
                self.send_json(ergebnis)
            elif path == "/api/beenden":  # Anwendung ohne Terminal beenden
                self.send_json({"ok": True})
                if self.server_ref:
                    log.info("Beendet über die Oberfläche.")
                    Thread(target=self.server_ref.shutdown, daemon=True).start()
            elif path == "/api/scanordner/oeffnen":
                ordner = self.scanordner.ordner if self.scanordner else SCAN_ORDNER
                ordner.mkdir(parents=True, exist_ok=True)
                if Path("/usr/bin/open").exists():
                    subprocess.Popen(["/usr/bin/open", str(ordner)])
                self.send_json({"pfad": str(ordner)})
            elif path == "/api/mail/markierung":
                self.mail.markierung_setzen(int(json.loads(self.read_body(4000))["markierung"]))
                self.send_json({"ok": True})
            elif path == "/api/posteingang/scan":
                self.send_json({"id": self.scanner.start(None)}, 201)
            elif path == "/api/archiv/scan":  # Scans direkt ins Archiv
                self.send_json({"id": self.scanner.start(None, archiv=True)}, 201)
            elif match := re.fullmatch(r"/api/cases/(\d+)/scan", path):
                self.send_json({"id": self.scanner.start(int(match[1]))}, 201)
            elif match := re.fullmatch(r"/api/scans/([0-9a-f]{32})/poll", path):
                self.send_json(self.scanner.finish(match[1]))
            elif match := re.fullmatch(r"/api/cases/(\d+)/documents", path):
                doc_id, created = self.ablegen(int(match[1]))
                self.send_json({"id": doc_id, "created": created}, 201 if created else 200)
            elif match := re.fullmatch(r"/api/documents/(\d+)/title", path):
                self.store.rename_document(int(match[1]), json.loads(self.read_body(4000))["title"])
                self.send_json({"ok": True})
            elif match := re.fullmatch(r"/api/documents/(\d+)/ocr", path):
                self.store.retry_ocr(int(match[1]))
                self.send_json({"ok": True})
            elif any(method == "POST" and pattern.fullmatch(path) for method, pattern, _ in AKTE_ROUTES):
                data = json.loads(self.read_body(64000)) if self.headers.get("Content-Length", "0") != "0" else {}
                if not isinstance(data, dict):
                    raise ValueError("Ungültige Eingabe.")
                self.send_json(*route_akte(self.akte, "POST", path, data))
            else:
                self.send_json({"error": "Seite nicht gefunden."}, 404)
        except (ValueError, KeyError, AttributeError, TypeError) as error:
            log.info("Abgelehnt %s: %s", path, error)
            self.send_json({"error": str(error) if isinstance(error, ValueError) else "Ungültige Eingabe."}, 400)
        except (OSError, sqlite3.Error) as error:
            log.exception("Fehler bei %s", path)
            grund = getattr(error, "strerror", None) or str(error)
            hinweis = (" macOS verweigert den Zugriff auf einen Ordner (Systemeinstellungen → Datenschutz & Sicherheit → "
                       "Dateien und Ordner)." if isinstance(error, PermissionError) else
                       " Eine andere Aktion schreibt gerade; bitte in einigen Sekunden erneut versuchen."
                       if "locked" in str(error) else "")
            self.send_json({"error": f"Speichern fehlgeschlagen ({grund}).{hinweis} "
                                     "Details stehen in Daten/Logs/korrespondenz.log."}, 500)


class LocalServer(ThreadingHTTPServer):
    """Bedient Anfragen parallel. Abgebrochene Verbindungen des Browsers landen nur im Protokoll."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            log.info("Verbindung vom Browser vorzeitig geschlossen.")
        else:
            log.exception("Unerwarteter Fehler bei einer Anfrage.")


def build_helper(name, source, command, timeout):
    """Baut einen nativen Helfer mit fester macOS-Mindestversion.

    Ein vorhandener Helfer wird neu gebaut, wenn sich Quelltext oder Bauoptionen geändert haben.
    So ersetzt die Anwendung auch Helfer, die früher ohne Mindestversion gebaut wurden."""
    runtime = ROOT / "Daten" / "Laufzeit"
    runtime.mkdir(parents=True, exist_ok=True)
    binary = runtime / name
    stamp = runtime / (name + ".build")
    signature = " ".join(command)
    if (binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime
            and stamp.is_file() and stamp.read_text() == signature):
        return binary
    stage = binary.with_suffix(".tmp")
    try:
        run = subprocess.run(command + [str(source), "-o", str(stage)], capture_output=True, timeout=timeout)
        if run.returncode != 0:
            log.error("Bau von %s fehlgeschlagen (Code %s): %s", name, run.returncode,
                      (run.stderr or run.stdout).decode("utf-8", "replace")[-4000:])
            return None
        os.replace(stage, binary)
        stamp.write_text(signature)
        log.info("%s gebaut für macOS ab %s.", name, MIN_MACOS)
        return binary
    except (OSError, subprocess.SubprocessError) as error:
        log.error("Bau von %s nicht möglich: %s", name, error)
        return None
    finally:
        stage.unlink(missing_ok=True)


def build_ocr():
    runtime = ROOT / "Daten" / "Laufzeit"
    binary = build_helper("korrespondenz-ocr", ROOT / "ocr.swift",
                          ["/usr/bin/swiftc", "-O", "-target", f"{platform.machine()}-apple-macos{MIN_MACOS}",
                           "-module-cache-path", str(runtime / "SwiftCache")], 160)
    if not binary:
        print("OCR ist derzeit nicht verfügbar. Das Anlegen von Vorgängen und der Import bleiben möglich. "
              "Details stehen in Daten/Logs/korrespondenz.log.", flush=True)
    return binary


class ScanOrdner:
    """Überwachter Ordner: Was die Scanner-Software dort ablegt, landet automatisch im Posteingang.
    Eine Datei wird erst übernommen, wenn sich ihre Größe zwischen zwei Durchläufen nicht mehr ändert
    (der Scanner schreibt fertig). Übernommene Dateien wandern in den Unterordner „Übernommen“."""
    ENDUNGEN = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

    def __init__(self, store, ordner):
        self.store, self.ordner = store, Path(ordner)
        self.groessen = {}
        self.zuletzt = None

    def einmal(self, jetzt=None):
        jetzt = jetzt or time.time()
        self.ordner.mkdir(parents=True, exist_ok=True)
        fertig = self.ordner / "Übernommen"
        neu = 0
        for datei in sorted(self.ordner.iterdir()):
            if datei.name.startswith(".") or not datei.is_file() or datei.suffix.lower() not in self.ENDUNGEN:
                continue
            stat = datei.stat()
            if self.groessen.get(datei) != stat.st_size or jetzt - stat.st_mtime < 3:
                self.groessen[datei] = stat.st_size
                continue
            try:
                self.store.import_document(None, datei.name, datei.read_bytes())
            except ValueError as error:
                log.warning("Scan-Ordner: %s nicht übernommen: %s", datei.name, error)
                fertig = self.ordner / "Nicht übernommen"
            fertig.mkdir(exist_ok=True)
            ziel = fertig / datei.name
            if ziel.exists():
                ziel = fertig / f"{datei.stem} {time.strftime('%Y-%m-%d %H%M%S')}{datei.suffix}"
            os.replace(datei, ziel)
            self.groessen.pop(datei, None)
            fertig = self.ordner / "Übernommen"
            neu += 1
        if neu:
            self.zuletzt = time.strftime("%Y-%m-%d %H:%M:%S")
            log.info("Scan-Ordner: %s Datei(en) übernommen.", neu)
        return neu

    def starten(self):
        def schleife():
            while True:
                try:
                    self.einmal()
                except OSError as error:
                    log.warning("Scan-Ordner nicht lesbar: %s", error)
                time.sleep(4)
        Thread(target=schleife, name="Scan-Ordner", daemon=True).start()


def build_scanner():
    return build_helper("korrespondenz-scanner", ROOT / "scanner.m",
                        ["/usr/bin/clang", "-fobjc-arc", "-O2", f"-mmacosx-version-min={MIN_MACOS}",
                         "-framework", "Cocoa", "-framework", "Quartz", "-framework", "ImageCaptureCore"], 120)


def test_dateien(store):
    """Word-Dokumente (Text, Ansicht, Datum), Erstellungsdatum aus PDF und EXIF, Ersatz für das Dokumentdatum."""
    store = type(store)(store.data / "Dateitest", None)
    akte = Akte(store, today=lambda: "2026-11-23")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Kündigung Mietvertrag</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>Bitte bestätigen Sie den Eingang bis zum 15.12.2026.</w:t></w:r></w:p></w:body></w:document>')
        z.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="x" xmlns:dcterms="y"><dcterms:created xsi:type="z">'
                   '2026-10-02T08:00:00Z</dcterms:created></cp:coreProperties>')
    docx = puffer.getvalue()
    assert datei_erstellt(docx, ".docx") == "2026-10-02"
    assert datei_erstellt(b"%PDF-1.4\n<< /CreationDate (D:20250314101500+01'00') >>", ".pdf") == "2025-03-14"
    assert datei_erstellt(b"\xff\xd8\xff\xe1Exif..2024:07:09 12:00:00", ".jpg") == "2024-07-09"
    assert datei_erstellt(b"%PDF-1.4\nohne", ".pdf") is None
    doc, _ = store.import_document(None, "Kuendigung.docx", docx)
    store.process_pending()
    row = store.document(doc)
    assert row["datei_datum"] == "2026-10-02" and row["ocr_status"] == "Text übernommen", dict(row)
    assert "15.12.2026" in store.pages(doc)[0]["text"] and row["titel"] == "Kündigung Mietvertrag", row["titel"]
    p = [x for x in akte.posteingang() if x["id"] == doc][0]
    assert p["vorschlag"]["datum"] == "2026-10-02" and p["vorschlag"]["datum_quelle"] == "Erstellungsdatum der Datei"
    assert p["vorschlag"]["fristen"][0]["faellig_am"] == "2026-12-15"
    assert "<h2>Kündigung Mietvertrag</h2>" in docx_html(docx, "x")
    try:
        file_type("falsch.docx", b"PK\x03\x04kaputt")
        raise AssertionError("Kaputte Word-Datei muss abgelehnt werden")
    except ValueError:
        pass
    # Datum aus dem Browser als Ersatz, wenn die Datei keins trägt
    d2, _ = store.import_document(None, "Scan.pdf", b"%PDF-1.4\nohne Datum", "2026-09-30")
    assert store.document(d2)["datei_datum"] == "2026-09-30"


def self_test(ocr=None, image=None):
    line = {"text": "Betreff: Stellungnahme zum Frontschaden"}
    assert select_title([{"number": 1, "lines": [{"text": "Aktenzeichen 4711"}, line]}]) == (
        "Stellungnahme zum Frontschaden", 1, "Betreff")
    assert select_title([{"number": 1, "lines": [{"text": "Betreff"}, {"text": "Unterlagen zur Prüfung"}]}])[0] == "Unterlagen zur Prüfung"
    assert select_title([{"number": 1, "lines": [{"text": "Datum: 24.11.2026"}]}])[0] == ""
    assert select_title([{"number": 1, "lines": [{"text": "Schaden-Nr. KFZ-2026-1842"}, {"text": "Ihr Schadenfall"}]}])[0] \
        == "Ihr Schadenfall"
    assert select_title([{"number": 1, "lines": [{"text": "Handelsregister B des Amtsgerichts Rostock"},
                                                 {"text": "Nummer der Firma: HRB 11893"},
                                                 {"text": "6. a) Rechtsform, Beginn, Satzung"}]}]) == (
        "Handelsregisterauszug HRB 11893", 1, "Dokumentart")
    with tempfile.TemporaryDirectory(prefix="korrespondenz-test-") as temporary:
        folder = Path(temporary)
        store = Store(folder, ocr)
        case_id = store.create_case("Testvorgang", "Versicherungen", "Synthetische Testdaten")
        content = image.read_bytes() if image else b"%PDF-1.4\n"
        name = image.name if image else "Muster.pdf"
        doc_id, created = store.import_document(case_id, name, content)
        assert created and store.import_document(case_id, name, content) == (doc_id, False)
        assert store.document(doc_id)["ocr_status"] == OCR_WAITING
        assert store.pending_documents() == [doc_id]
        store.process_pending()
        assert store.pending_documents() == []
        result = store.document(doc_id)
        assert (store.uploads / result["dateipfad"]).read_bytes() == content
        assert len(Store(folder, ocr).list_cases()) == 1
        assert store.list_cases()[0]["status"] == "Schreiben verfassen"
        store.change_case_due_date(case_id, "2026-12-09")
        assert Store(folder, ocr).list_cases()[0]["naechste_frist"] == "2026-12-09"
        try:
            store.change_case_due_date(case_id, "2026-02-30")
        except ValueError:
            assert store.list_cases()[0]["naechste_frist"] == "2026-12-09"
        else:
            raise AssertionError("Ungültige Frist wurde gespeichert.")
        store.change_case_due_date(case_id, "")
        assert store.list_cases()[0]["naechste_frist"] is None
        store.change_case_group(case_id, "Finanzamt und Steuern")
        assert Store(folder, ocr).list_cases()[0]["bereich"] == "Finanzamt und Steuern"
        store.change_case_status(case_id, "Recherchieren")
        assert Store(folder, ocr).list_cases()[0]["status"] == "Recherchieren"
        try:
            store.change_case_status(case_id, "Unbekannt")
        except ValueError:
            assert store.list_cases()[0]["status"] == "Recherchieren"
        else:
            raise AssertionError("Unbekannter Status wurde gespeichert.")
        if image:
            assert result["titel_quelle"] != "Dateiname", result["ocr_status"]
            assert "Stellungnahme" in result["titel"], result["titel"]
            assert store.pages(doc_id)[0]["methode"] == "ocr"
        else:
            assert result["titel"] == "Muster"
        store.rename_document(doc_id, "Manuell korrigierter Titel")
        assert store.case_documents(case_id)[0]["titel"] == "Manuell korrigierter Titel"
        assert store.document(doc_id)["titel_quelle"] == "Manuell"
        scan_folder = folder / "scan-test"
        scan_folder.mkdir()
        (scan_folder / "scan.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (scan_folder / "scan-result.json").write_text('["scan.png"]')
        scanner = Scanner(store)
        process = type("Completed", (), {"poll": lambda self: 0})()
        scanner.job = {"id":"test", "case":case_id, "folder":scan_folder, "process":process, "result":None}
        assert scanner.finish("test") == {"state":"done", "imported":1, "duplicates":0, "errors":[]}
        haengend = folder / "scan-haengt"
        haengend.mkdir()
        laeuft = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        scanner.job = {"id": "alt", "case": case_id, "folder": haengend, "process": laeuft, "result": None}
        global build_scanner
        echter_bau, build_scanner = build_scanner, lambda: None  # im Test kein echtes Scanfenster öffnen
        try:
            scanner.start(case_id)
        except ValueError as error:
            assert "bereits" not in str(error), error  # erwartet: „konnte nicht gestartet werden“
        finally:
            build_scanner = echter_bau
        assert laeuft.poll() is not None, "Hängender Scandialog wurde nicht beendet."
        assert len(store.case_documents(case_id)) == 2
        assert not scan_folder.exists()
        test_chat_sync(store)
        test_akte(store)
        test_posteingang(store)
        test_absender(store)
        test_archiv(store)
        test_fristen_ablage(store)
        test_dateien(store)
        test_mail(store)
        test_chatnotiz(store)
        test_export(store)
        with closing(store.connect()) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
        test_foundation(folder)
    print("Selbsttest erfolgreich" + (" einschließlich echter Bilderkennung." if image else "."))


def test_foundation(folder):
    """Prüft Etappe 1: Schema-Update mit Sicherung, Warteschlange, Wiederanlauf, Protokoll, Parallelbetrieb."""
    import socket
    import urllib.request
    logfile = setup_logging(folder / "Logs")

    # 1. Älterer Bestand ohne Status, Frist und Archivtabelle wird gesichert und aktualisiert.
    legacy = folder / "Altbestand"
    legacy.mkdir()
    with closing(sqlite3.connect(legacy / "Rechtsberatung.sqlite3")) as db, db:
        db.executescript("""CREATE TABLE vorgang(id INTEGER PRIMARY KEY, titel TEXT NOT NULL,
            bereich TEXT NOT NULL, beschreibung TEXT NOT NULL,
            angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO vorgang(titel,bereich,beschreibung) VALUES('Altvorgang','Altbereich','');
            CREATE TABLE dokument(id INTEGER PRIMARY KEY, vorgang_id INTEGER NOT NULL REFERENCES vorgang(id),
                dateiname TEXT NOT NULL, titel TEXT NOT NULL, titel_seite INTEGER, titel_quelle TEXT NOT NULL,
                mime TEXT NOT NULL, dateipfad TEXT NOT NULL, sha256 TEXT NOT NULL, ocr_status TEXT NOT NULL,
                angelegt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(vorgang_id, sha256));
            CREATE TABLE dokumentseite(dokument_id INTEGER NOT NULL REFERENCES dokument(id), nummer INTEGER NOT NULL,
                methode TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(dokument_id, nummer));
            INSERT INTO dokument(vorgang_id,dateiname,titel,titel_quelle,mime,dateipfad,sha256,ocr_status)
                VALUES(1,'Bescheid.pdf','Bescheid','Betreff','application/pdf','abc.pdf','abc','PDF-Text übernommen');
            INSERT INTO dokumentseite VALUES(1,1,'pdf','Steuernummer 217/5123/4567 Einkommensteuerbescheid');""")
    old = Store(legacy, None)
    # Bestand aus dem bisherigen Stand: Dokument bleibt im Vorgang, Text ist durchsuchbar, Bereich bleibt wählbar.
    assert [d["titel"] for d in old.case_documents(1)] == ["Bescheid"]
    assert Akte(old).suche("Einkommensteuerbescheid")[0]["dokument_id"] == 1
    assert "Altbereich" in old.groups()
    assert old.list_cases()[0]["titel"] == "Altvorgang" and old.list_cases()[0]["status"] == "Schreiben verfassen"
    with closing(old.connect()) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='archivdatei'").fetchone()
        assert {"ocr_fehler", "ocr_aktualisiert_am"} <= columns_of(db, "dokument")
    backups = list((legacy / "Sicherungen").glob("*.sqlite3"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute("SELECT titel FROM vorgang").fetchone()[0] == "Altvorgang"
        assert "status" not in columns_of(db, "vorgang")  # Die Sicherung zeigt den Stand vor dem Update.
    Store(legacy, None)
    assert len(list((legacy / "Sicherungen").glob("*.sqlite3"))) == 1  # Kein Update, keine neue Sicherung.
    fresh = folder / "Neuinstallation"
    Store(fresh, None)
    assert not (fresh / "Sicherungen").exists()

    # 2. Warteschlange mit simuliertem OCR-Helfer: Titel wird übernommen, manueller Titel bleibt.
    fake = folder / "fake-ocr"
    fake.write_text("#!" + sys.executable + "\nimport json\nprint(json.dumps({'issues':[],'pages':[{'number':1,"
                    "'method':'ocr','text':'Betreff: Stellungnahme zum Heckschaden',"
                    "'lines':[{'text':'Betreff: Stellungnahme zum Heckschaden'}]}]}))\n")
    fake.chmod(0o755)
    queued = Store(folder / "Warteschlange", fake)
    case_id = queued.create_case("Warteschlange", "Versicherungen", "")
    first, _ = queued.import_document(case_id, "Scan_0001.pdf", b"%PDF-1.4\n1")
    second, _ = queued.import_document(case_id, "Scan_0002.pdf", b"%PDF-1.4\n2")
    queued.rename_document(second, "Eigener Titel")
    # Neustart: Ein neuer Dienst nimmt die unterbrochenen Aufträge wieder auf.
    restarted = Store(folder / "Warteschlange", fake)
    restarted.start_worker()
    restarted.queue.join()
    assert restarted.document(first)["titel"] == "Stellungnahme zum Heckschaden"
    assert restarted.document(first)["titel_quelle"] == "Betreff"
    assert restarted.document(first)["ocr_status"] == "OCR abgeschlossen"
    assert restarted.document(second)["titel"] == "Eigener Titel"
    assert restarted.pages(first)[0]["methode"] == "ocr"
    assert restarted.document(first)["ansicht"] is None and restarted.pages(first)[0]["drehung"] == 0

    # 2a. Automatische Drehung: Liegt eine Seite auf dem Kopf, entsteht eine aufrechte Ansichtsfassung.
    dreh = folder / "fake-ocr-dreh"
    dreh.write_text("#!" + sys.executable + "\nimport json,sys\nif len(sys.argv)==4: open(sys.argv[3],'wb').write(b'%PDF-1.4 aufrecht')\n"
                    "print(json.dumps({'issues':[],'pages':[{'number':1,'method':'ocr','rotation':180,"
                    "'text':'Betreff: Kopfstand','lines':[]}]}))\n")
    dreh.chmod(0o755)
    gedreht = Store(folder / "Drehung", dreh)
    dcase = gedreht.create_case("Drehung", "Versicherungen", "")
    ddoc, _ = gedreht.import_document(dcase, "Scan_kopf.pdf", b"%PDF-1.4\nkopf")
    gedreht.process_pending()
    drow = gedreht.document(ddoc)
    assert gedreht.pages(ddoc)[0]["drehung"] == 180 and drow["ansicht"] == drow["sha256"] + ".pdf", drow["ansicht"]
    assert (gedreht.ansicht / drow["ansicht"]).read_bytes() == b"%PDF-1.4 aufrecht"
    assert (gedreht.uploads / drow["dateipfad"]).read_bytes() == b"%PDF-1.4\nkopf"  # Original unverändert
    assert not list(gedreht.ansicht.glob("*.tmp"))
    # Scan-Ordner: fertige Dateien kommen in den Posteingang, halbfertige erst im nächsten Durchlauf
    so = ScanOrdner(gedreht, folder / "Scanordner")
    so.ordner.mkdir()
    (so.ordner / "Scan 1.pdf").write_bytes(b"%PDF-1.4\nScanordner")
    (so.ordner / "notiz.txt").write_text("nein")
    assert so.einmal(time.time() + 10) == 0  # erster Blick: Größe merken
    assert so.einmal(time.time() + 10) == 1
    assert (so.ordner / "Übernommen" / "Scan 1.pdf").is_file() and (so.ordner / "notiz.txt").is_file()
    assert any(d["dateiname"] == "Scan 1.pdf" for d in Akte(gedreht).posteingang())
    (so.ordner / "kaputt.pdf").write_bytes(b"kein pdf")
    so.einmal(time.time() + 10); so.einmal(time.time() + 10)
    assert (so.ordner / "Nicht übernommen" / "kaputt.pdf").is_file()
    if not Path("/usr/bin/sips").exists():  # ohne sips: Vorschaubild nur für unverändertes JPEG/PNG
        assert gedreht.vorschaubild(ddoc) is None
    # Bild auf dem Kopf: Ansichtsfassung als JPEG, damit Kachel und Vorschau es als Bild zeigen
    bild = folder / "fake-ocr-bild"
    bild.write_text("#!" + sys.executable + "\nimport json,sys\nif len(sys.argv)==4: open(sys.argv[3],'wb').write(b'\\xff\\xd8\\xff jpeg')\n"
                    "print(json.dumps({'issues':[],'pages':[{'number':1,'method':'ocr','rotation':180,"
                    "'text':'Betreff: Kopfstand Bild','lines':[]}]}))\n")
    bild.chmod(0o755)
    gedreht.ocr = bild
    bdoc, _ = gedreht.import_document(dcase, "Scan_kopf.jpg", b"\xff\xd8\xff\xe0 original")
    gedreht.process_pending()
    assert gedreht.document(bdoc)["ansicht"].endswith(".jpg")
    # Fehlgeschlagene erneute Erkennung löscht vorhandenen Text nicht
    gedreht.ocr = folder / "fehlt"
    gedreht.retry_ocr(bdoc)
    gedreht.process_pending()
    assert gedreht.pages(bdoc)[0]["text"] == "Betreff: Kopfstand Bild", gedreht.pages(bdoc)
    assert gedreht.document(bdoc)["ocr_status"].startswith("Erneute Erkennung fehlgeschlagen")
    restarted.retry_ocr(first)
    restarted.queue.join()
    assert restarted.document(first)["ocr_status"] == "OCR abgeschlossen"
    assert len(restarted.pages(first)) == 1  # Erneute Erkennung ersetzt die Seiten, statt sie zu verdoppeln.

    # 3. Fehler des Helfers landen mit Ursache in Datenbank und Protokoll.
    broken = folder / "broken-ocr"
    broken.write_text("#!" + sys.executable + "\nimport sys\nsys.stderr.write('Failed to create CVPixelBuffer')\n"
                      "sys.exit(3)\n")
    broken.chmod(0o755)
    failing = Store(folder / "Fehlerfall", broken)
    case_id = failing.create_case("Fehlerfall", "Anderes", "")
    doc_id, _ = failing.import_document(case_id, "Foto.png", b"\x89PNG\r\n\x1a\nx")
    failing.process_pending()
    assert failing.document(doc_id)["ocr_status"] == "Texterkennung fehlgeschlagen"
    assert "CVPixelBuffer" in failing.document(doc_id)["ocr_fehler"]
    assert failing.document(doc_id)["titel"] == "Foto"

    # 4. Der Server beantwortet Anfragen, während eine andere Anfrage noch hängt.
    Handler.store, Handler.scanner, Handler.chat, Handler.akte = queued, Scanner(queued), ChatSync(queued), Akte(queued)
    server = LocalServer(("127.0.0.1", 0), Handler)
    saved_host = Handler.host
    Handler.host = f"127.0.0.1:{server.server_address[1]}"
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        slow = socket.create_connection(("127.0.0.1", server.server_address[1]))
        slow.sendall(f"POST /api/cases HTTP/1.1\r\nHost: {Handler.host}\r\nX-Korrespondenz: lokal\r\n"
                     "Content-Length: 500\r\n\r\n{".encode())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        started = time.monotonic()
        with opener.open(f"http://{Handler.host}/api/cases", timeout=5) as response:
            assert response.status == 200 and json.loads(response.read())["cases"]
        assert time.monotonic() - started < 2, "Server blockiert"
        slow.close()
    finally:
        server.shutdown()
        server.server_close()
        Handler.host = saved_host
    for handler in log.handlers:
        handler.flush()
    text = logfile.read_text(encoding="utf-8")
    assert "Sicherung vor Schemaänderung" in text and "CVPixelBuffer" in text and "HTTP" in text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--test-image", type=Path)
    parser.add_argument("--ocr-binary", type=Path)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--sicherung", action="store_true", help="Vollständige Sicherung erstellen und prüfen")
    parser.add_argument("--wiederherstellen", type=Path, help="Sicherung (ZIP) in den Datenordner zurückspielen")
    parser.add_argument("--ueberschreiben", action="store_true", help="Beim Wiederherstellen vorhandene Daten ersetzen")
    args = parser.parse_args()
    os.umask(0o077)
    if args.self_test:
        self_test(args.ocr_binary, args.test_image)
        return
    if args.wiederherstellen:  # Bei beendeter Anwendung ausführen
        try:
            p = wiederherstellen(args.wiederherstellen, ROOT / "Daten", args.ueberschreiben)
        except ValueError as error:
            print(error)
            raise SystemExit(1) from None
        print(f"Wiederhergestellt: Sicherung vom {p['erstellt']}, {p['anzahl']['vorgang']} Vorgänge, "
              f"{p['anzahl']['dokument']} Dokumente, {p['dateien']} Dateien. Prüfung in Ordnung.")
        return
    if args.sicherung:
        ziel = sicherung_erstellen(Store(ROOT / "Daten", None))
        print(f"Sicherung: {ziel}\nPrüfung: {'in Ordnung' if sicherung_pruefen(ziel)['ok'] else 'FEHLER'}")
        return
    logfile = setup_logging(ROOT / "Daten" / "Logs")
    log.info("Start: Python %s, %s %s", platform.python_version(), platform.platform(), platform.machine())
    try:
        Handler.store = Store(ROOT / "Daten", args.ocr_binary)
    except (RuntimeError, sqlite3.Error) as error:
        log.exception("Datenbank konnte nicht geöffnet werden.")
        print(f"Die Datenbank konnte nicht geöffnet werden: {error}", flush=True)
        raise SystemExit(1) from None
    Handler.scanner = Scanner(Handler.store)
    Handler.chat = ChatSync(Handler.store)
    Handler.akte = Akte(Handler.store)
    Handler.store.nach_texterkennung = Handler.akte.ablage_nachtragen
    Handler.scanner.ins_archiv = lambda doc_id: Handler.ins_archiv(Handler, doc_id)
    Handler.mail = MailImport(Handler.store)
    Handler.scanordner = ScanOrdner(Handler.store, SCAN_ORDNER)
    try:
        server = LocalServer(("127.0.0.1", PORT), Handler)
    except OSError as error:
        log.error("Port %s nicht verfügbar: %s", PORT, error)
        print(f"\nDie Anwendung konnte nicht starten: Die Adresse http://{Handler.host} ist schon belegt.\n"
              "Vermutlich läuft noch eine frühere Version (zum Beispiel die bisherige Korrespondenz.app).\n"
              "Beenden Sie sie mit diesem Befehl und starten Sie danach erneut:\n\n"
              f"    lsof -ti tcp:{PORT} | xargs kill\n", flush=True)
        raise SystemExit(1) from None
    print(f"Protokoll: {logfile}", flush=True)

    def prepare_ocr():
        try:
            Handler.store.ocr = build_ocr()
        finally:
            Handler.store.ocr_ready.set()

    Handler.server_ref = server
    with server:
        if not args.ocr_binary:
            Handler.store.ocr_ready.clear()
            Thread(target=prepare_ocr, name="OCR vorbereiten", daemon=True).start()
        Handler.store.start_worker()
        Handler.scanordner.starten()
        url = f"http://{Handler.host}"
        print(f"{APP_VERSION}\nKorrespondenz läuft auf {url}. Beenden mit Ctrl+C.", flush=True)
        if args.open:
            subprocess.Popen(["/usr/bin/open", url])
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nKorrespondenz beendet.")
        finally:
            Handler.scanner.stop()


if __name__ == "__main__":
    main()

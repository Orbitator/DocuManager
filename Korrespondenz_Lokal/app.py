#!/usr/bin/env python3
"""Lokale Korrespondenzverwaltung. Startet ausschließlich auf diesem Mac."""
import argparse
import hashlib
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
from contextlib import closing
from datetime import date
from email.utils import encode_rfc2231
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import unquote, urlsplit

from chat_sync import ChatSync, MAX_EXPORT, test_chat_sync

ROOT = Path(__file__).resolve().parent
PORT = 8765
MAX_UPLOAD = 25 * 1024 * 1024
MIN_MACOS = "14.0"
SCHEMA_VERSION = 2
OCR_WAITING = "Wartet auf Texterkennung"
OCR_RUNNING = "Texterkennung läuft"
log = logging.getLogger("korrespondenz")
CASE_STATUSES = ("Schreiben verfassen", "Recherchieren", "Schreiben abgeschickt")
CASE_GROUPS = ("Rechtliche Angelegenheiten", "Finanzamt und Steuern", "Versicherungen", "Anderes")
TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
HEADING = re.compile(r"bescheid|widerspruch|einspruch|mahnung|rechnung|kündigung|schaden|"
                     r"zahlungsaufforderung|stellungnahme|anforderung|rückfrage|mitteilung|"
                     r"ordnungs(?:geld|widrigkeit)|entscheidung|aufforderung", re.IGNORECASE)
REFERENCE = re.compile(r"^(?:aktenzeichen|schadennummer|referenz|zeichen|datum|seite|"
                       r"telefon|kontakt|e-mail|telefonisch|iban|steuer(?:nr|nummer)|"
                       r"sehr geehrte|guten tag|mit freundlichen|deutschland|"
                       r"(?:ihr|unser)\s+(?:zeichen|schreiben|kontakt)|"
                       r"finanzamt|amtsgericht|landgericht|bundesamt|musterstraße)\b", re.IGNORECASE)
SUBJECT = re.compile(r"^(?:betreff|subject)\s*(?::\s*(.*))?$", re.IGNORECASE)


def select_title(pages):
    """Gibt einen erkannten Titel mit Fundstelle zurück."""
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
        raise ValueError("Erlaubt sind PDF, JPEG, PNG und TIFF.")
    signatures = {".pdf": b"%PDF-", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff",
                  ".png": b"\x89PNG\r\n\x1a\n",
                  ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*")}
    if not raw.startswith(signatures[suffix]):
        raise ValueError("Der Dateiinhalt passt nicht zur Endung.")
    return suffix


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


MIGRATIONS = ((1, migrate_1), (2, migrate_2))


class Store:
    def __init__(self, data, ocr):
        self.data = data
        self.ocr = ocr
        self.ocr_ready = Event()
        self.ocr_ready.set()
        self.queue = queue.Queue()
        self.worker = None
        self.uploads = data / "Uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
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
            return [dict(row) for row in db.execute("""SELECT v.*, count(d.id) AS dokumente
                FROM vorgang v LEFT JOIN dokument d ON d.vorgang_id=v.id
                GROUP BY v.id ORDER BY v.id DESC""")]

    def create_case(self, title, group, description, status=CASE_STATUSES[0], due=None):
        title = title.strip()
        group = group.strip() or CASE_GROUPS[-1]
        if not title or len(title) > 160 or len(description) > 4000:
            raise ValueError("Prüfe Titel und Beschreibung.")
        if group not in CASE_GROUPS:
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
        if group not in CASE_GROUPS:
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
            return [dict(row) for row in db.execute("""SELECT id,titel,dateiname,titel_seite,
                    titel_quelle,ocr_status,ocr_fehler,mime,angelegt_am FROM dokument
                    WHERE vorgang_id=? ORDER BY id DESC""", (case_id,))]

    def document(self, document_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM dokument WHERE id=?", (document_id,)).fetchone()
            return dict(row) if row else None

    def pages(self, document_id):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""SELECT nummer,methode,text FROM dokumentseite
                    WHERE dokument_id=? ORDER BY nummer""", (document_id,))]

    def rename_document(self, document_id, title):
        title = title.strip()
        if not 1 <= len(title) <= 160:
            raise ValueError("Der Titel muss 1 bis 160 Zeichen lang sein.")
        with closing(self.connect()) as db, db:
            changed = db.execute("UPDATE dokument SET titel=?,titel_seite=NULL,titel_quelle='Manuell' WHERE id=?",
                                 (title, document_id)).rowcount
        if not changed:
            raise ValueError("Dokument nicht gefunden.")

    def read_ocr(self, path, suffix):
        """Gibt Seiten, Status und gegebenenfalls einen Fehlertext für das Protokoll zurück."""
        self.ocr_ready.wait(timeout=165)
        if not self.ocr or not self.ocr.is_file():
            return [], "OCR nicht verfügbar", "OCR-Helfer fehlt oder konnte nicht gebaut werden."
        try:
            run = subprocess.run([str(self.ocr), "pdf" if suffix == ".pdf" else "image", str(path)],
                                 check=True, capture_output=True, timeout=150)
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
        pages, status, error = self.read_ocr(self.uploads / row["dateipfad"], Path(row["dateipfad"]).suffix)
        self._set_ocr_result(doc_id, pages, status, error)
        log.info("Dokument %s: %s nach %.1f s%s", doc_id, status, time.monotonic() - started,
                 f" ({error})" if error else "")

    def _set_ocr_result(self, doc_id, pages, status, error):
        title, page, source = select_title(pages)
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM dokumentseite WHERE dokument_id=?", (doc_id,))
            db.executemany("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)",
                           ((doc_id, p["number"], p["method"], p["text"]) for p in pages))
            db.execute("""UPDATE dokument SET ocr_status=?, ocr_fehler=?, ocr_aktualisiert_am=CURRENT_TIMESTAMP
                          WHERE id=?""", (status, error, doc_id))
            if title:  # Ein manuell gesetzter Titel bleibt unangetastet.
                db.execute("""UPDATE dokument SET titel=?, titel_seite=?, titel_quelle=?
                              WHERE id=? AND titel_quelle='Dateiname'""", (title, page, source, doc_id))

    def retry_ocr(self, doc_id):
        with closing(self.connect()) as db, db:
            if not db.execute("UPDATE dokument SET ocr_status=?, ocr_fehler=NULL WHERE id=?",
                              (OCR_WAITING, doc_id)).rowcount:
                raise ValueError("Dokument nicht gefunden.")
        if self.worker:
            self.queue.put(doc_id)

    def import_document(self, case_id, name, raw):
        name = unicodedata.normalize("NFC", name)
        if not name or len(name) > 240 or any(c in name for c in "/\\") or any(ord(c) < 32 for c in name):
            raise ValueError("Ungültiger Dateiname.")
        suffix = file_type(name, raw)
        digest = hashlib.sha256(raw).hexdigest()
        with closing(self.connect()) as db:
            if not db.execute("SELECT 1 FROM vorgang WHERE id=?", (case_id,)).fetchone():
                raise ValueError("Vorgang nicht gefunden.")
            existing = db.execute("SELECT id FROM dokument WHERE vorgang_id=? AND sha256=?", (case_id, digest)).fetchone()
            if existing:
                return existing["id"], False
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
            doc_id = db.execute("""INSERT INTO dokument(vorgang_id,dateiname,titel,titel_seite,titel_quelle,mime,
                dateipfad,sha256,ocr_status) VALUES(?,?,?,?,?,?,?,?,?)""",
                (case_id, name, Path(name).stem[:160], None, "Dateiname", TYPES[suffix], path.name, digest,
                 OCR_WAITING)).lastrowid
        log.info("Dokument %s in Vorgang %s abgelegt (%s Bytes).", doc_id, case_id, len(raw))
        if self.worker:
            self.queue.put(doc_id)
        return doc_id, True


class Scanner:
    def __init__(self, store):
        self.store = store
        self.job = None
        self.lock = Lock()  # Der Server bedient Anfragen parallel; ein Scanauftrag zur Zeit.

    def start(self, case_id):
        with self.lock:
            return self._start(case_id)

    def finish(self, job_id):
        with self.lock:
            return self._finish(job_id)

    def _start(self, case_id):
        if self.job and self.job["result"] is None:
            self._finish(self.job["id"])
            if self.job["result"] is None:
                raise ValueError("Der macOS-Scandialog ist bereits geöffnet.")
        if not any(item["id"] == case_id for item in self.store.list_cases()):
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
            process = subprocess.Popen([str(binary), str(folder)], stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT)
        except OSError:
            output.close()
            folder.rmdir()
            raise
        self.job = {"id": secrets.token_hex(16), "case": case_id, "folder": folder,
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
                    _, created = self.store.import_document(job["case"], name, file.read_bytes())
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
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value, status=200):
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(value, ensure_ascii=False).encode())

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
        static = {"/": ("Korrespondenz_Rechtsberatung.html", "text/html; charset=utf-8"),
                  "/lokale_vorgaenge.js": ("lokale_vorgaenge.js", "text/javascript; charset=utf-8"),
                  "/chat_notizen.js": ("chat_notizen.js", "text/javascript; charset=utf-8")}
        if path in static:
            name, mime = static[path]
            self.send_bytes(200, mime, (ROOT / name).read_bytes())
        elif path == "/api/cases":
            self.send_json({"cases": self.store.list_cases(), "statuses": CASE_STATUSES, "groups": CASE_GROUPS,
                            "ocr": bool(self.store.ocr and self.store.ocr.is_file()),
                            "ocr_loading": not self.store.ocr_ready.is_set()})
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
        elif match := re.fullmatch(r"/api/documents/(\d+)/(original|pages)", path):
            doc_id = int(match[1])
            row = self.store.document(doc_id)
            if row is None:
                self.send_json({"error": "Dokument nicht gefunden."}, 404)
            elif match[2] == "pages":
                self.send_json({"pages": self.store.pages(doc_id)})
            else:
                file = self.store.uploads / row["dateipfad"]
                if not file.is_file():
                    self.send_json({"error": "Das Original fehlt."}, 404)
                else:
                    encoded = encode_rfc2231(row["dateiname"], "utf-8")
                    self.send_bytes(200, row["mime"], file.read_bytes(), "inline; filename*=" + encoded)
        else:
            self.send_json({"error": "Seite nicht gefunden."}, 404)

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
                                                 data.get("status", CASE_STATUSES[0]), data.get("due"))
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
            elif match := re.fullmatch(r"/api/cases/(\d+)/scan", path):
                self.send_json({"id": self.scanner.start(int(match[1]))}, 201)
            elif match := re.fullmatch(r"/api/scans/([0-9a-f]{32})/poll", path):
                self.send_json(self.scanner.finish(match[1]))
            elif match := re.fullmatch(r"/api/cases/(\d+)/documents", path):
                name = unquote(self.headers.get("X-Dateiname", ""), errors="strict")
                doc_id, created = self.store.import_document(int(match[1]), name, self.read_body(MAX_UPLOAD))
                self.send_json({"id": doc_id, "created": created}, 201 if created else 200)
            elif match := re.fullmatch(r"/api/documents/(\d+)/title", path):
                self.store.rename_document(int(match[1]), json.loads(self.read_body(4000))["title"])
                self.send_json({"ok": True})
            elif match := re.fullmatch(r"/api/documents/(\d+)/ocr", path):
                self.store.retry_ocr(int(match[1]))
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "Seite nicht gefunden."}, 404)
        except (ValueError, KeyError, AttributeError, TypeError) as error:
            log.info("Abgelehnt %s: %s", path, error)
            self.send_json({"error": str(error) if isinstance(error, ValueError) else "Ungültige Eingabe."}, 400)
        except (OSError, sqlite3.Error):
            log.exception("Fehler bei %s", path)
            self.send_json({"error": "Speichern fehlgeschlagen. Prüfe freien Speicher und Schreibrechte. "
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


def build_scanner():
    return build_helper("korrespondenz-scanner", ROOT / "scanner.m",
                        ["/usr/bin/clang", "-fobjc-arc", "-O2", f"-mmacosx-version-min={MIN_MACOS}",
                         "-framework", "Cocoa", "-framework", "Quartz", "-framework", "ImageCaptureCore"], 120)


def self_test(ocr=None, image=None):
    line = {"text": "Betreff: Stellungnahme zum Frontschaden"}
    assert select_title([{"number": 1, "lines": [{"text": "Aktenzeichen 4711"}, line]}]) == (
        "Stellungnahme zum Frontschaden", 1, "Betreff")
    assert select_title([{"number": 1, "lines": [{"text": "Betreff"}, {"text": "Unterlagen zur Prüfung"}]}])[0] == "Unterlagen zur Prüfung"
    assert select_title([{"number": 1, "lines": [{"text": "Datum: 24.11.2026"}]}])[0] == ""
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
        assert len(store.case_documents(case_id)) == 2
        assert not scan_folder.exists()
        test_chat_sync(store)
        with closing(store.connect()) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
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
            INSERT INTO vorgang(titel,bereich,beschreibung) VALUES('Altvorgang','Anderes','');""")
    old = Store(legacy, None)
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
    Handler.store, Handler.scanner, Handler.chat = queued, Scanner(queued), ChatSync(queued)
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
    args = parser.parse_args()
    os.umask(0o077)
    if args.self_test:
        self_test(args.ocr_binary, args.test_image)
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
    try:
        server = LocalServer(("127.0.0.1", PORT), Handler)
    except OSError as error:
        log.error("Port %s nicht verfügbar: %s", PORT, error)
        print(f"Die Anwendung konnte http://{Handler.host} nicht starten: {error}", flush=True)
        raise SystemExit(1) from None
    print(f"Protokoll: {logfile}", flush=True)

    def prepare_ocr():
        try:
            Handler.store.ocr = build_ocr()
        finally:
            Handler.store.ocr_ready.set()

    with server:
        if not args.ocr_binary:
            Handler.store.ocr_ready.clear()
            Thread(target=prepare_ocr, name="OCR vorbereiten", daemon=True).start()
        Handler.store.start_worker()
        url = f"http://{Handler.host}"
        print(f"Korrespondenz läuft auf {url}. Beenden mit Ctrl+C.", flush=True)
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

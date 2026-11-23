#!/usr/bin/env python3
"""Lokale Korrespondenzverwaltung. Startet ausschließlich auf diesem Mac."""
import argparse
import hashlib
import json
import os
import re
import shutil
import secrets
import sqlite3
import subprocess
import tempfile
import unicodedata
from contextlib import closing
from datetime import date
from email.utils import encode_rfc2231
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import unquote, urlsplit

from chat_sync import ChatSync, MAX_EXPORT, test_chat_sync

ROOT = Path(__file__).resolve().parent
PORT = 8765
MAX_UPLOAD = 25 * 1024 * 1024
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


class Store:
    def __init__(self, data, ocr):
        self.data = data
        self.ocr = ocr
        self.ocr_ready = Event()
        self.ocr_ready.set()
        self.uploads = data / "Uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
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
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(vorgang)")}
            if "status" not in columns:
                db.execute("ALTER TABLE vorgang ADD COLUMN status TEXT NOT NULL DEFAULT 'Schreiben verfassen'")
            if "naechste_frist" not in columns:
                db.execute("ALTER TABLE vorgang ADD COLUMN naechste_frist TEXT")

    def connect(self):
        db = sqlite3.connect(self.data / "Rechtsberatung.sqlite3")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

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
                    titel_quelle,ocr_status,mime,angelegt_am FROM dokument
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
        self.ocr_ready.wait(timeout=165)
        if not self.ocr or not self.ocr.is_file():
            return [], "OCR nicht verfügbar"
        try:
            run = subprocess.run([str(self.ocr), "pdf" if suffix == ".pdf" else "image", str(path)],
                                 check=True, capture_output=True, timeout=150)
            result = json.loads(run.stdout)
            pages = result["pages"]
            if not pages:
                return [], "Kein Text erkannt"
            if result["issues"]:
                return pages, "Text teilweise erkannt"
            return pages, "OCR abgeschlossen" if any(p["method"] == "ocr" for p in pages) else "PDF-Text übernommen"
        except subprocess.CalledProcessError as error:
            if b"tooManyPages" in error.stderr:
                return [], "Texterkennung übersprungen: mehr als 40 Seiten"
            return [], "Texterkennung fehlgeschlagen"
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            return [], "Texterkennung fehlgeschlagen"

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
        pages, status = self.read_ocr(path, suffix)
        title, page, source = select_title(pages)
        if not title:
            title, source = Path(name).stem[:160], "Dateiname"
        with closing(self.connect()) as db, db:
            doc_id = db.execute("""INSERT INTO dokument(vorgang_id,dateiname,titel,titel_seite,titel_quelle,mime,
                dateipfad,sha256,ocr_status) VALUES(?,?,?,?,?,?,?,?,?)""",
                (case_id, name, title, page, source, TYPES[suffix], path.name, digest, status)).lastrowid
            db.executemany("""INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)""",
                           ((doc_id, p["number"], p["method"], p["text"]) for p in pages))
        return doc_id, True


class Scanner:
    def __init__(self, store):
        self.store = store
        self.job = None

    def start(self, case_id):
        if self.job and self.job["result"] is None:
            self.finish(self.job["id"])
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
        try:
            process = subprocess.Popen([str(binary), str(folder)], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            folder.rmdir()
            raise
        self.job = {"id": secrets.token_hex(16), "case": case_id, "folder": folder,
                    "process": process, "result": None}
        return self.job["id"]

    def finish(self, job_id):
        job = self.job
        if not job or job["id"] != job_id:
            raise ValueError("Scanvorgang nicht gefunden.")
        if job["result"] is not None:
            return job["result"]
        code = job["process"].poll()
        if code is None:
            return {"state": "open"}
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
            errors.append("Die Scan-Dateien liegen weiterhin im lokalen Ordner Daten/Scan_Eingang/" + folder.name + ".")
        else:
            shutil.rmtree(folder)
        job["result"] = {"state": "done", "imported": imported, "duplicates": duplicates, "errors": errors}
        return job["result"]

    def stop(self):
        if self.job and self.job["process"].poll() is None:
            self.job["process"].terminate()



class Handler(BaseHTTPRequestHandler):
    store = None
    scanner = None
    chat = None
    host = f"127.0.0.1:{PORT}"

    def log_message(self, *_):
        pass

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
                self.send_json(self.chat.preview(self.read_body(MAX_EXPORT)))
            elif path == "/api/chat/import":
                data = json.loads(self.read_body(24000))
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
            else:
                self.send_json({"error": "Seite nicht gefunden."}, 404)
        except (ValueError, KeyError, AttributeError, TypeError) as error:
            self.send_json({"error": str(error) if isinstance(error, ValueError) else "Ungültige Eingabe."}, 400)
        except (OSError, sqlite3.Error):
            self.send_json({"error": "Speichern fehlgeschlagen. Prüfe freien Speicher und Schreibrechte."}, 500)


def build_ocr():
    runtime = ROOT / "Daten" / "Laufzeit"
    runtime.mkdir(parents=True, exist_ok=True)
    source = ROOT / "ocr.swift"
    binary = runtime / "korrespondenz-ocr"
    if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary
    stage = binary.with_suffix(".tmp")
    try:
        subprocess.run(["/usr/bin/swiftc", "-O", "-module-cache-path", str(runtime / "SwiftCache"),
                        str(source), "-o", str(stage)], check=True, timeout=160)
        os.replace(stage, binary)
        return binary
    except (OSError, subprocess.SubprocessError):
        print("OCR ist derzeit nicht verfügbar. Das Anlegen von Vorgängen und der Import bleiben möglich.")
        return None
    finally:
        stage.unlink(missing_ok=True)


def build_scanner():
    runtime = ROOT / "Daten" / "Laufzeit"
    runtime.mkdir(parents=True, exist_ok=True)
    source = ROOT / "scanner.m"
    binary = runtime / "korrespondenz-scanner"
    if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary
    stage = binary.with_suffix(".tmp")
    try:
        subprocess.run(["/usr/bin/clang", "-fobjc-arc", "-O2", "-framework", "Cocoa",
                        "-framework", "Quartz", "-framework", "ImageCaptureCore",
                        str(source), "-o", str(stage)], check=True, timeout=120)
        os.replace(stage, binary)
        return binary
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        stage.unlink(missing_ok=True)


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
    print("Selbsttest erfolgreich" + (" einschließlich echter Bilderkennung." if image else "."))


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
    Handler.store = Store(ROOT / "Daten", args.ocr_binary)
    Handler.scanner = Scanner(Handler.store)
    Handler.chat = ChatSync(Handler.store)
    try:
        server = HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as error:
        print(f"Die Anwendung konnte http://{Handler.host} nicht starten: {error}", flush=True)
        raise SystemExit(1) from None

    def prepare_ocr():
        try:
            Handler.store.ocr = build_ocr()
        finally:
            Handler.store.ocr_ready.set()

    with server:
        if not args.ocr_binary:
            Handler.store.ocr_ready.clear()
            Thread(target=prepare_ocr, name="OCR vorbereiten", daemon=True).start()
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

"""Importiert ausgewählte ChatGPT-Unterhaltungen und ihre Anlagen lokal."""
import hashlib
import io
import json
import math
import os
import re
import secrets
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

MAX_EXPORT = 250 * 1024 * 1024
MAX_JSON = 150 * 1024 * 1024
MAX_ASSET = 25 * 1024 * 1024
JSON_NAME = re.compile(r"conversations(?:[-_]\d+)?\.json$", re.I)
ID = re.compile(r"[A-Za-z0-9_-]{1,160}$")
FILE_ID = re.compile(r"file[-_][A-Za-z0-9]{6,100}")
ROLES = {"user", "assistant"}


def stable_id(value):
    return value if isinstance(value, str) and ID.fullmatch(value) else ""


def asset_id(value):
    if not isinstance(value, str):
        return ""
    match = FILE_ID.search(value)
    return match[0] if match else ""


def clean_name(value):
    if not isinstance(value, str):
        return ""
    name = PurePosixPath(value.replace("\\", "/")).name
    return "".join(c for c in name if 32 <= ord(c) != 127)[:240]


def timestamp(value):
    return value if type(value) in {float, int} and math.isfinite(value) and 0 <= value < 253402300799 else None


def collect_attachments(message):
    metadata = message.get("metadata") or {}
    content = message.get("content") or {}
    parts = content.get("parts") or ([content] if content.get("asset_pointer") else [])
    attachments = []
    by_id = {}
    for entry in [*(metadata.get("attachments") or []), *parts]:
        if not isinstance(entry, dict):
            continue
        identity = asset_id(entry.get("id") or entry.get("file_id") or entry.get("asset_pointer"))
        name = clean_name(entry.get("name") or entry.get("filename") or entry.get("file_name"))
        if not identity and (not name or entry in parts):
            continue
        if identity and identity in by_id:
            if name and not by_id[identity]["name"]:
                by_id[identity]["name"] = name
            continue
        item = {"id": identity, "name": name}
        if identity:
            by_id[identity] = item
        attachments.append(item)
    return attachments


def messages(conversation):
    graph = conversation.get("mapping") or {}
    if not isinstance(graph, dict):
        return []
    current = conversation.get("current_node")
    visible_branch = set()
    while isinstance(current, str) and current in graph and current not in visible_branch:
        visible_branch.add(current)
        node = graph[current]
        current = node.get("parent") if isinstance(node, dict) else None
    result = []
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        identity = stable_id(message.get("id") or node_id)
        role = (message.get("author") or {}).get("role")
        if role not in ROLES or not identity or message.get("recipient", "all") not in {"all", None}:
            continue
        meta = message.get("metadata") or {}
        if meta.get("is_visually_hidden_from_conversation"):
            continue
        content = message.get("content") or {}
        if content.get("content_type") not in {None, "text", "multimodal_text", "image_asset_pointer"}:
            continue
        parts = content.get("parts") or []
        text = "\n\n".join(part for part in parts if isinstance(part, str)).strip()
        attachments = collect_attachments(message)
        if text or attachments:
            result.append({"id":identity, "role":role, "text":text, "attachments":attachments,
                           "date":timestamp(message.get("create_time")),
                           "alternate":bool(visible_branch and node_id not in visible_branch)})
    return sorted(result, key=lambda row: row["date"] if row["date"] is not None else -1)


class ChatExport:
    def __init__(self, raw):
        self.archive = None
        self.conversations = {}
        self.assets = {}
        try:
            if zipfile.is_zipfile(io.BytesIO(raw)):
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    entries = archive.infolist()
                    chosen = [entry for entry in entries if not entry.is_dir() and
                              JSON_NAME.fullmatch(PurePosixPath(entry.filename).name)]
                    if not chosen or sum(entry.file_size for entry in chosen) > MAX_JSON:
                        raise ValueError("Die ZIP-Datei enthält keine lesbare Unterhaltungs-JSON bis 150 MB.")
                    for entry in chosen:
                        self.add(json.loads(archive.read(entry)))
                    for entry in entries:
                        if not entry.is_dir() and 0 < entry.file_size <= MAX_ASSET:
                            name = PurePosixPath(entry.filename).name
                            self.assets.setdefault(name, []).append(entry.filename)
                self.archive = raw
            else:
                if len(raw) > MAX_JSON:
                    raise ValueError("JSON-Exporte dürfen bis zu 150 MB groß sein.")
                self.add(json.loads(raw.decode("utf-8-sig")))
        except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile, RuntimeError) as error:
            raise ValueError("Die Exportdatei konnte nicht gelesen werden.") from error
        if not self.conversations:
            raise ValueError("Der Export enthält keine unterstützten ChatGPT-Unterhaltungen.")

    def add(self, value):
        rows = value.get("conversations", [value]) if isinstance(value, dict) else value
        if not isinstance(rows, list):
            raise ValueError("Die Datei enthält keine Liste mit ChatGPT-Unterhaltungen.")
        for row in rows:
            if not isinstance(row, dict):
                continue
            identity = stable_id(row.get("conversation_id") or row.get("id"))
            if not identity or not isinstance(row.get("mapping"), dict):
                continue
            previous = self.conversations.get(identity)
            updated = timestamp(row.get("update_time")) or timestamp(row.get("create_time")) or 0
            previous_date = (timestamp(previous.get("update_time")) or timestamp(previous.get("create_time")) or 0) if previous else -1
            if updated >= previous_date:
                self.conversations[identity] = row

    def file_member(self, identity, name):
        if not self.archive:
            return None
        if identity:
            matches = [(key, entries) for key, entries in self.assets.items()
                       if key == identity or key.startswith((identity + "-", identity + "_", identity + "."))]
            if len(matches) == 1 and len(matches[0][1]) == 1:
                return matches[0][1][0]
            if name:
                exact = self.assets.get(identity + "-" + name, [])
                return exact[0] if len(exact) == 1 else None
            return None
        exact = self.assets.get(name, [])
        return exact[0] if name and len(exact) == 1 else None


class ChatSync:
    def __init__(self, store):
        self.store = store
        self.pending = None
        self.originals = store.data / "Chat_Originale"
        self.originals.mkdir(exist_ok=True)
        with closing(store.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chat_thread(
                    id TEXT PRIMARY KEY, titel TEXT NOT NULL, stand REAL, importiert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_notiz(
                    thread_id TEXT NOT NULL REFERENCES chat_thread(id), id TEXT NOT NULL,
                    rolle TEXT NOT NULL, text TEXT NOT NULL, datum REAL, alternativ INTEGER NOT NULL,
                    PRIMARY KEY(thread_id,id)
                );
                CREATE TABLE IF NOT EXISTS chat_anlage(
                    id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL, notiz_id TEXT NOT NULL,
                    schluessel TEXT NOT NULL, datei_id TEXT NOT NULL, name TEXT NOT NULL,
                    archiv_id TEXT, sha256 TEXT,
                    FOREIGN KEY(thread_id,notiz_id) REFERENCES chat_notiz(thread_id,id),
                    UNIQUE(thread_id,notiz_id,schluessel)
                );
            """)

    def preview(self, raw):
        self.pending = None
        export = ChatExport(raw)
        token = secrets.token_hex(24)
        self.pending = (token, time.monotonic(), export)
        with closing(self.store.connect()) as db:
            imported = {row["id"] for row in db.execute("SELECT id FROM chat_thread")}
        rows = [{"id":identity, "title":str(item.get("title") or "Unterhaltung ohne Titel")[:250],
                 "date":timestamp(item.get("update_time")) or timestamp(item.get("create_time")),
                 "known":identity in imported} for identity,item in export.conversations.items()]
        return {"token":token, "threads":sorted(rows, key=lambda row: row["date"] or 0, reverse=True)}

    def threads(self):
        with closing(self.store.connect()) as db:
            rows = db.execute("""SELECT t.*, count(n.id) AS notizen FROM chat_thread t
                LEFT JOIN chat_notiz n ON n.thread_id=t.id GROUP BY t.id ORDER BY t.stand DESC, t.titel""")
            return [dict(row) for row in rows]

    def notes(self, identity):
        with closing(self.store.connect()) as db:
            notes = [dict(row, anlagen=[]) for row in db.execute("""SELECT id,rolle,text,datum,alternativ
                FROM chat_notiz WHERE thread_id=? ORDER BY datum,rowid""", (identity,))]
            by_id = {row["id"]:row for row in notes}
            for row in db.execute("SELECT * FROM chat_anlage WHERE thread_id=? ORDER BY id", (identity,)):
                item = dict(row)
                item["local"] = bool(item.pop("sha256") and (self.originals / row["sha256"]).is_file())
                by_id[row["notiz_id"]]["anlagen"].append(item)
            return notes

    def original(self, identity):
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT name,sha256 FROM chat_anlage WHERE id=?", (identity,)).fetchone()
        if row and row["sha256"]:
            path = self.originals / row["sha256"]
            if path.is_file():
                return row["name"], path.read_bytes()
        return None

    def import_selected(self, token, identities):
        if not self.pending or token != self.pending[0] or time.monotonic() - self.pending[1] > 1800:
            raise ValueError("Die Exportvorschau ist abgelaufen. Wähle die Exportdatei erneut.")
        export = self.pending[2]
        if not isinstance(identities, list) or not identities or len(identities) > 100 or not all(
            stable_id(identity) in export.conversations for identity in identities
        ):
            raise ValueError("Wähle bis zu 100 Unterhaltungen aus der Vorschau aus.")
        counts = {"notes":0,"updated":0,"unchanged":0,"originals":0,"missing":0}
        archive = zipfile.ZipFile(io.BytesIO(export.archive)) if export.archive else None
        try:
            with closing(self.store.connect()) as db, db:
                has_library = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='archivdatei'").fetchone()
                for identity in dict.fromkeys(identities):
                    conversation = export.conversations[identity]
                    updated = timestamp(conversation.get("update_time")) or timestamp(conversation.get("create_time"))
                    title = str(conversation.get("title") or "Unterhaltung ohne Titel")[:250]
                    prior = db.execute("SELECT stand FROM chat_thread WHERE id=?", (identity,)).fetchone()
                    older = bool(prior and prior["stand"] and (updated or 0) < prior["stand"])
                    db.execute("""INSERT INTO chat_thread(id,titel,stand) VALUES(?,?,?) ON CONFLICT(id)
                        DO UPDATE SET titel=excluded.titel,stand=coalesce(excluded.stand,chat_thread.stand),
                        importiert_am=CURRENT_TIMESTAMP WHERE chat_thread.stand IS NULL
                        OR coalesce(excluded.stand, 0)>=chat_thread.stand""", (identity,title,updated))
                    for note in messages(conversation):
                        old = db.execute("SELECT text,datum,rolle,alternativ FROM chat_notiz WHERE thread_id=? AND id=?",
                                         (identity,note["id"])).fetchone()
                        values = (note["text"],note["date"],note["role"],int(note["alternate"]))
                        if old is not None and older:
                            values = tuple(old)
                        if old is None:
                            counts["notes"] += 1
                        elif tuple(old) == values:
                            counts["unchanged"] += 1
                        else:
                            counts["updated"] += 1
                        db.execute("""INSERT INTO chat_notiz(thread_id,id,text,datum,rolle,alternativ) VALUES(?,?,?,?,?,?)
                            ON CONFLICT(thread_id,id) DO UPDATE SET text=excluded.text,datum=excluded.datum,
                            rolle=excluded.rolle,alternativ=excluded.alternativ""", (identity,note["id"],*values))
                        for item in note["attachments"]:
                            self.save_attachment(db, archive, export, identity, note["id"], item, has_library, counts)
        finally:
            if archive:
                archive.close()
        self.pending = None
        return counts

    def save_attachment(self, db, archive, export, thread, note, item, has_library, counts):
        file_id, name = item["id"], item["name"]
        key = file_id or ("name:" + name)
        candidates = db.execute("""SELECT id,dateiname FROM archivdatei WHERE datei_id=? OR id=?""",
                                (file_id, file_id)).fetchall() if file_id and has_library else []
        if not candidates and not file_id and name and has_library:
            candidates = db.execute("SELECT id,dateiname FROM archivdatei WHERE dateiname=?", (name,)).fetchall()
        source = candidates[0] if len(candidates) == 1 else None
        member = export.file_member(file_id, name or (source["dateiname"] if source else ""))
        previous = db.execute("""SELECT sha256 FROM chat_anlage WHERE thread_id=? AND notiz_id=? AND schluessel=?""",
                              (thread,note,key)).fetchone()
        digest = previous["sha256"] if previous else None
        if digest and not (self.originals / digest).is_file():
            digest = None
        if member and archive and not digest:
            digest = self.save_original(archive, member)
            counts["originals"] += 1
        if not digest:
            counts["missing"] += 1
        display = name or (source["dateiname"] if source else clean_name(member)) or file_id or "Anlage"
        db.execute("""INSERT INTO chat_anlage(thread_id,notiz_id,schluessel,datei_id,name,archiv_id,sha256)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(thread_id,notiz_id,schluessel) DO UPDATE SET name=excluded.name,
            archiv_id=coalesce(excluded.archiv_id,chat_anlage.archiv_id),sha256=excluded.sha256""",
            (thread,note,key,file_id,display,source["id"] if source else None,digest))

    def save_original(self, archive, member):
        with archive.open(member) as source:
            raw = source.read(MAX_ASSET + 1)
        if len(raw) > MAX_ASSET:
            raise ValueError("Eine Exportanlage ist größer als 25 MB.")
        digest = hashlib.sha256(raw).hexdigest()
        path = self.originals / digest
        if not path.is_file():
            with tempfile.NamedTemporaryFile(dir=self.originals, delete=False) as stage:
                stage_path = Path(stage.name)
                try:
                    stage.write(raw)
                    stage.close()
                    os.replace(stage_path, path)
                finally:
                    stage_path.unlink(missing_ok=True)
        return digest


def test_chat_sync(store):
    """Synthetische Exportdaten, ohne Zugriff auf ChatGPT oder fremde Nutzerdaten."""
    def message_graph(text, time_value, more=False):
        graph = {
            "u1": {"parent":None,"message":{"id":"u1","author":{"role":"user"},
                "create_time":1,"content":{"parts":["Aufgabe prüfen"]},"metadata":{"attachments":[
                    {"id":"file-abcdef1","name":"Beleg.pdf"},{"id":"file_abcdef2","name":"Register.pdf"},
                    {"id":"file-abcdef3","name":"Fehlt.pdf"}]}}},
            "a1": {"parent":"u1","message":{"id":"a1","author":{"role":"assistant"},"create_time":2,
                "content":{"parts":[text]}}},
            "other-branch": {"parent":"u1","message":{"id":"other-branch","author":{"role":"assistant"},
                "create_time":1.5,"content":{"parts":["Andere sichtbare Variante"]}}},
            "hidden": {"parent":"u1","message":{"id":"hidden","author":{"role":"assistant"},"create_time":1.6,
                "metadata":{"is_visually_hidden_from_conversation":True},"content":{"parts":["Ausgeschlossen"]}}},
        }
        if more:
            graph["u2"] = {"parent":"a1","message":{"id":"u2","author":{"role":"user"},"create_time":3,
                                           "content":{"parts":["Entwurf übernehmen"]}}}
        return {"id":"thread-1","title":"Rechtsberatung","current_node":"u2" if more else "a1",
                "update_time":time_value,"mapping":graph}

    payload = [message_graph("Schlussfolgerung eins", 2), {"id":"foreign","title":"Privater anderer Chat",
        "update_time":2,"mapping":{"m":{"message":{"id":"other","author":{"role":"user"},
        "content":{"parts":["Wird nicht übernommen"]}}}}}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nested/conversations-001.json", json.dumps(payload))
        archive.writestr("assets/file-abcdef1-Beleg.pdf", b"%PDF-1.4\nexample")
    with closing(store.connect()) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS archivdatei(id TEXT PRIMARY KEY, datei_id TEXT NOT NULL, "
                   "dateiname TEXT NOT NULL, mime_typ TEXT NOT NULL, groesse_bytes INTEGER NOT NULL, "
                   "archiviert_am TEXT NOT NULL, lokaler_pfad TEXT, sha256 TEXT)")
        db.execute("INSERT INTO archivdatei(id,datei_id,dateiname,mime_typ,groesse_bytes,archiviert_am) "
                   "VALUES('libfile_example','file_abcdef2','Register.pdf','application/pdf',0,'2026-01-01')")
    sync = ChatSync(store)
    selection = sync.preview(buffer.getvalue())
    assert {row["id"] for row in selection["threads"]} == {"thread-1","foreign"}
    count = sync.import_selected(selection["token"], ["thread-1"])
    assert count == {"notes":3,"updated":0,"unchanged":0,"originals":1,"missing":2}, count
    assert len(sync.threads()) == 1 and not sync.notes("foreign")
    notes = sync.notes("thread-1")
    assert notes[1]["alternativ"] == 1
    by_name = {attachment["name"]:attachment for attachment in notes[0]["anlagen"]}
    assert by_name["Beleg.pdf"]["local"] and by_name["Register.pdf"]["archiv_id"] == "libfile_example"
    assert not by_name["Fehlt.pdf"]["local"]
    assert sync.original(by_name["Beleg.pdf"]["id"]) == ("Beleg.pdf", b"%PDF-1.4\nexample")
    preview = sync.preview(json.dumps([message_graph("Schlussfolgerung zwei", 3, True)]).encode())
    assert preview["threads"][0]["known"]
    count = sync.import_selected(preview["token"], ["thread-1","thread-1"])
    assert count["notes"] == 1 and count["updated"] == 1
    assert len(sync.notes("thread-1")) == 4
    assert sync.notes("thread-1")[0]["anlagen"][0]["local"]
    preview = sync.preview(buffer.getvalue())
    count = sync.import_selected(preview["token"], ["thread-1"])
    assert count["updated"] == count["notes"] == 0
    assert "Schlussfolgerung zwei" in {note["text"] for note in sync.notes("thread-1")}

"""Übernahme von E-Mails aus Apple Mail.

E-Mails mit einer bestimmten Markierung (Vorgabe: Grau, in Mail „Erfasster Beleg“) werden über die
macOS-Automatisierung (osascript, JavaScript for Automation) gelesen und in den Posteingang übernommen:
die E-Mail selbst als Dokument mit Text, unterstützte Anlagen (PDF, JPEG, PNG, TIFF) als eigene Dokumente.
Doppelungen verhindern zwei Prüfungen: die Message-ID und ein Fingerabdruck (SHA-256) der ganzen E-Mail.
Zeitpunkt und Ergebnis des letzten Abrufs werden gespeichert. Die Markierung in Mail bleibt unverändert.
"""
import email
import email.policy
import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

FARBEN = {0: "Rot", 1: "Orange", 2: "Gelb", 3: "Grün", 4: "Blau", 5: "Violett", 6: "Grau"}
MAX_JE_ABRUF = 25
MAX_MAIL = 40 * 1024 * 1024

SCHEMA_5 = """
CREATE TABLE IF NOT EXISTS mail_import(
    message_id TEXT PRIMARY KEY, dokument_id INTEGER NOT NULL REFERENCES dokument(id),
    betreff TEXT, absender TEXT, postfach TEXT, importiert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mail_anlage(
    message_id TEXT NOT NULL REFERENCES mail_import(message_id), dokument_id INTEGER NOT NULL REFERENCES dokument(id),
    PRIMARY KEY(message_id, dokument_id)
);
"""


def migrate_5(db):
    db.executescript(SCHEMA_5)


# Liest markierte E-Mails aus Apple Mail. Bereits übernommene Message-IDs stehen in der Datei argv[1].
JXA = r"""
ObjC.import('Foundation');
function run(argv) {
  const known = new Set(JSON.parse($.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null).js));
  const flag = parseInt(argv[1], 10), limit = parseInt(argv[2], 10);
  const Mail = Application('Mail');
  const out = [], seen = new Set();
  let more = false;
  const boxes = [];
  Mail.accounts().forEach(acc => { try { acc.mailboxes().forEach(b => boxes.push(b)); } catch (e) {} });
  try { Mail.mailboxes().forEach(b => boxes.push(b)); } catch (e) {}
  for (const box of boxes) {
    let msgs = [];
    try { msgs = box.messages.whose({_and: [{flaggedStatus: true}, {flagIndex: flag}]})(); } catch (e) { continue; }
    for (const m of msgs) {
      let id = '';
      try { id = String(m.messageId() || '').replace(/^<|>$/g, ''); } catch (e) { id = ''; }
      if (!id) { try { id = 'mail-intern-' + m.id(); } catch (e) { continue; } }
      if (known.has(id) || seen.has(id)) continue;
      if (out.length >= limit) { more = true; break; }
      seen.add(id);
      out.push({id: id, mailbox: box.name(), source: m.source()});
    }
    if (more) break;
  }
  return JSON.stringify({messages: out, more: more});
}
"""


def _text_aus_html(markup):
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def mail_lesen(raw):
    """Zerlegt eine E-Mail: Kopfangaben, Text und Anlagen."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    absender = msg.get("From", "")
    try:
        adresse = msg["From"].addresses[0]
        name, mailadresse = adresse.display_name or adresse.addr_spec, adresse.addr_spec
    except (AttributeError, IndexError, TypeError):
        name, mailadresse = absender, ""
    datum = None
    try:
        datum = parsedate_to_datetime(msg.get("Date")).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    text = ""
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is not None:
        try:
            text = body.get_content()
        except (LookupError, ValueError):
            text = body.get_payload(decode=True).decode("utf-8", "replace")
        if body.get_content_type() == "text/html":
            text = _text_aus_html(text)
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\r", "")).strip()
    anlagen = []
    for teil in msg.iter_attachments():
        dateiname = teil.get_filename() or "Anlage"
        try:
            inhalt = teil.get_payload(decode=True) or b""
        except Exception:  # beschädigte Anlage: Mail trotzdem übernehmen
            inhalt = b""
        anlagen.append((dateiname, inhalt))
    return {"betreff": str(msg.get("Subject", "") or "").strip() or "(ohne Betreff)", "name": str(name).strip(),
            "adresse": mailadresse, "datum": datum, "an": str(msg.get("To", "") or ""), "text": text, "anlagen": anlagen,
            "message_id": str(msg.get("Message-ID", "") or "").strip()}


class MailImport:
    def __init__(self, store, runner=None):
        self.store = store
        self.runner = runner or self._osascript

    def markierung(self):
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='mail_markierung'").fetchone()
            return int(row[0]) if row else 6

    def markierung_setzen(self, index):
        if index not in FARBEN:
            raise ValueError("Bitte eine der sieben Markierungsfarben wählen.")
        with closing(self.store.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('mail_markierung',?)", (str(index),))

    def status(self):
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT count(DISTINCT dokument_id), max(importiert_am) FROM mail_import").fetchone()
            abruf = db.execute("SELECT wert FROM einstellung WHERE schluessel='mail_letzter_abruf'").fetchone()
        return {"markierung": self.markierung(), "farben": FARBEN, "uebernommen": row[0], "zuletzt": row[1],
                "letzter_abruf": json.loads(abruf[0]) if abruf else None, "verfuegbar": Path("/usr/bin/osascript").exists()}

    def _abruf_merken(self, neu, bekannt):
        wert = json.dumps({"zeit": datetime.now().isoformat(timespec="seconds"), "neu": neu, "bereits_vorhanden": bekannt})
        with closing(self.store.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('mail_letzter_abruf',?)", (wert,))

    def _osascript(self, known, flag, limit):
        if not Path("/usr/bin/osascript").exists():
            raise ValueError("Die Übernahme aus Apple Mail ist nur auf dem Mac verfügbar.")
        with tempfile.TemporaryDirectory() as tmp:
            ids = Path(tmp) / "bekannt.json"
            script = Path(tmp) / "mail.js"
            ids.write_text(json.dumps(sorted(known)), encoding="utf-8")
            script.write_text(JXA, encoding="utf-8")
            run = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", str(script), str(ids), str(flag), str(limit)],
                                 capture_output=True, timeout=300)
        if run.returncode != 0:
            fehler = run.stderr.decode("utf-8", "replace")
            if "-1743" in fehler or "not allowed" in fehler.lower() or "nicht erlaubt" in fehler.lower():
                raise ValueError("macOS erlaubt den Zugriff auf Mail noch nicht. Bitte unter Systemeinstellungen → "
                                 "Datenschutz & Sicherheit → Automation erlauben, dass Terminal bzw. Python Mail steuert.")
            raise ValueError("Mail konnte nicht gelesen werden: " + fehler.strip()[-300:])
        return json.loads(run.stdout.decode("utf-8"))

    def abholen(self):
        """Holt neue markierte E-Mails. Gibt Zähler zurück."""
        with closing(self.store.connect()) as db:
            known = {r[0] for r in db.execute("SELECT message_id FROM mail_import")}
        ergebnis = self.runner(known, self.markierung(), MAX_JE_ABRUF)
        neu, bekannt, fehler = 0, 0, []
        for m in ergebnis.get("messages", []):
            try:
                if self.uebernehmen(m["source"].encode("utf-8", "surrogateescape") if isinstance(m["source"], str)
                                    else m["source"], m["id"], m.get("mailbox")):
                    neu += 1
                else:
                    bekannt += 1
            except (ValueError, OSError) as error:
                fehler.append(str(error))
        self._abruf_merken(neu, bekannt)
        return {"neu": neu, "weitere": bool(ergebnis.get("more")), "fehler": fehler, "bereits_vorhanden": bekannt}

    def uebernehmen(self, raw, message_id=None, postfach=None):
        """Legt eine E-Mail mit ihren Anlagen im Posteingang ab. False, wenn sie schon übernommen ist."""
        if len(raw) > MAX_MAIL:
            raise ValueError("Die E-Mail ist größer als 40 MB.")
        daten = mail_lesen(raw)
        digest = hashlib.sha256(raw).hexdigest()
        message_id = (message_id or daten["message_id"] or digest).strip("<>")
        with closing(self.store.connect()) as db, db:
            if db.execute("SELECT 1 FROM mail_import WHERE message_id=?", (message_id,)).fetchone():
                return False
            # Dieselbe E-Mail unter anderer Kennung (z. B. in zwei Postfächern): Kennung merken, nicht erneut übernehmen
            gleich = db.execute("SELECT id FROM dokument WHERE sha256=? AND mime='message/rfc822'", (digest,)).fetchone()
            if gleich:
                db.execute("INSERT INTO mail_import(message_id,dokument_id,betreff,absender,postfach) VALUES(?,?,?,?,?)",
                           (message_id, gleich[0], daten["betreff"], daten["adresse"] or daten["name"], postfach))
                return False
        anlagen, uebersprungen = [], []
        for dateiname, inhalt in daten["anlagen"]:
            try:
                doc_id, _ = self.store.import_document(None, Path(dateiname).name or "Anlage", inhalt)
                anlagen.append((doc_id, dateiname))
            except ValueError:
                uebersprungen.append(dateiname)
        kopf = [f"Von: {daten['name']}" + (f" <{daten['adresse']}>" if daten["adresse"] and daten["adresse"] != daten["name"] else ""),
                f"An: {daten['an']}", f"Datum: {daten['datum'].split('-')[2]}.{daten['datum'].split('-')[1]}.{daten['datum'].split('-')[0]}"
                if daten["datum"] else "Datum: unbekannt", f"Betreff: {daten['betreff']}"]
        if anlagen:
            kopf.append("Anlagen: " + ", ".join(n for _, n in anlagen))
        if uebersprungen:
            kopf.append("Nicht übernommene Anlagen (Format nicht unterstützt): " + ", ".join(uebersprungen))
        seite = "\n".join(kopf) + "\n\n" + daten["text"]
        pfad = self.store.uploads / (digest + ".eml")
        if not pfad.is_file():
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.store.uploads, delete=False) as stage:
                stage.write(raw)
            os.replace(stage.name, pfad)
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", daten["betreff"])[:120] + ".eml"
        with closing(self.store.connect()) as db, db:
            eingang = db.execute("SELECT id FROM vorgang WHERE system='posteingang'").fetchone()[0]
            doc_id = db.execute("""INSERT INTO dokument(vorgang_id,dateiname,titel,titel_seite,titel_quelle,mime,dateipfad,
                sha256,ocr_status,dokument_datum) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (eingang, name, daten["betreff"][:160], 1, "Betreff der E-Mail", "message/rfc822", pfad.name, digest,
                 "E-Mail-Text übernommen", daten["datum"])).lastrowid
            db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)",
                       (doc_id, 1, "mail", seite))
            db.execute("INSERT INTO mail_import(message_id,dokument_id,betreff,absender,postfach) VALUES(?,?,?,?,?)",
                       (message_id, doc_id, daten["betreff"], daten["adresse"] or daten["name"], postfach))
            db.executemany("INSERT OR IGNORE INTO mail_anlage(message_id,dokument_id) VALUES(?,?)",
                           ((message_id, a) for a, _ in anlagen))
        return True


def test_mail(store):
    """Übernahme einer E-Mail mit Anlage, Vorschläge aus dem Mailkopf, Doppelungsschutz, Anlagen beim Zuordnen."""
    from email.message import EmailMessage
    from akte import Akte
    store = type(store)(store.data / "Mailtest", store.ocr)
    akte = Akte(store, today=lambda: "2026-11-23")
    vorgang = store.create_case("Unitask – Rechnungsklärung", "Versicherungen", "")
    msg = EmailMessage()
    msg["From"] = "Unitask Buchhaltung <buchhaltung@unitask.example>"
    msg["To"] = "a.mustermann@mail.example"
    msg["Subject"] = "Korrigierte Rechnung R-2026-11873"
    msg["Date"] = "Sun, 22 Nov 2026 09:12:00 +0100"
    msg["Message-ID"] = "<abc123@unitask.example>"
    msg.set_content("Guten Tag,\nanbei die korrigierte Rechnung zur Kundennummer UT-30418.\nFreundliche Grüße")
    msg.add_attachment(b"%PDF-1.4\nRechnung", maintype="application", subtype="pdf", filename="Rechnung.pdf")
    msg.add_attachment(b"PK\x03\x04", maintype="application", subtype="zip", filename="Archiv.zip")
    raw = bytes(msg)
    abgeholt = []
    mi = MailImport(store, runner=lambda known, flag, limit: (abgeholt.append((set(known), flag)),
                                                             {"messages": [] if "abc123@unitask.example" in known else
                                                              [{"id": "abc123@unitask.example", "mailbox": "INBOX",
                                                                "source": raw.decode("utf-8")}], "more": False})[1])
    assert mi.abholen() == {"neu": 1, "weitere": False, "fehler": [], "bereits_vorhanden": 0}
    assert mi.status()["letzter_abruf"]["neu"] == 1
    assert mi.abholen() == {"neu": 0, "weitere": False, "fehler": [], "bereits_vorhanden": 0}
    abruf = mi.status()["letzter_abruf"]
    assert abruf["neu"] == 0 and len(abruf["zeit"]) == 19, abruf
    # Dieselbe E-Mail unter anderer Kennung (zweites Postfach) wird nicht doppelt übernommen
    assert mi.uebernehmen(raw, "andere-kennung", "Archiv") is False
    zweit = MailImport(store, runner=lambda known, flag, limit: {"messages": [
        {"id": "abc123@unitask.example", "mailbox": "INBOX", "source": raw.decode("utf-8")},
        {"id": "dritte-kennung", "mailbox": "Gesendet", "source": raw.decode("utf-8")}], "more": False})
    assert zweit.abholen() == {"neu": 0, "weitere": False, "fehler": [], "bereits_vorhanden": 2}
    assert abgeholt[0][1] == 6 and "abc123@unitask.example" in abgeholt[1][0]
    eingang = akte.posteingang()
    mail = [d for d in eingang if d["mime"] == "message/rfc822"][0]
    assert mail["titel"] == "Korrigierte Rechnung R-2026-11873" and mail["ocr_status"] == "E-Mail-Text übernommen"
    assert mail["vorschlag"]["datum"] == "2026-11-22", mail["vorschlag"]
    assert mail["vorschlag"]["absender"]["name"] == "Unitask Buchhaltung", mail["vorschlag"]
    assert "Archiv.zip" in mail["seiten"][0]["text"]
    pdf = [d for d in eingang if d["mime"] == "application/pdf"][0]
    akte.zuordnen(mail["id"], {"vorgang_id": vorgang})
    a = akte.akte(vorgang)
    assert {d["id"] for d in a["dokumente"]} == {mail["id"], pdf["id"]}  # Anlage wandert mit
    anlage = [e for e in a["eintraege"] if e["dokument_id"] == pdf["id"]][0]
    assert anlage["bezug_id"] == [e for e in a["eintraege"] if e["dokument_id"] == mail["id"]][0]["id"]
    assert akte.posteingang() == []
    mi.markierung_setzen(2)
    assert mi.markierung() == 2 and mi.status()["uebernommen"] == 1

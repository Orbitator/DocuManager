"""Aktenexport, Briefansicht und Datensicherung.

Ohne zusätzliche Pakete: ein kleiner PDF-Schreiber für die Chronik (Helvetica, WinAnsi), ZIP aus der
Standardbibliothek, die Datenbank über die Sicherungsschnittstelle von SQLite.
"""
import hashlib
import html
import io
import json
import re
import shutil
import sqlite3
import tempfile
import textwrap
import time
import zipfile
from contextlib import closing
from pathlib import Path

ART = {"eingang": "Eingang", "ausgang": "Versendet", "entwurf": "Entwurf", "nachweis": "Versandnachweis",
       "telefonat": "Telefonat", "notiz": "Notiz", "entscheidung": "Entscheidung", "chat": "Chat-Notiz",
       "fehlt": "Original fehlt"}
FRIST = {"frist": "Verbindliche Frist", "wiedervorlage": "Wiedervorlage", "aufgabe": "Aufgabe"}


def datum(iso):
    return ".".join(reversed(iso[:10].split("-"))) if iso else "–"


# --- Minimaler PDF-Schreiber ---------------------------------------------------------------
def _pdf_text(s):
    raw = s.encode("cp1252", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf_aus_absaetzen(absaetze, titel="Dokument"):
    """absaetze: Liste von (Text, Schriftgröße, fett, Einzug). Gibt die PDF-Datei als Bytes zurück."""
    seiten, zeilen, y = [], [], 800
    for text, groesse, fett, einzug in absaetze:
        if text is None:  # Leerraum
            y -= groesse
            continue
        breite = int((495 - einzug) / (groesse * 0.5))
        for teil in (textwrap.wrap(text, breite, break_long_words=True, replace_whitespace=False) or [""]):
            for zeile in teil.split("\n"):
                if y < 55:
                    seiten.append(zeilen)
                    zeilen, y = [], 800
                zeilen.append((zeile, groesse, fett, 50 + einzug, y))
                y -= groesse * 1.35
    seiten.append(zeilen)
    objekte = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kinder = []
    for nr, zeilen in enumerate(seiten, 1):
        strom = b"".join(b"BT /%s %.1f Tf 1 0 0 1 %d %d Tm (%s) Tj ET\n" % (b"F2" if f else b"F1", g, x, y, _pdf_text(t))
                         for t, g, f, x, y in zeilen)
        strom += b"BT /F1 8 Tf 1 0 0 1 50 30 Tm (%s) Tj ET\n" % _pdf_text(f"{titel} · Seite {nr} von {len(seiten)}")
        objekte.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(strom), strom))
        inhalt = len(objekte)
        objekte.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R "
                       b"/F2 4 0 R >> >> /Contents %d 0 R >>" % inhalt)
        kinder.append(len(objekte))
    objekte[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kinder), len(kinder))
    ausgabe, lage = io.BytesIO(), []
    ausgabe.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    for i, obj in enumerate(objekte, 1):
        lage.append(ausgabe.tell())
        ausgabe.write(b"%d 0 obj\n%s\nendobj\n" % (i, obj))
    xref = ausgabe.tell()
    ausgabe.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1))
    for pos in lage:
        ausgabe.write(b"%010d 00000 n \n" % pos)
    ausgabe.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objekte) + 1, xref))
    return ausgabe.getvalue()


def chronik_pdf(a, kontakte):
    name = lambda k: next((x.get("kurzname") or x["name"] for x in kontakte if x["id"] == k), "")
    teil = {t["id"]: t["name"] for t in a["teilvorgaenge"]}
    s = [(a["titel"], 16, True, 0), (f"Bereich: {a['bereich']} · Status: {a['status']} · Stand {time.strftime('%d.%m.%Y')}",
                                     9, False, 0), (None, 8, False, 0)]
    if a["teilvorgaenge"]:
        s.append(("Teilvorgänge", 11, True, 0))
        s += [(f"{t['name']}: {t['status']}" + (f" · zuständig {t['zustaendig']}" if t["zustaendig"] else "")
               + (f" · nächster Schritt: {t['naechster_schritt']}" if t["naechster_schritt"] else ""), 9.5, False, 0)
              for t in a["teilvorgaenge"]]
        s.append((None, 6, False, 0))
    if a["referenzen"]:
        s.append(("Referenzen", 11, True, 0))
        s += [(f"{r['bezeichnung']}: {r['wert']}", 9.5, False, 0) for r in a["referenzen"]]
        s.append((None, 6, False, 0))
    if a["beteiligte"]:
        s.append(("Beteiligte", 11, True, 0))
        s += [(f"{b['name']}" + (f" – {b['rolle']}" if b["rolle"] else ""), 9.5, False, 0) for b in a["beteiligte"]]
        s.append((None, 6, False, 0))
    if a["fristen"]:
        s.append(("Fristen", 11, True, 0))
        for f in sorted(a["fristen"], key=lambda f: f["faellig_am"]):
            zeile = f"{datum(f['faellig_am'])} · {FRIST[f['art']]} · {f['titel']}" + (" (erledigt)" if f["erledigt_am"] else "")
            if f["verlauf"]:
                zeile += f" · ursprünglich {datum(f['verlauf'][0]['faellig_alt'])}"
            if f["quelle_zitat"]:
                zeile += f" · Quelle: „{f['quelle_zitat']}“"
            s.append((zeile, 9.5, False, 0))
        s.append((None, 6, False, 0))
    s.append(("Chronik", 11, True, 0))
    for e in sorted(a["eintraege"], key=lambda e: (e["ereignis_datum"], e["id"])):
        kopf = f"{datum(e['ereignis_datum'])}  {ART.get(e['art'], e['art'])}"
        if e["teile"] and len(a["teilvorgaenge"]) > 1:
            kopf += " · " + ", ".join(teil.get(t, "") for t in e["teile"])
        s.append((kopf, 9.5, True, 0))
        s.append((e["titel"] + (f" – {e['richtung'] or ''} {name(e['kontakt_id'])}" if e["kontakt_id"] else ""), 9.5, False, 14))
        if e["versand"]:
            v = e["versand"]
            s.append((f"Versand: {v['art']}{' ' + v['sendungsnummer'] if v['sendungsnummer'] else ''} am {datum(v['datum'])} an "
                      + v["empfaenger"].replace("\n", ", "), 9, False, 14))
        if e["text"]:
            s.append((e["text"][:3000], 9, False, 14))
        if e["quelle"]:
            s.append(("Quelle: " + e["quelle"], 8.5, False, 14))
        s.append((None, 4, False, 0))
    return pdf_aus_absaetzen(s, f"Chronik {a['titel']}")


def sicherer_name(text):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", text).strip()[:90] or "Dokument"


def akte_zip(store, akte, a, dokument_ids):
    """ZIP mit Chronik.pdf, akte.json und den ausgewählten Originalen."""
    kontakte = akte.kontakte()
    puffer = io.BytesIO()
    wurzel = sicherer_name(f"{a['titel']} {time.strftime('%Y-%m-%d')}")
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{wurzel}/Chronik.pdf", chronik_pdf(a, kontakte))
        z.writestr(f"{wurzel}/akte.json", json.dumps(a, ensure_ascii=False, indent=1, default=str))
        namen = set()
        for d in a["dokumente"]:
            if dokument_ids is not None and d["id"] not in dokument_ids:
                continue
            row = store.document(d["id"])
            datei = store.uploads / row["dateipfad"]
            if not datei.is_file():
                continue
            name = sicherer_name(f"{(row['dokument_datum'] or row['angelegt_am'])[:10]} {row['titel']}") + Path(row["dateipfad"]).suffix
            while name in namen:
                name = name.replace(".", "_.", 1)
            namen.add(name)
            z.write(datei, f"{wurzel}/Dokumente/{name}")
    return f"{wurzel}.zip", puffer.getvalue()


# --- Briefansicht nach DIN 5008 ------------------------------------------------------------
# Maße in mm ab oberer linker Blattkante (DIN 5008, Form B; passt in Fensterumschläge DIN lang und C5/C4,
# deren Fenster das Blatt von 45 bis 90 mm abdeckt).
BRIEF_MASSE = {"rand_links": 25, "rand_rechts": 20, "ruecksende": 49, "empfaenger": 55, "empfaenger_bis": 90,
               "info": 55, "betreff": 100, "falz1": 105, "loch": 148.5, "falz2": 210}


def brief_html(e, eigene, drucken=False):
    b = e.get("brief") or {}
    m = BRIEF_MASSE
    absender = [z.strip() for z in (eigene or "").splitlines() if z.strip()]
    esc = lambda s: html.escape(s or "")
    teile = [t.strip() for t in re.split(r"\n\s*\n", e.get("text") or "") if t.strip()]
    # Raum für die Unterschrift zwischen Grußformel und Name
    unterschrift = len(teile) >= 2 and re.search(r"(Grüßen?|Gruß|Hochachtungsvoll)\W*$", teile[-2]) and len(teile[-1]) < 80
    klasse = lambda i: ' class="name"' if unterschrift and i == len(teile) - 1 else ""
    absaetze = "".join(f"<p{klasse(i)}>{esc(t).replace(chr(10), '<br>')}</p>" for i, t in enumerate(teile))
    info = [("Ihr Zeichen", b.get("zeichen")), ("Ihr Schreiben vom", b.get("bezug_datum")), ("Datum", b.get("datum"))]
    anlagen = b.get("anlagen") or []
    empfaenger = "\n".join(z.strip() for z in (b.get("empfaenger") or "").splitlines() if z.strip())
    kopf = (f"<b>{esc(absender[0])}</b><br>" + "<br>".join(esc(z) for z in absender[1:])) if absender else ""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{esc(b.get('betreff') or e.get('titel'))}</title>
<style>
/* Jede Seite hat oben 15 mm Rand (auch Seite 2 ff.); die Angaben der ersten Seite werden im Druck um diesen Rand
   nach oben versetzt, damit die Anschrift trotzdem bei 55 mm im Sichtfenster steht. */
@page{{size:A4;margin:15mm 0 18mm 0}}
:root{{--oben:0mm}}
@media print{{:root{{--oben:15mm}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:#eceef3;font-family:Arial,"Helvetica Neue",Helvetica,sans-serif;color:#000;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}}
.blatt{{width:210mm;min-height:297mm;margin:12px auto;background:#fff;position:relative;
  padding:calc({m['betreff']}mm - var(--oben)) {m['rand_rechts']}mm 20mm {m['rand_links']}mm;font-size:10.5pt;line-height:1.35;box-shadow:0 2px 12px rgba(0,0,0,.15)}}
.kopf{{position:absolute;top:calc(15mm - var(--oben));right:{m['rand_rechts']}mm;text-align:right;font-size:9pt;line-height:1.4}}
.kopf b{{font-size:10.5pt}}
.ruecksende{{position:absolute;top:calc({m['ruecksende']}mm - var(--oben));left:{m['rand_links']}mm;width:85mm;font-size:7pt;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-bottom:.25pt solid #000;padding-bottom:.5mm}}
.anschrift{{position:absolute;top:calc({m['empfaenger']}mm - var(--oben));left:{m['rand_links']}mm;width:85mm;
  max-height:{m['empfaenger_bis'] - m['empfaenger']}mm;overflow:hidden;white-space:pre-line;line-height:1.25}}
.info{{position:absolute;top:calc({m['info']}mm - var(--oben));left:125mm;width:{210 - 125 - m['rand_rechts']}mm;font-size:9pt;line-height:1.5;
  display:grid;grid-template-columns:auto 1fr;gap:0 4mm}}
.info span:nth-child(odd){{color:#444}}
.marke{{position:absolute;left:4mm;width:5mm;border-top:.25pt solid #888}}
.marke.loch{{width:7mm}}
.betreff{{font-weight:700;margin:0 0 8.5mm}}
.inhalt p{{margin:0 0 4.5mm;orphans:3;widows:3}}
.inhalt p.name{{margin-top:14mm}}
.anlagen{{margin-top:8mm}}
.leiste{{position:sticky;top:0;z-index:2;background:#1f2a5a;color:#fff;padding:8px 16px;font-size:13px;display:flex;gap:12px;align-items:center}}
.leiste button{{font:inherit;padding:4px 10px;border-radius:6px;border:0;cursor:pointer}}
@media print{{body{{background:#fff}}.leiste{{display:none}}.blatt{{margin:0;box-shadow:none;min-height:0;zoom:1!important}}}}
</style></head><body>
<div class="leiste">{'Versendet' if e.get('art') == 'ausgang' else 'Entwurf'} · {esc(e.get('titel'))}<span style="flex:1"></span>
<span style="opacity:.8">DIN 5008 · Anschrift im Sichtfenster</span><button onclick="print()">Drucken oder als PDF sichern</button></div>
<div class="blatt">
<div class="kopf">{kopf}</div>
<div class="ruecksende">{esc(' · '.join(absender))}</div>
<div class="anschrift">{esc(empfaenger)}</div>
<div class="info">{''.join(f'<span>{k}</span><span>{esc(v)}</span>' for k, v in info if v)}</div>
<div class="marke" style="top:calc({m['falz1']}mm - var(--oben))"></div><div class="marke loch" style="top:calc({m['loch']}mm - var(--oben))"></div><div class="marke" style="top:calc({m['falz2']}mm - var(--oben))"></div>
<div class="inhalt"><p class="betreff">{esc(b.get('betreff') or e.get('titel'))}</p>{absaetze}
{('<p class="anlagen"><b>Anlagen</b><br>' + '<br>'.join(esc(a) for a in anlagen) + '</p>') if anlagen else ''}</div>
</div>
<script>/* Bildschirm: Blatt an die Fensterbreite anpassen; der Druck bleibt in Originalgröße */
function passen(){{var b=document.querySelector('.blatt');b.style.zoom='';var f=Math.min(1,(innerWidth-24)/b.offsetWidth);b.style.zoom=f<1?f:'';}}
addEventListener('resize',passen);passen();addEventListener('beforeprint',function(){{document.querySelector('.blatt').style.zoom='';}});addEventListener('afterprint',passen);</script>
{'<script>addEventListener("load",()=>setTimeout(print,400))</script>' if drucken else ''}</body></html>"""


# --- Datensicherung ------------------------------------------------------------------------
TABELLEN_ZAEHLEN = ("vorgang", "dokument", "eintrag", "frist", "kontakt", "teilvorgang", "chat_notiz")


def _zaehlen(db):
    werte = {}
    for t in TABELLEN_ZAEHLEN:
        try:
            werte[t] = db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            werte[t] = 0
    return werte


def sicherung_erstellen(store, ziel=None):
    """Vollständige Sicherung: Datenbank, Originale, Chat-Anlagen und eine Prüfliste mit Prüfsummen.
    Ohne `ziel` gibt es immer nur eine Sicherungsdatei: Nach erfolgreicher Prüfung der neuen werden ältere entfernt."""
    ordner = store.data / "Sicherungen"
    ordner.mkdir(parents=True, exist_ok=True)
    if ziel is None:
        ziel = ordner / f"Korrespondenz-Sicherung_{time.strftime('%Y-%m-%d_%H%M%S')}.zip"
        _sicherung_schreiben(store, ziel)
        if sicherung_pruefen(ziel)["ok"]:
            for alt in ordner.glob("Korrespondenz-Sicherung_*.zip"):
                if alt != ziel:
                    alt.unlink(missing_ok=True)
        return ziel
    return _sicherung_schreiben(store, ziel)


def _sicherung_schreiben(store, ziel):
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "Rechtsberatung.sqlite3"
        with closing(store.connect()) as quelle, closing(sqlite3.connect(kopie)) as db:
            quelle.backup(db)
            zahlen = _zaehlen(db)
            version = db.execute("PRAGMA user_version").fetchone()[0]
        dateien = {}
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(kopie, "Rechtsberatung.sqlite3")
            for unterordner in ("Uploads", "Chat_Originale"):
                for datei in sorted((store.data / unterordner).glob("*")) if (store.data / unterordner).is_dir() else []:
                    if datei.is_file():
                        name = f"{unterordner}/{datei.name}"
                        z.write(datei, name)
                        dateien[name] = hashlib.sha256(datei.read_bytes()).hexdigest()
            z.writestr("sicherung.json", json.dumps({"format": "korrespondenz-sicherung", "erstellt": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                     "schemaversion": version, "anzahl": zahlen, "dateien": dateien},
                                                    ensure_ascii=False, indent=1))
    return ziel


def sicherung_pruefen(pfad):
    """Prüft eine Sicherung, ohne etwas zu verändern: Vollständigkeit, Prüfsummen, Datenbank, Originale."""
    fehler = []
    with zipfile.ZipFile(pfad) as z:
        namen = set(z.namelist())
        if "sicherung.json" not in namen or "Rechtsberatung.sqlite3" not in namen:
            return {"ok": False, "fehler": ["Das ist keine vollständige Sicherung dieser Anwendung."]}
        info = json.loads(z.read("sicherung.json"))
        for name, summe in info["dateien"].items():
            if name not in namen:
                fehler.append(f"Fehlt: {name}")
            elif hashlib.sha256(z.read(name)).hexdigest() != summe:
                fehler.append(f"Beschädigt: {name}")
        with tempfile.TemporaryDirectory() as tmp:
            db_pfad = Path(tmp) / "pruefung.sqlite3"
            db_pfad.write_bytes(z.read("Rechtsberatung.sqlite3"))
            with closing(sqlite3.connect(db_pfad)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    fehler.append("Die Datenbank in der Sicherung ist beschädigt.")
                zahlen = _zaehlen(db)
                for (pfad_datei,) in db.execute("SELECT DISTINCT dateipfad FROM dokument WHERE geloescht_am IS NULL"):
                    if f"Uploads/{pfad_datei}" not in namen:
                        fehler.append(f"Original fehlt in der Sicherung: {pfad_datei}")
    if zahlen != info["anzahl"]:
        fehler.append("Die Anzahl der Datensätze stimmt nicht mit der Prüfliste überein.")
    return {"ok": not fehler, "fehler": fehler[:20], "erstellt": info["erstellt"], "anzahl": zahlen,
            "dateien": len(info["dateien"]), "schemaversion": info["schemaversion"]}


def wiederherstellen(pfad, daten, ueberschreiben=False):
    """Stellt eine geprüfte Sicherung in einen Datenordner wieder her (bei beendeter Anwendung)."""
    pruefung = sicherung_pruefen(pfad)
    if not pruefung["ok"]:
        raise ValueError("Die Sicherung ist nicht in Ordnung: " + "; ".join(pruefung["fehler"]))
    daten = Path(daten)
    if (daten / "Rechtsberatung.sqlite3").exists() and not ueberschreiben:
        raise ValueError("Im Zielordner liegt bereits eine Datenbank. Zum Ersetzen --ueberschreiben angeben.")
    daten.mkdir(parents=True, exist_ok=True)
    if (daten / "Rechtsberatung.sqlite3").exists():
        shutil.copy2(daten / "Rechtsberatung.sqlite3", daten / f"Rechtsberatung.vor-wiederherstellung-{time.strftime('%Y%m%d%H%M%S')}.sqlite3")
    with zipfile.ZipFile(pfad) as z:
        for name in z.namelist():
            if name == "sicherung.json" or name.endswith("/") or ".." in Path(name).parts or Path(name).is_absolute():
                continue
            ziel = daten / name
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(z.read(name))
    return pruefung


def wiederherstellen_laufend(store, pfad):
    """Stellt eine geprüfte Sicherung bei laufender Anwendung wieder her. Die Datenbank wird über die
    SQLite-Sicherungsschnittstelle ersetzt (sicher bei offenen Verbindungen); Originale und Chat-Anlagen werden
    ergänzt. Die bisherige Datenbank bleibt als Kopie in `Sicherungen/` erhalten."""
    pruefung = sicherung_pruefen(pfad)
    if not pruefung["ok"]:
        raise ValueError("Die Sicherung ist nicht in Ordnung: " + "; ".join(pruefung["fehler"]))
    ordner = store.data / "Sicherungen"
    ordner.mkdir(parents=True, exist_ok=True)
    with closing(store.connect()) as quelle, closing(sqlite3.connect(
            ordner / f"Rechtsberatung.vor-wiederherstellung-{time.strftime('%Y%m%d%H%M%S')}.sqlite3")) as kopie:
        quelle.backup(kopie)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(pfad) as z:
        for name in z.namelist():
            if name.endswith("/") or ".." in Path(name).parts or Path(name).is_absolute():
                continue
            if name.startswith(("Uploads/", "Chat_Originale/")):
                ziel = store.data / name
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_bytes(z.read(name))
        db_datei = Path(tmp) / "Rechtsberatung.sqlite3"
        db_datei.write_bytes(z.read("Rechtsberatung.sqlite3"))
        with closing(sqlite3.connect(db_datei)) as quelle, closing(store.connect()) as ziel:
            quelle.backup(ziel)
    store.migrate()
    return pruefung


def test_export(store):
    """Export, Briefansicht, Sicherung und geprüfte Wiederherstellung auf einer frischen Installation."""
    from akte import Akte
    store = type(store)(store.data / "Exporttest", store.ocr)
    akte = Akte(store, today=lambda: "2026-11-23")
    v = store.create_case("Kia-Schadenabwicklung", "Versicherungen", "")
    k = akte.kontakt_anlegen({"name": "Allsicher Versicherung AG", "abteilungen": [{"anschrift": "Allsicher\nRheinuferstraße 12\n50668 Köln"}]})
    doc, _ = store.import_document(v, "Gutachten.pdf", b"%PDF-1.4\nGutachten")
    akte.eintrag_anlegen(v, {"art": "eingang", "titel": "Gutachten", "datum": "2026-11-10", "dokument_id": doc, "kontakt_id": k})
    entwurf = akte.eintrag_anlegen(v, {"art": "entwurf", "titel": "Stellungnahme", "text": "Sehr geehrte Damen und Herren,\n\nich widerspreche (Teil 1).",
                                       "kontakt_id": k, "brief": {"empfaenger": "Allsicher\nRheinuferstraße 12\n50668 Köln",
                                                                  "betreff": "Stellungnahme – Ihr Zeichen KFZ-2026-1842",
                                                                  "zeichen": "KFZ-2026-1842", "datum": "23.11.2026",
                                                                  "anlagen": ["Gutachten"]}})
    akte.frist_anlegen(v, {"art": "frist", "titel": "Stellungnahme", "faellig_am": "2026-12-16", "quelle_zitat": "bis zum 16.12.2026"})
    a = akte.akte(v)
    e = [x for x in a["eintraege"] if x["id"] == entwurf][0]
    assert e["brief"]["betreff"].startswith("Stellungnahme")
    seite = brief_html(e, "A. Mustermann\nLindenweg 4\n50733 Köln")
    assert "top:calc(55mm - var(--oben))" in seite and "@page{size:A4;margin:15mm 0 18mm 0}" in seite  # Sichtfenster, Rand ab Seite 2
    gruss = brief_html({"titel": "T", "text": "Sehr geehrte Damen und Herren,\n\nText.\n\nMit freundlichen Grüßen\n\nA. Mustermann",
                        "brief": {"empfaenger": "X"}}, "A. Mustermann")
    assert '<p class="name">A. Mustermann</p>' in gruss
    assert "Lindenweg 4" in seite and "KFZ-2026-1842" in seite and "(Teil 1)" in seite and "print,400" not in seite
    pdf = chronik_pdf(a, akte.kontakte())
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF") and b"Chronik" in pdf
    assert "Stellungnahme".encode("cp1252") in pdf and b"\\(Teil 1\\)" in pdf
    name, inhalt = akte_zip(store, akte, a, None)
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        dateien = z.namelist()
    assert name.startswith("Kia-Schadenabwicklung") and any(d.endswith("/Chronik.pdf") for d in dateien)
    assert any(d.endswith("/akte.json") for d in dateien) and any("/Dokumente/" in d for d in dateien)
    _, ohne = akte_zip(store, akte, a, set())
    with zipfile.ZipFile(io.BytesIO(ohne)) as z:
        assert not any("/Dokumente/" in d for d in z.namelist())
    # Sicherung, Prüfung, Wiederherstellung auf frischer Installation
    sicherung = sicherung_erstellen(store)
    p = sicherung_pruefen(sicherung)
    assert p["ok"] and p["anzahl"]["vorgang"] >= 2 and p["dateien"] == 1, p
    neu = store.data / "Frisch"
    wiederherstellen(sicherung, neu)
    frisch = type(store)(neu, None)
    assert [c["titel"] for c in frisch.list_cases()] == [c["titel"] for c in store.list_cases()]
    a2 = Akte(frisch).akte(v)
    assert [x["titel"] for x in a2["eintraege"]] == [x["titel"] for x in a["eintraege"]] and len(a2["fristen"]) == 1
    assert (frisch.uploads / store.document(doc)["dateipfad"]).read_bytes() == b"%PDF-1.4\nGutachten"
    try:
        wiederherstellen(sicherung, neu)
    except ValueError:
        pass
    else:
        raise AssertionError("Bestehende Daten wurden ohne Rückfrage überschrieben.")
    # Immer nur eine Sicherungsdatei
    time.sleep(1.1)
    zweite = sicherung_erstellen(store)
    assert sorted(p.name for p in (store.data / "Sicherungen").glob("Korrespondenz-Sicherung_*.zip")) == [zweite.name]
    sicherung = zweite
    # Wiederherstellen bei laufender Anwendung: Änderungen nach der Sicherung verschwinden, Daten der Sicherung sind da
    spaeter = store.create_case("Nach der Sicherung", "Versicherungen", "")
    wiederherstellen_laufend(store, sicherung)
    assert spaeter not in [c["id"] for c in store.list_cases()] and v in [c["id"] for c in store.list_cases()]
    assert list((store.data / "Sicherungen").glob("Rechtsberatung.vor-wiederherstellung-*.sqlite3"))
    # Beschädigte Sicherung wird erkannt
    kaputt = store.data / "kaputt.zip"
    with zipfile.ZipFile(sicherung) as z, zipfile.ZipFile(kaputt, "w") as k2:
        for n in z.namelist():
            k2.writestr(n, b"veraendert" if n.startswith("Uploads/") else z.read(n))
    assert not sicherung_pruefen(kaputt)["ok"]

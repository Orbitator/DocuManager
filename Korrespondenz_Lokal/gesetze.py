"""Gesetzestexte für zitierte Vorschriften: erkennen, amtlichen Wortlaut abrufen, lokal ablegen.

Quelle ist gesetze-im-internet.de (Bundesministerium der Justiz, frei abrufbar). Abgerufen wird nur, was in einer
Bewertung oder Antwort zitiert ist, und jede Vorschrift wird in Daten/Gesetze gespeichert und erst nach 30 Tagen
neu geladen. Landesrecht und Rechtsprechung sind dort nicht enthalten.
"""
import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

QUELLE = "https://www.gesetze-im-internet.de"
GUELTIG_TAGE = 30

# Abkürzung → Pfad auf gesetze-im-internet.de (der Pfad weicht oft von der Abkürzung ab)
GESETZE = {
    "BGB": "bgb", "EGBGB": "bgbeg", "ZPO": "zpo", "EGZPO": "zpoeg", "GG": "gg", "GVG": "gvg", "FamFG": "famfg",
    "ZVG": "zvg", "InsO": "inso", "GKG": "gkg_2004", "RVG": "rvg", "JVEG": "jveg", "VwVfG": "vwvfg", "VwGO": "vwgo",
    "VwZG": "vwzg_2005", "AO": "ao_1977", "FGO": "fgo", "EStG": "estg", "UStG": "ustg_1980", "ErbStG": "erbstg_1974",
    "GrStG": "grstg_1973", "KraftStG": "kraftstg", "VVG": "vvg_2008", "PflVG": "pflvg", "HGB": "hgb", "GmbHG": "gmbhg",
    "UWG": "uwg_2004", "PAngV": "pangv_2022", "StGB": "stgb", "StPO": "stpo", "OWiG": "owig_1968", "StVG": "stvg",
    "StVO": "stvo_2013", "BetrKV": "betrkv", "HeizkostenV": "heizkostenv", "WEG": "woeigg", "BauGB": "bbaug",
    "BDSG": "bdsg_2018", "TKG": "tkg_2021", "TDDDG": "ttdsg", "EnWG": "enwg_2005", "KSchG": "kschg",
    "ArbGG": "arbgg", "TzBfG": "tzbfg", "BUrlG": "burlg", "MiLoG": "milog", "EntgFG": "entgfg", "GewO": "gewo",
    "BEEG": "beeg", "BKGG": "bkgg_1996", "WoGG": "wogg", "IfSG": "ifsg", "SGG": "sgg",
    "SGB I": "sgb_1", "SGB II": "sgb_2", "SGB III": "sgb_3", "SGB IV": "sgb_4", "SGB V": "sgb_5", "SGB VI": "sgb_6",
    "SGB VII": "sgb_7", "SGB VIII": "sgb_8", "SGB IX": "sgb_9_2018", "SGB X": "sgb_10", "SGB XI": "sgb_11",
    "SGB XII": "sgb_12",
}
# Gesetze, die nach Artikeln gegliedert sind
ARTIKEL = {"GG", "EGBGB", "EGZPO"}

_ABK = sorted(GESETZE, key=len, reverse=True)
ZITAT = re.compile(
    r"(?P<art>§§?|Art\.|Artikel)\s*"
    r"(?P<nummern>\d+[a-z]?(?:\s*(?:Abs\.|Absatz|S\.|Satz|Nr\.|Ziff\.|lit\.)\s*\d+[a-z]?)*"
    r"(?:\s*(?:,|und|bis|–|-|/)\s*\d+[a-z]?(?:\s*(?:Abs\.|Absatz|S\.|Satz|Nr\.|Ziff\.|lit\.)\s*\d+[a-z]?)*)*)"
    r"\s*(?:ff?\.\s*)?"
    r"(?P<gesetz>" + "|".join(re.escape(a) for a in _ABK) + r")(?![A-Za-zÄÖÜäöü])")
_EINZEL = re.compile(r"(\d+[a-z]?)((?:\s*(?:Abs\.|Absatz)\s*(\d+[a-z]?))?)")


def zitate_finden(text):
    """Liefert die zitierten Vorschriften in der Reihenfolge des Vorkommens, ohne Doppelungen.
    [{zitat, gesetz, norm ('§ 362' / 'Art. 3'), absatz, pfad}]"""
    gefunden, gesehen = [], set()
    for m in ZITAT.finditer(text or ""):
        gesetz = m["gesetz"]
        artikel = m["art"].startswith("Art") or gesetz in ARTIKEL
        # Hauptnummern: vor „,“/„und“ getrennte Zahlen; Zahlen hinter Abs./Satz/Nr. sind Unterteilungen
        teile = re.split(r"\s*(?:,|und|bis|–|-|/)\s*", m["nummern"])
        for teil in teile:
            e = _EINZEL.match(teil.strip())
            if not e:
                continue
            nummer, absatz = e.group(1), e.group(3)
            norm = f"Art. {nummer}" if artikel else f"§ {nummer}"
            schluessel = (gesetz, norm)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            gefunden.append({"zitat": m.group(0).strip(), "gesetz": gesetz, "norm": norm, "absatz": absatz,
                             "pfad": f"{GESETZE[gesetz]}/{'art_' if artikel else '__'}{nummer}.html"})
    return gefunden


def seite_lesen(roh, content_type=""):
    """Wortlaut aus einer Seite von gesetze-im-internet.de: {titel, absaetze}. None, wenn nichts erkennbar ist."""
    zeichensatz = re.search(r"charset=([\w-]+)", content_type or "") or re.search(rb'charset="?([\w-]+)', roh[:2000])
    zeichensatz = (zeichensatz.group(1).decode() if isinstance(zeichensatz.group(1), bytes) else zeichensatz.group(1)) \
        if zeichensatz else "iso-8859-1"
    try:
        seite = roh.decode(zeichensatz, errors="replace")
    except LookupError:
        seite = roh.decode("iso-8859-1", errors="replace")
    klar = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
    bez = re.search(r'class="jnenbez"[^>]*>(.*?)</span>', seite, re.S)
    tit = re.search(r'class="jnentitel"[^>]*>(.*?)</span>', seite, re.S)
    absaetze = [klar(a) for a in re.findall(r'<div class="jurAbsatz"[^>]*>(.*?)</div>', seite, re.S)]
    absaetze = [a for a in absaetze if a]
    if not absaetze:
        block = re.search(r'<div class="jnhtml"[^>]*>(.*?)</div>\s*</div>\s*</div>', seite, re.S)
        if block and klar(block.group(1)):
            absaetze = [klar(block.group(1))]
    if not absaetze:
        return None
    return {"titel": " ".join(x for x in (klar(bez.group(1)) if bez else "", klar(tit.group(1)) if tit else "") if x),
            "absaetze": absaetze}


class Gesetze:
    def __init__(self, ordner, holen=None):
        self.ordner = Path(ordner)
        self.holen = holen or self._http  # im Selbsttest ersetzt

    def _http(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "DocuManager (lokal)"})
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read(), res.headers.get("Content-Type", "")

    def vorschrift(self, z):
        """Wortlaut einer gefundenen Vorschrift, aus der Ablage oder frisch abgerufen."""
        datei = self.ordner / (z["pfad"].replace("/", "__").replace(".html", ".json"))
        url = f"{QUELLE}/{z['pfad']}"
        ergebnis = {"gesetz": z["gesetz"], "norm": z["norm"], "absatz": z.get("absatz"), "url": url}
        try:
            gespeichert = json.loads(datei.read_text(encoding="utf-8"))
            if time.time() - gespeichert.get("abgerufen", 0) < GUELTIG_TAGE * 86400:
                return {**ergebnis, **gespeichert}
        except (OSError, ValueError):
            gespeichert = None
        try:
            roh, art = self.holen(url)
            gelesen = seite_lesen(roh, art)
            if not gelesen:
                raise ValueError("Wortlaut nicht erkennbar")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as fehler:
            if gespeichert:  # lieber den älteren Stand als nichts
                return {**ergebnis, **gespeichert, "veraltet": True}
            nicht_da = isinstance(fehler, urllib.error.HTTPError) and fehler.code == 404
            return {**ergebnis, "fehler": "Diese Vorschrift wurde auf gesetze-im-internet.de nicht gefunden." if nicht_da
                    else "Gesetzestext gerade nicht abrufbar (Internetverbindung?)."}
        gelesen["abgerufen"] = time.time()
        self.ordner.mkdir(parents=True, exist_ok=True)
        datei.write_text(json.dumps(gelesen, ensure_ascii=False), encoding="utf-8")
        return {**ergebnis, **gelesen}

    def fuer_text(self, text, hoechstens=20):
        return [self.vorschrift(z) for z in zitate_finden(text)[:hoechstens]]


def test_gesetze(ordner):
    z = zitate_finden("Erfüllt nach § 362 Abs. 1 BGB; vgl. §§ 366, 367 Abs. 2 BGB, Art. 3 GG, § 286 ff. BGB, "
                      "§ 44 SGB X und § 91 ZPO. Kein Zitat: § 5 der Satzung, 3 BGB-Gesellschaften.")
    normen = [(x["gesetz"], x["norm"], x["absatz"]) for x in z]
    assert normen == [("BGB", "§ 362", "1"), ("BGB", "§ 366", None), ("BGB", "§ 367", "2"), ("GG", "Art. 3", None),
                      ("BGB", "§ 286", None), ("SGB X", "§ 44", None), ("ZPO", "§ 91", None)], normen
    assert z[0]["pfad"] == "bgb/__362.html" and z[3]["pfad"] == "gg/art_3.html" and z[5]["pfad"] == "sgb_10/__44.html"
    # Nachgebaute Seite im Aufbau von gesetze-im-internet.de (ISO-8859-1)
    seite = ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"></head><body>'
             '<div class="jnheader"><h1><span class="jnenbez">&#167; 362</span>&#160;<span class="jnentitel">'
             'Erl&ouml;schen durch Leistung</span></h1></div><div class="jnhtml"><div><div class="jurAbsatz">(1) Das '
             'Schuldverhältnis erlischt, wenn die geschuldete Leistung an den Gläubiger bewirkt wird.</div>'
             '<div class="jurAbsatz">(2) Wird an einen Dritten ...</div></div></div></body></html>').encode("iso-8859-1")
    abrufe = []

    def holen(url):
        abrufe.append(url)
        if "__362" in url:
            return seite, "text/html; charset=iso-8859-1"
        raise urllib.error.HTTPError(url, 404, "nicht gefunden", None, None)

    g = Gesetze(Path(ordner) / "Gesetzetest", holen)
    v = g.vorschrift(z[0])
    assert v["titel"] == "§ 362 Erlöschen durch Leistung" and v["absaetze"][0].startswith("(1) Das Schuldverhältnis erlischt")
    assert v["url"] == "https://www.gesetze-im-internet.de/bgb/__362.html"
    assert g.vorschrift(z[0])["titel"] and len(abrufe) == 1, "zweiter Abruf muss aus der Ablage kommen"
    assert "nicht gefunden" in g.vorschrift(z[1])["fehler"]

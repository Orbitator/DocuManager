"""Zusammenarbeit mit ChatGPT ohne Schnittstelle: Akte als ZIP hinaus, Antwort per Einfügen zurück.

Das Paket enthält einen Auftrag (wie ChatGPT vorgehen und in welchem Format es Briefe liefern soll), die ganze Akte
als Text (dieselbe Aufbereitung wie für Claude: Stand, Volltexte mit Faktenregister, Chronik mit eigenen Schreiben)
und die Originaldateien. Die Antwort aus ChatGPT wird wieder eingefügt: Briefe werden an den Markierungen BETREFF /
BRIEFTEXT / HINWEISE erkannt und in den Briefdialog übernommen, Analysen im Verlauf gespeichert.
"""
import io
import re
import time
import zipfile
from pathlib import Path

from export import sicherer_name

AUFTRAEGE = {
    "bewerten": "Analysiere das gewählte Schreiben (bzw. den Vorgang) und bewerte es rechtlich vor dem Hintergrund der "
                "ganzen Akte: Worum geht es, ist die Forderung dem Grunde und der Höhe nach berechtigt (Normen nennen), "
                "stimmen Daten, Beträge und Aktenzeichen, welche Fristen laufen, welche Risiken bestehen, was fehlt? "
                "Schlage dann 2 bis 4 Handlungsoptionen mit Vor- und Nachteilen vor und empfiehl eine. Noch keinen Brief.",
    "antwort": "Entwirf ein Antwortschreiben auf das gewählte Schreiben. Beziehe dich auf frühere Schreiben mit Datum, "
               "bleibe bei dem, was ich bereits geschrieben habe, und greife offene Punkte auf.",
    "schreiben": "Entwirf ein neues Schreiben in diesem Vorgang, passend zum Stand der Akte.",
    "frage": "Beantworte meine Frage unten auf Grundlage der Akte.",
}

FORMAT = """## Format für Briefe (wichtig – DocuManager liest den Brief daran wieder ein)

Wann immer du einen Brief formulierst, gib ihn genau so aus, ohne Markdown-Formatierung im Brieftext:

=== BETREFF ===
(eine Zeile, ohne das Wort „Betreff“)
=== BRIEFTEXT ===
(ab der Anrede bis einschließlich Grußformel und meinem Namen; Absätze durch eine Leerzeile getrennt;
ohne Absender, Anschrift, Datum und Betreff – die setzt mein Briefbogen nach DIN 5008)
=== HINWEISE ===
(kurz: was ich vor dem Versand prüfen oder ergänzen sollte; worauf du dich stützt)
=== ENDE ===
"""


def auftrag(titel, stand, aufgabe, vorgabe="", bewertung=""):
    """Der Text, den ich in ChatGPT einfüge (steht auch als erste Datei im ZIP)."""
    teile = [
        f"# Auftrag: {titel}",
        "Du unterstützt mich (Privatperson bzw. Kleinunternehmer in Deutschland) bei Korrespondenz mit Behörden, "
        "Gerichten, Versicherungen, Vermietern und Firmen. Antworte auf Deutsch, sachlich und genau. Briefe nach "
        "DIN 5008, höflich und bestimmt, ohne Floskeln. Nenne Fundstellen (Dokumentnummer D…, Datum) und kennzeichne "
        "Annahmen. Fristen immer mit Datum. Bei Rechtsfragen: Einschätzung geben, Grenzen benennen.",
        "## Unterlagen",
        "Im ZIP liegen **Akte.md** (Stand des Vorgangs, Volltexte aller Dokumente mit Nummern D…, ein Faktenregister "
        "mit Beträgen, Daten und Aktenzeichen sowie die Chronik mit meinen eigenen Schreiben, Notizen und Einschätzungen "
        "Dritter in zeitlicher Reihenfolge) und der Ordner **Dokumente** mit den Originalen. Lies zuerst Akte.md "
        "vollständig; nutze die Originale zur Kontrolle, etwa wenn ein erkannter Text unklar ist. Meine eigenen "
        "Schreiben sind verbindlich: Was ich dort erklärt, zugesagt oder bestritten habe, gilt fort.",
        "## Stand",
        stand,
        "## Erste Aufgabe",
        AUFTRAEGE.get(aufgabe, AUFTRAEGE["frage"]),
    ]
    if vorgabe.strip():
        teile.append(f"Meine Vorgaben: {vorgabe.strip()}")
    if bewertung.strip():
        teile += ["## Bisherige Bewertung (zuvor erarbeitet)", bewertung.strip()]
    teile.append(FORMAT)
    return "\n\n".join(teile)


def paket(ki, vorgang_id, dokument_id=None, aufgabe="bewerten", vorgabe="", bewertung=""):
    """ZIP für ChatGPT: Auftrag, Akte.md, Originale. Liefert (Dateiname, Inhalt, Auftragstext)."""
    a, stand, unterlagen, chronik, _ = ki.kontext(vorgang_id, dokument_id)
    text = auftrag(a["titel"], stand, aufgabe, vorgabe, bewertung)
    akte = (f"# Akte: {a['titel']}\n\n## Stand\n\n{stand}\n\n## Unterlagen (Volltexte)\n\n{unterlagen or '(keine)'}"
            f"\n\n## Chronik (älteste zuerst)\n\n{chronik or '(leer)'}\n")
    wurzel = sicherer_name(f"ChatGPT {a['titel']} {time.strftime('%Y-%m-%d')}")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{wurzel}/00 Auftrag – zuerst lesen.md", text)
        z.writestr(f"{wurzel}/Akte.md", akte)
        namen = set()
        for d in sorted(a["dokumente"], key=lambda x: x["id"]):
            row = ki.store.document(d["id"])
            datei = ki.store.uploads / row["dateipfad"]
            if not datei.is_file():
                continue
            name = sicherer_name(f"D{d['id']} {(row['dokument_datum'] or row['angelegt_am'])[:10]} {row['titel']}")[:120] \
                + Path(row["dateipfad"]).suffix
            while name in namen:
                name = name.replace(".", "_.", 1)
            namen.add(name)
            z.write(datei, f"{wurzel}/Dokumente/{name}")
    return f"{wurzel}.zip", puffer.getvalue(), text


_KOPF = re.compile(r"^[\s#>*_=\-]*(BETREFF|BRIEFTEXT|BRIEF|HINWEISE|ENDE)[\s*_=:\-]*(.*)$", re.I)


def auswerten(text):
    """Erkennt einen Brief in der eingefügten Antwort. {betreff, brieftext, hinweise} oder None."""
    teile, aktuell = {}, None
    for zeile in (text or "").replace("\r\n", "\n").split("\n"):
        m = _KOPF.match(zeile)
        kopf_allein = m and not m.group(2).strip(" =*_")
        betreff_zeile = m and m.group(1).upper() == "BETREFF" and "BRIEFTEXT" not in teile \
            and zeile.lstrip(" #>*_=").upper().startswith("BETREFF")
        if kopf_allein or betreff_zeile:
            aktuell = {"BRIEF": "BRIEFTEXT"}.get(m.group(1).upper(), m.group(1).upper())
            if aktuell == "ENDE":
                aktuell = None
                continue
            rest = m.group(2).strip(" =*_")
            teile[aktuell] = [rest] if rest else []
            continue
        if aktuell:
            teile[aktuell].append(zeile)
    if "BRIEFTEXT" not in teile:
        return None
    from claude_ki import brieftext_saeubern
    zusammen = lambda k: brieftext_saeubern("\n".join(teile.get(k, [])))
    brief = {"betreff": zusammen("BETREFF").replace("\n", " ").removeprefix("Betreff:").strip(),
             "brieftext": zusammen("BRIEFTEXT"), "hinweise": zusammen("HINWEISE")}
    return brief if brief["brieftext"] else None


def test_chatgpt(ki, vorgang_id, dokument_id):
    name, inhalt, text = paket(ki, vorgang_id, dokument_id, "antwort", "Zahlung ablehnen", "Option: Widersprechen")
    z = zipfile.ZipFile(io.BytesIO(inhalt))
    dateien = z.namelist()
    assert name.endswith(".zip") and any(n.endswith("00 Auftrag – zuerst lesen.md") for n in dateien)
    assert any("/Dokumente/D" in n for n in dateien) and any(n.endswith("Akte.md") for n in dateien)
    akte = z.read(next(n for n in dateien if n.endswith("Akte.md"))).decode()
    assert "FAKTENREGISTER" in akte and "Chronik" in akte and "=== BRIEFTEXT ===" in text and "Zahlung ablehnen" in text
    assert "Bisherige Bewertung" in text and f"GEWÄHLTES SCHREIBEN: D{dokument_id}" in text
    antwort = ("Hier ist der Entwurf:\n\n**=== BETREFF ===**\nWiderspruch gegen Ihre Forderung\n=== BRIEFTEXT ===\n"
               "Sehr geehrte Damen und Herren,\n\n**ich widerspreche.**\n\n\n\nMit freundlichen Grüßen\n\nA. Mustermann\n"
               "=== HINWEISE ===\nAktenzeichen prüfen.\n=== ENDE ===\nViel Erfolg!")
    b = auswerten(antwort)
    assert b == {"betreff": "Widerspruch gegen Ihre Forderung",
                 "brieftext": "Sehr geehrte Damen und Herren,\n\nich widerspreche.\n\nMit freundlichen Grüßen\n\nA. Mustermann",
                 "hinweise": "Aktenzeichen prüfen."}, b
    assert auswerten("### BETREFF: Kündigung\n### BRIEFTEXT\nSehr geehrte …\n")["betreff"] == "Kündigung"
    assert auswerten("Nur eine Analyse ohne Brief.") is None

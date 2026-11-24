"""Analyse und Textvorschläge mit Claude (Anthropic) für Dokumente und Vorgänge.

Aufruf der Claude-Schnittstelle per HTTP mit der Standardbibliothek (das Projekt nutzt keine Fremdpakete).
Der Zugangsschlüssel liegt in Daten/claude_schluessel (nur für den Benutzer lesbar) und bewusst nicht in der
Datenbank, damit er nicht in Datensicherungen landet. Übertragen wird nur, was der Anwender anfragt: der Text des
gewählten Dokuments und eine knappe Übersicht des Vorgangs.
"""
import json
import os
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

API = "https://api.anthropic.com/v1/messages"
MODELL = "claude-opus-5-5"  # gründlichste Stufe
# Stufen: Modell, Preise in $ je Million Token (Eingabe, Ausgabe, Cache lesen, Cache schreiben 5 Min.)
STUFEN = {
    "sparsam": {"modell": "claude-haiku-5-5", "name": "Sparsam", "preise": (0.10, 0.50, 0.01, 0.125)},
    "ausgewogen": {"modell": "claude-sonnet-5-5", "name": "Ausgewogen", "preise": (2.0, 10.0, 0.10, 2.50)},
    "gruendlich": {"modell": MODELL, "name": "Gründlich", "preise": (4.0, 20.0, 0.20, 5.0)},
}
STANDARD_STUFE = "gruendlich"
# Denktiefe je Aufgabe: einfache Aufgaben knapp, Bewertung gründlich (Denken kostet Ausgabe-Token)
AUFWAND = {"zusammenfassen": "low", "fristen": "low", "frage": "medium", "pruefen": "medium", "bewerten": "medium",
           "antwort": "medium", "schreiben": "medium", "ueberarbeiten": "medium"}
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # bei Ablehnung durch Sicherheitsfilter automatisch Ersatzmodell
MAX_KONTEXT = 600_000  # Zeichen Aktentext je Anfrage (rund 150 000 Token); darüber wird gekürzt
KURZFASSUNG = 3000  # so viel bleibt von einem älteren fremden Dokument, wenn gekürzt werden muss

SYSTEM = """Du unterstützt eine Privatperson bzw. einen Kleinunternehmer in Deutschland bei der Bearbeitung von
Korrespondenz (Behörden, Gerichte, Versicherungen, Vermieter, Firmen). Antworte auf Deutsch, sachlich und knapp.
Grundlage ist die mitgelieferte, vollständige Akte des Vorgangs in zeitlicher Reihenfolge – eingegangene Schreiben,
meine eigenen versendeten Schreiben und Entwürfe, Notizen und Telefonate. Lies sie ganz, bevor du antwortest, und
beziehe den bisherigen Verlauf immer ein. Eigene Schreiben sind verbindlich: Was ich dort erklärt, zugesagt oder
bestritten habe, gilt fort, außer ich sage etwas anderes. Nenne Fundstellen (Eintrag, Datum) und kennzeichne Annahmen.
Fristen immer mit Datum nennen. Bei rechtlichen Fragen: Einschätzung geben, aber auf Grenzen hinweisen, wo eine
Fachberatung sinnvoll ist. Briefe schreibst du nach DIN 5008, höflich und bestimmt, ohne Floskeln."""

AUFGABEN = {
    "zusammenfassen": "Fasse das Schreiben zusammen: Wer schreibt, worum geht es, was wird verlangt, bis wann? "
                      "Danach in einer Liste die wichtigsten Punkte und Beträge.",
    "pruefen": "Prüfe das Schreiben kritisch: Ist die Forderung bzw. das Anliegen nachvollziehbar und berechtigt? "
               "Gibt es Widersprüche zu den übrigen Unterlagen des Vorgangs, fehlende Angaben oder Fehler? "
               "Welche Möglichkeiten habe ich, und was empfiehlst du?",
    "fristen": "Welche Fristen, Termine und Handlungspflichten ergeben sich aus dem Schreiben? Liste sie mit Datum, "
               "Fundstelle und was jeweils zu tun ist.",
    "antwort": "Entwirf ein Antwortschreiben auf das gewählte Schreiben. Berücksichtige den gesamten bisherigen "
               "Schriftverkehr der Akte: Beziehe dich auf frühere Schreiben mit Datum, bleibe bei dem, was ich bereits "
               "geschrieben habe (keine Widersprüche, keine Wiederholung bereits beantworteter Punkte), und greife "
               "offene Punkte aus früheren Schreiben auf. Nenne in den Hinweisen, auf welche früheren Schreiben du dich stützt.",
}

AUFGABEN["schreiben"] = ("Entwirf ein neues Schreiben in diesem Vorgang an den unten genannten Empfänger, passend zum "
                         "Stand der Akte. Berücksichtige den gesamten bisherigen Schriftverkehr, beziehe dich auf frühere "
                         "Schreiben mit Datum und bleibe bei dem, was ich bereits geschrieben habe.")
AUFGABEN["ueberarbeiten"] = ("Überarbeite meinen Briefentwurf: sprachlich klar, höflich und bestimmt, sachlich richtig im "
                             "Abgleich mit der Akte (Daten, Beträge, Aktenzeichen, frühere Schreiben). Behalte meine Aussagen "
                             "und Absicht bei, ergänze Fehlendes und fülle Platzhalter, wo die Akte die Angabe enthält. In den "
                             "Hinweisen nenne kurz, was du geändert hast.")
BRIEF_AUFGABEN = ("antwort", "schreiben", "ueberarbeiten")
AUFGABEN["bewerten"] = (
    "Analysiere das gewählte Schreiben und bewerte es rechtlich vor dem Hintergrund der ganzen Akte, bevor ich antworte. "
    "Prüfe nach deutschem Recht (Normen nennen, wo einschlägig, z. B. BGB, ZPO, VwVfG, AO, VVG): Ist die Forderung bzw. "
    "das Anliegen dem Grunde und der Höhe nach berechtigt? Stimmen Daten, Beträge und Aktenzeichen mit der Akte überein? "
    "Fristen (mit Datum und Folge bei Versäumnis), Form- und Zustellungsfragen, Verjährung, Beweislage, Widersprüche zu "
    "früheren Schreiben. Schlage dann 2 bis 4 sinnvolle Handlungsoptionen vor (z. B. zahlen, widersprechen, Nachweise "
    "anfordern, Ratenzahlung oder Fristverlängerung erbitten, Fachanwalt einschalten) mit Vor- und Nachteilen und "
    "markiere genau eine als empfohlen. Nenne, welche Angaben oder Unterlagen fehlen. Bleibe sachlich und ehrlich, auch "
    "wenn die Gegenseite im Recht ist; die Einschätzung ersetzt keine anwaltliche Beratung.")
_TEXT = {"type": "string"}
BEWERTUNG_SCHEMA = {
    "type": "object",
    "properties": {
        "zusammenfassung": {"type": "string", "description": "Worum es geht, in 2 bis 4 Sätzen"},
        "rechtliche_bewertung": {"type": "string", "description": "Rechtliche Einschätzung mit Begründung und Normen; Absätze durch Leerzeilen"},
        "fristen": {"type": "array", "items": {"type": "object", "properties": {"datum": _TEXT, "was": _TEXT},
                                               "required": ["datum", "was"], "additionalProperties": False}},
        "risiken": {"type": "string", "description": "Was droht, wenn nichts oder das Falsche getan wird"},
        "fehlende_angaben": {"type": "string", "description": "Welche Angaben oder Unterlagen fehlen; leer, wenn nichts fehlt"},
        "optionen": {"type": "array", "items": {"type": "object", "properties": {
            "titel": _TEXT, "beschreibung": _TEXT, "vorteile": _TEXT, "nachteile": _TEXT, "empfohlen": {"type": "boolean"}},
            "required": ["titel", "beschreibung", "vorteile", "nachteile", "empfohlen"], "additionalProperties": False}},
    },
    "required": ["zusammenfassung", "rechtliche_bewertung", "fristen", "risiken", "fehlende_angaben", "optionen"],
    "additionalProperties": False,
}


def bewertung_als_text(b):
    """Lesbare Fassung einer Bewertung (für den Gesprächsverlauf, die Notiz und den Antwortentwurf)."""
    teile = [f"ZUSAMMENFASSUNG\n{b.get('zusammenfassung', '')}", f"RECHTLICHE BEWERTUNG\n{b.get('rechtliche_bewertung', '')}"]
    if b.get("fristen"):
        teile.append("FRISTEN\n" + "\n".join(f"– {f.get('datum', '')}: {f.get('was', '')}" for f in b["fristen"]))
    if b.get("risiken"):
        teile.append(f"RISIKEN\n{b['risiken']}")
    if b.get("fehlende_angaben"):
        teile.append(f"FEHLENDE ANGABEN\n{b['fehlende_angaben']}")
    for i, o in enumerate(b.get("optionen") or [], 1):
        teile.append(f"OPTION {i}{' (empfohlen)' if o.get('empfohlen') else ''}: {o.get('titel', '')}\n{o.get('beschreibung', '')}"
                     f"\nVorteile: {o.get('vorteile', '')}\nNachteile: {o.get('nachteile', '')}")
    return brieftext_saeubern("\n\n".join(teile))

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "betreff": {"type": "string", "description": "Betreffzeile ohne das Wort „Betreff“"},
        "brieftext": {"type": "string", "description": "Druckfertiger Brieftext nach DIN 5008: beginnt mit der Anrede, "
                      "endet mit Grußformel und meinem Namen aus MEINE ANGABEN. Ohne Absender, Anschrift, Datum und "
                      "Betreff (die setzt der Briefbogen). Absätze durch eine Leerzeile getrennt, kein Markdown, keine "
                      "Sternchen oder Rauten; Aufzählungen mit „–“. Platzhalter in eckigen Klammern nur für wirklich "
                      "unbekannte Angaben."},
        "hinweise": {"type": "string", "description": "Kurze Hinweise an den Absender (was zu prüfen/ergänzen ist)"},
    },
    "required": ["betreff", "brieftext", "hinweise"],
    "additionalProperties": False,
}


def brieftext_saeubern(text):
    """Entfernt Markdown-Reste und überzählige Leerzeilen, damit der Text druckfertig im Briefbogen steht."""
    import re
    text = text.replace("\r\n", "\n").replace("**", "").replace("__", "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^[ \t]*[*•][ \t]+", "– ", text, flags=re.M)
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


PRUEF_SCHEMA = {
    "type": "object",
    "properties": {"pruefungen": {"type": "array", "items": {"type": "object", "properties": {
        "vorschrift": {"type": "string", "description": "z. B. „§ 362 BGB“"},
        "ergebnis": {"type": "string", "enum": ["passt", "teilweise", "passt nicht", "unklar"]},
        "begruendung": {"type": "string", "description": "Ein bis zwei Sätze: was die Vorschrift regelt und ob die Aussage davon gedeckt ist"}},
        "required": ["vorschrift", "ergebnis", "begruendung"], "additionalProperties": False}}},
    "required": ["pruefungen"], "additionalProperties": False,
}


class ClaudeKI:
    def __init__(self, store, akte, senden=None):
        self.store = store
        self.akte = akte
        self.senden = senden or self._http  # im Selbsttest ersetzt

    # --- Zugangsschlüssel ----------------------------------------------------------------
    @property
    def _datei(self):
        return self.store.data / "claude_schluessel"

    def schluessel(self):
        try:
            return self._datei.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def schluessel_setzen(self, wert):
        wert = (wert or "").strip()
        if not wert:
            self._datei.unlink(missing_ok=True)
            return self.status()
        if not wert.startswith("sk-ant-") or len(wert) > 300 or any(c.isspace() for c in wert):
            raise ValueError("Das sieht nicht wie ein Claude-Zugangsschlüssel aus (beginnt mit „sk-ant-“).")
        self._datei.write_text(wert, encoding="utf-8")
        os.chmod(self._datei, 0o600)
        return self.status()

    def stufe(self):
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT wert FROM einstellung WHERE schluessel='claude_stufe'").fetchone()
        return row[0] if row and row[0] in STUFEN else STANDARD_STUFE

    def stufe_setzen(self, stufe):
        if stufe not in STUFEN:
            raise ValueError("Unbekannte Stufe.")
        with closing(self.store.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO einstellung(schluessel,wert) VALUES('claude_stufe',?)", (stufe,))
        return self.status()

    def status(self):
        s = self.schluessel()
        return {"eingerichtet": bool(s), "endung": s[-4:] if s else None, "stufe": self.stufe(),
                "stufen": {k: v["name"] for k, v in STUFEN.items()}}

    # --- Kontext aus dem Vorgang --------------------------------------------------------
    def kontext(self, vorgang_id, dokument_id=None):
        """Die ganze Akte in zeitlicher Reihenfolge: jeder Chronik-Eintrag mit seinem Text (eigene Briefe, Notizen,
        Telefonate, Chat-Notizen) und dem Volltext des zugehörigen Dokuments, dazu Dokumente ohne Eintrag.
        Gekürzt wird nur, wenn die Akte die Obergrenze übersteigt – dann zuerst ältere fremde Dokumente; das gewählte
        Dokument und alle eigenen Schreiben bleiben vollständig. Was gekürzt wurde, steht in `info`."""
        a = self.akte.akte(vorgang_id)
        zeilen = [f"VORGANG: {a['titel']} (Bereich: {', '.join(a.get('bereiche') or [a['bereich']])}; Status: {a['status']})"]
        if a.get("teilvorgaenge"):
            zeilen.append("TEILVORGÄNGE: " + "; ".join(f"{t['name']} ({t['status']})" for t in a["teilvorgaenge"]))
        if a["beteiligte"]:
            zeilen.append("BETEILIGTE: " + "; ".join(b["name"] for b in a["beteiligte"]))
        if a["referenzen"]:
            zeilen.append("REFERENZEN: " + "; ".join(f"{r['bezeichnung']} {r['wert']}" for r in a["referenzen"]))
        offen = [f for f in a["fristen"] if not f["erledigt_am"]]
        if offen:
            zeilen.append("OFFENE FRISTEN: " + "; ".join(f"{f['faellig_am']} {f['titel']}" for f in offen))
        eigene = self.akte.eigene_angaben()
        if eigene:
            zeilen.append("MEINE ANGABEN (Absender): " + eigene.replace("\n", ", "))
        uebersicht = "\n".join(zeilen)

        dok_text = {}
        for d in a["dokumente"]:
            dok_text[d["id"]] = "\n".join(s["text"] for s in self.store.pages(d["id"])).strip()
        namen = {k["kontakt_id"]: k["name"] for k in a["beteiligte"]}
        # Bausteine: [sortierschlüssel, kopf, text, kürzbar]
        teile, verwendet = [], set()
        for e in sorted(a["eintraege"], key=lambda x: (x["ereignis_datum"], x["id"])):
            if e["art"] == "entwurf" and e.get("versendet_als"):
                continue  # steht als „Versendet“ in der Chronik
            art = {"eingang": "EINGANG", "ausgang": "MEIN SCHREIBEN (versendet)", "entwurf": "MEIN ENTWURF (nicht versendet)",
                   "telefonat": "TELEFONAT", "notiz": "NOTIZ", "entscheidung": "ENTSCHEIDUNG", "chat": "CHAT-NOTIZ",
                   "nachweis": "NACHWEIS", "fehlt": "ORIGINAL FEHLT"}.get(e["art"], e["art"].upper())
            kopf = f"{e['ereignis_datum']} · {art}{' · ' + e['typ'] if e.get('typ') else ''} · {e['titel']}"
            if e.get("kontakt_id"):
                kopf += f" · {e.get('richtung') or ''} {namen.get(e['kontakt_id']) or self._kontakt(e['kontakt_id'])}".rstrip()
            v = e.get("versand")
            if v:
                kopf += f" · Versand per {v['art']} am {v['datum']} an {v['empfaenger'].replace(chr(10), ', ')}"
            text = (e.get("text") or "").strip()
            b = e.get("brief") or {}
            if b and text:
                text = f"Betreff: {b.get('betreff') or e['titel']}\n{text}"
            stuecke = [text] if text else []
            d = e.get("dokument_id")
            fremd = bool(d and dok_text.get(d) and d not in verwendet)
            if fremd:
                verwendet.add(d)
                if dok_text[d] != text:
                    stuecke.append(dok_text[d])
            fokus = d == dokument_id and dokument_id is not None
            kuerzbar = fremd and not fokus and e["art"] not in ("ausgang", "entwurf")
            teile.append([kopf + (" · [GEWÄHLTES SCHREIBEN]" if fokus else ""), "\n\n".join(stuecke), kuerzbar, d])
        for d in a["dokumente"]:
            if d["id"] not in verwendet and dok_text.get(d["id"]):
                fokus = d["id"] == dokument_id
                teile.append([f"{d.get('datum') or ''} · DOKUMENT ohne Chronik-Eintrag · {d['titel']}"
                              + (" · [GEWÄHLTES SCHREIBEN]" if fokus else ""), dok_text[d["id"]], not fokus, d["id"]])
        # Obergrenze: ältere kürzbare Dokumente zuerst auf einen Anfang kürzen
        gekuerzt = []
        ueber = sum(len(t[1]) for t in teile) - MAX_KONTEXT
        for t in teile:
            if ueber <= 0:
                break
            if t[2] and len(t[1]) > KURZFASSUNG:
                ueber -= len(t[1]) - KURZFASSUNG
                t[1] = t[1][:KURZFASSUNG] + "\n[… Rest dieses Dokuments aus Platzgründen weggelassen]"
                gekuerzt.append(t[0].split(" · ")[-1] if "GEWÄHLT" not in t[0] else t[0])
        akte = "\n\n".join(f"<eintrag nr=\"{i}\">\n{t[0]}\n{t[1] or '(kein Text)'}\n</eintrag>" for i, t in enumerate(teile, 1))
        info = {"eintraege": len(teile), "dokumente": sum(1 for t in teile if t[3] and dok_text.get(t[3])),
                "eigene_schreiben": sum(1 for t in teile if t[0].split(" · ")[1].startswith("MEIN")),
                "ohne_text": sum(1 for d in a["dokumente"] if not dok_text.get(d["id"])),
                "gekuerzt": gekuerzt, "zeichen": len(akte)}
        return a, uebersicht, akte, info

    def _kontakt(self, kontakt_id):
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT name FROM kontakt WHERE id=?", (kontakt_id,)).fetchone()
        return row[0] if row else ""

    # --- Anfrage ------------------------------------------------------------------------
    def fragen(self, vorgang_id, dokument_id, verlauf, aufgabe="frage", anweisung="", entwurf="", empfaenger="",
               bewertung="", option=""):
        """verlauf: Liste von {rolle: "user"|"assistant", text}. Die letzte Nachricht ist die neue Frage
        (bei aufgabe != "frage" wird sie aus AUFGABEN ergänzt)."""
        schluessel = self.schluessel()
        if not schluessel:
            raise ValueError("Claude ist noch nicht eingerichtet: Zugangsschlüssel unter Einstellungen → Claude eintragen.")
        if aufgabe not in ("frage", *AUFGABEN):
            raise ValueError("Unbekannte Aufgabe.")
        if not isinstance(verlauf, list) or len(verlauf) > 40:
            raise ValueError("Verlauf: ungültige Angabe.")
        a, uebersicht, akte, info = self.kontext(vorgang_id, dokument_id)
        nachrichten = []
        for n in verlauf:
            if not isinstance(n, dict) or n.get("rolle") not in ("user", "assistant") or not str(n.get("text", "")).strip():
                raise ValueError("Verlauf: ungültige Nachricht.")
            nachrichten.append({"role": n["rolle"], "content": str(n["text"])[:20000]})
        if aufgabe != "frage":
            auftrag = AUFGABEN[aufgabe]
            if aufgabe == "ueberarbeiten":
                if not str(entwurf).strip():
                    raise ValueError("Zum Überarbeiten zuerst einen Brieftext eingeben.")
                auftrag += f"\n\n<mein_entwurf>\n{str(entwurf)[:20000]}\n</mein_entwurf>"
            if aufgabe in BRIEF_AUFGABEN and str(bewertung).strip():
                auftrag += f"\n\nZugrunde liegende Bewertung (zuvor mit mir erarbeitet):\n<bewertung>\n{str(bewertung)[:30000]}\n</bewertung>"
            if aufgabe in BRIEF_AUFGABEN and str(option).strip():
                auftrag += (f"\n\nGewählte Vorgehensweise – das Schreiben muss genau diese Linie umsetzen:\n{str(option)[:4000]}")
            if str(empfaenger).strip():
                auftrag += f"\n\nEmpfänger des Briefs:\n{str(empfaenger)[:500]}"
            if str(anweisung).strip():
                auftrag += f"\n\nMeine Vorgaben dazu: {str(anweisung)[:2000]}"
            nachrichten.append({"role": "user", "content": auftrag})
        if not nachrichten or nachrichten[-1]["role"] != "user":
            raise ValueError("Bitte eine Frage stellen.")
        stufe = STUFEN[self.stufe()]
        anfrage = {
            "model": stufe["modell"],
            "max_tokens": 16000,
            # Zwischenspeicher (Prompt-Caching): Anweisung und Akte bilden einen gleichbleibenden Anfang. Der Merker
            # sitzt am Ende der Akte, nicht am Ende der wechselnden Frage – so lesen Bewertung, Entwurf und Folgefragen
            # zum selben Vorgang die Akte binnen 5 Minuten zu einem Zwanzigstel des Preises aus dem Speicher.
            "system": [{"type": "text", "text": SYSTEM},
                       {"type": "text", "text": uebersicht + "\n\nAKTE (vollständig, älteste zuerst):\n" + akte,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": nachrichten,
            "output_config": {"effort": AUFWAND.get(aufgabe, "medium")},
        }
        if stufe["modell"] != "claude-haiku-5-5":  # für Haiku gibt es kein Ersatzmodell bei Ablehnung
            anfrage["fallbacks"] = "default"
        if aufgabe in BRIEF_AUFGABEN:
            anfrage["output_config"]["format"] = {"type": "json_schema", "schema": BRIEF_SCHEMA}
        elif aufgabe == "bewerten":
            anfrage["output_config"]["format"] = {"type": "json_schema", "schema": BEWERTUNG_SCHEMA}
        antwort = self.senden(anfrage, schluessel)
        if antwort.get("stop_reason") == "refusal":
            raise ValueError("Claude hat diese Anfrage abgelehnt. Bitte anders formulieren.")
        text = "".join(b.get("text", "") for b in antwort.get("content", []) if b.get("type") == "text").strip()
        if antwort.get("stop_reason") == "max_tokens":
            text += "\n\n[Antwort wurde wegen der Länge abgeschnitten.]"
        nutzung = antwort.get("usage", {})
        ein, aus, lesen, schreiben = stufe["preise"]
        kosten = (nutzung.get("input_tokens", 0) * ein + nutzung.get("output_tokens", 0) * aus
                  + nutzung.get("cache_read_input_tokens", 0) * lesen + nutzung.get("cache_creation_input_tokens", 0) * schreiben) / 1e6
        info = dict(info, kosten_usd=round(kosten, 4), stufe=stufe["name"],
                    aus_speicher=nutzung.get("cache_read_input_tokens", 0))
        ergebnis = {"text": text, "aufgabe": aufgabe, "nutzung": nutzung, "kontext": info}
        if aufgabe in BRIEF_AUFGABEN:
            try:
                brief = json.loads(text)
                brief["brieftext"] = brieftext_saeubern(brief["brieftext"])
                brief["betreff"] = brief["betreff"].replace("*", "").removeprefix("Betreff:").strip()
                ergebnis.update(betreff=brief["betreff"], brieftext=brief["brieftext"], hinweise=brief.get("hinweise", ""),
                                text=f"Betreff: {brief['betreff']}\n\n{brief['brieftext']}"
                                     + (f"\n\nHinweise: {brief['hinweise']}" if brief.get("hinweise") else ""))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # dann als freier Text anzeigen
        elif aufgabe == "bewerten":
            try:
                b = json.loads(text)
                if not isinstance(b.get("optionen"), list):
                    raise TypeError
                ergebnis.update(bewertung=b, text=bewertung_als_text(b))
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        return ergebnis

    def zitate_pruefen(self, text, gesetze):
        """Gegenprüfung: Stimmen die zitierten Vorschriften mit ihrem amtlichen Wortlaut überein? Geschickt wird nur
        der geprüfte Text und der Wortlaut der zitierten Vorschriften, nicht die Akte – daher günstig."""
        schluessel = self.schluessel()
        if not schluessel:
            raise ValueError("Claude ist noch nicht eingerichtet: Zugangsschlüssel unter Einstellungen → Claude eintragen.")
        normen = gesetze.fuer_text(text)
        if not normen:
            raise ValueError("Im Text sind keine Vorschriften aus Bundesgesetzen zitiert.")
        belegt = [n for n in normen if n.get("absaetze")]
        if not belegt:
            return {"vorschriften": normen, "pruefungen": [], "kontext": {}}
        wortlaut = "\n\n".join(f"<vorschrift name=\"{n['norm']} {n['gesetz']}\" titel=\"{n.get('titel', '')}\">\n"
                                + "\n".join(n["absaetze"]) + "\n</vorschrift>" for n in belegt)
        stufe = STUFEN[self.stufe()]
        anfrage = {
            "model": stufe["modell"], "max_tokens": 8000,
            "system": "Du prüfst juristische Texte auf korrekte Gesetzeszitate. Antworte auf Deutsch, knapp und genau.",
            "messages": [{"role": "user", "content":
                          "Prüfe für jede unten im amtlichen Wortlaut mitgelieferte Vorschrift, ob die Aussagen im Text, "
                          "die sich auf sie stützen, vom Wortlaut gedeckt sind (richtiger Paragraf, richtiger Absatz, "
                          "passender Regelungsinhalt). „passt nicht“ heißt: falsche Vorschrift zitiert oder Aussage "
                          "widerspricht dem Wortlaut; nenne dann, welche Vorschrift gemeint sein dürfte.\n\n"
                          f"<text>\n{str(text)[:30000]}\n</text>\n\n{wortlaut}"}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": PRUEF_SCHEMA}},
        }
        if stufe["modell"] != "claude-haiku-5-5":
            anfrage["fallbacks"] = "default"
        antwort = self.senden(anfrage, schluessel)
        if antwort.get("stop_reason") == "refusal":
            raise ValueError("Claude hat die Prüfung abgelehnt.")
        roh = "".join(b.get("text", "") for b in antwort.get("content", []) if b.get("type") == "text")
        try:
            pruefungen = json.loads(roh)["pruefungen"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise ValueError("Die Prüfung konnte nicht ausgewertet werden. Bitte erneut versuchen.") from None
        nutzung = antwort.get("usage", {})
        ein, aus, lesen, schreiben = stufe["preise"]
        kosten = (nutzung.get("input_tokens", 0) * ein + nutzung.get("output_tokens", 0) * aus
                  + nutzung.get("cache_read_input_tokens", 0) * lesen + nutzung.get("cache_creation_input_tokens", 0) * schreiben) / 1e6
        return {"vorschriften": normen, "pruefungen": pruefungen, "kosten_usd": round(kosten, 4)}

    def _http(self, anfrage, schluessel):
        daten = json.dumps(anfrage).encode("utf-8")
        req = urllib.request.Request(API, data=daten, method="POST", headers={
            "Content-Type": "application/json", "x-api-key": schluessel, "anthropic-version": API_VERSION,
            **({"anthropic-beta": FALLBACK_BETA} if "fallbacks" in anfrage else {})})
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            try:
                meldung = json.loads(fehler.read().decode("utf-8")).get("error", {}).get("message", "")
            except (ValueError, OSError):
                meldung = ""
            grund = {401: "Der Zugangsschlüssel ist ungültig.", 403: "Der Zugangsschlüssel hat keine Berechtigung.",
                     429: "Zu viele Anfragen oder Guthaben aufgebraucht – bitte später erneut versuchen.",
                     529: "Claude ist gerade überlastet – bitte gleich erneut versuchen."}.get(fehler.code)
            raise ValueError(grund or f"Claude meldet einen Fehler ({fehler.code}): {meldung[:300]}") from None
        except (urllib.error.URLError, TimeoutError) as fehler:
            raise ValueError(f"Claude ist nicht erreichbar (Internetverbindung?): {getattr(fehler, 'reason', fehler)}") from None


def test_claude(store):
    """Anfrageaufbau, Briefentwurf als strukturierte Antwort, Ablehnung, Schlüsselablage – ohne Netz."""
    from akte import Akte
    store = type(store)(store.data / "Claudetest", None)
    akte = Akte(store, today=lambda: "2026-11-24")
    v = store.create_case("Amtsgericht Forderung TÜV", "Versicherungen", "")
    d, _ = store.import_document(v, "Forderung.pdf", b"%PDF-1.4\nForderung")
    with closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)",
                   (d, 1, "pdf", "Amtsgericht Rostock\nZahlen Sie 180,98 € bis zum 15.12.2026."))
    gesendet = []

    def falsch(anfrage, schluessel):
        gesendet.append((anfrage, schluessel))
        if anfrage["messages"][-1]["content"].startswith("Entwirf"):
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(
                {"betreff": "Ihre Forderung", "brieftext": "Sehr geehrte Damen und Herren,\n\nich widerspreche.", "hinweise": "Aktenzeichen ergänzen"})}]}
        if anfrage["messages"][-1]["content"].startswith("Analysiere"):
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps({
                "zusammenfassung": "Mahnung über 180,98 €.", "rechtliche_bewertung": "Forderung zweifelhaft (§ 286 BGB).",
                "fristen": [{"datum": "15.12.2026", "was": "Zahlung"}], "risiken": "Mahnbescheid", "fehlende_angaben": "",
                "optionen": [{"titel": "Zahlen", "beschreibung": "b", "vorteile": "v", "nachteile": "n", "empfohlen": False},
                             {"titel": "Widersprechen", "beschreibung": "b", "vorteile": "v", "nachteile": "n", "empfohlen": True}]})}]}
        if "verboten" in anfrage["messages"][-1]["content"]:
            return {"stop_reason": "refusal", "content": []}
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Zahlung 180,98 € bis 15.12.2026."}],
                "usage": {"input_tokens": 10, "output_tokens": 5}}

    ki = ClaudeKI(store, akte, senden=falsch)
    try:
        ki.fragen(v, d, [{"rolle": "user", "text": "Was steht drin?"}])
        raise AssertionError("Ohne Schlüssel darf nichts gesendet werden")
    except ValueError:
        assert not gesendet
    try:
        ki.schluessel_setzen("falsch")
        raise AssertionError("Unplausibler Schlüssel muss abgelehnt werden")
    except ValueError:
        pass
    assert ki.schluessel_setzen("sk-ant-test-1234")["endung"] == "1234"
    assert (store.data / "claude_schluessel").stat().st_mode & 0o077 == 0
    r = ki.fragen(v, d, [], "zusammenfassen")
    anfrage, schluessel = gesendet[-1]
    assert schluessel == "sk-ant-test-1234" and anfrage["model"] == MODELL and anfrage["fallbacks"] == "default"
    assert anfrage["system"][1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in anfrage
    assert anfrage["output_config"]["effort"] == "low" and r["kontext"]["kosten_usd"] == round((10 * 4 + 5 * 20) / 1e6, 4)
    assert ki.stufe_setzen("sparsam")["stufe"] == "sparsam"
    ki.fragen(v, d, [], "zusammenfassen")
    assert gesendet[-1][0]["model"] == "claude-haiku-5-5" and "fallbacks" not in gesendet[-1][0]
    ki.stufe_setzen("ausgewogen")
    ki.fragen(v, d, [], "zusammenfassen")
    assert gesendet[-1][0]["model"] == "claude-sonnet-5-5"
    ki.stufe_setzen("gruendlich")
    assert "180,98" in anfrage["system"][1]["text"] and "[GEWÄHLTES SCHREIBEN]" in anfrage["system"][1]["text"]
    assert "Amtsgericht Forderung TÜV" in anfrage["system"][1]["text"] and r["text"].startswith("Zahlung")
    r = ki.fragen(v, d, [], "ueberarbeiten", anweisung="kürzer", entwurf="Sehr geehrte Damen und Herren, nein.",
                  empfaenger="Amtsgericht Rostock")
    letzte = gesendet[-1][0]["messages"][-1]["content"]
    assert "<mein_entwurf>" in letzte and "kürzer" in letzte and "Amtsgericht Rostock" in letzte
    assert gesendet[-1][0]["output_config"]["format"]["type"] == "json_schema"
    r = ki.fragen(v, d, [], "bewerten")
    assert gesendet[-1][0]["output_config"]["format"]["schema"] is BEWERTUNG_SCHEMA
    assert r["bewertung"]["optionen"][1]["empfohlen"] and "OPTION 2 (empfohlen): Widersprechen" in r["text"]
    r = ki.fragen(v, d, [], "antwort", bewertung=r["text"], option="Widersprechen: Termin fand nie statt")
    letzte = gesendet[-1][0]["messages"][-1]["content"]
    assert "<bewertung>" in letzte and "genau diese Linie" in letzte and "Termin fand nie statt" in letzte
    r = ki.fragen(v, d, [], "antwort")
    assert gesendet[-1][0]["output_config"]["format"]["type"] == "json_schema"
    assert r["betreff"] == "Ihre Forderung" and r["brieftext"].startswith("Sehr geehrte")
    assert brieftext_saeubern("**Sehr geehrte**\n\n\n\n* Punkt\n## Titel") == "Sehr geehrte\n\n– Punkt\nTitel"
    try:
        ki.fragen(v, d, [{"rolle": "user", "text": "verboten"}])
        raise AssertionError("Ablehnung muss gemeldet werden")
    except ValueError as fehler:
        assert "abgelehnt" in str(fehler)

    # Kontext: eigene Schreiben, Notizen und alle Dokumente gehen vollständig und in zeitlicher Reihenfolge mit
    alt, _ = store.import_document(v, "Mahnung.pdf", b"%PDF-1.4\nMahnung alt")
    with closing(store.connect()) as db, db:
        db.execute("INSERT INTO dokumentseite(dokument_id,nummer,methode,text) VALUES(?,?,?,?)",
                   (alt, 1, "pdf", "Erste Mahnung über 180,98 €. " + "Langer Vertragstext. " * 400 + "SCHLUSSKLAUSEL-ALT"))
    akte.eintrag_anlegen(v, {"art": "eingang", "titel": "Erste Mahnung", "datum": "2026-10-01", "dokument_id": alt})
    entw = akte.eintrag_anlegen(v, {"art": "entwurf", "titel": "Widerspruch", "datum": "2026-10-10",
                                    "text": "Ich bestreite die Forderung, da der TÜV-Termin nie stattfand. " + "Begründung. " * 300 + "ENDE-MEINES-BRIEFS",
                                    "brief": {"betreff": "Widerspruch gegen Mahnung", "empfaenger": "Inkasso GmbH"}})
    akte.versand_erfassen(entw, {"art": "Einschreiben", "datum": "2026-10-11", "empfaenger": "Inkasso GmbH\nHauptstr. 1"})
    akte.eintrag_anlegen(v, {"art": "telefonat", "titel": "Anruf Inkasso", "datum": "2026-10-20",
                             "text": "Ratenzahlung abgelehnt, Sachbearbeiterin Frau Kurz."})
    r = ki.fragen(v, d, [], "zusammenfassen")
    akte_text = gesendet[-1][0]["system"][1]["text"]
    for muss in ("ENDE-MEINES-BRIEFS", "Versand per Einschreiben am 2026-10-11", "Ratenzahlung abgelehnt",
                 "SCHLUSSKLAUSEL-ALT", "Widerspruch gegen Mahnung", "MEIN SCHREIBEN (versendet)"):
        assert muss in akte_text, muss
    assert akte_text.count("ENDE-MEINES-BRIEFS") == 1, "versendeter Entwurf darf nicht doppelt erscheinen"
    assert akte_text.index("Erste Mahnung") < akte_text.index("Widerspruch gegen Mahnung") < akte_text.index("Ratenzahlung")
    assert r["kontext"]["eigene_schreiben"] == 1 and not r["kontext"]["gekuerzt"]
    # Obergrenze: gekürzt wird nur das ältere fremde Dokument, nie das eigene Schreiben oder das gewählte Schreiben
    global MAX_KONTEXT
    alt_grenze, MAX_KONTEXT = MAX_KONTEXT, 6000
    try:
        r = ki.fragen(v, d, [], "zusammenfassen")
    finally:
        MAX_KONTEXT = alt_grenze
    akte_text = gesendet[-1][0]["system"][1]["text"]
    assert "SCHLUSSKLAUSEL-ALT" not in akte_text and "ENDE-MEINES-BRIEFS" in akte_text and "180,98 € bis zum 15.12" in akte_text
    assert r["kontext"]["gekuerzt"] == ["Erste Mahnung"]
    # Zitate prüfen: nur Text und Wortlaut gehen hinaus, nicht die Akte
    from gesetze import Gesetze
    seite = ('<span class="jnenbez">&#167; 362</span><span class="jnentitel">Erl&ouml;schen durch Leistung</span>'
             '<div class="jurAbsatz">(1) Das Schuldverhältnis erlischt durch Leistung.</div>').encode("iso-8859-1")
    g = Gesetze(store.data / "Gesetze", lambda url: (seite, "text/html; charset=iso-8859-1"))
    vorher = len(gesendet)
    ki.senden = lambda anfrage, s: (gesendet.append((anfrage, s)) or {"stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 50},
        "content": [{"type": "text", "text": json.dumps({"pruefungen": [{"vorschrift": "§ 362 BGB", "ergebnis": "passt", "begruendung": "Erfüllung."}]})}]})
    r = ki.zitate_pruefen("Die Forderung ist nach § 362 Abs. 1 BGB erloschen.", g)
    anfrage = gesendet[-1][0]
    assert len(gesendet) == vorher + 1 and "Schuldverhältnis erlischt" in anfrage["messages"][0]["content"]
    assert "AKTE" not in json.dumps(anfrage) and r["pruefungen"][0]["ergebnis"] == "passt" and r["kosten_usd"] > 0
    try:
        ki.zitate_pruefen("Ohne Paragrafen.", g)
        raise AssertionError("ohne Zitat darf nichts gesendet werden")
    except ValueError:
        assert len(gesendet) == vorher + 1
    ki.schluessel_setzen("")
    assert not ki.status()["eingerichtet"]

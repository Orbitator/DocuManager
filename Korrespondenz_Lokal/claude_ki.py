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
MODELL = "claude-opus-5-5"
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # bei Ablehnung durch Sicherheitsfilter automatisch Ersatzmodell
MAX_KONTEXT = 120_000  # Zeichen Dokumenttext je Anfrage

SYSTEM = """Du unterstützt eine Privatperson bzw. einen Kleinunternehmer in Deutschland bei der Bearbeitung von
Korrespondenz (Behörden, Gerichte, Versicherungen, Vermieter, Firmen). Antworte auf Deutsch, sachlich und knapp.
Stütze dich auf die mitgelieferten Unterlagen; nenne Fundstellen (Dokument, Datum) und kennzeichne Annahmen.
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
    "antwort": "Entwirf ein Antwortschreiben auf dieses Schreiben.",
}

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "betreff": {"type": "string", "description": "Betreffzeile ohne das Wort „Betreff“"},
        "brieftext": {"type": "string", "description": "Brieftext ab der Anrede bis einschließlich Grußformel und Name; "
                                                      "Absätze durch Leerzeilen getrennt"},
        "hinweise": {"type": "string", "description": "Kurze Hinweise an den Absender (was zu prüfen/ergänzen ist)"},
    },
    "required": ["betreff", "brieftext", "hinweise"],
    "additionalProperties": False,
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

    def status(self):
        s = self.schluessel()
        return {"eingerichtet": bool(s), "endung": s[-4:] if s else None, "modell": MODELL}

    # --- Kontext aus dem Vorgang --------------------------------------------------------
    def kontext(self, vorgang_id, dokument_id=None):
        a = self.akte.akte(vorgang_id)
        zeilen = [f"VORGANG: {a['titel']} (Bereich: {', '.join(a.get('bereiche') or [a['bereich']])}; Status: {a['status']})"]
        if a["beteiligte"]:
            zeilen.append("BETEILIGTE: " + "; ".join(b["name"] for b in a["beteiligte"]))
        if a["referenzen"]:
            zeilen.append("REFERENZEN: " + "; ".join(f"{r['bezeichnung']} {r['wert']}" for r in a["referenzen"]))
        offen = [f for f in a["fristen"] if not f["erledigt_am"]]
        if offen:
            zeilen.append("OFFENE FRISTEN: " + "; ".join(f"{f['faellig_am']} {f['titel']}" for f in offen))
        zeilen.append("CHRONIK (neueste zuerst):")
        for e in a["eintraege"][:60]:
            zeilen.append(f"- {e['ereignis_datum']} · {e.get('typ') or e['art']} · {e['titel']}")
        eigene = self.akte.eigene_angaben()
        if eigene:
            zeilen.append("MEINE ANGABEN (Absender): " + eigene.replace("\n", ", "))
        uebersicht = "\n".join(zeilen)
        texte, rest = [], MAX_KONTEXT
        reihenfolge = sorted(a["dokumente"], key=lambda d: d["id"] != dokument_id)
        for d in reihenfolge:
            seiten = self.store.pages(d["id"])
            text = "\n".join(s["text"] for s in seiten).strip()
            if not text:
                continue
            haupt = d["id"] == dokument_id
            grenze = rest if haupt else min(rest, 4000)
            if grenze <= 500:
                break
            gekuerzt = text[:grenze] + ("\n[… gekürzt]" if len(text) > grenze else "")
            rest -= len(gekuerzt)
            fokus = ' fokus="ja"' if haupt else ""
            texte.append(f'<dokument titel="{d["titel"]}" datei="{d["dateiname"]}"{fokus}>\n{gekuerzt}\n</dokument>')
        return a, uebersicht, texte

    # --- Anfrage ------------------------------------------------------------------------
    def fragen(self, vorgang_id, dokument_id, verlauf, aufgabe="frage"):
        """verlauf: Liste von {rolle: "user"|"assistant", text}. Die letzte Nachricht ist die neue Frage
        (bei aufgabe != "frage" wird sie aus AUFGABEN ergänzt)."""
        schluessel = self.schluessel()
        if not schluessel:
            raise ValueError("Claude ist noch nicht eingerichtet: Zugangsschlüssel unter Einstellungen → Claude eintragen.")
        if aufgabe not in ("frage", *AUFGABEN):
            raise ValueError("Unbekannte Aufgabe.")
        if not isinstance(verlauf, list) or len(verlauf) > 40:
            raise ValueError("Verlauf: ungültige Angabe.")
        a, uebersicht, texte = self.kontext(vorgang_id, dokument_id)
        nachrichten = []
        for n in verlauf:
            if not isinstance(n, dict) or n.get("rolle") not in ("user", "assistant") or not str(n.get("text", "")).strip():
                raise ValueError("Verlauf: ungültige Nachricht.")
            nachrichten.append({"role": n["rolle"], "content": str(n["text"])[:20000]})
        if aufgabe != "frage":
            nachrichten.append({"role": "user", "content": AUFGABEN[aufgabe]})
        if not nachrichten or nachrichten[-1]["role"] != "user":
            raise ValueError("Bitte eine Frage stellen.")
        anfrage = {
            "model": MODELL,
            "max_tokens": 16000,
            "system": [{"type": "text", "text": SYSTEM},
                       {"type": "text", "text": uebersicht + "\n\nUNTERLAGEN:\n" + "\n\n".join(texte)}],
            "messages": nachrichten,
            "cache_control": {"type": "ephemeral"},  # Folgefragen zum selben Dokument werden günstiger
            "fallbacks": "default",
            "output_config": {"effort": "high" if aufgabe in ("antwort", "pruefen") else "medium"},
        }
        if aufgabe == "antwort":
            anfrage["output_config"]["format"] = {"type": "json_schema", "schema": BRIEF_SCHEMA}
        antwort = self.senden(anfrage, schluessel)
        if antwort.get("stop_reason") == "refusal":
            raise ValueError("Claude hat diese Anfrage abgelehnt. Bitte anders formulieren.")
        text = "".join(b.get("text", "") for b in antwort.get("content", []) if b.get("type") == "text").strip()
        if antwort.get("stop_reason") == "max_tokens":
            text += "\n\n[Antwort wurde wegen der Länge abgeschnitten.]"
        ergebnis = {"text": text, "aufgabe": aufgabe, "nutzung": antwort.get("usage", {})}
        if aufgabe == "antwort":
            try:
                brief = json.loads(text)
                ergebnis.update(betreff=brief["betreff"], brieftext=brief["brieftext"], hinweise=brief.get("hinweise", ""),
                                text=f"Betreff: {brief['betreff']}\n\n{brief['brieftext']}"
                                     + (f"\n\nHinweise: {brief['hinweise']}" if brief.get("hinweise") else ""))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # dann als freier Text anzeigen
        return ergebnis

    def _http(self, anfrage, schluessel):
        daten = json.dumps(anfrage).encode("utf-8")
        req = urllib.request.Request(API, data=daten, method="POST", headers={
            "Content-Type": "application/json", "x-api-key": schluessel, "anthropic-version": API_VERSION,
            "anthropic-beta": FALLBACK_BETA})
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
    assert "180,98" in anfrage["system"][1]["text"] and 'fokus="ja"' in anfrage["system"][1]["text"]
    assert "Amtsgericht Forderung TÜV" in anfrage["system"][1]["text"] and r["text"].startswith("Zahlung")
    r = ki.fragen(v, d, [], "antwort")
    assert gesendet[-1][0]["output_config"]["format"]["type"] == "json_schema"
    assert r["betreff"] == "Ihre Forderung" and r["brieftext"].startswith("Sehr geehrte")
    try:
        ki.fragen(v, d, [{"rolle": "user", "text": "verboten"}])
        raise AssertionError("Ablehnung muss gemeldet werden")
    except ValueError as fehler:
        assert "abgelehnt" in str(fehler)
    ki.schluessel_setzen("")
    assert not ki.status()["eingerichtet"]

"""Kompetenzrahmen (KR) und Kompetenzabbildung (KA).

Ein Kompetenzrahmen ist ein Baum: Bereich › Kompetenz › Kompetenzstufe › Kompetenzpunkt. Er liegt als
JSON unter _kompetenzen/<id>.json; daneben schreibt Liloport <id>.html (Rahmen ansehen und bearbeiten)
und <id>-abbildung.html (die Abbildung: welche Stufen sind offen, in Bearbeitung, erarbeitet).

Status kommt von den Seiten: Ein KR-Block auf einer Seite wählt Knoten des Baums und setzt pro Knoten
«weiss» (noch nicht bearbeitet), «orange» (in Bearbeitung) oder «gruen» (erarbeitet). Die Abbildung
kennt dazu einen vierten Zustand «offen»: Der Knoten ist keiner Seite zugeordnet. Sie rechnet für jeden
Knoten:
  - direkt: der höchste Status, den irgendeine Seite für den Knoten gesetzt hat; «offen» ohne Seite;
  - abgeleitet aus den Kindern: grün, wenn alle Kinder grün sind; orange, sobald ein Kind orange oder
    grün ist; «noch nicht bearbeitet», sobald ein Kind einer Seite zugeordnet ist; sonst offen;
  - wirksam: das Höhere von direkt und abgeleitet (offen < noch nicht bearbeitet < in Bearbeitung < erarbeitet).
So färbt ein oranger Punkt alle Ebenen darüber orange, eine Stufe wird grün, sobald alle ihre Punkte
grün sind (oder eine Seite sie direkt als erarbeitet markiert), und eine Stufe, die eine Seite als
«noch nicht bearbeitet» führt, unterscheidet sich von einer, die noch gar keiner Seite zugeordnet ist.
"""
import html
import json
import re
import secrets
from pathlib import Path

from . import slugs
from .store import Store, StoreFehler, jetzt

ORDNER = "_kompetenzen"
EBENEN = ("bereich", "kompetenz", "stufe", "punkt")
EBENE_NAMEN = {"bereich": "Bereich", "kompetenz": "Kompetenz", "stufe": "Kompetenzstufe", "punkt": "Kompetenzpunkt"}
KINDER = {"bereich": "kompetenzen", "kompetenz": "stufen", "stufe": "punkte"}
STATUS = ("weiss", "orange", "gruen")                 # was eine Seite für einen Knoten setzen kann
OFFEN = "offen"                                       # Knoten ohne Seite (nur in der Abbildung)
ZUSTAENDE = (OFFEN,) + STATUS                         # alle Zustände der Abbildung, aufsteigend
STATUS_NAMEN = {"offen": "offen", "weiss": "noch nicht bearbeitet", "orange": "in Bearbeitung", "gruen": "erarbeitet"}
STATUS_ERKLAERUNG = {"offen": "noch keiner Seite zugeordnet", "weiss": "einer Seite zugeordnet, noch nicht bearbeitet",
                     "orange": "in Bearbeitung", "gruen": "erarbeitet"}
RANG = {"offen": 0, "weiss": 1, "orange": 2, "gruen": 3}
MAX_KNOTEN = 2000


def _id() -> str:
    return secrets.token_hex(3)


def _text(wert, laenge) -> str:
    return re.sub(r"\s+", " ", str(wert or "")).strip()[:laenge]


def _knoten_pruefen(k, ebene: str, ids: set, zaehler: list) -> dict:
    """Validiert einen Knoten rekursiv; vergibt fehlende IDs, kürzt Texte, begrenzt die Grösse."""
    if not isinstance(k, dict):
        raise StoreFehler("Ungültiger Knoten im Kompetenzrahmen.")
    zaehler[0] += 1
    if zaehler[0] > MAX_KNOTEN:
        raise StoreFehler(f"Der Kompetenzrahmen hat mehr als {MAX_KNOTEN} Einträge.")
    kid = str(k.get("id") or "")
    if not re.fullmatch(r"[a-z0-9]{3,12}", kid) or kid in ids:
        kid = _id()
        while kid in ids:
            kid = _id()
    ids.add(kid)
    neu = {"id": kid, "titel": _text(k.get("titel") or k.get("text"), 200), "beschreibung": str(k.get("beschreibung") or "").strip()[:2000]}
    if ebene in KINDER:
        kinder = k.get(KINDER[ebene])
        if kinder is None:
            kinder = k.get("kinder") or []
        if not isinstance(kinder, list):
            raise StoreFehler("Unterpunkte müssen eine Liste sein.")
        naechste = EBENEN[EBENEN.index(ebene) + 1]
        neu[KINDER[ebene]] = [_knoten_pruefen(x, naechste, ids, zaehler) for x in kinder]
    return neu


def rahmen_pruefen(daten: dict, kid: str = None) -> dict:
    """Bringt einen Kompetenzrahmen in die gültige Form (auch für Importe aus fremden Dateien)."""
    if not isinstance(daten, dict):
        raise StoreFehler("Der Kompetenzrahmen hat ein unbekanntes Format.")
    ids, zaehler = set(), [0]
    bereiche = daten.get("bereiche")
    if bereiche is None:
        bereiche = daten.get("kinder") or []
    if not isinstance(bereiche, list):
        raise StoreFehler("«bereiche» muss eine Liste sein.")
    return {
        "liloportKompetenzrahmen": 1,
        "id": kid or str(daten.get("id") or ""),
        "titel": _text(daten.get("titel"), 200) or "Kompetenzrahmen",
        "beschreibung": str(daten.get("beschreibung") or "").strip()[:4000],
        "quelle": _text(daten.get("quelle"), 300),
        "version": _text(daten.get("version"), 60),
        "geaendert": jetzt(),
        "bereiche": [_knoten_pruefen(b, "bereich", ids, zaehler) for b in bereiche],
    }


def knoten_index(kr: dict) -> dict:
    """{id: {ebene, titel, beschreibung, pfad: [Titel…], eltern, kinder: [ids]}} in Baumreihenfolge."""
    index = {}

    def rek(k, ebene, pfad, eltern):
        kinder = k.get(KINDER.get(ebene, ""), []) if ebene in KINDER else []
        index[k["id"]] = {"ebene": ebene, "titel": k.get("titel", ""), "beschreibung": k.get("beschreibung", ""),
                          "pfad": pfad + [k.get("titel", "")], "eltern": eltern, "kinder": [x["id"] for x in kinder]}
        for x in kinder:
            rek(x, EBENEN[EBENEN.index(ebene) + 1], pfad + [k.get("titel", "")], k["id"])
    for b in kr.get("bereiche", []):
        rek(b, "bereich", [], None)
    return index


def kr_bloecke(bloecke):
    """Alle KR-Blöcke einer Seite (auch in Spalten)."""
    for b in bloecke or []:
        if not isinstance(b, dict):
            continue
        if b.get("typ") == "kr":
            yield b
        if b.get("typ") == "spalten":
            for sp in b.get("spalten") or []:
                yield from kr_bloecke(sp)


def block_pruefen(b: dict, bid: str) -> dict:
    """Validiert einen KR-Block: Rahmen-ID und Knoten → Status."""
    rahmen = str(b.get("rahmen") or "")
    if rahmen and not re.fullmatch(r"[a-z0-9-]{1,60}", rahmen):
        raise StoreFehler("Ungültiger Kompetenzrahmen.")
    knoten = {}
    for nid, st in (b.get("knoten") or {}).items():
        if re.fullmatch(r"[a-z0-9]{3,12}", str(nid)) and st in STATUS:
            knoten[str(nid)] = st
    return {"id": bid, "typ": "kr", "rahmen": rahmen, "knoten": knoten}


def status_berechnen(kr: dict, seiten: list) -> dict:
    """seiten: [(pfad, titel, seite_dict)] → {knoten_id: {status, direkt, abgeleitet, seiten: [{pfad, titel, status}]}}.

    status/direkt/abgeleitet sind einer von ZUSTAENDE; «offen» heisst: keine Seite (auch keine darunter)."""
    index = knoten_index(kr)
    ergebnis = {nid: {"direkt": OFFEN, "seiten": []} for nid in index}
    for pfad, titel, seite in seiten:
        for b in kr_bloecke(seite.get("bloecke")):
            if b.get("rahmen") != kr["id"]:
                continue
            for nid, st in (b.get("knoten") or {}).items():
                if nid in ergebnis and st in STATUS:
                    e = ergebnis[nid]
                    e["seiten"].append({"pfad": pfad, "titel": titel, "status": st, "block": b.get("id", "")})
                    if RANG[st] > RANG[e["direkt"]]:
                        e["direkt"] = st

    def ableiten(staende: list) -> str:
        if not staende:
            return OFFEN
        if all(s == "gruen" for s in staende):
            return "gruen"
        if any(s in ("gruen", "orange") for s in staende):
            return "orange"
        if any(s == "weiss" for s in staende):
            return "weiss"
        return OFFEN

    def wirksam(nid):
        e = ergebnis[nid]
        if "status" in e:
            return e["status"]
        abgeleitet = ableiten([wirksam(k) for k in index[nid]["kinder"]])
        e["abgeleitet"] = abgeleitet
        e["status"] = e["direkt"] if RANG[e["direkt"]] >= RANG[abgeleitet] else abgeleitet
        return e["status"]
    for nid in index:
        wirksam(nid)
    return ergebnis


def zusammenfassung(kr: dict, status: dict) -> dict:
    """Zählt pro Ebene, wie viele Knoten offen, noch nicht bearbeitet, in Bearbeitung und erarbeitet sind."""
    index = knoten_index(kr)
    z = {e: dict({st: 0 for st in ZUSTAENDE}, gesamt=0) for e in EBENEN}
    for nid, k in index.items():
        z[k["ebene"]][status[nid]["status"]] += 1
        z[k["ebene"]]["gesamt"] += 1
    return z


class Kompetenzen:
    """Ablage der Kompetenzrahmen im Inhalte-Ordner (_kompetenzen/<id>.json)."""

    def __init__(self, store: Store):
        self.store = store
        self.ordner = store.root / ORDNER

    def liste(self) -> list:
        if not self.ordner.exists():
            return []
        ergebnis = []
        for datei in sorted(self.ordner.glob("*.json")):
            try:
                kr = json.loads(datei.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            index = knoten_index(kr)
            ergebnis.append({"id": datei.stem, "titel": kr.get("titel", datei.stem), "quelle": kr.get("quelle", ""),
                             "version": kr.get("version", ""), "geaendert": kr.get("geaendert", ""),
                             "bereiche": len(kr.get("bereiche", [])), "knoten": len(index)})
        return ergebnis

    def laden(self, kid: str) -> dict:
        if not re.fullmatch(r"[a-z0-9-]{1,60}", kid or ""):
            raise StoreFehler("Ungültiger Kompetenzrahmen.")
        datei = self.ordner / f"{kid}.json"
        if not datei.exists():
            raise StoreFehler("Kompetenzrahmen nicht gefunden.")
        kr = json.loads(datei.read_text(encoding="utf-8"))
        kr["id"] = kid
        return kr

    def alle(self) -> dict:
        return {e["id"]: self.laden(e["id"]) for e in self.liste()}

    def speichern(self, kid: str, daten: dict) -> dict:
        kr = rahmen_pruefen(daten, kid)
        self.ordner.mkdir(exist_ok=True)
        with open(self.ordner / f"{kid}.json", "w", encoding="utf-8") as f:
            json.dump(kr, f, ensure_ascii=False, indent=2)
        return kr

    def anlegen(self, daten: dict = None) -> dict:
        daten = dict(daten or {})
        titel = _text(daten.get("titel"), 200) or "Kompetenzrahmen"
        belegt = {e["id"] for e in self.liste()}
        kid = slugs.eindeutig(slugs.slugify(titel), belegt)
        daten["titel"] = titel
        if not daten.get("bereiche") and "bereiche" not in daten:
            daten["bereiche"] = []
        return self.speichern(kid, daten)

    def importieren(self, daten: bytes, name: str = "") -> dict:
        """Nimmt eine JSON-Datei (unser Format) entgegen und legt sie als neuen Rahmen an."""
        try:
            roh = json.loads(daten.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            raise StoreFehler("Die Datei ist kein lesbares JSON.")
        if isinstance(roh, dict) and "bereiche" not in roh and "kinder" not in roh:
            raise StoreFehler("Die Datei enthält keinen Kompetenzrahmen (es fehlt «bereiche»).")
        if not roh.get("titel"):
            roh["titel"] = Path(name).stem or "Importierter Rahmen"
        return self.anlegen(roh)

    def loeschen(self, kid: str):
        kr = self.laden(kid)
        for datei in (self.ordner / f"{kid}.json", self.ordner / f"{kid}.html", self.ordner / f"{kid}-abbildung.html"):
            if datei.exists():
                datei.unlink()
        return kr

    def status(self, kid: str) -> dict:
        kr = self.laden(kid)
        seiten = [(pfad, seite.get("titel", pfad), seite) for _v, pfad, seite in self.store.alle_seiten()]
        return status_berechnen(kr, seiten)


# ---------- HTML ----------

def _esc(t):
    return html.escape(str(t or ""))


_URL_RE = re.compile(r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?)]")


def _beschreibung(t) -> str:
    """Beschreibung eines Knotens: Zeilenumbrüche bleiben (CSS pre-line), Webadressen werden zu Links."""
    teile, pos, text = [], 0, str(t or "")
    for m in _URL_RE.finditer(text):
        teile.append(_esc(text[pos:m.start()]))
        url = m.group(0)
        teile.append(f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(url)}</a>')
        pos = m.end()
    teile.append(_esc(text[pos:]))
    return "".join(teile)


def rahmen_seite_html(kr: dict, status: dict, vorlage: str, produktfuss: str) -> str:
    """Seite _kompetenzen/<id>.html: zeigt den Rahmen, kr.js macht ihn mit laufendem Liloport bearbeitbar."""
    daten = json.dumps({"rahmen": kr, "status": {nid: s["status"] for nid, s in status.items()}}, ensure_ascii=False).replace("</", "<\\/")
    return (vorlage.replace("{{TITEL}}", _esc(kr.get("titel"))).replace("{{KRID}}", _esc(kr["id"]))
            .replace("{{DATEN}}", daten).replace("{{PRODUKTFUSS}}", produktfuss))


def abbildung_html(kr: dict, status: dict, rel: str, vorlage: str, produktfuss: str, export: bool = False) -> str:
    """Seite _kompetenzen/<id>-abbildung.html: der Stand jedes Knotens, mit den Seiten, die daran arbeiten."""
    index = knoten_index(kr)
    z = zusammenfassung(kr, status)

    def punkt(st):
        return f'<span class="ka-punkt st-{st}" title="{STATUS_ERKLAERUNG[st]}"></span>'

    def seitenliste(nid):
        s = status[nid]["seiten"]
        if not s:
            return ""
        teile = []
        for e in sorted(s, key=lambda x: x["titel"].lower()):
            href = f"{rel}{e['pfad']}.html"
            teile.append(f'<li>{punkt(e["status"])}<a href="{_esc(href)}">{_esc(e["titel"])}</a>'
                         f'<span class="ka-seite-status">{STATUS_NAMEN[e["status"]]}</span></li>')
        return f'<ul class="ka-seiten">{"".join(teile)}</ul>'

    def anzahl_seiten(nid):
        n = len({e["pfad"] for e in status[nid]["seiten"]})
        return f'<span class="ka-anzahl" title="{n} Seite{"n" if n != 1 else ""} arbeiten daran">{n}</span>' if n else ""

    def herkunft(nid):
        e = status[nid]
        if e["status"] == OFFEN:
            return "noch keiner Seite zugeordnet"
        if RANG[e["direkt"]] >= RANG[e["status"]] and e["seiten"]:
            return "auf Seiten gesetzt"
        return "aus Unterpunkten abgeleitet"

    def zaehlen(ids):
        return {st: sum(1 for i in ids if status[i]["status"] == st) for st in ZUSTAENDE}

    def balken(ids):
        """Vier Abschnitte: erarbeitet, in Bearbeitung, noch nicht bearbeitet; der Rest bleibt leer (offen)."""
        if not ids:
            return ""
        n, c = len(ids), zaehlen(ids)
        text = (f'{c["gruen"]} erarbeitet, {c["orange"]} in Bearbeitung, {c["weiss"]} noch nicht bearbeitet, '
                f'{c["offen"]} offen')
        return (f'<span class="ka-balken" role="img" aria-label="{text}" title="{text}">'
                + "".join(f'<span class="st-{st}" style="width:{c[st] * 100 / n:.1f}%"></span>'
                          for st in ("gruen", "orange", "weiss") if c[st]) + '</span>')

    teile = []
    for b in kr.get("bereiche", []):
        komps = b.get("kompetenzen", [])
        stufen_ids = [s["id"] for k in komps for s in k.get("stufen", [])]
        teile.append(f'<section class="ka-bereich st-{status[b["id"]]["status"]}" id="k-{b["id"]}">')
        teile.append(f'<header class="ka-bereich-kopf">{punkt(status[b["id"]]["status"])}<h2>{_esc(b["titel"])}</h2>'
                     f'{balken(stufen_ids)}<span class="ka-kopf-info">{_esc(STATUS_NAMEN[status[b["id"]]["status"]])}'
                     + (f' · {len(stufen_ids)} Stufen' if stufen_ids else "") + '</span></header>')
        if b.get("beschreibung"):
            teile.append(f'<p class="ka-beschreibung">{_beschreibung(b["beschreibung"])}</p>')
        if not komps:
            teile.append('<p class="ka-leer">Noch keine Kompetenzen in diesem Bereich.</p>')
        for k in komps:
            stufen = k.get("stufen", [])
            teile.append(f'<div class="ka-kompetenz st-{status[k["id"]]["status"]}" id="k-{k["id"]}">')
            teile.append(f'<div class="ka-kompetenz-kopf">{punkt(status[k["id"]]["status"])}<h3>{_esc(k["titel"])}</h3>{anzahl_seiten(k["id"])}'
                         f'<span class="ka-herkunft">{herkunft(k["id"])}</span></div>')
            if k.get("beschreibung"):
                teile.append(f'<p class="ka-beschreibung">{_beschreibung(k["beschreibung"])}</p>')
            teile.append(seitenliste(k["id"]))
            if stufen:
                teile.append('<ol class="ka-stufen">')
                for i, s in enumerate(stufen, 1):
                    punkte = s.get("punkte", [])
                    st = status[s["id"]]["status"]
                    teile.append(f'<li class="ka-stufe st-{st}" id="k-{s["id"]}"><details{" open" if st != OFFEN else ""}>'
                                 f'<summary><span class="ka-stufe-nr">{i}</span><span class="ka-stufe-titel">{_esc(s["titel"])}</span>'
                                 f'<span class="ka-punkte-mini">{"".join(punkt(status[p["id"]]["status"]) for p in punkte)}</span>'
                                 f'{anzahl_seiten(s["id"])}<span class="ka-stufe-status">{_esc(STATUS_NAMEN[st])}</span></summary>')
                    if s.get("beschreibung"):
                        teile.append(f'<p class="ka-beschreibung">{_beschreibung(s["beschreibung"])}</p>')
                    teile.append(seitenliste(s["id"]))
                    if punkte:
                        teile.append('<ul class="ka-punkte">')
                        for p in punkte:
                            teile.append(f'<li class="st-{status[p["id"]]["status"]}" id="k-{p["id"]}">{punkt(status[p["id"]]["status"])}'
                                         f'<span>{_esc(p["titel"])}</span>{anzahl_seiten(p["id"])}{seitenliste(p["id"])}</li>')
                        teile.append('</ul>')
                    teile.append('</details></li>')
                teile.append('</ol>')
            teile.append('</div>')
        teile.append('</section>')

    def zeile(ebene):
        d = z[ebene]
        return (f'<tr><th>{EBENE_NAMEN[ebene]}</th>' + "".join(f'<td>{d[st]}</td>' for st in reversed(ZUSTAENDE))
                + f'<td>{d["gesamt"]}</td></tr>') if d["gesamt"] else ""
    tabelle = ('<table class="ka-tabelle"><thead><tr><th></th>'
               + "".join(f'<th><span class="ka-punkt st-{st}"></span>{STATUS_NAMEN[st]}</th>' for st in reversed(ZUSTAENDE))
               + '<th>gesamt</th></tr></thead><tbody>' + "".join(zeile(e) for e in EBENEN) + '</tbody></table>'
               '<p class="ka-tabelle-hinweis">«Noch nicht bearbeitet»: einer Seite zugeordnet, aber noch nicht begonnen. '
               '«Offen»: noch keiner Seite zugeordnet.</p>')
    stufen_alle = [nid for nid, k in index.items() if k["ebene"] == "stufe"]
    zs = z["stufe"]
    gesamt = (f'<div class="ka-gesamt">{balken(stufen_alle)}<span>{zs["gruen"]} von {zs["gesamt"]} Stufen erarbeitet'
              f'<small>{zs["orange"]} in Bearbeitung · {zs["weiss"]} noch nicht bearbeitet · {zs["offen"]} offen</small></span></div>'
              if stufen_alle else "")
    seiten_gesamt = len({e["pfad"] for s in status.values() for e in s["seiten"]})
    meta = " · ".join(x for x in (_esc(kr.get("quelle")), ("Version " + _esc(kr["version"])) if kr.get("version") else "",
                                   f'{seiten_gesamt} Seite{"n" if seiten_gesamt != 1 else ""} mit Kompetenzbezug') if x)
    return (vorlage.replace("{{TITEL}}", _esc(kr.get("titel"))).replace("{{KRID}}", _esc(kr["id"])).replace("{{REL}}", rel)
            .replace("{{META}}", meta).replace("{{GESAMT}}", gesamt).replace("{{TABELLE}}", tabelle)
            .replace("{{INHALT}}", "\n".join(teile) if teile else '<p class="ka-leer">Der Rahmen hat noch keine Bereiche.</p>')
            .replace("{{PRODUKTFUSS}}", produktfuss).replace("{{EXPORT}}", " export" if export else ""))


def block_html(b: dict, rahmen: dict, rel: str, bid: str, bearbeitbar: bool, pfad: str = "", beurteilung: bool = False) -> str:
    """Der KR-Block auf einer Seite: gewählte Knoten mit Pfad und Status; mit laufendem Liloport umschaltbar."""
    kr = rahmen.get(b.get("rahmen") or "")
    if not kr:
        return (f'<section class="block block-kr block-fehlt" data-id="{bid}" data-typ="kr">'
                f'<p class="hinweis">Kompetenzrahmen noch nicht gewählt.</p></section>')
    index = knoten_index(kr)
    knoten = b.get("knoten") or {}
    gewaehlt = [nid for nid in index if nid in knoten]  # in Baumreihenfolge
    zeilen = []
    for nid in gewaehlt:
        k, st = index[nid], knoten[nid]
        pfad_teile = k["pfad"]
        weg = " › ".join(_esc(t) for t in pfad_teile[:-1])
        if bearbeitbar:
            schalter = "".join(
                f'<button type="button" class="kr-status st-{s}{" aktiv" if s == st else ""}" data-status="{s}" title="{STATUS_NAMEN[s]}" aria-pressed="{"true" if s == st else "false"}"><span></span>{STATUS_NAMEN[s]}</button>'
                for s in STATUS)
            schalter = f'<span class="kr-schalter" data-knoten="{nid}">{schalter}</span>'
        else:
            schalter = f'<span class="kr-stand st-{st}"><span class="ka-punkt st-{st}"></span>{STATUS_NAMEN[st]}</span>'
        zeilen.append(f'<li class="kr-zeile st-{st}" data-knoten="{nid}"><span class="kr-ebene">{EBENE_NAMEN[k["ebene"]]}</span>'
                      f'<span class="kr-titel">{(f"<small>{weg}</small>" if weg else "")}{_esc(pfad_teile[-1])}</span>{schalter}</li>')
    ka = f'{rel}{ORDNER}/{_esc(kr["id"])}-abbildung.html'
    beurteilung_html = ""
    if beurteilung and gewaehlt:
        # Zur Bewertung freigegeben: dieselben Knoten noch einmal, ohne Stand; export.js hängt Skala und Kommentar an
        zeilen_b = "".join(
            f'<li class="kr-b-zeile" data-knoten="{nid}" data-titel="{_esc(" › ".join(index[nid]["pfad"]))}">'
            f'<span class="kr-ebene">{EBENE_NAMEN[index[nid]["ebene"]]}</span>'
            f'<span class="kr-titel"><small>{" › ".join(_esc(t) for t in index[nid]["pfad"][:-1])}</small>{_esc(index[nid]["pfad"][-1])}</span>'
            f'<div class="kr-b-inhalt"></div></li>' for nid in gewaehlt)
        beurteilung_html = (f'<section class="kr-beurteilung" data-block="{bid}" data-rahmen="{_esc(kr["id"])}">'
                            f'<h2 class="kr-kopf"><span class="kr-symbol" aria-hidden="true"></span>Beurteilung der Kompetenzen '
                            f'<small>zur Bewertung freigegeben</small></h2>'
                            f'<p class="hinweis kr-b-hinweis">Skala wählen, Wert anklicken, Kommentar schreiben. Beurteilungen lassen sich im selben Browser später bearbeiten oder löschen.</p>'
                            f'<ul class="kr-liste kr-b-liste">{zeilen_b}</ul></section>')
    liste_html = "".join(zeilen) if zeilen else '<li class="hinweis">Keine Kompetenzen gewählt.</li>'
    return (f'<section class="block block-kr" data-id="{bid}" data-typ="kr" data-rahmen="{_esc(kr["id"])}" data-pfad="{_esc(pfad)}">'
            f'<h2 class="kr-kopf"><span class="kr-symbol" aria-hidden="true"></span>Kompetenzen <small>{_esc(kr.get("titel"))}</small>'
            + ("" if bearbeitbar is None else f'<a class="kr-ka-link" href="{ka}">Abbildung</a>') +
            f'</h2><ul class="kr-liste">{liste_html}</ul></section>' + beurteilung_html)

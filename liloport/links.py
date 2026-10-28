"""Interne Links (lp:pfad), Rückverweise und Fussnoten.

Interne Links werden in den Seiten-JSON als href="lp:ordner/slug" gespeichert, nicht als relativer Pfad.
So bleiben sie gültig, wenn ein Verzeichnis umbenannt wird, und lassen sich beim Rendern für jede
Ausgabe passend auflösen: lokal relativ zur Seite, im Export auf den Zufallsnamen der Zielseite oder –
wenn die Zielseite nicht mit exportiert wird – als einfacher Text.
"""
import html
import re

LP_RE = re.compile(r'href="lp:([^"#]*)(#[^"]*)?"')
FUSSNOTE_RE = re.compile(r'<span class="fussnote">(.*?)</span>', re.S)


def _bloecke(bloecke):
    for b in bloecke or []:
        if isinstance(b, dict):
            yield b
            if b.get("typ") == "spalten":
                for sp in b.get("spalten") or []:
                    yield from _bloecke(sp)


def ziele(seite: dict) -> set:
    """Alle Seitenpfade, auf die eine Seite intern verlinkt (Text, HTML, Buttons)."""
    gefunden = set()
    for b in _bloecke(seite.get("bloecke")):
        if b.get("typ") in ("text", "html"):
            gefunden.update(m.group(1) for m in LP_RE.finditer(b.get("html") or ""))
        if b.get("typ") == "button" and str(b.get("ziel") or "").startswith("lp:"):
            gefunden.add(b["ziel"][3:].split("#", 1)[0])
    return gefunden


def rueckverweise(store, site=None, alle=None) -> dict:
    """{zielpfad: [(pfad, titel), …]} über alle Seiten (alle: schon geladene store.alle_seiten())."""
    ergebnis = {}
    for _v, pfad, seite in (alle if alle is not None else store.alle_seiten(site)):
        for ziel in sorted(ziele(seite)):
            if ziel != pfad:
                ergebnis.setdefault(ziel, []).append((pfad, seite.get("titel", pfad)))
    return ergebnis


def pfade_umbenennen(store, alt: str, neu: str) -> int:
    """Nach dem Umbenennen eines Verzeichnisses oder Verschieben einer Seite: lp:alt… → lp:neu… in allen Seiten."""
    geaendert = 0

    def ersetzen(text):
        # alt = Verzeichnis (dann folgt «/») oder alt = Seite (dann folgt «"», «#» oder Ende)
        return re.sub(r'lp:' + re.escape(alt) + r'(?=[/"#]|$)', 'lp:' + neu, text)

    for _v, pfad, seite in store.alle_seiten():
        vorher = repr(seite.get("bloecke"))
        for b in _bloecke(seite.get("bloecke")):
            if b.get("typ") in ("text", "html") and "lp:" in (b.get("html") or ""):
                b["html"] = ersetzen(b["html"])
            if b.get("typ") == "button" and str(b.get("ziel") or "").startswith("lp:"):
                b["ziel"] = ersetzen(b["ziel"])
        if repr(seite.get("bloecke")) != vorher:
            store.seite_speichern(pfad, seite)
            geaendert += 1
    return geaendert


def aufloesen(text: str, ziel_fuer) -> str:
    """Ersetzt href="lp:pfad" durch ziel_fuer(pfad); None macht aus dem Link einen markierten Text."""
    def ersetzen(m):
        ziel = ziel_fuer(m.group(1))
        if ziel is None:
            return 'data-link-fehlt="1" title="Diese Seite ist hier nicht verfügbar"'
        return f'href="{html.escape(ziel, quote=True)}{m.group(2) or ""}"'
    text = LP_RE.sub(ersetzen, text)
    # <a data-link-fehlt…>Text</a> → <span class="link-fehlt">Text</span>
    return re.sub(r'<a data-link-fehlt="1" title="([^"]*)">(.*?)</a>',
                  r'<span class="link-fehlt" title="\1">\2</span>', text, flags=re.S)


def ziel_aufloesen(ziel: str, ziel_fuer) -> str:
    """Wie aufloesen(), aber für das Ziel eines Buttons; leer, wenn die Seite fehlt."""
    if not str(ziel or "").startswith("lp:"):
        return ziel
    pfad, _, anker = ziel[3:].partition("#")
    neu = ziel_fuer(pfad)
    return "" if neu is None else neu + ("#" + anker if anker else "")


def fussnoten(text: str) -> str:
    """Nummeriert <span class="fussnote">…</span> durch und hängt die Liste der Fussnoten an."""
    noten = []

    def ersetzen(m):
        noten.append(m.group(1).strip())
        n = len(noten)
        return (f'<sup class="fn-ref" id="fnref-{n}"><a href="#fn-{n}" title="{html.escape(re.sub(r"<[^>]+>", "", m.group(1)).strip(), quote=True)}">'
                f'{n}</a></sup>')

    text = FUSSNOTE_RE.sub(ersetzen, text)
    if not noten:
        return text
    liste = "".join(f'<li id="fn-{i}">{n} <a class="fn-zurueck" href="#fnref-{i}" title="Zurück zum Text">↩</a></li>'
                    for i, n in enumerate(noten, 1))
    return text + f'\n<section class="fussnoten" aria-label="Fussnoten"><h2>Fussnoten</h2><ol>{liste}</ol></section>'

"""Slug-Regel: aus Titeln und Namen sichere Datei- und Ordnernamen machen."""
import re
import unicodedata

_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
MAX_LAENGE = 60


def slugify(text: str) -> str:
    """Macht aus beliebigem Text einen Slug: Kleinbuchstaben, a-z 0-9 und Bindestrich."""
    text = (text or "").strip().lower()
    for umlaut, ersatz in _UMLAUTE.items():
        text = text.replace(umlaut, ersatz)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    text = text[:MAX_LAENGE].rstrip("-")
    return text or "seite"


def eindeutig(slug: str, vorhandene) -> str:
    """Hängt -2, -3, … an, bis der Slug in `vorhandene` nicht mehr vorkommt."""
    vorhandene = set(vorhandene)
    if slug not in vorhandene:
        return slug
    zaehler = 2
    while f"{slug}-{zaehler}" in vorhandene:
        zaehler += 1
    return f"{slug}-{zaehler}"


def ist_slug(text: str) -> bool:
    """Prüft, ob ein Text bereits ein gültiger Slug ist."""
    return bool(text) and slugify(text) == text

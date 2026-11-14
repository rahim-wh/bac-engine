"""Theme atomisation: turns a raw `Chapitres / Thèmes` cell into atomic themes.

The dataset mixes several encodings of one cell:
  * Maths/SVT/Physique : "Suite; Matrice; Graphe"      (';' separated)
  * Philosophie        : "الأنا والغير / الحقيقة"       (' / ' separated)
  * Physique-Chimie    : "Chi: 1/Acide 2/Amides | Phy: 1/RC 2/Nucl" ('|' + numbered)
  * Par exercice       : "Ex1: QCM | Ex2: Suite"
  * Génie/Physique     : "Frein + engrenage + cotation" (' + ' separated)
  * Languages / French : a single atomic theme (never split on ':' or ',')
"""
import re
import unicodedata

_SPLIT = re.compile(r"\s*(?:;|\||\s/\s|\s\+\s)\s*")
_NUMBERED = re.compile(r"\s*\b\d\s*/\s*")           # "1/Acide 2/Amides"
_EX_PREFIX = re.compile(r"^\s*Ex\s*\d+(?:\s*-\s*\d+)?\s*:\s*", re.I)
_LABEL = re.compile(r"^\s*(?:Chi|Phy)\s*:\s*", re.I)  # discipline labels in Physique-Chimie
_NOISE_PAREN = re.compile(r"\s*\((?:doc|\d+)\)", re.I)
_EMPTY = {"", "(aucun chapitre coché)", "-", "—", "— (non renseigné)"}


def norm(s: str) -> str:
    """NFC-normalise and collapse whitespace."""
    s = unicodedata.normalize("NFC", str(s))
    return re.sub(r"\s+", " ", s).strip()


def atomize(cell: str) -> list[str]:
    """Return the ordered, de-duplicated list of atomic themes in a cell."""
    out: list[str] = []
    for part in _SPLIT.split(norm(cell)):
        part = _LABEL.sub("", _EX_PREFIX.sub("", part))
        pieces = _NUMBERED.split(part) if _NUMBERED.search(part) else [part]
        for p in pieces:
            p = norm(_NOISE_PAREN.sub("", p)).strip(" .,:")
            if p.lower() not in _EMPTY and p not in out:
                out.append(p)
    return out

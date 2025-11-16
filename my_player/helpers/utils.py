from __future__ import annotations

import re
import unicodedata


def title_case(s: str) -> str:
    """
    Basic title-case helper with some mild normalisation.
    """
    s = s.strip()
    if not s:
        return s
    # Fix underscores → spaces, normalize whitespace, and Title Case
    return re.sub(r"\s+", " ", s.replace("_", " ")).title()


def norm(s: str) -> str:
    """
    Normalise a string for fuzzy matching:
    - lowercase
    - strip accents
    - remove extra spaces
    """
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())

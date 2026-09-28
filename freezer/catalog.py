"""Tipi e unità: unica fonte di verità, inviata anche al telefono."""

# (codice, etichetta, mesi per la scadenza proposta in "Aggiungi"; None = nessuna proposta).
# `carne` è il vecchio tipo unico per la carne: il codice resta valido per i lotti già salvati
# e per le aggiunte ancora in coda sui telefoni offline, ma ora vuol dire "Altra carne".
CATEGORIES: list[tuple[str, str, int | None]] = [
    ("pollo_tacchino", "Pollo e tacchino", 6),
    ("manzo", "Manzo", 9),
    ("maiale", "Maiale", 6),
    ("carne", "Altra carne", 3),
    ("pesce", "Pesce", 3),
    ("verdure", "Verdure", 9),
    ("frutta", "Frutta", 9),
    ("sughi", "Sughi", 3),
    ("piatti_pronti", "Piatti pronti", 3),
    ("pane_pizza", "Pane e pizza", 3),
    ("dolci", "Dolci", 3),
    ("altro", "Altro", None),
]

UNITS: list[tuple[str, str, str]] = [
    ("pezzi", "pezzo", "pezzi"),
    ("buste", "busta", "buste"),
    ("porzioni", "porzione", "porzioni"),
    ("vaschette", "vaschetta", "vaschette"),
    ("barattoli_piccoli", "barattolo piccolo", "barattoli piccoli"),
    ("barattoli_grandi", "barattolo grande", "barattoli grandi"),
    ("grammi", "g", "g"),
]

CATEGORY_CODES = frozenset(code for code, _, _ in CATEGORIES)
UNIT_CODES = frozenset(code for code, _, _ in UNITS)
_UNIT_LABELS = {code: (singular, plural) for code, singular, plural in UNITS}


def catalog_json() -> dict:
    return {
        "categories": [
            {"code": code, "label": label, "months": months} for code, label, months in CATEGORIES
        ],
        "units": [
            {"code": code, "singular": singular, "plural": plural}
            for code, singular, plural in UNITS
        ],
    }


def format_quantity(quantity: int, unit: str) -> str:
    singular, plural = _UNIT_LABELS[unit]
    return f"{quantity} {singular if quantity == 1 else plural}"

"""Tipi e unità: unica fonte di verità, inviata anche al telefono."""

CATEGORIES: list[tuple[str, str]] = [
    ("carne", "Carne"),
    ("pesce", "Pesce"),
    ("verdure", "Verdure"),
    ("frutta", "Frutta"),
    ("sughi", "Sughi"),
    ("piatti_pronti", "Piatti pronti"),
    ("pane_pizza", "Pane e pizza"),
    ("dolci", "Dolci"),
    ("altro", "Altro"),
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

CATEGORY_CODES = frozenset(code for code, _ in CATEGORIES)
UNIT_CODES = frozenset(code for code, _, _ in UNITS)
_UNIT_LABELS = {code: (singular, plural) for code, singular, plural in UNITS}


def catalog_json() -> dict:
    return {
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES],
        "units": [
            {"code": code, "singular": singular, "plural": plural}
            for code, singular, plural in UNITS
        ],
    }


def format_quantity(quantity: int, unit: str) -> str:
    singular, plural = _UNIT_LABELS[unit]
    return f"{quantity} {singular if quantity == 1 else plural}"

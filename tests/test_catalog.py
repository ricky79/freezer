import pytest

from freezer.catalog import CATEGORY_CODES, UNIT_CODES, catalog_json, format_quantity


def test_catalog_contains_requested_codes():
    assert {"sughi", "pollo_tacchino", "manzo", "maiale"} <= CATEGORY_CODES
    assert {"barattoli_piccoli", "barattoli_grandi", "grammi"} <= UNIT_CODES
    assert len(CATEGORY_CODES) == 12
    assert len(UNIT_CODES) == 7


def test_catalog_json_shape():
    data = catalog_json()
    assert {"code": "manzo", "label": "Manzo", "months": 9} in data["categories"]
    assert {"code": "buste", "singular": "busta", "plural": "buste"} in data["units"]


def test_meat_types_come_first_with_legacy_carne_as_other_meat():
    # `carne` resta valido (lotti già salvati, code offline) ma ora vuol dire "Altra carne".
    categories = catalog_json()["categories"]
    assert [c["code"] for c in categories[:4]] == ["pollo_tacchino", "manzo", "maiale", "carne"]
    assert categories[3] == {"code": "carne", "label": "Altra carne", "months": 3}


def test_every_type_proposes_months_except_other():
    months = {c["code"]: c["months"] for c in catalog_json()["categories"]}
    assert months.pop("altro") is None
    assert all(isinstance(m, int) and m > 0 for m in months.values())


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (1, "buste", "1 busta"),
        (3, "buste", "3 buste"),
        (1, "barattoli_piccoli", "1 barattolo piccolo"),
        (2, "barattoli_grandi", "2 barattoli grandi"),
        (500, "grammi", "500 g"),
        (1, "grammi", "1 g"),
    ],
)
def test_format_quantity(quantity, unit, expected):
    assert format_quantity(quantity, unit) == expected

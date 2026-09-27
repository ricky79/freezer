import pytest

from freezer.catalog import CATEGORY_CODES, UNIT_CODES, catalog_json, format_quantity


def test_catalog_contains_requested_codes():
    assert "sughi" in CATEGORY_CODES
    assert {"barattoli_piccoli", "barattoli_grandi", "grammi"} <= UNIT_CODES
    assert len(CATEGORY_CODES) == 9
    assert len(UNIT_CODES) == 7


def test_catalog_json_shape():
    data = catalog_json()
    assert data["categories"][0] == {"code": "carne", "label": "Carne"}
    assert {"code": "buste", "singular": "busta", "plural": "buste"} in data["units"]


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

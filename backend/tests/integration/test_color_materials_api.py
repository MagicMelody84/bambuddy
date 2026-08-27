"""Integration tests for GET /api/v1/inventory/colors/materials — the distinct
material list per manufacturer.

Exists because /colors/search was the only way to answer "which materials does
this manufacturer offer", by fetching colour rows and collecting their material
values. That endpoint caps at 100 rows, so for a broad catalog the answer was
silently short: Bambu Lab's first 100 entries by colour name carry only 18
distinct materials, and anything appearing solely in later rows never reached
the client.

Regression guards:
 - The distinct list is complete even when the manufacturer has far more than
   the 100 colour rows /colors/search would return (the actual bug).
 - Values are distinct, sorted, and free of blank/NULL rows.
 - Manufacturer matching is contains + case-insensitive, the same rule
   /colors/search uses, so both answer consistently for the same input.
"""

import pytest
from httpx import AsyncClient

from backend.app.models.color_catalog import ColorCatalogEntry

MATERIALS_URL = "/api/v1/inventory/colors/materials"


async def _seed(db_session, entries):
    for kwargs in entries:
        db_session.add(ColorCatalogEntry(**kwargs))
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_empty_catalog(async_client: AsyncClient):
    """No catalog rows means an empty list, not an error."""
    response = await async_client.get(MATERIALS_URL)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_are_distinct_and_sorted(async_client: AsyncClient, db_session):
    await _seed(
        db_session,
        [
            {"manufacturer": "Bambu Lab", "color_name": "Jade White", "hex_color": "FFFFFF", "material": "PLA Basic"},
            {"manufacturer": "Bambu Lab", "color_name": "Black", "hex_color": "000000", "material": "PLA Basic"},
            {"manufacturer": "Bambu Lab", "color_name": "Ivory", "hex_color": "FFFFF0", "material": "ABS"},
        ],
    )
    response = await async_client.get(MATERIALS_URL, params={"manufacturer": "Bambu Lab"})
    assert response.status_code == 200
    assert response.json() == ["ABS", "PLA Basic"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_skip_null_and_blank(async_client: AsyncClient, db_session):
    """A catalog row without a usable material must not become an empty entry
    in a picker built from this list."""
    await _seed(
        db_session,
        [
            {"manufacturer": "Polymaker", "color_name": "A", "hex_color": "112233", "material": "PETG"},
            {"manufacturer": "Polymaker", "color_name": "B", "hex_color": "223344", "material": None},
            {"manufacturer": "Polymaker", "color_name": "C", "hex_color": "334455", "material": "   "},
        ],
    )
    response = await async_client.get(MATERIALS_URL, params={"manufacturer": "Polymaker"})
    assert response.status_code == 200
    assert response.json() == ["PETG"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_filter_is_contains_and_case_insensitive(async_client: AsyncClient, db_session):
    """Same matching rule as /colors/search, so a client can pass either
    endpoint the manufacturer string it got from /colors."""
    await _seed(
        db_session,
        [
            {"manufacturer": "Bambu Lab", "color_name": "A", "hex_color": "AABBCC", "material": "PLA Basic"},
            {"manufacturer": "Elegoo", "color_name": "B", "hex_color": "BBCCDD", "material": "PETG"},
        ],
    )
    response = await async_client.get(MATERIALS_URL, params={"manufacturer": "bambu"})
    assert response.status_code == 200
    assert response.json() == ["PLA Basic"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_without_manufacturer_covers_whole_catalog(async_client: AsyncClient, db_session):
    await _seed(
        db_session,
        [
            {"manufacturer": "Bambu Lab", "color_name": "A", "hex_color": "AABBCC", "material": "PLA Basic"},
            {"manufacturer": "Elegoo", "color_name": "B", "hex_color": "BBCCDD", "material": "PETG"},
        ],
    )
    response = await async_client.get(MATERIALS_URL)
    assert response.status_code == 200
    assert response.json() == ["PETG", "PLA Basic"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_materials_complete_beyond_the_search_row_cap(async_client: AsyncClient, db_session):
    """The reason this endpoint exists.

    Seeds 120 colour rows for one manufacturer where the only row carrying
    "TPU" sorts last by colour name, i.e. past /colors/search's 100-row cap.
    Deriving materials from that endpoint would miss it; this one must not.
    """
    entries = [
        {"manufacturer": "Bambu Lab", "color_name": f"Colour {i:03d}", "hex_color": f"{i:06X}", "material": "PLA Basic"}
        for i in range(119)
    ]
    entries.append({"manufacturer": "Bambu Lab", "color_name": "ZZZ Last", "hex_color": "FEFEFE", "material": "TPU"})
    await _seed(db_session, entries)

    search = await async_client.get(
        "/api/v1/inventory/colors/search", params={"manufacturer": "Bambu Lab"}
    )
    assert search.status_code == 200
    search_materials = {row["material"] for row in search.json()}
    assert "TPU" not in search_materials, "cap moved; this test's premise no longer holds"

    response = await async_client.get(MATERIALS_URL, params={"manufacturer": "Bambu Lab"})
    assert response.status_code == 200
    assert response.json() == ["PLA Basic", "TPU"]

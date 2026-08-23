"""Custom-field round-trip through the Spoolman spool mapping.

Values live in Spoolman's `extra` dict as JSON typed to the field, under the
`bambu_cf_` prefix. The read side flattens them back to the canonical string
Bambuddy stores, and must survive whatever is actually there — including entries
written by other tools.
"""

from __future__ import annotations

import json

from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool


def _spool(extra: dict) -> dict:
    return {
        "id": 7,
        "filament": {"material": "PLA", "name": "PLA Basic", "weight": 1000},
        "extra": extra,
    }


def test_prefixed_extra_keys_become_custom_fields():
    mapped = _map_spoolman_spool(_spool({"bambu_cf_kunde": json.dumps("Acme")}))
    assert mapped["custom_fields"] == {"kunde": "Acme"}


def test_unprefixed_keys_are_ignored():
    mapped = _map_spoolman_spool(
        _spool({"bambu_color_name": json.dumps("Jade White"), "bambu_cf_charge": json.dumps("B")})
    )
    assert mapped["custom_fields"] == {"charge": "B"}


def test_cleared_value_maps_to_none():
    mapped = _map_spoolman_spool(_spool({"bambu_cf_kunde": json.dumps("")}))
    assert mapped["custom_fields"] == {"kunde": None}


def test_explicit_null_maps_to_none():
    mapped = _map_spoolman_spool(_spool({"bambu_cf_kunde": "null"}))
    assert mapped["custom_fields"] == {"kunde": None}


def test_typed_values_flatten_to_their_canonical_string():
    mapped = _map_spoolman_spool(
        _spool(
            {
                "bambu_cf_lagen": "12",
                "bambu_cf_laenge": "1.5",
                "bambu_cf_trocken": "true",
                "bambu_cf_temp": "[200, 230]",
                "bambu_cf_geoeffnet": json.dumps("2026-08-23T14:30:00"),
            }
        )
    )
    assert mapped["custom_fields"] == {
        "lagen": "12",
        "laenge": "1.5",
        "trocken": "true",
        "temp": "200,230",
        "geoeffnet": "2026-08-23T14:30:00",
    }


def test_bare_prefix_without_a_key_is_skipped():
    mapped = _map_spoolman_spool(_spool({"bambu_cf_": json.dumps("orphan")}))
    assert mapped["custom_fields"] == {}


def test_malformed_json_does_not_raise():
    # A single bad entry must not 500 the whole inventory list — same hardening
    # as the unconstrained rgba on SpoolResponse.
    mapped = _map_spoolman_spool(_spool({"bambu_cf_kunde": "{not json", "bambu_cf_charge": 42}))
    assert mapped["custom_fields"] == {"kunde": "{not json", "charge": "42"}


def test_no_extra_yields_empty_dict():
    assert _map_spoolman_spool(_spool({}))["custom_fields"] == {}

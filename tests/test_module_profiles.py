"""Vehicle profile loading and CBF enrichment stay data-driven."""

from __future__ import annotations

import json

from backend.mb import modules


def test_default_profile_is_loaded_into_runtime_module_registry():
    info = modules.profile_info()
    assert info["id"] == "w221-x164"
    assert info["error"] is None
    assert info["module_count"] == len(modules.MODULES)
    assert modules.MODULES_BY_ID["me97"]["group"] == "powertrain"
    assert modules.MODULES_BY_ID["ezs"]["cbf"] == "EZS164"
    assert modules.simulator_profile()["capture"]
    assert modules.gateway_probes()["zgw"]["requests"]
    assert modules.gateway_info_spec()["target"] == "zgw"


def test_only_packaged_profiles_can_be_selected():
    packaged = modules.available_profiles()

    assert any(profile["id"] == "w221-x164" for profile in packaged)
    assert modules.select_profile("not-a-profile") is None


def test_custom_profile_is_loaded_without_python_changes(tmp_path):
    path = tmp_path / "bench.json"
    path.write_text(json.dumps({
        "id": "bench",
        "label": "Bench ECU",
        "modules": [{"id": "engine", "cbf": "TEST_ECU", "chassis": ["BENCH"]}],
    }), encoding="utf-8")

    profile = modules._load_profile(path)

    assert profile["error"] is None
    assert profile["id"] == "bench"
    assert profile["modules"] == [
        {"id": "engine", "cbf": "TEST_ECU", "chassis": ["BENCH"]},
    ]


def test_invalid_profile_is_reported_without_crashing(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"modules": [{"id": "duplicate", "cbf": "A"}, '
                    '{"id": "duplicate", "cbf": "B"}]}', encoding="utf-8")

    profile = modules._load_profile(path)

    assert profile["modules"] == []
    assert "duplicate module id" in profile["error"]

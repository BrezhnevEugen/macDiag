from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import build_measure_db
import measure_diag_coverage
import measure_layout_check
import measure_unmatched_jobs


def test_insert_service_output_preserves_explicit_empty_formula():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(build_measure_db.SCHEMA)
        build_measure_db._insert_service_output(
            conn,
            "CEPC_MFA",
            "DT_BOOL",
            {
                "presentation": "PRES_bool_1bit_inverted",
                "presentation_raw_type": "ubyte",
                "presentation_byte_len": 1,
                "presentation_unit": "",
                "presentation_scale_kind": "enum",
                "presentation_formula": "",
                "presentation_meta_source": "cbf_presentation_enum_record",
                "presentation_value_map": [
                    {"low": 0, "high": 0, "label": "Ja"},
                    {"low": 1, "high": 1, "label": "Nein"},
                ],
                "presentation_bit_pos": 24,
                "presentation_bit_len": 1,
                "presentation_byte_offset": 3,
                "presentation_bit_offset": 0,
            },
        )
        row = conn.execute(
            """
            SELECT raw_type, byte_len, scale_kind, formula, value_map_json,
                   bit_pos, bit_len, byte_offset, bit_offset, source
            FROM service_outputs
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == (
        "ubyte",
        1,
        "enum",
        "",
        '[{"low": 0, "high": 0, "label": "Ja"}, {"low": 1, "high": 1, "label": "Nein"}]',
        24,
        1,
        3,
        0,
        "cbf_diag_inline+cbf_presentation_enum_record",
    )


def test_insert_service_output_infers_linear_raw_type_from_layout():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(build_measure_db.SCHEMA)
        build_measure_db._insert_service_output(
            conn,
            "CRD3_DEV",
            "DT_ENGINE_SPEED",
            {
                "presentation": "PRES_EngN",
                "presentation_raw_type": "",
                "presentation_byte_len": 1,
                "presentation_unit": "rpm",
                "presentation_scale_kind": "linear",
                "presentation_formula": "x * 0.5",
                "presentation_meta_source": "cbf_presentation_record",
                "presentation_bit_pos": 24,
                "presentation_bit_len": 16,
                "presentation_byte_offset": 3,
                "presentation_bit_offset": 0,
            },
        )
        build_measure_db._insert_service_output(
            conn,
            "CRD3_DEV",
            "DT_TEMP",
            {
                "presentation": "PRES_Temp_Cels",
                "presentation_raw_type": "",
                "presentation_byte_len": 0,
                "presentation_unit": "deg C",
                "presentation_scale_kind": "",
                "presentation_formula": "",
                "presentation_meta_source": "presentation_name",
                "presentation_bit_pos": 24,
                "presentation_bit_len": 16,
                "presentation_byte_offset": 3,
                "presentation_bit_offset": 0,
            },
        )
        rows = conn.execute(
            """
            SELECT qualifier, raw_type, byte_len, unit, scale_kind, formula, bit_len
            FROM service_outputs
            ORDER BY qualifier
            """
        ).fetchall()
    finally:
        conn.close()
    assert rows == [
        ("DT_ENGINE_SPEED", "uword", 2, "rpm", "linear", "x * 0.5", 16),
        ("DT_TEMP", "uword", 2, "deg C", "", "", 16),
    ]


def test_build_measure_db_and_read_from_backend(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    out = tmp_path / "measurements.sqlite"
    (mwg_dir / "VediamoData" / "CRD3_DEV").mkdir(parents=True)
    (mwg_dir / "VediamoData" / "CRD3_DEV" / "dpf.mwg").write_text(
        ";D:\\Vediamodaten\\crd3_dev\\CRD3_DPF-Wiegen_SB.mwg\n"
        ";System:crd3_dev\n"
        "[Entries]\n"
        "Count=2\n"
        "Service1=CRD3_DEV:DT_6043_P_T_Dpf_soot_mass\n"
        "Service2=CRD3_DEV:DT_604B_P_T_Dpf_load_percent_wgh\n",
        encoding="latin-1",
    )

    stats = build_measure_db.build(vsg_dir, mwg_dir, out)

    assert stats["groups"] == 1
    assert stats["mwg"] == 1
    assert out.exists()
    with sqlite3.connect(out) as db:
        schema_version = db.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        translation_count = db.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    assert schema_version == "17"
    assert translation_count == 3

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()

    groups = measurements.groups_for("CRD3_DEV", "ru")
    db_groups = [g for g in groups["measurement"] if g.get("source") == "mwg"]
    assert len(db_groups) == 1
    assert db_groups[0]["localization_key"].startswith("measure.group.")

    path = db_groups[0]["path"]
    g = measurements.get_group(path, "ru")
    assert g and g["source"] == "mwg"
    assert g["localization_key"].startswith("measure.group.")
    assert [s["job"] for s in g["services"]] == [
        "DT_6043_P_T_Dpf_soot_mass",
        "DT_604B_P_T_Dpf_load_percent_wgh",
    ]
    assert all(s["localization_key"].startswith("measure.service.") for s in g["services"])


def test_build_measure_db_imports_reference_links(tmp_path: Path):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    refs = tmp_path / "can_bookmarks.json"
    out = tmp_path / "measurements.sqlite"
    refs.write_text(
        json.dumps({
            "bookmarks": [
                {
                    "title": "Mercedes-Benz W164. Общая сеть обмена данными",
                    "url": "https://example.test/w164/network",
                    "domain": "example.test",
                    "tags": ["mercedes-network"],
                    "folders": ["Мерс / x164"],
                    "sources": ["Закладки.html"],
                    "attrs": {"add_date": "123"},
                },
                {
                    "title": "CAN Gateway Mercedes E 211",
                    "url": "https://canhacker.test/e211",
                    "domain": "canhacker.test",
                    "tags": ["can", "gateway", "mercedes-network"],
                    "folders": ["Мерс"],
                    "sources": ["Закладки.html"],
                },
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    stats = build_measure_db.build(vsg_dir, mwg_dir, out, references_json=refs)

    assert stats["reference_links"] == 2
    with sqlite3.connect(out) as db:
        rows = db.execute(
            """
            SELECT url, title, domain, tags_json, folders_json, vehicle_hints_json, source_file
            FROM reference_links ORDER BY domain
            """
        ).fetchall()
        meta_ref = db.execute(
            "SELECT value FROM meta WHERE key = 'references_json'"
        ).fetchone()[0]
    assert meta_ref == str(refs)
    assert rows == [
        (
            "https://canhacker.test/e211",
            "CAN Gateway Mercedes E 211",
            "canhacker.test",
            '["can", "gateway", "mercedes-network"]',
            '["Мерс"]',
            '["E211"]',
            str(refs),
        ),
        (
            "https://example.test/w164/network",
            "Mercedes-Benz W164. Общая сеть обмена данными",
            "example.test",
            '["mercedes-network"]',
            '["Мерс / x164"]',
            '["W164", "X164"]',
            str(refs),
        ),
    ]


def test_build_measure_db_imports_can_examples(tmp_path: Path):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    examples = tmp_path / "can_examples.json"
    out = tmp_path / "measurements.sqlite"
    examples.write_text(
        json.dumps({
            "examples": [
                {
                    "id": "w211-cluster-09e",
                    "source_url": "https://canhacker.test/e211",
                    "source_title": "CAN Gateway Mercedes E 211",
                    "vehicle": "Mercedes-Benz E 211",
                    "body": "W211",
                    "bus": "slow interior CAN",
                    "speed_kbit_s": 83.333,
                    "can_id": "0x09E",
                    "dlc": 7,
                    "data_hex": "0081D9B32C05E8",
                    "source_node": "instrument cluster",
                    "target_node": "EIS / ignition lock",
                    "direction": "cluster to EIS",
                    "payload_meaning": "distance payload",
                    "tags": ["mercedes-network", "gateway", "frame"],
                    "confidence": "reviewed",
                    "safety_note": "passive documentation only",
                    "notes": "cluster replacement context",
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    stats = build_measure_db.build(vsg_dir, mwg_dir, out, can_examples_json=examples)

    assert stats["can_examples"] == 1
    with sqlite3.connect(out) as db:
        row = db.execute(
            """
            SELECT id, body, speed_kbit_s, can_id, dlc, data_hex, source_node,
                   target_node, payload_meaning, tags_json, safety_note
            FROM can_examples
            """
        ).fetchone()
        meta_examples = db.execute(
            "SELECT value FROM meta WHERE key = 'can_examples_json'"
        ).fetchone()[0]
    assert meta_examples == str(examples)
    assert row == (
        "w211-cluster-09e",
        "W211",
        83.333,
        "0x09E",
        7,
        "0081D9B32C05E8",
        "instrument cluster",
        "EIS / ignition lock",
        "distance payload",
        '["mercedes-network", "gateway", "frame"]',
        "passive documentation only",
    )


def test_reference_links_api_filters_local_bookmarks(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    refs = tmp_path / "can_bookmarks.json"
    out = tmp_path / "measurements.sqlite"
    refs.write_text(
        json.dumps({
            "bookmarks": [
                {
                    "title": "Mercedes-Benz W164. Общая сеть обмена данными",
                    "url": "https://example.test/w164/network",
                    "domain": "example.test",
                    "tags": ["mercedes-network"],
                    "folders": ["Мерс / x164"],
                    "sources": ["Закладки.html"],
                },
                {
                    "title": "CAN Gateway Mercedes E 211",
                    "url": "https://canhacker.test/e211",
                    "domain": "canhacker.test",
                    "tags": ["can", "gateway", "mercedes-network"],
                    "folders": ["Мерс"],
                    "sources": ["Закладки.html"],
                },
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    build_measure_db.build(vsg_dir, mwg_dir, out, references_json=refs)

    from backend.mb import measurements
    import backend.main as main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    measurements._db_reference_links.cache_clear()
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()

    with TestClient(main.app) as client:
        stats = client.get("/api/references/stats").json()
        assert stats["total"] == 2
        assert stats["tags"]["mercedes-network"] == 2
        assert stats["vehicles"] == {"E211": 1, "W164": 1, "X164": 1}

        network = client.get("/api/references", params={"tag": "mercedes-network"}).json()
        assert network["total"] == 2

        x164 = client.get("/api/references", params={"vehicle": "X164"}).json()
        assert x164["total"] == 1
        assert x164["rows"][0]["title"] == "Mercedes-Benz W164. Общая сеть обмена данными"

        gateway = client.get("/api/references", params={"q": "gateway"}).json()
        assert gateway["total"] == 1
        assert gateway["rows"][0]["vehicle_hints"] == ["E211"]


def test_can_examples_api_filters_reviewed_facts(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    examples = tmp_path / "can_examples.json"
    out = tmp_path / "measurements.sqlite"
    examples.write_text(
        json.dumps({
            "examples": [
                {
                    "id": "w211-cluster-09e",
                    "source_url": "https://canhacker.test/e211",
                    "source_title": "CAN Gateway Mercedes E 211",
                    "vehicle": "Mercedes-Benz E 211",
                    "body": "W211",
                    "bus": "slow interior CAN",
                    "speed_kbit_s": 83.333,
                    "can_id": "0x09E",
                    "dlc": 7,
                    "data_hex": "0081D9B32C05E8",
                    "source_node": "instrument cluster",
                    "target_node": "EIS / ignition lock",
                    "direction": "cluster to EIS",
                    "payload_meaning": "distance payload",
                    "tags": ["mercedes-network", "gateway", "frame"],
                    "confidence": "reviewed",
                    "safety_note": "passive documentation only",
                    "notes": "cluster replacement context",
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    build_measure_db.build(vsg_dir, mwg_dir, out, can_examples_json=examples)

    from backend.mb import measurements
    import backend.main as main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    measurements._db_can_examples.cache_clear()
    measurements._db_reference_links.cache_clear()

    with TestClient(main.app) as client:
        stats = client.get("/api/can/examples/stats").json()
        assert stats["total"] == 1
        assert stats["vehicles"] == {"W211": 1}
        assert stats["can_ids"] == {"0x09E": 1}

        by_vehicle = client.get("/api/can/examples", params={"vehicle": "W211"}).json()
        assert by_vehicle["total"] == 1
        assert by_vehicle["rows"][0]["speed_kbit_s"] == 83.333

        by_id = client.get("/api/can/examples", params={"can_id": "0x09E"}).json()
        assert by_id["total"] == 1
        assert by_id["rows"][0]["source_node"] == "instrument cluster"

        by_q = client.get("/api/can/examples", params={"q": "cluster replacement"}).json()
        assert by_q["total"] == 1


def test_measure_db_maps_cbf_diag_services(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    cbf_dir = tmp_path / "cbf"
    out = tmp_path / "measurements.sqlite"
    (mwg_dir / "VediamoData" / "CRD3_DEV").mkdir(parents=True)
    (cbf_dir).mkdir()
    (cbf_dir / "CRD3_DEV.CBF").write_bytes(b"fake")
    (mwg_dir / "VediamoData" / "CRD3_DEV" / "dpf.mwg").write_text(
        ";D:\\Vediamodaten\\crd3_dev\\CRD3_DPF-Wiegen_SB.mwg\n"
        ";System:crd3_dev\n"
        "[Entries]\n"
        "Count=2\n"
        "Service1=CRD3_DEV:DT_6043_P_T_Dpf_soot_mass\n"
        "Service2=CRD3_DEV:DT_604B_P_T_Dpf_load_percent_wgh\n",
        encoding="latin-1",
    )

    def fake_diag_catalog(path: Path) -> dict:
        assert path.name == "CRD3_DEV.CBF"
        return {
            "DT_6043_P_T_Dpf_soot_mass": {
                "request": "220123",
                "sec_level": 3,
                "svc_type": 1,
                "name": "Soot mass",
                "description": "DPF soot mass",
                "presentation": "PRES_DOP_PRESENTATION_Nein_Ja",
                "presentation_raw_type": "ubyte",
                "presentation_byte_len": 1,
                "presentation_scale_kind": "enum",
                "presentation_formula": "",
                "presentation_meta_source": "cbf_presentation_enum_record",
                "presentation_value_map": [
                    {"low": 0, "high": 0, "label": "Nein"},
                    {"low": 1, "high": 1, "label": "Ja"},
                ],
                "presentation_bit_pos": 24,
                "presentation_bit_len": 8,
                "presentation_byte_offset": 3,
                "presentation_bit_offset": 0,
            },
            "DT_604B_P_T_Dpf_load_percent_wgh": {
                "request": "2105",
                "sec_level": 0,
                "svc_type": 1,
                "name": "DPF load",
                "description": "DPF load percent",
                "presentation": "PRES_CM_0184_BIN7_BAR_UWORD",
                "presentation_raw_type": "uword",
                "presentation_byte_len": 2,
                "presentation_bit_pos": 16,
                "presentation_bit_len": 16,
                "presentation_byte_offset": 2,
                "presentation_bit_offset": 0,
            },
        }

    monkeypatch.setattr(build_measure_db.caesar_vc, "diag_catalog", fake_diag_catalog)
    stats = build_measure_db.build(vsg_dir, mwg_dir, out, cbf_dir=cbf_dir)

    assert stats["diag_ecus"] == 1
    assert stats["diag_services"] == 2
    assert stats["diag_matched_services"] == 2
    assert stats["diag_exact_matched_services"] == 2
    assert stats["diag_normalized_matched_services"] == 0
    assert stats["diag_unmatched_services"] == 0
    assert stats["output_presentations"] == 2
    assert stats["output_raw_types"] == 2
    assert stats["output_units"] == 1
    assert stats["output_formulas"] == 1
    assert stats["output_value_maps"] == 1
    coverage_rows = measure_diag_coverage.coverage_rows(out, ["CRD3_DEV"])
    assert coverage_rows == [{
        "ecu": "CRD3_DEV",
        "service_rows": 2,
        "matched_rows": 2,
        "exact_rows": 2,
        "normalized_rows": 0,
        "output_rows": 2,
        "raw_type_rows": 2,
        "unit_rows": 1,
        "formula_rows": 1,
        "missing_rows": 0,
        "distinct_jobs": 2,
        "matched_jobs": 2,
        "missing_jobs": 0,
        "coverage_pct": 100.0,
    }]
    with sqlite3.connect(out) as db:
        rows = db.execute(
            """
            SELECT qualifier, request_hex, sid, sid_hex, identifier_type, identifier_hex,
                   sec_level, description
            FROM diag_services ORDER BY qualifier
            """
        ).fetchall()
        matches = db.execute(
            """
            SELECT job, qualifier, match_kind, rule, confidence
            FROM diag_service_matches ORDER BY job
            """
        ).fetchall()
        outputs = db.execute(
            """
            SELECT qualifier, presentation, raw_type, byte_len, unit, scale_kind,
                   formula, value_map_json, bit_pos, bit_len, byte_offset, bit_offset,
                   source
            FROM service_outputs ORDER BY qualifier
            """
        ).fetchall()
    assert rows == [
        ("DT_6043_P_T_Dpf_soot_mass", "220123", 0x22, "22", "did", "0123", 3, "DPF soot mass"),
        ("DT_604B_P_T_Dpf_load_percent_wgh", "2105", 0x21, "21", "lid", "05", 0, "DPF load percent"),
    ]
    assert matches == [
        ("DT_6043_P_T_Dpf_soot_mass", "DT_6043_P_T_Dpf_soot_mass", "exact", "exact", 1.0),
        ("DT_604B_P_T_Dpf_load_percent_wgh", "DT_604B_P_T_Dpf_load_percent_wgh", "exact", "exact", 1.0),
    ]
    assert outputs == [
        ("DT_6043_P_T_Dpf_soot_mass", "PRES_DOP_PRESENTATION_Nein_Ja",
         "ubyte", 1, "", "enum", "",
         '[{"low": 0, "high": 0, "label": "Nein"}, {"low": 1, "high": 1, "label": "Ja"}]',
         24, 8, 3, 0,
         "cbf_diag_inline+cbf_presentation_enum_record"),
        ("DT_604B_P_T_Dpf_load_percent_wgh", "PRES_CM_0184_BIN7_BAR_UWORD",
         "uword", 2, "bar", "binary", "x / 128", "",
         16, 16, 2, 0,
         "cbf_diag_inline+presentation_name"),
    ]

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    groups = measurements.groups_for("CRD3_DEV", "ru")
    assert groups["coverage"]["coverage_pct"] == 100
    assert groups["coverage"]["matched_rows"] == 2
    path = groups["measurement"][0]["path"]
    group = measurements.get_group(path, "ru")
    assert group["services"][0]["req"] == "220123"
    assert group["services"][0]["sid"] == 0x22
    assert group["services"][0]["identifier_type"] == "did"
    assert group["services"][0]["identifier"] == "0123"
    assert group["services"][0]["sec_level"] == 3
    assert group["services"][0]["diag_description"] == "DPF soot mass"
    assert group["services"][0]["diag_qualifier"] == "DT_6043_P_T_Dpf_soot_mass"
    assert group["services"][0]["diag_match_kind"] == "exact"
    assert group["services"][0]["output_presentation"] == "PRES_DOP_PRESENTATION_Nein_Ja"
    assert group["services"][0]["output_raw_type"] == "ubyte"
    assert group["services"][0]["output_byte_len"] == 1
    assert group["services"][0]["output_bit_pos"] == 24
    assert group["services"][0]["output_bit_len"] == 8
    assert group["services"][0]["output_byte_offset"] == 3
    assert group["services"][0]["output_bit_offset"] == 0
    assert group["services"][0]["output_value_map"] == [
        {"low": 0, "high": 0, "label": "Nein"},
        {"low": 1, "high": 1, "label": "Ja"},
    ]
    assert group["services"][0]["value_source"] == "enum"
    assert group["services"][1]["output_unit"] == "bar"
    assert group["services"][1]["output_formula"] == "x / 128"
    assert group["services"][1]["value_source"] == "scaled"

    class Client:
        def __init__(self):
            self.requests = []

        def raw_request(self, payload: bytes) -> bytes:
            self.requests.append(payload.hex().upper())
            if payload == bytes.fromhex("220123"):
                return bytes.fromhex("62012301")
            return bytes.fromhex("61050007")

    def no_cbf_parse(ecu: str) -> dict:
        raise AssertionError(f"CBF fallback should not be used for {ecu}")

    client = Client()
    monkeypatch.setattr(measurements, "_diag_cat", no_cbf_parse)
    values = measurements.read_values(path, lang="ru", hw=True, client=client)
    assert client.requests == ["220123", "2105"]
    assert [v["value"] for v in values] == ["Ja", 0.0547]
    assert values[0]["value_source"] == "enum"
    assert values[1]["unit"] == "bar"
    assert values[1]["value_source"] == "scaled"


def test_unmatched_jobs_report_suggests_cbf_candidates(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    cbf_dir = tmp_path / "cbf"
    out = tmp_path / "measurements.sqlite"
    (mwg_dir / "VediamoData" / "CRD3_DEV").mkdir(parents=True)
    cbf_dir.mkdir()
    (cbf_dir / "CRD3_DEV.CBF").write_bytes(b"fake")
    (mwg_dir / "VediamoData" / "CRD3_DEV" / "dpf.mwg").write_text(
        ";System:crd3_dev\n"
        "[Entries]\n"
        "Count=2\n"
        "Service1=CRD3_DEV:ADJ_IO0352_Comb_nm_total_time\n"
        "Service2=CRD3_DEV:DT_IO0352_Comb_nm_total_time\n",
        encoding="latin-1",
    )

    def fake_diag_catalog(path: Path) -> dict:
        return {
            "ADJ_IOC352_Comb_nm_total_time": {
                "request": "2EC35200000000",
                "sec_level": 0,
                "svc_type": 1,
                "name": "Comb nm total time",
                "description": "combustion normal total time",
            },
            "DT_IOC352_Comb_nm_total_time": {
                "request": "22C352",
                "sec_level": 0,
                "svc_type": 1,
                "name": "Comb nm total time",
                "description": "combustion normal total time",
                "presentation": "PRES_IOC352",
                "presentation_raw_type": "",
                "presentation_byte_len": 0,
            },
        }

    monkeypatch.setattr(build_measure_db.caesar_vc, "diag_catalog", fake_diag_catalog)
    stats = build_measure_db.build(vsg_dir, mwg_dir, out, cbf_dir=cbf_dir)
    assert stats["diag_matched_services"] == 1
    assert stats["diag_exact_matched_services"] == 0
    assert stats["diag_normalized_matched_services"] == 1
    assert stats["diag_unmatched_services"] == 1
    assert stats["diag_services"] == 2
    coverage_rows = measure_diag_coverage.coverage_rows(out, ["CRD3_DEV"])
    assert coverage_rows == [{
        "ecu": "CRD3_DEV",
        "service_rows": 2,
        "matched_rows": 1,
        "exact_rows": 0,
        "normalized_rows": 1,
        "output_rows": 1,
        "raw_type_rows": 0,
        "unit_rows": 0,
        "formula_rows": 0,
        "missing_rows": 1,
        "distinct_jobs": 2,
        "matched_jobs": 1,
        "missing_jobs": 1,
        "coverage_pct": 50.0,
    }]

    report = measure_unmatched_jobs.unmatched_jobs(out, "CRD3_DEV")
    assert report["summary"]["missing_jobs"] == 1
    assert report["summary"]["confidence"]["strong"] == 1
    jobs = {job["job"]: job for job in report["jobs"]}
    adj_job = jobs["ADJ_IO0352_Comb_nm_total_time"]
    assert adj_job["confidence"] == "strong"
    assert adj_job["candidates"][0]["qualifier"] == "ADJ_IOC352_Comb_nm_total_time"
    assert adj_job["candidates"][0]["score"] == 1.0
    assert "DT_IO0352_Comb_nm_total_time" not in jobs

    with sqlite3.connect(out) as db:
        matches = db.execute(
            """
            SELECT job, qualifier, match_kind, rule
            FROM diag_service_matches ORDER BY job
            """
        ).fetchall()
    assert matches == [
        ("DT_IO0352_Comb_nm_total_time", "DT_IOC352_Comb_nm_total_time",
         "normalized", "dt_io0_to_ioc"),
    ]

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    path = "mwg:VediamoData/CRD3_DEV/dpf.mwg"
    group = measurements.get_group(path, "ru")
    services = {s["job"]: s for s in group["services"]}
    assert "req" not in services["ADJ_IO0352_Comb_nm_total_time"]
    dt_job = services["DT_IO0352_Comb_nm_total_time"]
    assert dt_job["req"] == "22C352"
    assert dt_job["diag_qualifier"] == "DT_IOC352_Comb_nm_total_time"
    assert dt_job["diag_match_kind"] == "normalized"
    assert dt_job["diag_match_rule"] == "dt_io0_to_ioc"
    assert dt_job["output_presentation"] == "PRES_IOC352"
    assert dt_job["value_source"] == "raw"


def test_hardware_read_values_blocks_non_read_only_requests(tmp_path: Path, monkeypatch):
    vsg_dir = tmp_path / "vsg"
    mwg_dir = tmp_path / "raw"
    cbf_dir = tmp_path / "cbf"
    out = tmp_path / "measurements.sqlite"
    (mwg_dir / "VediamoData" / "CRD3_DEV").mkdir(parents=True)
    cbf_dir.mkdir()
    (cbf_dir / "CRD3_DEV.CBF").write_bytes(b"fake")
    (mwg_dir / "VediamoData" / "CRD3_DEV" / "guard.mwg").write_text(
        ";System:crd3_dev\n"
        "[Entries]\n"
        "Count=3\n"
        "Service1=CRD3_DEV:DT_SAFE_READ\n"
        "Service2=CRD3_DEV:ADJ_WRITE_VALUE\n"
        "Service3=CRD3_DEV:DT_UNSAFE_ROUTINE\n",
        encoding="latin-1",
    )

    def fake_diag_catalog(path: Path) -> dict:
        return {
            "DT_SAFE_READ": {
                "request": "220123",
                "sec_level": 0,
                "svc_type": 1,
                "name": "Safe read",
                "description": "safe read",
            },
            "ADJ_WRITE_VALUE": {
                "request": "2E01230000",
                "sec_level": 3,
                "svc_type": 1,
                "name": "Write value",
                "description": "write value",
            },
            "DT_UNSAFE_ROUTINE": {
                "request": "310100",
                "sec_level": 0,
                "svc_type": 1,
                "name": "Routine-like",
                "description": "routine-like",
            },
        }

    monkeypatch.setattr(build_measure_db.caesar_vc, "diag_catalog", fake_diag_catalog)
    build_measure_db.build(vsg_dir, mwg_dir, out, cbf_dir=cbf_dir)

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", out)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    class Client:
        def __init__(self):
            self.requests = []

        def raw_request(self, payload: bytes) -> bytes:
            self.requests.append(payload.hex().upper())
            return bytes.fromhex("620123000A")

    client = Client()
    values = measurements.read_values(
        "mwg:VediamoData/CRD3_DEV/guard.mwg",
        lang="ru",
        hw=True,
        client=client,
    )

    assert client.requests == ["220123"]
    by_job = {v["job"]: v for v in values}
    assert by_job["DT_SAFE_READ"]["read_status"] == "hw_ok"
    assert by_job["DT_SAFE_READ"]["value"] == 10
    assert by_job["ADJ_WRITE_VALUE"]["read_status"] == "blocked"
    assert by_job["ADJ_WRITE_VALUE"]["read_sid"] == "2E"
    assert "not in hardware read allowlist" in by_job["ADJ_WRITE_VALUE"]["read_reason"]
    assert by_job["DT_UNSAFE_ROUTINE"]["read_status"] == "blocked"
    assert by_job["DT_UNSAFE_ROUTINE"]["read_sid"] == "31"


def test_apply_output_formula_supports_linear_records():
    from backend.mb import measurements

    assert measurements._apply_output_formula(
        1,
        {
            "output_scale_kind": "enum",
            "output_value_map": [
                {"low": 0, "high": 0, "label": "Nein"},
                {"low": 1, "high": 1, "label": "Ja"},
            ],
        },
    ) == ("Ja", "enum")
    assert measurements._apply_output_formula(
        5010, {"output_formula": "x * 0.01 - 50"}
    ) == (0.1, "scaled")
    assert measurements._apply_output_formula(
        4000, {"output_formula": "x * 0.25"}
    ) == (1000, "scaled")
    assert measurements._apply_output_formula(
        32768, {"output_formula": "x * 0.0078125 - 256"}
    ) == (0, "scaled")
    assert measurements._apply_output_formula(
        10, {"output_formula": "unsupported(x)"}
    ) == (10, "raw")
    assert measurements._apply_output_formula(
        1, {"output_formula": "x != 0"}
    ) == (True, "enum")
    assert measurements._apply_output_formula(
        1, {"output_formula": "x == 0"}
    ) == (False, "enum")
    assert measurements._apply_output_formula(
        12345678, {"output_formula": "bcd"}
    ) == (12345678, "scaled")


def test_raw_value_decodes_bcd_and_keeps_blocks_as_hex():
    from backend.mb import measurements

    req = bytes.fromhex("220123")
    assert measurements._raw_value(
        req, bytes.fromhex("62012312345678"), {"output_raw_type": "bcd"}
    ) == 12345678
    assert measurements._raw_value(
        req, bytes.fromhex("6201230A0B0C0D"), {"output_raw_type": "block"}
    ) == "0A0B0C0D"
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123AABBCCDDEE"),
        {
            "output_raw_type": "hexdump",
            "output_byte_len": 4,
            "output_bit_pos": 24,
            "output_bit_len": 16,
        },
    ) == "AABBCCDD"
    assert measurements._raw_value(
        req, bytes.fromhex("62012341424300"), {"output_raw_type": "ascii"}
    ) == "ABC"
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123000AFF"),
        {"output_raw_type": "uword", "output_bit_pos": 24, "output_bit_len": 16},
    ) == 10

    shared_resp = bytes.fromhex("620105") + (b"\x00" * 134) + bytes.fromhex("1234FF")
    assert measurements._raw_value(
        bytes.fromhex("220105"),
        shared_resp,
        {"output_raw_type": "block", "output_bit_pos": 0x448, "output_bit_len": 16},
    ) == "1234"
    assert measurements._raw_value(
        req,
        bytes.fromhex("62012308"),
        {
            "output_raw_type": "ubyte",
            "output_scale_kind": "enum",
            "output_value_map": [
                {"low": 0, "high": 0, "label": "No"},
                {"low": 1, "high": 1, "label": "Yes"},
            ],
            "output_bit_pos": 27,
            "output_bit_len": 16,
        },
    ) == 1
    assert measurements._raw_value(
        req,
        bytes.fromhex("62012308"),
        {
            "output_presentation": "PRES_Active_Not_active",
            "output_raw_type": "ubyte",
            "output_scale_kind": "enum",
            "output_bit_pos": 27,
            "output_bit_len": 16,
        },
    ) == 1
    # A multi-value enum with no matching value map returns the raw integer; a
    # byte-aligned 1-byte field reads the whole byte (0x08).
    assert measurements._raw_value(
        req,
        bytes.fromhex("62012308"),
        {
            "output_presentation": "PRES_DOP_PRESENTATION_Pending_Undefiniert_Ok_Fault",
            "output_raw_type": "ubyte",
            "output_scale_kind": "enum",
            "output_bit_pos": 24,
            "output_bit_len": 8,
        },
    ) == 8
    assert measurements._raw_value(
        req,
        bytes.fromhex("6201230A"),
        {
            "output_presentation": "PRES_Low_Nibble",
            "output_raw_type": "ubyte",
            "output_scale_kind": "bitfield",
            "output_bit_pos": 24,
            "output_bit_len": 16,
        },
    ) == 0x0A
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123A0"),
        {
            "output_presentation": "PRES_Unsigned_4Bit",
            "output_raw_type": "ubyte",
            "output_scale_kind": "bitfield",
            "output_bit_pos": 28,
            "output_bit_len": 16,
        },
    ) == 0x0A
    # A 16-bit field at a non-byte-aligned bit position cannot be read without
    # scrambling the word, so it is reported as unreadable rather than guessed.
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123000AFF"),
        {"output_raw_type": "uword", "output_bit_pos": 25, "output_bit_len": 16},
    ) is None


def test_raw_value_uses_real_byte_width_not_constant_bit_len():
    """The CBF layout bit_len is a constant 0x10; the read width must come from
    the presentation byte_len, not from bit_len, or 1- and 4-byte fields are
    misread as 2-byte values."""
    from backend.mb import measurements

    req = bytes.fromhex("220123")
    # 1-byte field at byte offset 3: must read only 0x08, not 0x08FF.
    assert measurements._raw_value(
        req,
        bytes.fromhex("62012308FF"),
        {"output_raw_type": "ubyte", "output_byte_len": 1,
         "output_bit_pos": 24, "output_bit_len": 16},
    ) == 0x08
    # 4-byte field at byte offset 3: must read all four bytes, not just two.
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123000A0001"),
        {"output_raw_type": "ulong", "output_byte_len": 4,
         "output_bit_pos": 24, "output_bit_len": 16},
    ) == 0x000A0001


def test_raw_value_decodes_signed_types():
    """sbyte/sword/slong must be two's-complement, not unsigned."""
    from backend.mb import measurements

    req = bytes.fromhex("220123")
    # sword 0xFFC0 = -64; unsigned would read 65472.
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123FFC0"),
        {"output_raw_type": "sword", "output_byte_len": 2,
         "output_bit_pos": 24, "output_bit_len": 16},
    ) == -64
    # sbyte 0xFF = -1 (must read one byte).
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123FF7E"),
        {"output_raw_type": "sbyte", "output_byte_len": 1,
         "output_bit_pos": 24, "output_bit_len": 16},
    ) == -1
    # unsigned counterpart stays positive.
    assert measurements._raw_value(
        req,
        bytes.fromhex("620123FFC0"),
        {"output_raw_type": "uword", "output_byte_len": 2,
         "output_bit_pos": 24, "output_bit_len": 16},
    ) == 0xFFC0


def test_raw_value_extracts_sub_byte_fields():
    """bit_len carries the authoritative width; sub-byte fields extract by bits,
    and wide non-byte-aligned fields are unreadable (not guessed)."""
    from backend.mb import measurements

    req = bytes.fromhex("220123")
    resp = bytes.fromhex("620123A5")  # data byte 0xA5 = 1010_0101
    # 1-bit flag at bit offset 3 of byte 3: (0xA5 >> 3) & 1 == 0.
    assert measurements._raw_value(
        req, resp,
        {"output_raw_type": "ubyte", "output_byte_len": 0,
         "output_bit_pos": 27, "output_bit_len": 1},
    ) == 0
    # 4-bit field at the byte boundary: low nibble of 0xA5 == 0x5.
    assert measurements._raw_value(
        req, resp,
        {"output_raw_type": "ubyte", "output_byte_len": 0,
         "output_bit_pos": 24, "output_bit_len": 4},
    ) == 0x5
    # 16-bit field at a non-byte-aligned position is unreadable.
    assert measurements._raw_value(
        req, resp,
        {"output_raw_type": "uword", "output_byte_len": 0,
         "output_bit_pos": 25, "output_bit_len": 16},
    ) is None


def test_raw_value_honors_byte_order_from_db():
    """ByteOrder from the presentation pool drives endianness; default is big."""
    from backend.mb import measurements

    req = bytes.fromhex("220123")
    base = {"output_raw_type": "uword", "output_byte_len": 2,
            "output_bit_pos": 24, "output_bit_len": 16}
    assert measurements._raw_value(
        req, bytes.fromhex("6201231234"), {**base, "output_byte_order": "big"}
    ) == 0x1234
    assert measurements._raw_value(
        req, bytes.fromhex("6201231234"), {**base, "output_byte_order": "little"}
    ) == 0x3412
    # output_signed from the DB overrides the raw_type guess.
    assert measurements._raw_value(
        req, bytes.fromhex("620123FFC0"),
        {**base, "output_byte_order": "big", "output_signed": 1},
    ) == -64


def test_stride_consistency_scores_only_clean_groups():
    # Clean, densely packed group: offsets 0,1,3,7 with widths 1,2,4,2.
    # Gaps 1,2,4 each equal the field width -> 3/3 match.
    clean = [("a", 0, 1), ("a", 1, 2), ("a", 3, 4), ("a", 7, 2)]
    assert measure_layout_check.stride_consistency(clean) == (3, 3, 1)

    # A mismatch: width says 2 but the next field is 4 bytes away.
    mismatch = [("b", 0, 2), ("b", 4, 2), ("b", 6, 2), ("b", 8, 2)]
    match, total, scored = measure_layout_check.stride_consistency(mismatch)
    assert (match, total, scored) == (2, 3, 1)  # first gap=4!=2, rest match

    # Overlapping/aliased reads (duplicate offsets) must be skipped entirely,
    # so a noisy block cannot mask a real regression.
    overlapping = [("c", 0, 4), ("c", 0, 4), ("c", 1, 4), ("c", 2, 4)]
    assert measure_layout_check.stride_consistency(overlapping) == (0, 0, 0)

    # Groups smaller than min_fields are ignored.
    assert measure_layout_check.stride_consistency([("d", 0, 1), ("d", 1, 1)]) == (0, 0, 0)


def test_layout_stride_matches_byte_len_on_local_db():
    """If the proprietary DB is present, the on-wire field stride must agree
    with the inferred byte_len for the vast majority of clean fields -- this is
    the CBF-only guard that byte_len (not the constant bit_len) is the width."""
    db_path = measure_layout_check.DEFAULT_DB
    if not db_path.exists():
        pytest.skip("local measurements.sqlite not present")
    match, total, scored = measure_layout_check.stride_consistency(
        measure_layout_check.stride_rows(db_path)
    )
    if total == 0:
        pytest.skip("DB has no scalar output fields with layout offsets")
    assert match / total >= 0.90, (
        f"field stride agrees with byte_len only {match}/{total} "
        f"({100 * match / total:.1f}%) across {scored} DIDs -- byte_len "
        f"inference may have regressed"
    )

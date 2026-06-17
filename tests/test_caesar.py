"""
Caesar/CBF parser tests against a real Vediamo CBF.

These need the proprietary data library (gitignored), so they self-skip when
./data/cbf is absent — locally they pin the parser to known-good values
(EZS164: KWP over the 83.3k interior CAN, req 0x4E0 / resp 0x5FF).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EZS = ROOT / "data" / "cbf" / "EZS164.cbf"
CRD3 = ROOT / "data" / "cbf" / "CRD3_DEV.CBF"
CEPC_MFA = ROOT / "data" / "cbf" / "CEPC_MFA.cbf"


def test_presentation_meta_from_qualifier_name():
    from caesar_vc import presentation_meta

    meta = presentation_meta("PRES_CM_0184_BIN7_BAR_UWORD")
    assert meta == {
        "raw_type": "uword",
        "byte_len": 2,
        "unit": "bar",
        "scale_kind": "binary",
        "formula": "x / 128",
    }

    ascii_meta = presentation_meta("PRES_100ByteASCII")
    assert ascii_meta["raw_type"] == "ascii"
    assert ascii_meta["byte_len"] == 100

    assert presentation_meta("PRES_bool_1bit") == {
        "raw_type": "bool",
        "byte_len": 1,
        "unit": "",
        "scale_kind": "boolean",
        "formula": "x != 0",
    }
    assert presentation_meta("PRES_bool_1bit_inverted")["formula"] == "x == 0"
    bcd_meta = presentation_meta("PRES_BCD_8")
    assert bcd_meta["raw_type"] == "bcd"
    assert bcd_meta["byte_len"] == 4
    assert bcd_meta["scale_kind"] == "bcd"
    assert bcd_meta["formula"] == "bcd"

    hex_meta = presentation_meta("PRES_HexDump_55_Bytes")
    assert hex_meta["raw_type"] == "hexdump"
    assert hex_meta["byte_len"] == 55
    vin_dump = presentation_meta("PRES_VIN_17_ByteDump")
    assert vin_dump["raw_type"] == "hexdump"
    assert vin_dump["byte_len"] == 17
    assert presentation_meta("PRES_Hex_Dump_18Bytes")["byte_len"] == 18
    assert presentation_meta("PRES_DOP_IDENTICAL_BYTEFIELD_16_Bytes") == {
        "raw_type": "bytes",
        "byte_len": 16,
        "unit": "",
        "scale_kind": "",
        "formula": "",
    }
    assert presentation_meta("PRES_IDENTICAL_HEX_160")["byte_len"] == 20
    assert presentation_meta("PRES_Identical_HEX_display_for_24_bits")["byte_len"] == 3

    block_meta = presentation_meta("PRES_BLK_EngSpd_GearState_COL_format")
    assert block_meta["raw_type"] == "block"
    assert block_meta["scale_kind"] == "block"

    assert presentation_meta("PRES_2ByteDump") == {
        "raw_type": "hexdump",
        "byte_len": 2,
        "unit": "",
        "scale_kind": "",
        "formula": "",
    }
    assert presentation_meta("PRES_2ByteBcd") == {
        "raw_type": "bcd",
        "byte_len": 2,
        "unit": "",
        "scale_kind": "bcd",
        "formula": "bcd",
    }
    assert presentation_meta("PRES_CM_0026_BIN0_NA_2") == {
        "raw_type": "uword",
        "byte_len": 2,
        "unit": "",
        "scale_kind": "binary",
        "formula": "x",
    }
    assert presentation_meta("PRES_DOP_IDENTICAL_UINT_DEC_4_Bytes")["raw_type"] == "ulong"
    assert presentation_meta("PRES_DOP_IDENTICAL_INT_DEC_2_Bytes")["raw_type"] == "sword"
    assert presentation_meta("PRES_nein_ja_1Bit")["raw_type"] == "bool"
    assert presentation_meta("PRES_nein_ja_1Bit")["formula"] == "x != 0"
    assert presentation_meta("PRES_Bit_ja")["raw_type"] == "bool"
    assert presentation_meta("PRES_Bit_ja")["formula"] == "x != 0"
    nibble = presentation_meta("PRES_Low_Nibble")
    assert nibble["raw_type"] == "ubyte"
    assert nibble["scale_kind"] == "bitfield"
    yes_no = presentation_meta("PRES_DOP_PRESENTATION_Nein_Ja")
    assert yes_no["raw_type"] == "ubyte"
    assert yes_no["scale_kind"] == "enum"
    assert yes_no["formula"] == ""
    active = presentation_meta("PRES_Active_Not_active")
    assert active["raw_type"] == "ubyte"
    assert active["scale_kind"] == "enum"
    assert presentation_meta("PRES_SigOn_Off")["raw_type"] == "ubyte"
    pending = presentation_meta("PRES_DOP_PRESENTATION_Pending_Undefiniert_Ok_Fault")
    assert pending["raw_type"] == "ubyte"
    assert pending["scale_kind"] == "enum"
    assert presentation_meta("PRES_Session_Type_7Bit")["raw_type"] == "ubyte"
    assert presentation_meta("PRES_Session_Type_7Bit")["scale_kind"] == "enum"
    assert presentation_meta("PRES_Volt")["unit"] == "V"
    assert presentation_meta("PRES_IN_Battery_voltage")["unit"] == "V"
    assert presentation_meta("PRES_Temp_Cels")["unit"] == "deg C"
    assert presentation_meta("PRES_Trq")["unit"] == "Nm"
    assert presentation_meta("PRES_Tastverhaeltnis_E")["unit"] == "%"
    assert presentation_meta("PRES_Pres_Rail")["unit"] == "bar"
    assert presentation_meta("PRES_EngN")["unit"] == "rpm"


@pytest.mark.skipif(not CRD3.exists(), reason="proprietary CBF library not present")
def test_presentation_records_extract_linear_formula():
    from caesar_vc import presentation_records

    records = presentation_records(CRD3)
    speed = records["PRES_5017_IN_Engine_cycle_speed_UWORD"]
    assert speed["raw_type"] == "uword"
    assert speed["byte_len"] == 2
    assert speed["scale_kind"] == "linear"
    assert speed["formula"] == "x * 0.25"
    assert speed["source"] == "cbf_presentation_record"

    soot = records["PRES_6043_P_T_Dpf_soot_mass_ULONG"]
    assert soot["raw_type"] == "ulong"
    assert soot["formula"] == "x * 0.01 - 50"


@pytest.mark.skipif(not CEPC_MFA.exists(), reason="proprietary CBF library not present")
def test_presentation_records_extract_range_linear_formula():
    from caesar_vc import presentation_records

    records = presentation_records(CEPC_MFA)
    battery = records["PRES_IN_Battery_voltage"]
    assert battery["raw_type"] == "uword"
    assert battery["byte_len"] == 2
    assert battery["unit"] == "V"
    assert battery["scale_kind"] == "linear"
    assert battery["formula"] == "x * 0.0078125"
    assert battery["source"] == "cbf_presentation_range_record"

    tsl = records["PRES_TslPosnSnsrVolt_Volt_App"]
    assert tsl["raw_type"] == "uword"
    assert tsl["byte_len"] == 2
    assert tsl["unit"] == "V"
    assert tsl["formula"] == "x * 0.001221"


@pytest.mark.skipif(not CEPC_MFA.exists(), reason="proprietary CBF library not present")
def test_presentation_records_extract_enum_record():
    from caesar_vc import presentation_records

    records = presentation_records(CEPC_MFA)
    glps = records["PRES_GLPS_Adap_Mode"]
    assert glps["raw_type"] == "ubyte"
    assert glps["byte_len"] == 1
    assert glps["scale_kind"] == "enum"
    assert glps["formula"] == ""
    assert glps["source"] == "cbf_presentation_enum_record"
    assert glps["value_map"] == [
        {"low": 0, "high": 0, "label": "Nein"},
        {"low": 1, "high": 1, "label": "Ja"},
    ]

    bool_record = records["PRES_bool_1bit_inverted"]
    assert bool_record["raw_type"] == "ubyte"
    assert bool_record["scale_kind"] == "enum"
    assert bool_record["formula"] == ""


@pytest.mark.skipif(not CEPC_MFA.exists(), reason="proprietary CBF library not present")
def test_presentation_records_do_not_scale_block_layouts():
    from caesar_vc import presentation_records

    records = presentation_records(CEPC_MFA)
    assert "PRES_BLK3S_Stopcluster_COL_format" not in records
    assert "PRES_BLK_FirstStrt_Km" not in records


@pytest.mark.skipif(not EZS.exists(), reason="proprietary CBF library not present")
def test_parse_cbf_ezs164():
    from parse_cbf import parse_cbf
    info = parse_cbf(EZS)
    assert info["ecu"] == "EZS164"
    assert info["protocol"] == "kwp"


@pytest.mark.skipif(not EZS.exists(), reason="proprietary CBF library not present")
def test_comparam_real_can_ids():
    from caesar_comparam import parse_file
    cp = parse_file(EZS)["ecus"][0]["can"]
    assert cp["CP_REQUEST_CANIDENTIFIER"] == 0x4E0
    assert cp["CP_RESPONSE_CANIDENTIFIER"] == 0x5FF
    assert cp["CP_BAUDRATE"] == 83333


@pytest.mark.skipif(not EZS.exists(), reason="proprietary CBF library not present")
def test_ecu_db_has_ezs164_ids():
    db = ROOT / "data" / "ecu_db.sqlite"
    if not db.exists():
        pytest.skip("ecu_db.sqlite not built")
    import sqlite3
    row = sqlite3.connect(db).execute(
        "SELECT can_request, can_response, baudrate FROM ecu WHERE name='EZS164'"
    ).fetchone()
    assert row == (0x4E0, 0x5FF, 83333)


@pytest.mark.skipif(not CRD3.exists(), reason="proprietary CBF library not present")
def test_diag_catalog_extracts_output_presentation():
    from caesar_vc import diag_catalog

    cat = diag_catalog(CRD3)
    soot = cat["DT_6043_P_T_Dpf_soot_mass"]
    assert soot["presentation"] == "PRES_6043_P_T_Dpf_soot_mass_ULONG"
    assert soot["presentation_raw_type"] == "ulong"
    assert soot["presentation_byte_len"] == 4
    assert soot["presentation_scale_kind"] == "linear"
    assert soot["presentation_formula"] == "x * 0.01 - 50"
    assert soot["presentation_meta_source"] == "cbf_presentation_record"

    speed = cat["DT_5017_IN_Engine_cycle_speed"]
    assert speed["presentation"] == "PRES_5017_IN_Engine_cycle_speed_UWORD"
    assert speed["presentation_formula"] == "x * 0.25"

    total_time = cat["DT_IOC352_Comb_nm_total_time"]
    assert total_time["presentation"] == "PRES_IOC352"
    assert total_time["presentation_raw_type"] == ""


@pytest.mark.skipif(not CEPC_MFA.exists(), reason="proprietary CBF library not present")
def test_diag_catalog_extracts_enum_value_map():
    from caesar_vc import diag_catalog

    cat = diag_catalog(CEPC_MFA)
    glps = cat["DT_Neutralgangsensor"]
    assert glps["presentation"] == "PRES_GLPS_Adap_Mode"
    assert glps["presentation_raw_type"] == "ubyte"
    assert glps["presentation_scale_kind"] == "enum"
    assert glps["presentation_formula"] == ""
    assert glps["presentation_value_map"] == [
        {"low": 0, "high": 0, "label": "Nein"},
        {"low": 1, "high": 1, "label": "Ja"},
    ]


@pytest.mark.skipif(not CEPC_MFA.exists(), reason="proprietary CBF library not present")
def test_diag_catalog_extracts_output_bit_layout():
    from caesar_vc import diag_catalog

    cat = diag_catalog(CEPC_MFA)
    battery = cat["DT_Batteriespannung"]
    assert battery["presentation"] == "PRES_IN_Battery_voltage"
    assert battery["presentation_bit_pos"] == 0x18
    assert battery["presentation_bit_len"] == 0x10
    assert battery["presentation_byte_offset"] == 3
    assert battery["presentation_bit_offset"] == 0

    col0 = cat["DT_BLK_EngSpd_GearState_COL_0"]
    col1 = cat["DT_BLK_EngSpd_GearState_COL_1"]
    assert col0["presentation"] == "PRES_BLK_EngSpd_GearState_COL_format"
    assert col0["presentation_bit_pos"] == 0x448
    assert col0["presentation_bit_len"] == 0x10
    assert col0["presentation_byte_offset"] == 137
    assert col1["presentation_bit_pos"] == 0x468

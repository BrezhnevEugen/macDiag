from __future__ import annotations

from pathlib import Path

import parse_mwg
import parse_vsg


def test_parse_mwg_ecoute_ini(tmp_path: Path):
    p = tmp_path / "CRD3_DPF-Wiegen_SB.mwg"
    p.write_text(
        ";C:\\ProgramData\\Vediamo\\VediamoDaten\\crd3_dev\\CRD3_DPF-Wiegen_SB.mwg\n"
        ";Version:05.00.00\n"
        ";System:crd3_dev\n"
        "\n"
        "[Entries]\n"
        "Count=3\n"
        "Service1=CRD3_DEV:DT_6043_P_T_Dpf_soot_mass\n"
        "Service2=$=>comment<=$\n"
        "Service3=CRD3_DEV:ADJ_1234_Test_value\n"
        "\n"
        "[Ecoute]\n"
        "FileVer=2\n",
        encoding="latin-1",
    )

    g = parse_mwg.parse_mwg(p)

    assert g["title"] == "CRD3 DPF-Wiegen SB"
    assert g["ecu"] == "CRD3_DEV"
    assert g["kind"] == "measurement"
    assert [s["job"] for s in g["services"]] == [
        "DT_6043_P_T_Dpf_soot_mass",
        "ADJ_1234_Test_value",
    ]
    assert [s["kind"] for s in g["services"]] == ["data", "adapt"]


def test_parse_mwg_xml_delegates_to_vsg(tmp_path: Path):
    p = tmp_path / "dpf_regen.mwg"
    p.write_text(
        '<?xml version="1.0"?>\n'
        '<experiment><diagwin title="DPF regeneration"></diagwin>'
        '<measurements>'
        '<service ECU="CRD3H_DEV" lowlimit="0" uplimit="5">'
        'FN_Start_Routine_DPF_Regeneration_On_Demand'
        '</service>'
        '<service ECU="CRD3H_DEV" unit="g" lowlimit="0" uplimit="20">'
        'DT_0170_P_T_Dpf_soot_mass'
        '</service>'
        '</measurements></experiment>',
        encoding="latin-1",
    )

    g = parse_mwg.parse_mwg(p)

    assert g["ecu"] == "CRD3H_DEV"
    assert g["kind"] == "service"
    assert [s["kind"] for s in g["services"]] == ["routine", "data"]


def test_parse_vsg_treats_fn_jobs_as_routines(tmp_path: Path):
    p = tmp_path / "service.vsg"
    p.write_text(
        '<experiment><diagwin title="Function"></diagwin><measurements>'
        '<service ECU="CRD3H_DEV">FN_Start_Routine</service>'
        '</measurements></experiment>',
        encoding="latin-1",
    )

    g = parse_vsg.parse_vsg(p)

    assert g["kind"] == "service"
    assert g["services"][0]["kind"] == "routine"

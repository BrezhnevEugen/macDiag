from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import build_measure_db
import manage_measure_translations
import seed_measure_ru_translations
from fastapi.testclient import TestClient


def _build_sample_db(tmp_path: Path) -> Path:
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
    build_measure_db.build(vsg_dir, mwg_dir, out)
    return out


def test_measure_translation_export_import_and_runtime(tmp_path: Path, monkeypatch):
    db_path = _build_sample_db(tmp_path)
    csv_path = tmp_path / "measurements_ru.csv"

    exported = manage_measure_translations.export_csv(db_path, "ru", csv_path)
    assert exported["written"] == 3

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    for row in rows:
        if row["kind"] == "group":
            row["translation"] = "Группа DPF"
        elif row["source_text"] == "DT_6043_P_T_Dpf_soot_mass":
            row["translation"] = "Масса сажи DPF"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manage_measure_translations.FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    imported = manage_measure_translations.import_csv(db_path, "ru", csv_path)
    assert imported["upserted"] == 2
    assert imported["skipped_empty"] == 1
    assert manage_measure_translations.stats(db_path, "ru")["translated_count"] == 2

    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT text FROM translations WHERE lang = 'ru' AND text = 'Группа DPF'"
        ).fetchone()

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", db_path)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    groups = measurements.groups_for("CRD3_DEV", "ru")
    db_group = next(g for g in groups["measurement"] if g.get("source") == "mwg")
    assert db_group["title"] == "Группа DPF"

    group = measurements.get_group(db_group["path"], "ru")
    assert group["title"] == "Группа DPF"
    assert group["services"][0]["label"] == "Масса сажи DPF"

    values = measurements.read_values(db_group["path"], lang="ru")
    assert values[0]["label"] == "Масса сажи DPF"


def test_seed_measure_ru_translations(tmp_path: Path, monkeypatch):
    db_path = _build_sample_db(tmp_path)

    seeded = seed_measure_ru_translations.seed(db_path)
    assert seeded["inserted"] == 2
    assert seeded["skipped_unknown"] == 1

    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            "SELECT text FROM translations WHERE lang = 'ru' ORDER BY text"
        ).fetchall()
    assert [r[0] for r in rows] == ["загрузка DPF", "масса сажи DPF"]

    from backend.mb import measurements

    monkeypatch.setattr(measurements, "MEASURE_DB", db_path)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    groups = measurements.groups_for("CRD3_DEV", "ru")
    path = next(g["path"] for g in groups["measurement"] if g.get("source") == "mwg")
    group = measurements.get_group(path, "ru")
    assert [s["label"] for s in group["services"]] == ["масса сажи DPF", "загрузка DPF"]


def test_measure_translation_api(tmp_path: Path, monkeypatch):
    db_path = _build_sample_db(tmp_path)

    from backend.mb import measurements
    import backend.main as main

    monkeypatch.setattr(measurements, "MEASURE_DB", db_path)
    monkeypatch.setattr(measurements, "VSG_DIR", tmp_path / "no-vsg")
    monkeypatch.setattr(measurements, "MWG_DIR", tmp_path / "no-mwg")
    measurements._index.cache_clear()
    measurements._db_index.cache_clear()
    measurements._db_translations.cache_clear()

    with TestClient(main.app) as client:
        missing = client.get(
            "/api/measure/translations",
            params={"lang": "ru", "status": "missing", "limit": 2},
        )
        assert missing.status_code == 200
        body = missing.json()
        assert body["total"] == 3
        assert len(body["rows"]) == 2

        key = body["rows"][0]["localization_key"]
        saved = client.post(
            "/api/measure/translations",
            json={"localization_key": key, "lang": "ru", "text": "Тестовый перевод"},
        )
        assert saved.status_code == 200
        assert saved.json()["ok"] is True

        translated = client.get(
            "/api/measure/translations",
            params={"lang": "ru", "status": "translated", "q": "Тестовый"},
        ).json()
        assert translated["total"] == 1
        assert translated["rows"][0]["translation"] == "Тестовый перевод"
        assert client.get("/api/measure/translations/stats", params={"lang": "ru"}).json()[
            "translated_count"
        ] == 1

        cleared = client.post(
            "/api/measure/translations",
            json={"localization_key": key, "lang": "ru", "text": ""},
        )
        assert cleared.status_code == 200
        assert client.get("/api/measure/translations/stats", params={"lang": "ru"}).json()[
            "translated_count"
        ] == 0

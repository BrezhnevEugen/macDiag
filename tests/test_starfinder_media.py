from __future__ import annotations

from pathlib import Path

import pytest


STARFINDER = Path(__file__).resolve().parent.parent / "data" / "starfinder"


pytestmark = pytest.mark.skipif(
    not (STARFINDER / "164.asar").exists(),
    reason="local StarFinder .asar data is not available",
)


def test_starfinder_provider_indexes_local_archives(monkeypatch):
    from backend.mb import media

    monkeypatch.setenv("MACDIAG_STARFINDER_DIR", str(STARFINDER))
    sf = next(p for p in media.status() if p["provider"] == "starfinder")

    assert sf["configured"] is True
    assert any(a["file"] == "164.asar" for a in sf["archives"])
    assert any(a["file"] == "221.asar" for a in sf["archives"])


def test_diag_context_returns_starfinder_media(monkeypatch):
    from backend.main import diag_context

    monkeypatch.setenv("MACDIAG_STARFINDER_DIR", str(STARFINDER))
    ctx = diag_context("B1535", "ezs", "ru")

    assert ctx["starfinder"]["configured"] is True
    assert ctx["starfinder"]["mapped"] is True
    assert ctx["starfinder"]["images"] > 0
    assert ctx["component"]["code"] == "N73"
    assert any(m.get("provider") == "starfinder" for m in ctx["media"])

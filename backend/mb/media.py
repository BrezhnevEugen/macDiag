"""
External media providers for the diagnostic drill-down: real Mercedes pictures
(connector pinouts, wiring diagrams) from StarFinder (and WIS later).

StarFinder ships per-series Electron archives `<series>.asar` (e.g. 164.asar for
W164/X164). We read images straight out of the archive (see asar.py) and serve
them. The first mapping implemented is ECU → MB component code → connector pinout
SVG (connectors/<code>.svg), which is reliable: the codes are standard MB
designations (N22 = climate, N73 = EIS, N10 = SAM, A1 = cluster, …).

Configure with:
  * MACDIAG_STARFINDER_DIR — folder holding <series>.asar (StarFinder .../resources).
  * MACDIAG_WIS_DIR        — a WIS/ASRA dataset (indexer TBD).
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from . import asar

PROVIDERS = ("starfinder", "wis")

CHASSIS_MODELS = {
    "118": "CLA (C118)", "129": "SL (R129)", "140": "S-Class (W140)",
    "163": "ML (W163)", "164": "ML / GL (W164 / X164)",
    "166": "ML→GLE / GL→GLS (W166 / X166)", "167": "GLE / GLS (W167 / X167)",
    "221": "S-Class (W221)", "216": "CL (C216)", "251": "R-Class (W251)",
}

# our chassis token (from the module/catalog) -> StarFinder series (.asar stem)
CHASSIS_SERIES = {
    "X164": "164", "W164": "164", "W221": "221", "C216": "216", "W251": "251",
    "X166": "166", "W166": "166", "W163": "163", "R129": "129", "W140": "140",
    "C118": "118",
}

# our curated module id -> MB component code (normalized: lowercase, '/'→'_').
# Codes verified against the StarFinder "Overall network (GVN)" component list.
COMPONENT_CODE = {
    "ezs": "n73", "eis447": "n73",          # EIS [EZS] control unit
    "kla": "n22",                            # air-conditioning control
    "samv": "n10", "samh": "n10_8",          # front / rear SAM control unit
    "ki": "a1", "ic204": "a1",               # instrument cluster
    "tcm": "n15_3",                          # electronic transmission control (VGS)
    "crd3": "n3_9",                          # CDI control unit (diesel)
    "me97": "n3_10",                         # ME-SFI (petrol)
    "fscm": "n118", "fscm221": "n118",       # fuel pump / fuel system control
}

_PIN = {"ru": "Распиновка разъёма", "en": "Connector pinout", "de": "Steckerbelegung"}
_LOC = {"ru": "Расположение", "en": "Location", "de": "Einbauort"}
_DIA = {"ru": "Схема проводки", "en": "Wiring diagram", "de": "Stromlaufplan"}

# component code as a standalone text label inside a wiring-diagram SVG (e.g. N3/9)
_CODE_IN_SVG = re.compile(r">\s*([A-Z]\d{1,3}(?:/\d{1,2})?)\s*<")

_DRAW_RE = re.compile(
    r"drawNewEmpty\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'[^']*'\s*,\s*'([^']*)'")


# Schematic sources ship with the project under data/; env vars override.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DEFAULT_DIRS = {
    "starfinder": _DATA_DIR / "starfinder",
    "wis": _DATA_DIR / "dist_raw" / "docs_and_tables" / "загрузки" / "WIS_0420_1of1",
}


def _root(name: str) -> Path | None:
    env = {"starfinder": "MACDIAG_STARFINDER_DIR", "wis": "MACDIAG_WIS_DIR"}[name]
    p = os.environ.get(env)
    root = Path(p) if p else _DEFAULT_DIRS.get(name)
    return root if (root and root.exists()) else None


def chassis_model(code: str) -> str:
    return CHASSIS_MODELS.get(str(code).strip(), "")


def _asar_archives(root: Path) -> list[dict]:
    try:
        return [{"file": p.name, "chassis": p.stem, "model": chassis_model(p.stem)}
                for p in sorted(root.rglob("*.asar"))]
    except Exception:  # noqa: BLE001
        return []


def status() -> list[dict]:
    out = []
    for name in PROVIDERS:
        root = _root(name)
        item = {"provider": name, "configured": root is not None,
                "path": str(root) if root else None,
                "env": {"starfinder": "MACDIAG_STARFINDER_DIR", "wis": "MACDIAG_WIS_DIR"}[name]}
        if name == "starfinder" and root is not None:
            item["archives"] = _asar_archives(root)
        out.append(item)
    return out


# ---- StarFinder archive helpers -------------------------------------------

def _archive_path(series: str) -> Path | None:
    root = _root("starfinder")
    if not root:
        return None
    for p in root.rglob(f"{series}.asar"):
        return p
    return None


@lru_cache(maxsize=16)
def _file_index(archive: str, mtime: float) -> dict:
    """inner path -> (offset, size); cached per (archive, mtime)."""
    try:
        return asar.list_files(archive)
    except Exception:  # noqa: BLE001
        return {}


def _index_for(archive: Path) -> dict:
    return _file_index(str(archive), archive.stat().st_mtime)


def _archive_for_module(module: dict | None) -> Path | None:
    if not module:
        return None
    for ch in module.get("chassis", []) or []:
        series = CHASSIS_SERIES.get(str(ch).upper())
        if not series:
            continue
        ap = _archive_path(series)
        if ap:
            return ap
    return None


def _connector_files(index: dict, code: str) -> list[str]:
    """All connector SVGs for a component code: /connectors/<code>.svg and
    /connectors/<code>_<n>.svg."""
    code = code.lower()
    pat = re.compile(rf"^/connectors/{re.escape(code)}(?:[._]\d+)?\.svg$")
    return sorted(p for p in index if pat.match(p))


def _norm_code(c: str) -> str:
    return c.lower().replace("/", "_")


@lru_cache(maxsize=8)
def _diagram_index_cached(archive: str, mtime: float) -> dict:
    """code (normalized) -> [diagram inner paths]. Built once by scanning every
    /diagrams/*.svg for the component codes printed in it; cached to a temp JSON
    so a restart is instant."""
    cache = Path(tempfile.gettempdir()) / f"macdiag_sfdiag_{Path(archive).stem}_{int(mtime)}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    idx: dict[str, list[str]] = {}
    for inner, data in asar.iter_files(archive, "/diagrams/"):
        if not inner.endswith(".svg"):
            continue
        text = data.decode("utf-8", "replace")
        for code in set(_CODE_IN_SVG.findall(text)):
            idx.setdefault(_norm_code(code), []).append(inner)
    for k in idx:
        idx[k] = sorted(set(idx[k]))
    try:
        cache.write_text(json.dumps(idx))
    except Exception:  # noqa: BLE001
        pass
    return idx


def _diagram_index(archive: Path) -> dict:
    return _diagram_index_cached(str(archive), archive.stat().st_mtime)


# ---- component names + description docs (sysinfo) --------------------------

_DESC = {"ru": "Описание", "en": "Description", "de": "Beschreibung"}
_CODE_TOK = re.compile(r"^[A-Z]\d{1,3}(?:/\d{1,2})?$")
_CODE_WORD = re.compile(r"\b([A-Z]\d{1,3}(?:/\d{1,2})?)\b")


def _denorm(code: str) -> str:
    """normalized code (n10_8) -> StarFinder form (N10/8)."""
    return code.upper().replace("_", "/")


@lru_cache(maxsize=8)
def _master_names_cached(archive: str, mtime: float) -> dict:
    """MB component code -> English name, from the 'Overall network (GVN)'
    component-list docs (GF00.19-P-0001-*)."""
    names: dict[str, str] = {}
    for inner, data in asar.iter_files(archive, "/sysinfo/docs/GF00.19-P-0001-"):
        toks = _clean(data.decode("utf-8", "replace")).split()
        i = 0
        while i < len(toks):
            if _CODE_TOK.match(toks[i]):
                code, j, nm = toks[i], i + 1, []
                while j < len(toks) and not _CODE_TOK.match(toks[j]) and len(nm) < 8:
                    nm.append(toks[j]); j += 1
                if nm and code not in names:
                    names[code] = " ".join(nm).rstrip(" (,")
                i = j
            else:
                i += 1
    return names


def _master_names(archive: Path) -> dict:
    return _master_names_cached(str(archive), archive.stat().st_mtime)


def component_name(archive: Path, code: str) -> str:
    nm = _master_names(archive).get(_denorm(code), "")
    return nm.split(" (")[0].strip()  # drop variant qualifiers for the header


@lru_cache(maxsize=8)
def _doc_index_cached(archive: str, mtime: float) -> dict:
    """component code (normalized) -> [doc inner paths], ranked most-specific
    first (docs mentioning fewer components rank higher)."""
    tmp: dict[str, list[tuple[int, str]]] = {}
    for inner, data in asar.iter_files(archive, "/sysinfo/docs/"):
        if not inner.endswith((".htm", ".html")):
            continue
        text = _clean(data.decode("utf-8", "replace"))
        codes = set(_CODE_WORD.findall(text))
        if not codes or len(codes) > 60:
            continue
        for c in codes:
            tmp.setdefault(_norm_code(c), []).append((len(codes), inner))
    return {k: [inner for _, inner in sorted(v)] for k, v in tmp.items()}


def _doc_index(archive: Path) -> dict:
    return _doc_index_cached(str(archive), archive.stat().st_mtime)


def _doc_title(archive: Path, inner: str) -> str:
    data = asar.read_file(str(archive), inner)
    if not data:
        return inner.rsplit("/", 1)[-1]
    text = _clean(data.decode("utf-8", "replace"))
    # docs start with the document number (repeated) then the heading
    text = re.sub(r"^(\S+)\s+\1\s+", "", text)
    return text[:70].strip() or inner.rsplit("/", 1)[-1]



def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _locator(index: dict, archive: Path, code: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Parse /locator/ressources/<CODE>.html -> (component name, location text,
    [(photo_inner_path, variant)]). The page lists drawNewEmpty(photo, code,
    name, '', location, …) per installation photo."""
    page = "/locator/ressources/" + code.upper() + ".html"
    if page not in index:
        return "", "", []
    raw = asar.read_file(str(archive), page)
    if not raw:
        return "", "", []
    html = raw.decode("utf-8", "replace")
    name = location = ""
    photos: list[tuple[str, str]] = []
    seen = set()
    for ph, _cd, nm, loc in _DRAW_RE.findall(html):
        name = name or _clean(nm)
        location = location or _clean(loc)
        inner = "/locator/ressources/images/" + ph
        if ph and ph not in seen and inner in index:
            seen.add(ph)
            photos.append((inner, _clean(loc)))
    return name, location, photos


# ---- token <-> file/asar resolution ---------------------------------------

def _tok(*parts: str) -> str:
    return base64.urlsafe_b64encode("|".join(parts).encode()).decode()


def _under_starfinder(p: Path) -> bool:
    root = _root("starfinder")
    try:
        return bool(root) and root.resolve() in p.resolve().parents or root.resolve() == p.resolve()
    except Exception:  # noqa: BLE001
        return False


def resolve(token: str) -> dict | None:
    """Decode a media token to something the API can serve. Returns either
    {'kind':'asar','archive':..,'inner':..} or {'kind':'file','path':..}."""
    try:
        parts = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except Exception:  # noqa: BLE001
        return None
    if parts[0] == "asar" and len(parts) == 3:
        ap = Path(parts[1])
        if not _under_starfinder(ap) or not ap.exists():
            return None
        return {"kind": "asar", "archive": str(ap), "inner": parts[2]}
    if parts[0] == "file" and len(parts) == 3:
        root = Path(parts[1]).resolve()
        if not any((_root(n) and _root(n).resolve() == root) for n in PROVIDERS):
            return None
        f = (root / parts[2]).resolve()
        if root in f.parents and f.exists():
            return {"kind": "file", "path": str(f)}
    return None


def read_media(token: str) -> tuple[bytes, str] | None:
    """Return (bytes, media_type) for a token, or None. SVGs from StarFinder are
    wrapped with a viewBox + white background so they render in the dark panel."""
    r = resolve(token)
    if not r:
        return None
    if r["kind"] == "asar":
        data = asar.read_file(r["archive"], r["inner"])
        if data is None:
            return None
        if r["inner"].lower().endswith(".svg"):
            return _wrap_svg(data.decode("utf-8", "replace")).encode("utf-8"), "image/svg+xml"
        mime = _mime(r["inner"])
        return data, mime
    if r["kind"] == "file":
        return Path(r["path"]).read_bytes(), _mime(r["path"])
    return None


def _mime(name: str) -> str:
    n = name.lower()
    for ext, m in ((".svg", "image/svg+xml"), (".png", "image/png"),
                   (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
                   (".gif", "image/gif"), (".htm", "text/html"), (".html", "text/html")):
        if n.endswith(ext):
            return m
    return "application/octet-stream"


def _wrap_svg(svg: str) -> str:
    """StarFinder connector SVGs are meant to be injected inline by the app: the
    root <svg> has no xmlns and uses width/height:100%, so as a standalone <img>
    source they fail to render. Add the SVG namespace, drop the collapsing size
    style, give a viewBox sized from the largest coordinate, and a white page
    background (their strokes/text are black)."""
    head = svg[:300]
    if "xmlns" not in head:
        # declare the SVG namespace plus every prefix actually used (StarFinder
        # diagrams carry custom hotspot attrs like daisy:… which otherwise make
        # the standalone file invalid XML — "unbound prefix").
        prefixes = set(re.findall(r"<\s*(\w+):", svg)) | set(re.findall(r'[\s"](\w+):[\w-]+\s*=', svg))
        prefixes -= {"xml", "xmlns", "xlink"}
        ns = ['xmlns="http://www.w3.org/2000/svg"',
              'xmlns:xlink="http://www.w3.org/1999/xlink"']
        ns += [f'xmlns:{p}="urn:macdiag:{p}"' for p in sorted(prefixes)]
        svg = svg.replace("<svg", "<svg " + " ".join(ns), 1)
    # remove the app's width/height:100% style (collapses to 0 height in <img>)
    svg = re.sub(r'\s*style="width:\s*100%;\s*height:\s*100%;\s*"', "", svg, count=1)
    # tight viewBox from real coordinates: max X and max Y separately (square
    # would leave huge whitespace on wide connectors). Ignore stray text numbers.
    xs = [float(v) for v in re.findall(r'\b(?:x|cx)="([-\d.]+)"', svg)]
    ys = [float(v) for v in re.findall(r'\b(?:y|cy)="([-\d.]+)"', svg)]
    for blob in re.findall(r'(?:points|d)="([^"]+)"', svg):
        nums = [float(n) for n in re.findall(r"-?\d+\.?\d+|-?\d+", blob)]
        xs += nums[0::2]
        ys += nums[1::2]
    w = int(max(xs, default=400)) + 20
    h = int(max(ys, default=400)) + 20
    if "viewBox" not in svg[:200]:
        # explicit width/height too — Safari renders SVG-as-<img> at 0 height
        # without an intrinsic size.
        svg = svg.replace(
            "<svg",
            f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet"',
            1)
    bg = f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>'
    i = svg.find(">")
    return svg[:i + 1] + bg + svg[i + 1:]


# ---- the actual lookup -----------------------------------------------------

def lookup(code: str | None = None, module: dict | None = None, lang: str = "ru") -> list[dict]:
    """Real pictures for this ECU from StarFinder: connector pinout(s)."""
    items: list[dict] = []
    archive = _archive_for_module(module)
    if not archive or not module:
        return items
    comp = COMPONENT_CODE.get(str(module.get("id", "")).lower())
    if not comp:
        return items
    index = _index_for(archive)

    # connector pinout(s)
    title0 = _PIN.get(lang, _PIN["en"])
    for inner in _connector_files(index, comp)[:8]:
        label = inner.rsplit("/", 1)[-1].rsplit(".", 1)[0].upper().replace("_", "/")
        items.append({
            "kind": "image", "provider": "starfinder",
            "title": f"{title0} · {label}",
            "src": "/api/diag/media/raw?token=" + _tok("asar", str(archive), inner),
        })

    # installation location photo(s) + component name
    name, location, photos = _locator(index, archive, comp)
    loc0 = _LOC.get(lang, _LOC["en"])
    for inner, variant in photos[:4]:
        cap = loc0 + (f" · {location}" if location else "")
        if variant and variant != location:
            cap += f" ({variant})"
        items.append({
            "kind": "image", "provider": "starfinder", "title": cap,
            "src": "/api/diag/media/raw?token=" + _tok("asar", str(archive), inner),
        })

    # wiring diagram(s) that show this component
    dia0 = _DIA.get(lang, _DIA["en"])
    for inner in _diagram_index(archive).get(comp, [])[:6]:
        did = inner.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        items.append({
            "kind": "image", "provider": "starfinder",
            "title": f"{dia0} · {did}",
            "src": "/api/diag/media/raw?token=" + _tok("asar", str(archive), inner),
        })

    # description doc(s) from sysinfo (opened as HTML pages, not images)
    series = archive.stem
    for inner in _doc_index(archive).get(comp, [])[:4]:
        items.append({
            "kind": "doc", "provider": "starfinder",
            "title": _doc_title(archive, inner),
            "src": f"/api/diag/sf/{series}{inner}",
        })
    return items


def component_for(module: dict | None) -> dict:
    """{code, name} for the ECU's MB component, for the panel header."""
    archive = _archive_for_module(module)
    code = COMPONENT_CODE.get(str((module or {}).get("id", "")).lower())
    if not archive or not code:
        return {}
    return {"code": _denorm(code), "name": component_name(archive, code)}


def serve_path(series: str, inner: str) -> tuple[bytes, str] | None:
    """Serve any file from a chassis archive by series + inner path (for the
    description-page static endpoint)."""
    ap = _archive_path(series)
    if not ap:
        return None
    inner = "/" + inner.lstrip("/")
    if inner.lower().endswith(".svg"):
        data = asar.read_file(str(ap), inner)
        return (_wrap_svg(data.decode("utf-8", "replace")).encode("utf-8"),
                "image/svg+xml") if data else None
    data = asar.read_file(str(ap), inner)
    return (data, _mime(inner)) if data is not None else None

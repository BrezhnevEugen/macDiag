#!/usr/bin/env python3
"""Extract topical links from Safari/Netscape bookmark exports."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT / "data" / "references" / "safari_bookmarks_2026-06-17"


KEYWORD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("can", re.compile(r"(?<![a-z])can(?![a-z])|can[-_ ]?bus|can[-_ ]?шина|canhacker", re.I)),
    ("can-hardware", re.compile(r"\bmcp2515\b|\blawicel\b|\bcanny\b", re.I)),
    (
        "mercedes-network",
        re.compile(
            r"общ[а-я]+ сеть обмена данными|сеть обмена данными|data exchange network|"
            r"data bus|body bus|chassis bus|can[-_ ]?[bc]\b|can[-_ ]?gateway",
            re.I,
        ),
    ),
    ("uds", re.compile(r"\buds\b|unified diagnostic", re.I)),
    ("iso-tp", re.compile(r"iso[-_ ]?tp|\bisotp\b", re.I)),
    ("j2534", re.compile(r"\bj2534\b|pass.?thru|passthr", re.I)),
    ("openport", re.compile(r"open.?port|openport|\btactrix\b", re.I)),
    ("obd", re.compile(r"\bobd2?\b|\belm327\b", re.I)),
    ("kwp", re.compile(r"\bkwp(?:2000)?\b", re.I)),
    ("doip", re.compile(r"\bdoip\b", re.I)),
    ("xentry", re.compile(r"\bxentry\b|\bdas\b|star diagnosis", re.I)),
    ("vediamo", re.compile(r"\bvediamo\b|\bcbf\b|\bseedcalc\b", re.I)),
    ("gateway", re.compile(r"\bgateway\b", re.I)),
    ("dtc", re.compile(r"\bdtc\b|diagnostic trouble|код[аы]? ошибок|ошибк", re.I)),
]

AUTOMOTIVE_CONTEXT = re.compile(
    r"mercedes|benz|w163|w164|x164|w166|w211|w212|e211|ntg|comand|"
    r"авто|автомоб|мотор|двигател|эбу|\becu\b|obd|canhacker|xentry|"
    r"vediamo|\bcbf\b|j2534|open.?port|tactrix|star diagnosis",
    re.I,
)
WEAK_CONTEXT_TAGS = {"gateway", "dtc"}


@dataclass
class Bookmark:
    title: str
    url: str
    source: str
    folders: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def folder_path(self) -> str:
        return " / ".join(self.folders)


def _clean(text: str) -> str:
    return " ".join((text or "").split())


class SafariBookmarkParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.bookmarks: list[Bookmark] = []
        self._folder_stack: list[str] = []
        self._dl_folder_marks: list[bool] = []
        self._pending_folder: str | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._link_attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {k.upper(): v or "" for k, v in attrs}
        if tag == "dl":
            if self._pending_folder is not None:
                self._folder_stack.append(self._pending_folder)
                self._dl_folder_marks.append(True)
                self._pending_folder = None
            else:
                self._dl_folder_marks.append(False)
        elif tag == "h3":
            self._capture = "h3"
            self._buffer = []
        elif tag == "a":
            self._capture = "a"
            self._buffer = []
            self._link_attrs = attr_map

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "h3" and self._capture == "h3":
            self._pending_folder = _clean("".join(self._buffer)) or "Untitled"
            self._capture = None
            self._buffer = []
        elif tag == "a" and self._capture == "a":
            title = _clean("".join(self._buffer))
            url = self._link_attrs.get("HREF", "").strip()
            if url:
                self.bookmarks.append(
                    Bookmark(
                        title=title or url,
                        url=url,
                        source=self.source,
                        folders=list(self._folder_stack),
                        attrs=dict(self._link_attrs),
                    )
                )
            self._capture = None
            self._buffer = []
            self._link_attrs = {}
        elif tag == "dl" and self._dl_folder_marks:
            if self._dl_folder_marks.pop() and self._folder_stack:
                self._folder_stack.pop()


def parse_bookmarks(path: Path) -> list[Bookmark]:
    parser = SafariBookmarkParser(path.name)
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.bookmarks


def discover_inputs(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.rglob("*.html")))
            found.extend(sorted(path.rglob("*.htm")))
        elif path.exists():
            found.append(path)
    return found


def tags_for(bookmark: Bookmark) -> list[str]:
    haystack = "\n".join([
        bookmark.title,
        bookmark.url,
        bookmark.folder_path,
        urlparse(bookmark.url).netloc,
    ])
    tags = [tag for tag, pattern in KEYWORD_PATTERNS if pattern.search(haystack)]
    if not tags:
        return []
    has_context = bool(AUTOMOTIVE_CONTEXT.search(haystack))
    strong_tags = [tag for tag in tags if tag not in WEAK_CONTEXT_TAGS]
    if not strong_tags and not has_context:
        return []
    if not has_context:
        tags = strong_tags
    return tags


def collect(inputs: list[Path]) -> dict:
    by_url: dict[str, dict] = {}
    total = 0
    for path in inputs:
        for bookmark in parse_bookmarks(path):
            total += 1
            tags = tags_for(bookmark)
            if not tags:
                continue
            row = by_url.setdefault(
                bookmark.url,
                {
                    "title": bookmark.title,
                    "url": bookmark.url,
                    "domain": urlparse(bookmark.url).netloc,
                    "tags": [],
                    "folders": [],
                    "sources": [],
                    "attrs": {},
                },
            )
            row["tags"] = sorted(set(row["tags"]) | set(tags))
            if bookmark.folder_path and bookmark.folder_path not in row["folders"]:
                row["folders"].append(bookmark.folder_path)
            if bookmark.source not in row["sources"]:
                row["sources"].append(bookmark.source)
            for key in ("ADD_DATE", "LAST_VISIT", "PRIVATE"):
                if bookmark.attrs.get(key) and key.lower() not in row["attrs"]:
                    row["attrs"][key.lower()] = bookmark.attrs[key]

    rows = sorted(
        by_url.values(),
        key=lambda r: (
            r["folders"][0] if r["folders"] else "",
            r["domain"],
            r["title"].lower(),
        ),
    )
    return {
        "input_files": [str(p) for p in inputs],
        "total_bookmarks_seen": total,
        "matched_count": len(rows),
        "keywords": [tag for tag, _ in KEYWORD_PATTERNS],
        "bookmarks": rows,
    }


def write_markdown(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = {}
    for row in data["bookmarks"]:
        key = row["folders"][0] if row["folders"] else "(без папки)"
        grouped.setdefault(key, []).append(row)

    lines = [
        "# CAN / diagnostic bookmarks",
        "",
        f"Matched links: {data['matched_count']}",
        f"Total bookmarks scanned: {data['total_bookmarks_seen']}",
        "",
    ]
    for folder, rows in sorted(grouped.items()):
        lines.append(f"## {folder}")
        lines.append("")
        for row in rows:
            tags = ", ".join(row["tags"])
            sources = ", ".join(row["sources"])
            lines.append(f"- [{row['title']}]({row['url']})")
            lines.append(f"  - tags: {tags}")
            if row["folders"]:
                lines.append(f"  - safari_folder: {' | '.join(row['folders'])}")
            lines.append(f"  - source: {sources}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "input",
        nargs="+",
        type=Path,
        help="Safari/Netscape bookmark HTML file or directory",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=DEFAULT_OUT_DIR / "can_bookmarks.json",
    )
    ap.add_argument(
        "--out-md",
        type=Path,
        default=DEFAULT_OUT_DIR / "can_bookmarks.md",
    )
    args = ap.parse_args(argv)

    inputs = discover_inputs(args.input)
    if not inputs:
        raise SystemExit("No HTML bookmark files found")

    data = collect(inputs)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(data, args.out_md)
    print(json.dumps({
        "inputs": len(inputs),
        "total_bookmarks_seen": data["total_bookmarks_seen"],
        "matched_count": data["matched_count"],
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

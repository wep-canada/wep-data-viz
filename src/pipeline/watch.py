"""Watch the web pages that have no API for changes.

The ISC evacuation statistics, the BC season summary, the cultural/prescribed fire page
and the FireSmart funding page publish numbers as prose once in a while. Scraping prose
into numbers automatically is brittle, so this tool does something simpler and safer: it
fingerprints each page's visible text, and when a page changes it writes a short report
(the weekly GitHub Action turns that into an issue). You then update
``data/curated/indicators.csv`` by hand, with the source link and date.

    python -m pipeline.watch --report-path report.md

The first run only records a baseline. If a page fingerprints differently every week
because of a date or counter in its footer, add a regex to that page's ``ignore`` tuple.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from core import config
from core.http import get_text
from core.io import read_json, write_json


@dataclass(frozen=True)
class WatchedPage:
    key: str
    label: str
    url: str
    ignore: tuple[str, ...] = ()


PAGES = [
    WatchedPage("isc_evacuations", "ISC wildland fire and flood evacuation statistics",
                "https://www.sac-isc.gc.ca/eng/1583177459681/1583177553276"),
    WatchedPage("bc_season_summary", "BC Wildfire Service season summary",
                "https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/wildfire-history/wildfire-season-summary"),
    WatchedPage("bc_cultural_fire", "BC cultural and prescribed fire",
                "https://www2.gov.bc.ca/gov/content/safety/wildfire-status/prevention/prescribed-burning"),
    WatchedPage("bc_firesmart_funding", "BC FireSmart Community Funding and Supports",
                "https://www2.gov.bc.ca/gov/content/safety/wildfire-status/prevention/funding-for-wildfire-prevention/crip/fcfs"),
]


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def visible_text(html: str, ignore: tuple[str, ...] = ()) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(" ".join(parser.parts).split())
    for pattern in ignore:
        text = re.sub(pattern, "", text)
    return text


def fingerprint(html: str, ignore: tuple[str, ...] = ()) -> str:
    return hashlib.sha256(visible_text(html, ignore).encode("utf-8")).hexdigest()


@dataclass
class Change:
    page: WatchedPage
    kind: str            # "baseline" | "unchanged" | "changed" | "error"
    detail: str = ""


def hashes_path() -> Path:
    return config.WATCH_DIR / "hashes.json"


def check_pages(pages: list[WatchedPage] = PAGES,
                fetch: Callable[[str], str] = get_text) -> list[Change]:
    store = read_json(hashes_path(), default={}) or {}
    changes: list[Change] = []
    for page in pages:
        try:
            digest = fingerprint(fetch(page.url), page.ignore)
        except Exception as exc:  # noqa: BLE001
            changes.append(Change(page, "error", f"{type(exc).__name__}: {exc}"))
            continue
        previous = store.get(page.key, {}).get("sha256")
        if previous is None:
            changes.append(Change(page, "baseline"))
        elif previous != digest:
            changes.append(Change(page, "changed"))
        else:
            changes.append(Change(page, "unchanged"))
        store[page.key] = {"sha256": digest, "url": page.url}
    write_json(hashes_path(), store)
    return changes


def render_report(changes: list[Change]) -> str:
    """Markdown for a GitHub issue. Empty string when nothing needs attention."""
    changed = [c for c in changes if c.kind == "changed"]
    errors = [c for c in changes if c.kind == "error"]
    if not changed:
        return ""
    lines = ["These source pages changed since the last check. Review them and update "
             "`data/curated/indicators.csv` (value, definition, source link, origin) if a "
             "number changed.", ""]
    for c in changed:
        lines.append(f"- [{c.page.label}]({c.page.url})")
    if errors:
        lines += ["", "Pages that could not be checked this time:"]
        lines += [f"- {c.page.label}: {c.detail}" for c in errors]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--report-path", help="write a Markdown report here only if something changed")
    args = parser.parse_args(argv)

    changes = check_pages()
    for c in changes:
        suffix = f" ({c.detail})" if c.detail else ""
        print(f"{c.kind:9} {c.page.key}{suffix}")
    report = render_report(changes)
    if report and args.report_path:
        Path(args.report_path).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

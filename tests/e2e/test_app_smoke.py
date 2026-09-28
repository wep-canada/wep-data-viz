"""Start the real app on synthetic data and click through it in a headless browser.

Run with:  pytest -m e2e      (needs `playwright install chromium` once)
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

import pytest

from helpers import prepare_data_dir

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]

# Console noise that does not affect users: map tiles are blocked in some CI sandboxes, and
# switching tabs while a chart is still initialising can log an anywidget teardown message.
IGNORABLE = ("Failed to load resource", "ERR_TUNNEL", "[anywidget] Failed to initialize model")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = prepare_data_dir(tmp_path_factory.mktemp("e2e") / "data")
    port = free_port()
    env = {**os.environ, "WEPDASH_DATA_DIR": str(data), "WEPDASH_LIVE_FETCH": "0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "shiny", "run", "--port", str(port), str(ROOT / "src" / "app.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT, text=True)

    # Drain the app's stdout for as long as the server runs. If nobody reads a subprocess's
    # stdout, the OS pipe buffer (commonly 64 KB) fills once enough is logged, and the child
    # blocks on its next print — which freezes its whole event loop, including HTTP requests
    # that have nothing to do with logging. That looks like the *browser* timing out on
    # navigation, with no clue in the traceback that the app itself is the one stuck.
    log_tail: deque[str] = deque(maxlen=200)

    def _drain() -> None:
        for line in proc.stdout:
            log_tail.append(line)

    threading.Thread(target=_drain, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            proc.terminate()
            pytest.fail("app did not start:\n" + "".join(log_tail))
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def new_page(browser):
    """A factory for a fresh browser context+page, closed at the end of THIS test.

    Each context opens its own Shiny session (its own websocket and its own copy of the
    reactive graph, including the periodic timers in page.py and sources.py). Earlier this
    only closed the whole module-scoped browser at the very end, so every earlier test's
    session stayed open and live for the rest of the module. On Windows that reliably made
    every navigation after the first one hang until Playwright's 30s timeout — closing each
    context right after its test is the fix, independent of what exactly caused the hang.
    """
    contexts = []

    def _make(scheme="light"):
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme=scheme)
        contexts.append(ctx)
        return ctx.new_page()

    yield _make
    for ctx in contexts:
        ctx.close()


def open_page(new_page, url, scheme="light"):
    page = new_page(scheme)
    problems: list[str] = []
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    # domcontentloaded rather than the default "load": Shiny keeps a websocket open once the
    # document is parsed, and on a slow machine waiting for full "load" (every resource settled)
    # can run long for no useful reason, since the selectors below are the real readiness check.
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_selector(".kpi-value", timeout=30000)
    page.wait_for_selector(".js-plotly-plot .main-svg", timeout=30000)
    page.wait_for_timeout(1500)
    return page, problems


def real_problems(problems):
    return [p for p in problems if not any(marker in p for marker in IGNORABLE)]


def clear_filters(page):
    """Reset the sidebar's Fire centre / Fire status / Cause pickers back to "show
    everything". The dashboard now opens narrowed to a representative default instead of
    showing every fire at once (see ``filters.default_selection``), so a test that wants
    the full, unfiltered data has to clear these chips first. Min size and the layers
    checkboxes aren't selectize controls, so this only ever touches the three that are.

    Removing a chip gives its control focus, which pops open a dropdown of the remaining
    options - left open, that dropdown sits on top of and intercepts the next chip's own
    remove click. ``force=True`` clicks through it regardless, and Escape closes it before
    the next iteration so later clicks land normally too.

    Clearing all three filters means three separate round trips to the server (one per
    input), each swapping the map's overlay layers in place (see ``mapview.update_layers``)
    - so the fire count on screen passes through a few in-between values before settling.
    A caller that queries the map (its markers, click handlers) right after this returns
    would be racing that settling: it could click a marker from a layer that's about to be
    replaced, and the click silently goes nowhere. Waiting here for the fully-cleared
    count (all 24 active fires) makes the wait this function's problem, not every caller's.
    """
    remove = page.locator(".selectize-control .item .remove")
    while remove.count():
        remove.first.click(force=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
    page.wait_for_function("document.body.innerText.includes('Showing 24 fires')", timeout=15000)


def test_overview_renders_headline_numbers_and_charts(new_page, server):
    page, problems = open_page(new_page, server)
    assert page.title() == "WEP Canada wildfire resilience dashboard"
    values = page.locator(".kpi-value").all_inner_texts()
    assert len(values) == 5 and all(v.strip() and v != "—" for v in values)
    assert page.locator(".leaflet-container").count() == 1
    assert page.locator(".pill").count() == 4
    assert page.locator(".js-plotly-plot").count() >= 3
    assert real_problems(problems) == []


def test_filters_start_narrowed_to_a_default_not_everything(new_page, server):
    page, _ = open_page(new_page, server)
    chips = page.locator(".selectize-control .item").all_inner_texts()
    assert any("Under Control" in c for c in chips)          # the Fire status default
    assert len(chips) >= 2                                    # Fire centre and Cause narrowed too
    # The DataGrid's own "Viewing rows..." summary only renders once there are enough rows
    # to need paging, so it can be entirely absent for a narrowed default - the always-on
    # ".map-note" ("Showing N fires...") is the reliable signal here instead.
    page.wait_for_function(
        "document.querySelector('.map-note') && "
        "!document.querySelector('.map-note').innerText.includes('Showing 24 fires')",
        timeout=15000)
    text = page.locator(".map-note").inner_text()
    assert "Showing 24 fires" not in text                      # narrower than "show everything"


def test_clicking_a_fire_shows_its_details(new_page, server):
    page, _ = open_page(new_page, server)
    clear_filters(page)                       # the default view can hide Out of Control fires
    markers = page.locator("path.leaflet-interactive")
    for i in range(markers.count()):
        if (markers.nth(i).get_attribute("fill") or "").lower() == "#eb6834":
            markers.nth(i).click(force=True)
            break
    page.wait_for_selector(".fire-detail", timeout=10000)
    text = page.locator(".fire-detail").inner_text()
    assert "Status" in text and "Out of Control" in text and "Size" in text


def test_filters_change_the_fire_list(new_page, server):
    page, _ = open_page(new_page, server)
    clear_filters(page)
    page.wait_for_selector(".shiny-data-grid-summary", timeout=15000)
    page.wait_for_function("document.body.innerText.includes('of 24')", timeout=15000)
    page.get_by_label("Include fires declared out").check()
    page.wait_for_function("document.body.innerText.includes('of 40')", timeout=15000)


def test_other_tabs_render(new_page, server):
    page, problems = open_page(new_page, server)
    page.get_by_role("tab", name="Equity and governance").click()
    page.wait_for_selector("text=11,848", timeout=15000)
    assert "Definitions differ between years" in page.inner_text("body")
    page.get_by_role("tab", name="Data gaps").click()
    page.get_by_text("Who is affected differently by gender?").click()
    page.wait_for_selector("text=should not be converted into BC estimates", timeout=10000)
    page.get_by_role("tab", name="Data and sources").click()
    page.wait_for_selector("table.sources-table", timeout=10000)
    assert "Open Government Licence" in page.inner_text("body")
    assert real_problems(problems) == []


def test_dark_mode_switches_theme_and_charts(new_page, server):
    page, _ = open_page(new_page, server, scheme="dark")
    assert page.evaluate("document.documentElement.getAttribute('data-bs-theme')") == "dark"
    background = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert background == "rgb(18, 18, 17)"               # --wd-page in dark mode

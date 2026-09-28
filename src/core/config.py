"""Paths and runtime settings.

Everything can be overridden with an environment variable so tests and
alternate deployments never touch the real data folders. Other modules must
read these as ``config.LIVE_DIR`` (attribute access at call time), not
``from core.config import LIVE_DIR``, so tests can monkeypatch them.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from a local .env / .env.local file (never overrides real environment variables)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


for _name in (".env", ".env.local"):
    _load_dotenv(ROOT / _name)


def _path(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else default


def _flag(env: str, default: bool) -> bool:
    value = os.environ.get(env)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


# Machine-written data (pipeline output). Safe to point elsewhere for tests.
DATA_DIR = _path("WEPDASH_DATA_DIR", ROOT / "data")
LIVE_DIR = DATA_DIR / "live"
HISTORY_DIR = DATA_DIR / "history"
WATCH_DIR = DATA_DIR / "watch"
FRESHNESS_PATH = DATA_DIR / "freshness.json"

# Human-written data (hand-verified indicators, documented data gaps).
CURATED_DIR = _path("WEPDASH_CURATED_DIR", ROOT / "data" / "curated")

# Live-tier behaviour inside the running app.
LIVE_FETCH_ENABLED = _flag("WEPDASH_LIVE_FETCH", True)
LIVE_TTL_SECONDS = int(os.environ.get("WEPDASH_LIVE_TTL", "900"))
LIVE_FAILURE_TTL_SECONDS = int(os.environ.get("WEPDASH_LIVE_FAILURE_TTL", "120"))
HTTP_TIMEOUT = float(os.environ.get("WEPDASH_HTTP_TIMEOUT", "20"))

# Base map: CARTO asks for a free key on its raster tiles. Without one the map still works but
# carries an "API KEY REQUIRED" watermark. The key is visible in the browser, so restrict it to
# your website(s) in CARTO's key settings. Set it as an environment variable, never in git.
CARTO_KEY = os.environ.get("WEPDASH_CARTO_KEY", "").strip()

# Identify ourselves politely to the servers we call.
CONTACT = os.environ.get("WEPDASH_CONTACT", "wep-canada wildfire dashboard")
USER_AGENT = f"WEP-Canada-Wildfire-Dashboard/0.1 ({CONTACT})"

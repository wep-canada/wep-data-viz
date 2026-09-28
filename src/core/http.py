"""HTTP helpers with a polite User-Agent, a timeout and a couple of retries."""

from __future__ import annotations

import time
from typing import Any

import requests

from . import config


class FetchError(RuntimeError):
    """A source could not be fetched or returned something we cannot use."""


def _get(url: str, *, params: dict | None, timeout: float | None, retries: int,
         backoff: float, accept: str, session: Any = None):
    client = session or requests
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.get(
                url,
                params=params,
                timeout=timeout or config.HTTP_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT, "Accept": accept},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt < retries:
                time.sleep(backoff**attempt)
    raise FetchError(f"GET {url} failed: {last}") from last


def get_json(url: str, params: dict | None = None, *, timeout: float | None = None,
             retries: int = 2, backoff: float = 1.5, session: Any = None) -> Any:
    response = _get(url, params=params, timeout=timeout, retries=retries,
                    backoff=backoff, accept="application/json", session=session)
    try:
        return response.json()
    except ValueError as exc:
        raise FetchError(f"GET {url} did not return JSON: {exc}") from exc


def get_text(url: str, *, timeout: float | None = None, retries: int = 1,
             backoff: float = 1.5, session: Any = None) -> str:
    response = _get(url, params=None, timeout=timeout, retries=retries,
                    backoff=backoff, accept="text/html,*/*", session=session)
    return response.text

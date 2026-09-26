"""httpx client for the TypeSafe System One ``noul`` endpoint."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

import httpx

from jevq import __version__

DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"

_MAX_RETRY_AFTER = 10.0
_BASE_BACKOFF = 0.5


class JevqAPIError(Exception):
    """System One call failed; never a "no" answer."""


def _retry_after(resp: httpx.Response | None) -> float | None:
    if resp is None:
        return None
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return min(value, _MAX_RETRY_AFTER)


def _is_retryable(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


class SystemOneClient:
    """Ask System One one ``noul`` question about one state per call."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        url: str = DEFAULT_URL,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.url = url
        self.max_retries = max_retries
        self._sleep = sleep
        self._http = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": f"jevq/{__version__}",
            },
        )

    def build_body(self, state: Any, question: str) -> dict:
        return {
            "model": self.model,
            "state": state,
            "questions": {"q": {"type": "noul", "instructions": question}},
        }

    def noul(self, state: Any, question: str) -> float:
        body = self.build_body(state, question)
        attempts = self.max_retries + 1
        last_error = ""
        for attempt in range(attempts):
            resp: httpx.Response | None = None
            try:
                resp = self._http.post(self.url, json=body)
            except httpx.TransportError as exc:
                last_error = f"transport error: {type(exc).__name__}"
            else:
                if resp.is_success:
                    return _parse_noul(resp)
                if not _is_retryable(resp.status_code):
                    raise JevqAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                last_error = f"HTTP {resp.status_code}"
            if attempt < self.max_retries:
                delay = _retry_after(resp)
                if delay is None:
                    delay = _BASE_BACKOFF * 2**attempt
                self._sleep(delay)
        raise JevqAPIError(f"{last_error} after {attempts} attempts")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SystemOneClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _parse_noul(resp: httpx.Response) -> float:
    try:
        value = resp.json()["answers"]["q"]["noul"]
    except ValueError as exc:
        raise JevqAPIError(f"invalid response: not JSON ({exc})") from None
    except (KeyError, TypeError, IndexError):
        raise JevqAPIError("invalid response: missing answers.q.noul") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevqAPIError(f"invalid response: noul is {type(value).__name__}, not a number")
    try:
        score = float(value)
    except OverflowError:
        score = math.inf
    if not math.isfinite(score):
        raise JevqAPIError("invalid response: noul is not finite")
    return score

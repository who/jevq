import json

import httpx
import pytest

from jevq import __version__
from jevq.client import DEFAULT_MODEL, JevqAPIError, SystemOneClient

KEY = "sk-secret-test-key"
URL = "https://example.test/v1/systemone"


def ok(noul):
    return httpx.Response(200, json={"answers": {"q": {"noul": noul}}})


def make_client(responses, sleeps=None, **kwargs):
    """Client whose transport replays ``responses`` (Response or Exception) in order."""
    requests = []
    queue = list(responses)

    def handler(request):
        requests.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    sleep = (sleeps.append if sleeps is not None else lambda _: None)
    client = SystemOneClient(
        KEY, url=URL, transport=httpx.MockTransport(handler), sleep=sleep, **kwargs
    )
    return client, requests


def test_body_and_headers():
    client, requests = make_client([ok(0.9)])
    with client:
        client.noul({"id": 1}, "is it open")
    (req,) = requests
    assert req.method == "POST"
    assert str(req.url) == URL
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert req.headers["User-Agent"] == f"jevq/{__version__}"
    assert req.headers["Content-Type"] == "application/json"
    assert json.loads(req.content) == {
        "model": DEFAULT_MODEL,
        "state": {"id": 1},
        "questions": {"q": {"type": "noul", "instructions": "is it open"}},
    }


def test_returns_float_noul():
    client, _ = make_client([ok(0.25), ok(1)])
    assert client.noul(1, "q") == 0.25
    value = client.noul(1, "q")
    assert value == 1.0 and isinstance(value, float)


def test_retries_429_then_succeeds():
    sleeps = []
    client, requests = make_client(
        [httpx.Response(429), httpx.Response(429), ok(0.7)], sleeps
    )
    assert client.noul("s", "q") == 0.7
    assert len(requests) == 3
    assert sleeps == [0.5, 1.0]


def test_retry_after_header_used_and_capped():
    sleeps = []
    client, _ = make_client(
        [
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(503, headers={"Retry-After": "120"}),
            httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
            ok(0.1),
        ],
        sleeps,
    )
    assert client.noul("s", "q") == 0.1
    assert sleeps == [3.0, 10.0, 2.0]


def test_5xx_exhaustion_raises_after_4_attempts():
    sleeps = []
    client, requests = make_client([httpx.Response(500)] * 4, sleeps)
    with pytest.raises(JevqAPIError, match=r"HTTP 500 after 4 attempts"):
        client.noul("s", "q")
    assert len(requests) == 4
    assert sleeps == [0.5, 1.0, 2.0]


def test_401_not_retried():
    client, requests = make_client([httpx.Response(401, text="bad key")])
    with pytest.raises(JevqAPIError, match=r"HTTP 401: bad key"):
        client.noul("s", "q")
    assert len(requests) == 1


def test_transport_error_retried():
    sleeps = []
    client, requests = make_client(
        [httpx.ConnectError("boom"), httpx.ReadTimeout("slow"), ok(0.4)], sleeps
    )
    assert client.noul("s", "q") == 0.4
    assert len(requests) == 3
    assert sleeps == [0.5, 1.0]


def test_transport_error_exhaustion_raises():
    client, _ = make_client([httpx.ConnectError("boom")] * 4)
    with pytest.raises(JevqAPIError, match=r"ConnectError after 4 attempts"):
        client.noul("s", "q")


def test_missing_noul_raises():
    client, _ = make_client([httpx.Response(200, json={"answers": {}})])
    with pytest.raises(JevqAPIError, match="invalid response"):
        client.noul("s", "q")


def test_missing_non_json_raises():
    client, _ = make_client([httpx.Response(200, text="<html>")])
    with pytest.raises(JevqAPIError, match="invalid response"):
        client.noul("s", "q")


@pytest.mark.parametrize("value", [True, False])
def test_bool_noul_raises(value):
    client, _ = make_client([ok(value)])
    with pytest.raises(JevqAPIError, match="invalid response"):
        client.noul("s", "q")


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "\"0.5\"", "1e999"])
def test_nonfinite_or_string_noul_raises(raw):
    body = '{"answers": {"q": {"noul": %s}}}' % raw
    client, _ = make_client([httpx.Response(200, content=body.encode())])
    with pytest.raises(JevqAPIError, match="invalid response"):
        client.noul("s", "q")


def test_error_message_excludes_api_key():
    client, _ = make_client(
        [httpx.Response(403, text="forbidden"), httpx.ConnectError(KEY)]
        + [httpx.ConnectError(KEY)] * 3
    )
    with pytest.raises(JevqAPIError) as first:
        client.noul("s", "q")
    with pytest.raises(JevqAPIError) as second:
        client.noul("s", "q")
    for err in (first.value, second.value):
        assert KEY not in str(err)
        assert KEY not in repr(err)

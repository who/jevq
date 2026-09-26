import io
import json

import pytest

from jevq.cli import run
from jevq.client import DEFAULT_MODEL, DEFAULT_URL, JevqAPIError

KEY = {"TYPESAFE_API_KEY": "k"}


class FakeClient:
    def __init__(self, scores, fail_at=None):
        self.scores = list(scores)
        self.fail_at = fail_at
        self.calls = []
        self.closed = False
        self.config = None

    def noul(self, state, question):
        self.calls.append((state, question))
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise JevqAPIError("HTTP 500 after 4 attempts")
        return self.scores[len(self.calls) - 1]

    def close(self):
        self.closed = True


def _filter(data: bytes, argv, env=None, client=None):
    client = client or FakeClient([])
    stdout, stderr = io.BytesIO(), io.StringIO()

    def factory(api_key, model, url):
        client.config = (api_key, model, url)
        return client

    code = run(argv, io.BytesIO(data), stdout, stderr, KEY if env is None else env, client_factory=factory)
    return code, stdout.getvalue(), stderr.getvalue(), client


def test_keeps_values_at_or_above_threshold():
    data = b'{"id":1}\n{"id" : 2}\n{"id":3}\n{"id":4}\n'
    client = FakeClient([0.9, 0.5, 0.49, 1.0])
    code, out, err, client = _filter(data, ["q"], client=client)
    assert code == 0
    assert out == b'{"id":1}\n{"id" : 2}\n{"id":4}\n'
    assert err == "jevq: read 4, emitted 3\n"
    assert client.closed


def test_threshold_flag_overrides_env():
    client = FakeClient([0.7, 0.9])
    env = {**KEY, "JEV_THRESHOLD": "0.1"}
    code, out, _, _ = _filter(b"1\n2\n", ["-t", "0.8", "q"], env=env, client=client)
    assert code == 0
    assert out == b"2\n"


def test_env_threshold_used():
    client = FakeClient([0.7, 0.9])
    env = {**KEY, "JEV_THRESHOLD": "0.9"}
    code, out, _, _ = _filter(b"1\n2\n", ["q"], env=env, client=client)
    assert code == 0
    assert out == b"2\n"
    code, out, _, _ = _filter(b"1\n", ["q"], env={**KEY, "JEV_THRESHOLD": ""}, client=FakeClient([0.5]))
    assert out == b"1\n"


@pytest.mark.parametrize("value", ["1.5", "-0.1", "abc", "nan"])
def test_invalid_threshold_exits_2(value):
    stdin = io.BytesIO(b"1\n")
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = run(["-t", value, "q"], stdin, stdout, stderr, KEY, client_factory=lambda *a: FakeClient([]))
    assert code == 2
    assert stdout.getvalue() == b""
    assert stderr.getvalue() == "jevq: threshold must be a number in [0, 1]\n"
    assert stdin.tell() == 0
    code, _, err, _ = _filter(b"1\n", ["q"], env={**KEY, "JEV_THRESHOLD": value})
    assert code == 2


@pytest.mark.parametrize("env", [{}, {"TYPESAFE_API_KEY": "  "}])
def test_missing_api_key_exits_2_without_stdout(env):
    code, out, err, client = _filter(b'{"a":1}\n', ["q"], env=env)
    assert code == 2
    assert out == b""
    assert err == "jevq: TYPESAFE_API_KEY is not set\n"
    assert client.config is None


def test_fields_projects_state_but_emits_full_line():
    data = b'{"id":1,"body":"x","z":0}\n{"z":2}\n'
    client = FakeClient([0.9, 0.9])
    code, out, _, client = _filter(data, ["-f", " body , id,", "q"], client=client)
    assert code == 0
    assert out == data
    assert client.calls[0][0] == {"body": "x", "id": 1}
    assert list(client.calls[0][0]) == ["body", "id"]
    assert client.calls[1][0] == {}


def test_fields_on_non_object_value():
    client = FakeClient([0.9, 0.9, 0.9])
    code, out, _, client = _filter(b'[1]\n"s"\nnull\n', ["-f", "a", "q"], client=client)
    assert code == 0
    assert [c[0] for c in client.calls] == [{"value": [1]}, {"value": "s"}, {"value": None}]
    code, _, _, client = _filter(b'{"a":1}\n', ["q"], client=FakeClient([0.1]))
    assert client.calls[0][0] == {"a": 1}


@pytest.mark.parametrize("fields", ["", " , ,"])
def test_empty_fields_exits_2(fields):
    code, out, err, _ = _filter(b"1\n", ["-f", fields, "q"])
    assert code == 2
    assert out == b""
    assert err == "jevq: --fields needs at least one key name\n"


def test_api_error_exits_1_and_stops():
    data = b"1\n2\n3\n4\n"
    client = FakeClient([0.9, 0.9], fail_at=3)
    code, out, err, client = _filter(data, ["q"], client=client)
    assert code == 1
    assert out == b"1\n2\n"
    assert len(client.calls) == 3
    assert err == "jevq: line 3: API error: HTTP 500 after 4 attempts\njevq: read 3, emitted 2\n"
    assert client.closed


def test_model_and_url_resolution():
    _, _, _, client = _filter(b"", ["q"])
    assert client.config == ("k", DEFAULT_MODEL, DEFAULT_URL)
    env = {**KEY, "JEV_MODEL": "env-model", "JEV_BASE_URL": "http://x/y"}
    _, _, _, client = _filter(b"", ["q"], env=env)
    assert client.config == ("k", "env-model", "http://x/y")
    _, _, _, client = _filter(b"", ["--model", "flag-model", "q"], env=env)
    assert client.config == ("k", "flag-model", "http://x/y")
    env = {**KEY, "JEV_MODEL": "", "JEV_BASE_URL": ""}
    code, _, _, client = _filter(b"", ["q"], env=env)
    assert code == 0
    assert client.config == ("k", DEFAULT_MODEL, DEFAULT_URL)
    assert client.calls == []


def test_question_sent_verbatim():
    question = "  the customer is asking for a \"refund\"  "
    client = FakeClient([0.2])
    _, _, _, client = _filter(json.dumps({"a": 1}).encode() + b"\n", [question], client=client)
    assert client.calls == [({"a": 1}, question)]

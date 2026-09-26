import io
import json

import pytest

from jevq.cli import format_score_line, run
from jevq.client import JevqAPIError

KEY = {"TYPESAFE_API_KEY": "k"}


class FakeClient:
    def __init__(self, scores, fail_at=None):
        self.scores = list(scores)
        self.fail_at = fail_at
        self.calls = []
        self.closed = False

    def noul(self, state, question):
        self.calls.append((state, question))
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise JevqAPIError("HTTP 500 after 4 attempts")
        return self.scores[len(self.calls) - 1]

    def close(self):
        self.closed = True


def _score(data: bytes, argv, env=None, client=None):
    client = client or FakeClient([])
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = run(
        ["--score", *argv],
        io.BytesIO(data),
        stdout,
        stderr,
        KEY if env is None else env,
        client_factory=lambda *_: client,
    )
    return code, stdout.getvalue(), stderr.getvalue(), client


def test_score_emits_every_row_in_order():
    client = FakeClient([0.1, 0.9, 0.5])
    code, out, err, client = _score(b'{"id":1}\n{"id":2}\n{"id":3}\n', ["q"], client=client)
    assert code == 0
    assert out == (
        b'{"score":0.1,"value":{"id":1}}\n'
        b'{"score":0.9,"value":{"id":2}}\n'
        b'{"score":0.5,"value":{"id":3}}\n'
    )
    assert err == "jevq: read 3, emitted 3\n"
    assert client.closed


def test_score_line_shape_numeric_score():
    assert format_score_line(1, b"{}") == b'{"score":1.0,"value":{}}\n'
    client = FakeClient([1, 0.25])
    code, out, _, _ = _score(b'{"a":1}\n{"a":2}\n', ["q"], client=client)
    assert code == 0
    lines = [json.loads(line) for line in out.splitlines()]
    assert [list(obj) for obj in lines] == [["score", "value"]] * 2
    assert all(isinstance(obj["score"], float) for obj in lines)
    assert [obj["score"] for obj in lines] == [1.0, 0.25]


def test_score_value_equals_input_and_raw_bytes_embedded():
    raw = b'{ "id" : 7,  "tags": ["a", "b"], "n": {"x": null} }'
    code, out, _, _ = _score(raw + b"\n", ["q"], client=FakeClient([0.3]))
    assert code == 0
    assert out == b'{"score":0.3,"value":' + raw + b"}\n"
    assert json.loads(out)["value"] == json.loads(raw)


def test_score_ignores_threshold_but_validates_it():
    client = FakeClient([0.1, 0.95])
    code, out, _, _ = _score(b"1\n2\n", ["-t", "0.9", "q"], client=client)
    assert code == 0
    assert out == b'{"score":0.1,"value":1}\n{"score":0.95,"value":2}\n'

    code, out, err, _ = _score(b"1\n", ["-t", "1.5", "q"])
    assert code == 2 and out == b""
    assert "threshold" in err
    code, out, _, _ = _score(b"1\n", ["q"], env={**KEY, "JEV_THRESHOLD": "abc"})
    assert code == 2 and out == b""


def test_score_uses_fields_projection():
    client = FakeClient([0.6])
    code, out, _, client = _score(b'{"a":1,"b":2,"c":3}\n', ["-f", "c,a", "q"], client=client)
    assert code == 0
    assert client.calls == [({"c": 3, "a": 1}, "q")]
    assert out == b'{"score":0.6,"value":{"a":1,"b":2,"c":3}}\n'


def test_score_api_error_exits_1():
    client = FakeClient([0.2, 0.4, 0.8], fail_at=2)
    code, out, err, client = _score(b"1\n2\n3\n", ["q"], client=client)
    assert code == 1
    assert out == b'{"score":0.2,"value":1}\n'
    assert "jevq: line 2: API error: HTTP 500 after 4 attempts" in err
    assert err.endswith("jevq: read 2, emitted 1\n")
    assert len(client.calls) == 2
    assert client.closed


def test_score_missing_key_exits_2():
    code, out, err, _ = _score(b"1\n", ["q"], env={})
    assert code == 2 and out == b""
    assert "TYPESAFE_API_KEY" in err


@pytest.mark.parametrize("raw", [b'"text"', b"[1, 2]", b"42", b"null", b"true"])
def test_score_non_object_value(raw):
    client = FakeClient([0.5])
    code, out, _, client = _score(raw + b"\n", ["q"], client=client)
    assert code == 0
    assert out == b'{"score":0.5,"value":' + raw + b"}\n"
    assert json.loads(out)["value"] == json.loads(raw)
    assert client.calls == [({"value": json.loads(raw)}, "q")]


def test_score_empty_stdin():
    client = FakeClient([])
    code, out, err, client = _score(b"", ["q"], client=client)
    assert code == 0 and out == b""
    assert client.calls == []
    assert err == "jevq: read 0, emitted 0\n"

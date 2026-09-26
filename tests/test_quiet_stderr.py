import io
import json

import httpx
import pytest

from jevq.cli import run
from jevq.client import SystemOneClient

LINES = b'{"id":1,  "a":"x"}\n{"id":2}\n{"id":3}\n'
KEY = {"TYPESAFE_API_KEY": "k"}


def make_factory(responses):
    """A real SystemOneClient on a MockTransport; one response per call."""
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = next(calls)
        return httpx.Response(status, json=body)

    def factory(api_key, model, url):
        return SystemOneClient(
            api_key, model, url, transport=httpx.MockTransport(handler), sleep=lambda s: None
        )

    return factory


def ok(noul, model="jev-1.13.0"):
    return 200, {"answers": {"q": {"noul": noul}}, "model": model}


def invoke(argv, responses=(), stdin=LINES, env=KEY):
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = run(argv, io.BytesIO(stdin), stdout, stderr, env, client_factory=make_factory(responses))
    return code, stdout.getvalue(), stderr.getvalue()


def test_pass_success_stderr_empty():
    code, out, err = invoke(["--pass"], env={})
    assert code == 0
    assert out == LINES
    assert err == ""
    code, out, err = invoke(["--pass"], stdin=b"", env={})
    assert (code, out, err) == (0, b"", "")


def test_filter_and_score_success_stderr_empty():
    code, out, err = invoke(["q"], [ok(0.9), ok(0.1), ok(0.5)])
    assert code == 0
    assert out == b'{"id":1,  "a":"x"}\n{"id":3}\n'
    assert err == ""

    code, out, err = invoke(["--score", "q"], [ok(0.9), ok(0.1), ok(0.5)])
    assert code == 0
    assert out == (
        b'{"score":0.9,"value":{"id":1,  "a":"x"}}\n'
        b'{"score":0.1,"value":{"id":2}}\n'
        b'{"score":0.5,"value":{"id":3}}\n'
    )
    assert err == ""

    code, out, err = invoke(["q"], stdin=b"")
    assert (code, out, err) == (0, b"", "")


def test_verbose_reports_counts_and_model():
    code, out, err = invoke(["-v", "q"], [ok(0.9), ok(0.1), ok(0.5)])
    assert code == 0
    assert out == b'{"id":1,  "a":"x"}\n{"id":3}\n'
    assert err.splitlines() == ["jevq: read 3, emitted 2", "jevq: model: jev-1.13.0"]

    code, _, err = invoke(["--score", "q", "--verbose"], [ok(0.9), ok(0.1), ok(0.5)])
    assert code == 0
    assert err.splitlines() == ["jevq: read 3, emitted 3", "jevq: model: jev-1.13.0"]


def test_verbose_pass_counts_without_model():
    code, out, err = invoke(["--pass", "-v"], env={})
    assert code == 0
    assert out == LINES
    assert err == "jevq: read 3, emitted 3\n"


def test_verbose_after_api_error():
    responses = [ok(0.9), (400, {"error": "bad"})]
    code, out, err = invoke(["-v", "q"], responses)
    assert code == 1
    assert out == b'{"id":1,  "a":"x"}\n'
    lines = err.splitlines()
    assert lines[0].startswith("jevq: line 2: API error: HTTP 400")
    assert lines[1:] == ["jevq: read 2, emitted 1", "jevq: model: jev-1.13.0"]


@pytest.mark.parametrize(
    ("argv", "responses", "stdin", "env", "code", "message"),
    [
        (["q"], [], LINES, {}, 2, "jevq: TYPESAFE_API_KEY is not set"),
        (["q"], [ok(0.9)], b'{"id":1}\nnot json\n', KEY, 1, "jevq: line 2: invalid JSON:"),
        (["--pass"], [], b'{"id":1}\nnot json\n', {}, 1, "jevq: line 2: invalid JSON:"),
        (["q"], [(503, {})] * 4, LINES, KEY, 1, "jevq: line 1: API error: HTTP 503 after 4 attempts"),
        (["-t", "2", "q"], [], LINES, KEY, 2, "jevq: threshold must be a number in [0, 1]"),
        ([], [], LINES, KEY, 2, "jevq: QUESTION is required unless --pass"),
    ],
)
def test_errors_reported_without_verbose(argv, responses, stdin, env, code, message):
    got, _, err = invoke(argv, responses, stdin=stdin, env=env)
    assert got == code
    lines = err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith(message)
    assert "jevq: read" not in err and "jevq: model:" not in err


def test_help_lists_verbose(capsys):
    assert run(["--help"], io.BytesIO(), io.BytesIO(), io.StringIO(), {}) == 0
    assert "-v, --verbose" in capsys.readouterr().out


def test_score_line_values_unchanged_by_verbose():
    _, quiet, _ = invoke(["--score", "q"], [ok(0.25)] * 3)
    _, loud, _ = invoke(["--score", "-v", "q"], [ok(0.25)] * 3)
    assert quiet == loud
    assert [json.loads(line)["score"] for line in quiet.splitlines()] == [0.25] * 3

import contextlib
import io
import json

import httpx

from jevq.cli import run
from jevq.client import SystemOneClient

LINES = b'{"id":1,  "a":"x"}\n{"id":2}\n'


def make_factory(responses, captured):
    """A real SystemOneClient on a MockTransport; responses cycle per call."""
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=next(calls))

    def factory(api_key, model, url):
        return SystemOneClient(
            api_key, model, url, transport=httpx.MockTransport(handler), sleep=lambda s: None
        )

    return factory


def answer(noul, model=None):
    body = {"answers": {"q": {"noul": noul}}}
    if model is not None:
        body["model"] = model
    return body


def invoke(argv, env, responses, stdin=LINES):
    captured = []
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = run(
        argv,
        io.BytesIO(stdin),
        stdout,
        stderr,
        {"TYPESAFE_API_KEY": "k", **env},
        client_factory=make_factory(responses, captured),
    )
    return code, stdout.getvalue(), stderr.getvalue(), captured


def test_default_model_pinned():
    _, _, _, captured = invoke(["q"], {}, [answer(0.9), answer(0.1)])
    assert [body["model"] for body in captured] == ["jev-1.13.0", "jev-1.13.0"]


def test_default_model_pinned_when_env_empty():
    _, _, _, captured = invoke(["q"], {"JEV_MODEL": ""}, [answer(0.9), answer(0.1)])
    assert captured[0]["model"] == "jev-1.13.0"


def test_model_flag_override():
    _, _, _, captured = invoke(["--model", "jev-x", "q"], {}, [answer(0.9), answer(0.1)])
    assert captured[0]["model"] == "jev-x"


def test_env_model_override():
    _, _, _, captured = invoke(["q"], {"JEV_MODEL": "jev-env"}, [answer(0.9), answer(0.1)])
    assert captured[0]["model"] == "jev-env"


def test_flag_beats_env_override():
    _, _, _, captured = invoke(
        ["--model", "jev-flag", "q"], {"JEV_MODEL": "jev-env"}, [answer(0.9), answer(0.1)]
    )
    assert {body["model"] for body in captured} == {"jev-flag"}


def test_stderr_model_logged():
    code, _, err, _ = invoke(["-v", "q"], {}, [answer(0.9, "jev-1.13.0"), answer(0.1, "jev-1.13.0")])
    assert code == 0
    assert err.splitlines() == ["jevq: read 2, emitted 1", "jevq: model: jev-1.13.0"]


def test_stderr_model_logged_distinct_in_order():
    _, _, err, _ = invoke(["--score", "-v", "q"], {}, [answer(0.9, "m-b"), answer(0.1, "m-a")])
    assert err.splitlines()[-1] == "jevq: model: m-b, m-a"


def test_stderr_model_not_reported():
    _, _, err, _ = invoke(["-v", "q"], {}, [answer(0.9), {"answers": {"q": {"noul": 0.1}}, "model": 7}])
    assert err.splitlines()[-1] == "jevq: model: not reported"


def test_stderr_model_logged_after_api_error():
    stdin = LINES + b'{"id":3}\n'
    responses = [answer(0.9, "jev-1.13.0"), answer(0.1, "jev-1.13.0"), {"nope": 1}]
    code, _, err, _ = invoke(["-v", "q"], {}, responses, stdin=stdin)
    assert code == 1
    assert err.splitlines()[-1] == "jevq: model: jev-1.13.0"


def test_stderr_model_absent_without_responses():
    code, _, err, _ = invoke(["-v", "q"], {}, [], stdin=b"")
    assert code == 0
    assert "model" not in err
    stdout, stderr = io.BytesIO(), io.StringIO()
    assert run(["--pass", "-v"], io.BytesIO(LINES), stdout, stderr, {}) == 0
    assert "model" not in stderr.getvalue()


def test_stdout_unchanged():
    responses = [answer(0.9, "jev-1.13.0"), answer(0.1, "jev-1.13.0")]
    _, out, _, _ = invoke(["q"], {}, responses)
    assert out == b'{"id":1,  "a":"x"}\n'
    _, out, _, _ = invoke(["--score", "q"], {}, responses)
    assert out == (b'{"score":0.9,"value":{"id":1,  "a":"x"}}\n{"score":0.1,"value":{"id":2}}\n')


def test_help_shows_pinned_default():
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = run(["--help"], io.BytesIO(b""), io.BytesIO(), stderr, {})
    assert code == 0
    assert "default jev-1.13.0" in stdout.getvalue()

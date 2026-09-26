import io

from jevq.cli import run


def _pass(data: bytes, argv=None, env=None):
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = run(argv or ["--pass"], io.BytesIO(data), stdout, stderr, env or {})
    return code, stdout.getvalue(), stderr.getvalue()


def test_pass_identity_bytes():
    data = '{"a" : 1,  "b":[1, 2]}\n{"s":"caf\\u00e9","t":"café"}\n'.encode()
    code, out, _ = _pass(data)
    assert code == 0
    assert out == data


def test_pass_preserves_order_and_count():
    lines = [b'{"id":%d}' % i for i in range(50)]
    code, out, _ = _pass(b"\n".join(lines) + b"\n")
    assert code == 0
    assert out.splitlines() == lines


def test_pass_skips_blank_lines_and_crlf():
    code, out, err = _pass(b'\n{"a":1}\r\n   \n{"b":2}', argv=["--pass", "-v"])
    assert code == 0
    assert out == b'{"a":1}\n{"b":2}\n'
    assert err == "jevq: read 2, emitted 2\n"


def test_pass_non_object_values():
    data = b'[1,2]\n"x"\n3.5\ntrue\nnull\n'
    code, out, _ = _pass(data)
    assert code == 0
    assert out == data


def test_pass_invalid_json_exits_1_after_prior_rows():
    code, out, err = _pass(b'{"a":1}\nnot json\n{"b":2}\n', argv=["--pass", "-v"])
    assert code == 1
    assert out == b'{"a":1}\n'
    assert "jevq: line 2: invalid JSON:" in err
    assert err.endswith("jevq: read 1, emitted 1\n")


def test_pass_rejects_two_values_and_bad_utf8():
    assert _pass(b"1 2\n")[0] == 1
    assert _pass(b'"\xff"\n')[0] == 1


def test_pass_needs_no_key_or_question():
    code, out, _ = _pass(b'{"a":1}\n', argv=["--pass", "-t", "0.9", "--model", "m"], env={})
    assert code == 0
    assert out == b'{"a":1}\n'


def test_question_required_without_pass():
    stdin = io.BytesIO(b'{"a":1}\n')
    stderr = io.StringIO()
    code = run([], stdin, io.BytesIO(), stderr, {})
    assert code == 2
    assert stderr.getvalue() == "jevq: QUESTION is required unless --pass\n"
    assert stdin.tell() == 0


def test_pass_reports_counts():
    code, _, err = _pass(b"", argv=["--pass", "-v"])
    assert code == 0
    assert err == "jevq: read 0, emitted 0\n"
    _, _, err = _pass(b"1\n2\n3\n", argv=["-v", "--pass"])
    assert err == "jevq: read 3, emitted 3\n"

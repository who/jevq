import io

import pytest

from jevq.cli import run

EXAMPLES = [
    "jq -c '.[] | select(.status == \"open\")' tickets.json | jevq \"the customer is asking for a refund\" | jq -c '{id, subject}'",
    "jq -c '.[]' tickets.json | jevq --score \"the customer is angry\" | jq -c 'select(.score >= 0.8) | .value.id'",
    "jq -c '.[]' tickets.json | jevq --pass",
]


def _help(capsys) -> str:
    code = run(["--help"], io.BytesIO(), io.BytesIO(), io.StringIO(), {})
    assert code == 0
    return capsys.readouterr().out


def test_help_lists_examples(capsys):
    out = _help(capsys)
    assert "usage: jevq [options] QUESTION" in out
    for line in EXAMPLES:
        assert line in out


@pytest.mark.parametrize(
    "token",
    [
        "--score",
        "--pass",
        "-t N, --threshold N",
        "-f a,b, --fields a,b",
        "--model NAME",
        "-v, --verbose",
        "-h, --help",
        "TYPESAFE_API_KEY",
        "JEV_MODEL",
        "JEV_BASE_URL",
        "JEV_THRESHOLD",
    ],
)
def test_help_lists_flags_and_env(capsys, token):
    assert token in _help(capsys)


def test_score_and_pass_are_exclusive(capsys):
    code = run(["--score", "--pass", "q"], io.BytesIO(), io.BytesIO(), io.StringIO(), {})
    assert code == 2
    assert "not allowed with argument" in capsys.readouterr().err

"""Keep README.md and docs/examples.md in step with the real CLI."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from jevq.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLES = ROOT / "docs" / "examples.md"
DOCS = (README, EXAMPLES)

USE_CASE_QUESTIONS = [
    "the customer is asking for a refund",
    "this error is caused by a network timeout, not a bug in our code",
    "reports a crash or wrong output, not a feature request",
]


def _text(path: Path = README) -> str:
    return path.read_text(encoding="utf-8")


SHELL_INFO = {"bash", "sh", "shell", "zsh", "console"}
USE_CASES = "## Use cases"
OPTIONS = "## Options"
MAX_LINE = 100
MAX_README_LINES = 90


def fenced_shell_blocks(text: str) -> list[tuple[str, str]]:
    """(section heading, block body) for each fenced bash/sh/shell/zsh/console block."""
    blocks: list[tuple[str, str]] = []
    section = ""
    info: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if info is None:
            if line.startswith("## "):
                section = line.strip()
            elif line.startswith("```"):
                info = line[3:].strip().lower()
                body = []
        elif line.startswith("```"):
            if info in SHELL_INFO:
                blocks.append((section, "\n".join(body) + "\n"))
            info = None
        else:
            body.append(line)
    return blocks


def shell_pipe_positions(line: str) -> list[int]:
    """Indexes of each `|` outside single or double quotes, up to a shell comment."""
    positions: list[int] = []
    quote: str | None = None
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
        elif quote == "'":
            if ch == "'":
                quote = None
        elif ch == "\\":
            escaped = True
        elif quote == '"':
            if ch == '"':
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            break
        elif ch == "|":
            positions.append(i)
    return positions


def _offline_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["JEV_BASE_URL"] = "http://127.0.0.1:9/unreachable"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _options() -> list[str]:
    return [opt for action in build_parser()._actions for opt in action.option_strings]


def _section(text: str, heading: str) -> list[str]:
    """Lines under ``heading`` up to the next ``## `` heading."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    return lines[start:end]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row)[1:-1]]


def test_readme_mentions_every_cli_option() -> None:
    text = _text()
    options = _options()
    assert options
    missing = [opt for opt in options if opt not in text]
    assert not missing, f"README.md does not mention: {missing}"


def test_readme_mentions_env_vars_and_model() -> None:
    text = _text()
    for name in (
        "TYPESAFE_API_KEY",
        "JEV_MODEL",
        "JEV_BASE_URL",
        "JEV_THRESHOLD",
        "jev-1.13.0",
    ):
        assert name in text, name


def test_readme_under_90_lines() -> None:
    assert len(_text().splitlines()) < MAX_README_LINES


def test_readme_options_table_single_line_rows() -> None:
    section = _section(_text(), OPTIONS)
    assert not any(line.startswith("```") for line in section), (
        "fenced code in ## Options"
    )
    table = [i for i, line in enumerate(section) if line.startswith("|")]
    assert table, "no table under ## Options"
    assert table == list(range(table[0], table[-1] + 1)), (
        "table rows are not contiguous"
    )
    rows = [section[i] for i in table]
    assert rows[0] == "| Flag | Default | Description |"
    flags = []
    for row in rows:
        assert row.endswith("|"), row
        assert len(row) <= MAX_LINE, f"row over {MAX_LINE} chars: {row}"
        cells = _cells(row)
        assert len(cells) == 3, row
        for cell in cells:
            assert "<br" not in cell.lower(), row
            assert not re.search(r"\bjevq\s+\S", cell), f"example in cell: {row}"
        flags.append(cells[0])
    flag_column = " ".join(flags[2:])
    missing = [opt for opt in _options() if f"`{opt}" not in flag_column]
    assert not missing, f"Options table does not list: {missing}"


def test_readme_has_three_use_cases() -> None:
    text = _text()
    blocks = [
        body for section, body in fenced_shell_blocks(text) if section == USE_CASES
    ]
    assert len(blocks) == 3, f"expected 3 use cases, found {len(blocks)}"
    joined = "".join(blocks)
    for question in USE_CASE_QUESTIONS:
        assert f'"{question}"' in joined, question
    assert any("gh api 'repos/itchyny/gojq/issues" in body for body in blocks)
    assert "docs/examples.md" in text
    assert "docs/jevq.md" in text


def test_examples_doc_has_moved_examples() -> None:
    assert EXAMPLES.is_file()
    text = _text(EXAMPLES)
    for needle in (
        "this npm package is a test, lint or build tool, not a runtime library",
        "this log line records a failed login",
        "jevq -f ",
        "jevq -t ",
        "jevq --pass",
        "jevq -v ",
    ):
        assert needle in text, needle
    assert "## Tips" in text.splitlines()


def test_shell_example_lines_short() -> None:
    for path in DOCS:
        blocks = fenced_shell_blocks(_text(path))
        assert blocks, f"{path.name} has no fenced shell examples"
        long = [
            line
            for _, body in blocks
            for line in body.splitlines()
            if len(line) > MAX_LINE
        ]
        assert not long, f"{path.name} lines over {MAX_LINE} chars: {long}"


def test_pipes_break_after_pipe() -> None:
    for path in DOCS:
        for _, body in fenced_shell_blocks(_text(path)):
            lines = body.splitlines()
            for i, line in enumerate(lines):
                for pos in shell_pipe_positions(line):
                    assert not line[pos + 1 :].strip(), (
                        f"command after a pipe: {line!r}"
                    )
                if i and lines[i - 1].rstrip().endswith(("|", "\\")):
                    assert line.startswith("  "), f"continuation not indented: {line!r}"
                assert not re.search(r"\\[ \t]+$", line), (
                    f"space after backslash: {line!r}"
                )


def test_pass_examples_run_offline() -> None:
    blocks = [
        body
        for path in DOCS
        for _, body in fenced_shell_blocks(_text(path))
        if "jevq --pass" in body and "gh api" not in body
    ]
    assert blocks, "no jevq --pass example in README.md or docs/examples.md"
    env = _offline_env()
    for block in blocks:
        proc = subprocess.run(
            ["bash", "-o", "pipefail", "-c", block],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"{block}\n{proc.stderr}"
        assert proc.stdout.strip(), f"no output: {block}"


def test_shell_pipe_positions_ignores_quoted_pipes() -> None:
    assert shell_pipe_positions("jq -c 'select(.a) | .b' f.json |") == [31]
    assert shell_pipe_positions('echo "a | b" # c | d') == []
    assert shell_pipe_positions("a || b") == [2, 3]


def test_no_go_or_machine_names() -> None:
    for path in DOCS:
        text = _text(path)
        assert not re.search(
            r"go build|go install|golang|condor|/mnt/c", text, flags=re.I
        )
        assert not re.search(r"\bGo\b", text), path.name

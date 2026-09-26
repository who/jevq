"""Keep README.md in step with the real CLI."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from jevq.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

USE_CASE_QUESTIONS = [
    "the customer is asking for a refund",
    "this error is caused by a network timeout, not a bug in our code",
    "this npm package is a test, lint or build tool, not a runtime library",
    "reports a crash or wrong output, not a feature request",
    "this log line records a failed login",
]


def _text() -> str:
    return README.read_text(encoding="utf-8")


SHELL_INFO = {"bash", "sh", "shell", "zsh", "console"}
USE_CASES = "## Use cases"
MAX_USE_CASE_LINE = 100


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


def test_readme_mentions_every_cli_option() -> None:
    text = _text()
    options = [opt for action in build_parser()._actions for opt in action.option_strings]
    assert options
    missing = [opt for opt in options if opt not in text]
    assert not missing, f"README.md does not mention: {missing}"


def test_readme_mentions_env_vars_and_model() -> None:
    text = _text()
    for name in ("TYPESAFE_API_KEY", "JEV_MODEL", "JEV_BASE_URL", "JEV_THRESHOLD", "jev-1.13.0"):
        assert name in text, name


def test_readme_contains_use_case_questions() -> None:
    text = _text()
    for question in USE_CASE_QUESTIONS:
        assert f'"{question}"' in text, question


def test_readme_pass_examples_run_offline() -> None:
    blocks = [
        body
        for _, body in fenced_shell_blocks(_text())
        if "jevq --pass" in body and "gh api" not in body
    ]
    assert blocks, "README.md has no jevq --pass example"
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


def test_readme_use_case_lines_short() -> None:
    blocks = [body for section, body in fenced_shell_blocks(_text()) if section == USE_CASES]
    assert blocks, "README.md has no fenced shell examples under ## Use cases"
    long = [
        line for body in blocks for line in body.splitlines() if len(line) > MAX_USE_CASE_LINE
    ]
    assert not long, f"use-case lines over {MAX_USE_CASE_LINE} chars: {long}"


def test_readme_pipes_break_after_pipe() -> None:
    blocks = fenced_shell_blocks(_text())
    assert blocks
    for _, body in blocks:
        lines = body.splitlines()
        for i, line in enumerate(lines):
            for pos in shell_pipe_positions(line):
                assert not line[pos + 1 :].strip(), f"command after a pipe: {line!r}"
            if i and lines[i - 1].rstrip().endswith(("|", "\\")):
                assert line.startswith("  "), f"continuation not indented: {line!r}"
            assert not re.search(r"\\[ \t]+$", line), f"space after backslash: {line!r}"


def test_shell_pipe_positions_ignores_quoted_pipes() -> None:
    assert shell_pipe_positions("jq -c 'select(.a) | .b' f.json |") == [31]
    assert shell_pipe_positions('echo "a | b" # c | d') == []
    assert shell_pipe_positions("a || b") == [2, 3]


def test_readme_has_no_go_or_machine_names() -> None:
    text = _text()
    assert not re.search(r"go build|go install|golang|condor|/mnt/c", text, flags=re.I)
    assert not re.search(r"\bGo\b", text)

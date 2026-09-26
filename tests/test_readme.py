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


def _bash_commands(text: str) -> list[str]:
    """Every command in a fenced bash block, with backslash continuations joined."""
    commands: list[str] = []
    for block in re.findall(r"```bash\n(.*?)```", text, flags=re.S):
        joined = re.sub(r"\\\n\s*", " ", block)
        commands.extend(line.strip() for line in joined.splitlines() if line.strip())
    return commands


def _pass_examples(text: str) -> list[str]:
    return [
        cmd
        for cmd in _bash_commands(text)
        if "jevq --pass" in cmd and not cmd.startswith("gh ")
    ]


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
    examples = _pass_examples(_text())
    assert examples, "README.md has no jevq --pass example"
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["JEV_BASE_URL"] = "http://127.0.0.1:9/unreachable"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    for cmd in examples:
        proc = subprocess.run(
            ["bash", "-o", "pipefail", "-c", cmd],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"{cmd}\n{proc.stderr}"
        assert proc.stdout.strip(), f"no output: {cmd}"


def test_readme_has_no_go_or_machine_names() -> None:
    text = _text()
    assert not re.search(r"go build|go install|golang|condor|/mnt/c", text, flags=re.I)
    assert not re.search(r"\bGo\b", text)

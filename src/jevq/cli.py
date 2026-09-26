"""Command-line entry point for jevq."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Mapping
from typing import Any, BinaryIO, TextIO

DESCRIPTION = """\
Filter JSON values from stdin (JSONL from `jq -c`) with a System One noul.
One System One call per value. QUESTION is a yes/no claim about the current
object, not a search query."""

EPILOG = """\
environment:
  TYPESAFE_API_KEY  API key (required except --pass)
  JEV_MODEL         default model (default jev-1.13.0)
  JEV_BASE_URL      API base URL (default https://api.typesafe.ai/v1/systemone)
  JEV_THRESHOLD     default threshold (default 0.5)

examples:
  jq -c '.[] | select(.status == "open")' tickets.json | jevq "the customer is asking for a refund" | jq -c '{id, subject}'
  jq -c '.[]' tickets.json | jevq --score "the customer is angry" | jq -c 'select(.score >= 0.8) | .value.id'
  jq -c '.[]' tickets.json | jevq --pass"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jevq",
        usage="jevq [options] QUESTION",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "question",
        nargs="?",
        metavar="QUESTION",
        help="yes/no claim about the current object",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--score",
        action="store_true",
        help='emit every row as {"score": <noul>, "value": <original>}',
    )
    mode.add_argument(
        "--pass",
        dest="pass_",
        action="store_true",
        help="emit every input value unchanged. No API call. No key required",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        metavar="N",
        default=None,
        help="cutoff in [0,1]. Default 0.5 or $JEV_THRESHOLD",
    )
    parser.add_argument(
        "-f",
        "--fields",
        metavar="a,b",
        default=None,
        help="slim state only. Output is still the full original value",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        default=None,
        help="default jev-1.13.0 (pinned) or $JEV_MODEL",
    )
    return parser


class InputError(Exception):
    """A non-blank input line that is not exactly one JSON value."""

    def __init__(self, line_no: int, message: str) -> None:
        super().__init__(f"line {line_no}: invalid JSON: {message}")
        self.line_no = line_no
        self.message = message


def iter_values(stream: BinaryIO) -> Iterator[tuple[int, bytes, Any]]:
    """Yield (line_no, raw_bytes, value) per non-blank JSONL line, lazily."""
    for line_no, line in enumerate(stream, start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InputError(line_no, str(exc)) from None
        yield line_no, raw, value


def emit(stdout: BinaryIO, raw: bytes) -> None:
    stdout.write(raw + b"\n")
    stdout.flush()


def report(stderr: TextIO, read: int, emitted: int) -> None:
    stderr.write(f"jevq: read {read}, emitted {emitted}\n")


def run(
    argv: list[str] | None,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    env: Mapping[str, str],
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 2)
    if not args.pass_ and not (args.question or "").strip():
        stderr.write("jevq: QUESTION is required unless --pass\n")
        return 2
    if not args.pass_:
        stderr.write("jevq: not implemented yet\n")
        return 1

    read = emitted = 0
    try:
        for _line_no, raw, _value in iter_values(stdin):
            read += 1
            emit(stdout, raw)
            emitted += 1
    except InputError as exc:
        stderr.write(f"jevq: {exc}\n")
        report(stderr, read, emitted)
        return 1
    report(stderr, read, emitted)
    return 0


def main() -> None:
    try:
        code = run(sys.argv[1:], sys.stdin.buffer, sys.stdout.buffer, sys.stderr, os.environ)
    except BrokenPipeError:
        # Downstream closed early (e.g. `| head -1`): silence the flush at exit.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    sys.exit(code)

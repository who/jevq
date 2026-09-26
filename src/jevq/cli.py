"""Command-line entry point for jevq."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from typing import BinaryIO, TextIO

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


def run(
    argv: list[str] | None,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    env: Mapping[str, str],
) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 2)
    stderr.write("jevq: not implemented yet\n")
    return 1


def main() -> None:
    sys.exit(run(sys.argv[1:], sys.stdin.buffer, sys.stdout.buffer, sys.stderr, os.environ))

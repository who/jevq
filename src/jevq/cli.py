"""Command-line entry point for jevq."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import Any, BinaryIO, Protocol, TextIO

from jevq.client import DEFAULT_MODEL, DEFAULT_URL, JevqAPIError, SystemOneClient

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


def format_score_line(score: float, raw: bytes) -> bytes:
    """The only wrap: compact ``{"score":<noul>,"value":<raw>}`` plus newline."""
    return b'{"score":' + json.dumps(float(score)).encode() + b',"value":' + raw + b"}\n"


def report(stderr: TextIO, read: int, emitted: int) -> None:
    stderr.write(f"jevq: read {read}, emitted {emitted}\n")


def report_model(stderr: TextIO, client: object) -> None:
    """Name the model(s) that answered, once any System One response succeeded."""
    models = getattr(client, "answered_models", None)
    if models is None or not getattr(client, "responses", 0):
        return
    stderr.write(f"jevq: model: {', '.join(models) if models else 'not reported'}\n")


class UsageError(Exception):
    """Bad flags, environment or missing key; exit 2 before reading stdin."""


class NoulClient(Protocol):
    def noul(self, state: Any, question: str) -> float: ...


ClientFactory = Callable[[str, str, str], NoulClient]


def resolve_threshold(arg: str | None, env: Mapping[str, str]) -> float:
    raw = arg if arg is not None else (env.get("JEV_THRESHOLD") or None)
    if raw is None:
        return 0.5
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise UsageError("threshold must be a number in [0, 1]")
    return value


def parse_fields(arg: str | None) -> list[str] | None:
    if arg is None:
        return None
    names = [name.strip() for name in arg.split(",")]
    names = [name for name in names if name]
    if not names:
        raise UsageError("--fields needs at least one key name")
    return names


def build_state(value: Any, fields: list[str] | None) -> Any:
    """The state sent to System One; emitted output is always the raw line."""
    if not isinstance(value, dict):
        return {"value": value}
    if fields is None:
        return value
    return {k: value[k] for k in fields if k in value}


def _default_client_factory(api_key: str, model: str, url: str) -> NoulClient:
    return SystemOneClient(api_key, model, url)


def run(
    argv: list[str] | None,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    env: Mapping[str, str],
    *,
    client_factory: ClientFactory | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 2)
    if args.pass_:
        return _run_pass(stdin, stdout, stderr)
    if not (args.question or "").strip():
        stderr.write("jevq: QUESTION is required unless --pass\n")
        return 2
    try:
        threshold = resolve_threshold(args.threshold, env)
        fields = parse_fields(args.fields)
        api_key = (env.get("TYPESAFE_API_KEY") or "").strip()
        if not api_key:
            raise UsageError("TYPESAFE_API_KEY is not set")
    except UsageError as exc:
        stderr.write(f"jevq: {exc}\n")
        return 2
    model = args.model or env.get("JEV_MODEL") or DEFAULT_MODEL
    url = env.get("JEV_BASE_URL") or DEFAULT_URL
    client = (client_factory or _default_client_factory)(api_key, model, url)
    try:
        return _run_filter(
            client, args.question, threshold, fields, stdin, stdout, stderr, score_mode=args.score
        )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


def _run_filter(
    client: NoulClient,
    question: str,
    threshold: float,
    fields: list[str] | None,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    *,
    score_mode: bool = False,
) -> int:
    read = emitted = 0
    try:
        for line_no, raw, value in iter_values(stdin):
            read += 1
            try:
                score = client.noul(build_state(value, fields), question)
            except JevqAPIError as exc:
                stderr.write(f"jevq: line {line_no}: API error: {exc}\n")
                report(stderr, read, emitted)
                report_model(stderr, client)
                return 1
            if score_mode:
                stdout.write(format_score_line(score, raw))
                stdout.flush()
                emitted += 1
            elif score >= threshold:
                emit(stdout, raw)
                emitted += 1
    except InputError as exc:
        stderr.write(f"jevq: {exc}\n")
        report(stderr, read, emitted)
        report_model(stderr, client)
        return 1
    report(stderr, read, emitted)
    report_model(stderr, client)
    return 0


def _run_pass(stdin: BinaryIO, stdout: BinaryIO, stderr: TextIO) -> int:
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

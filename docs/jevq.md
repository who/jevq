# jevq

jevq filters JSON values with a TypeSafe System One `noul` score. It reads
JSONL on stdin (the output of `jq -c`), makes one System One call per value,
and writes JSONL on stdout.

## Usage

```
jevq [options] QUESTION
```

QUESTION is a yes/no claim about the current value, for example
`"the customer is asking for a refund"`. It is not a search query. It is
required unless `--pass` is given.

## Flags

| Flag | Meaning |
| --- | --- |
| `QUESTION` | Yes/no claim about the current value. |
| `--score` | Emit every value as `{"score":<noul>,"value":<original>}`. No threshold is applied. |
| `--pass` | Emit every input value unchanged. No API call and no key required. Cannot be combined with `--score`. |
| `-t N`, `--threshold N` | Cutoff in [0, 1]. A value is kept when its score is at least N. Default 0.5 or `$JEV_THRESHOLD`. |
| `-f a,b`, `--fields a,b` | Send only these top-level keys to the model. Output is still the full original value. |
| `--model NAME` | Model to ask. Default `jev-1.13.0` (pinned) or `$JEV_MODEL`. |
| `-h`, `--help` | Print help and exit. |

## Environment

| Variable | Meaning |
| --- | --- |
| `TYPESAFE_API_KEY` | API key, sent as `Authorization: Bearer <key>`. Required except with `--pass`. |
| `JEV_MODEL` | Default model when `--model` is not given. Default `jev-1.13.0`. |
| `JEV_BASE_URL` | Endpoint URL. Default `https://api.typesafe.ai/v1/systemone`. |
| `JEV_THRESHOLD` | Default threshold when `-t` is not given. Default `0.5`. |

## State sent to the model

- An object is sent as it is.
- With `--fields`, an object is cut down to the listed keys that it has. A
  missing key is skipped, not an error.
- Anything that is not an object (a string, number, array, `true`, `false` or
  `null`) is sent wrapped as `{"value": <value>}`. `--fields` does not apply
  to it.

`--fields` only changes what the model sees. stdout always carries the input
line, so `jq -c '.dependencies | to_entries[]' package.json | jevq -f key ...`
asks about the package name alone and still emits `{"key":...,"value":...}`.

## HTTP request

One `POST` to `$JEV_BASE_URL` (default
`https://api.typesafe.ai/v1/systemone`) per input value, with a 30 second
timeout and a `User-Agent: jevq/<version>` header. The body is:

```json
{
  "model": "jev-1.13.0",
  "state": {"id": 7, "subject": "Refund please"},
  "questions": {"q": {"type": "noul", "instructions": "the customer is asking for a refund"}}
}
```

The score is read from `answers.q.noul` in the response and must be a finite
number. A response that is not JSON, lacks `answers.q.noul`, or holds a
non-number there is an API error. The top-level `model` field of the response,
when present, is recorded for the stderr report.

Calls run one at a time, in input order. There is no caching.

## Retries

Transport errors, HTTP 429 and HTTP 5xx are retried, up to 4 attempts in all.
The wait before each retry is the `Retry-After` header in seconds, capped at
10 s, or when that header is missing or unusable, 0.5 s, 1 s, then 2 s. Any
other non-2xx status fails at once. An API failure is never treated as a "no".

## Output

- Default mode: each value whose score is at least the threshold is written
  exactly as it was read (whitespace around the line trimmed), one per line.
- `--score`: every value is written as the compact line
  `{"score":<noul>,"value":<original>}`. This is the only way jevq wraps a
  value.
- `--pass`: every value is written unchanged.

Blank input lines are skipped. Output is flushed after every line, so jevq
works in a streaming pipe, and a downstream reader that closes early (such as
`| head -1`) ends jevq quietly with status 0.

When it finishes, including after an error, jevq writes a summary to stderr:

```
jevq: read N, emitted M
```

After at least one successful API response it also writes the model or models
that answered, taken from the responses:

```
jevq: model: jev-1.13.0
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | Runtime failure: an API error (after retries) or an input line that is not valid JSON. jevq stops at that line; values already emitted stay emitted. |
| 2 | Usage error: bad flags, missing QUESTION, an invalid threshold or `--fields` value, or `TYPESAFE_API_KEY` not set. Reported before stdin is read. |

Errors go to stderr prefixed `jevq:`, for example
`jevq: line 3: invalid JSON: ...` or `jevq: line 3: API error: HTTP 401: ...`.

## Reinstalling the local tool

`uv tool install --editable .` can reuse a cached build or an existing tool
environment, so the global `jevq` may not match this checkout. After pulling
or changing code, run:

```bash
scripts/reinstall-cli.sh
```

It works from any directory. It force-reinstalls only the `jevq` uv tool from
the repo root (`uv tool install --editable --force --reinstall`), then prints
the version before and after, the source path and install mode, the HEAD short
sha (with ` (dirty)` when the tree has uncommitted or untracked files), and
where `jevq` resolves on PATH. It finishes with a smoke test that needs no API
key: `printf '{"a":1}\n' | jevq --pass` must reproduce its input byte for byte.

Flags:

- `--dry-run` prints the exact uv command and changes nothing.
- `--no-editable` installs a snapshot instead of an editable install.
- `--skip-smoke` skips the `--pass` smoke test.
- `-h`, `--help` prints usage.

The script honours `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR`, so you can install
into a scratch location without touching your real global tools.

## Sample pipes

`samples/` holds invented data for four realistic `jq | jevq | jq` pipes: stock
jq picks or reshapes values, jevq judges each one, and jq post-processes the
survivors. Run them from the repo root:

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq "the customer is asking for a refund" | jq -c '{id, subject}'
jq -c 'select(.level == "error")' samples/app.ndjson | jevq "this error is caused by a network timeout, not a bug in our code"
jq -c '.dependencies | to_entries[]' samples/package.json | jevq "this npm package is a test, lint or build tool, not a runtime library" | jq -r '.key'
jq -c '.[] | select(.pull_request | not) | {number, title, body}' samples/gh-issues.json | jevq --score "reports a crash or wrong output, not a feature request" | jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"'
```

`tests/samples/run.sh` runs these pipes end to end, plus checks for `--fields`,
`--threshold`, `--pass`, one request per value, and a missing key. It starts a
deterministic fake System One (`tests/samples/fake_systemone.py`, scored by
`tests/samples/rules.json`) on 127.0.0.1, so it needs no API key and makes no
network calls. It works from any directory:

```bash
bash tests/samples/run.sh
```

It prints `PASS`, `FAIL` or `SKIP` per case and a final
`samples: N passed, M failed, K skipped` line, and exits nonzero if any case
fails. To also run the four pipes against the real endpoint, with looser shape
checks, set:

```bash
JEVQ_LIVE=1 TYPESAFE_API_KEY=... bash tests/samples/run.sh
```

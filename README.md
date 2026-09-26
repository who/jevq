# jevq

[![CI](https://github.com/who/jevq/actions/workflows/ci.yml/badge.svg)](https://github.com/who/jevq/actions/workflows/ci.yml)

## What it is

`jq | jevq | jq`. jq handles structure: it selects, reshapes and prints.
jevq handles judgement: it reads one JSON value per line from stdin, asks Jev
(a TypeSafe System One model) a yes/no question about each value, and passes
through the values it answers yes to. You write QUESTION as a yes/no claim
about the current value ("the customer is asking for a refund"). It is not a
search query.

The detailed contract (HTTP request, state rules, retries) lives in
[docs/jevq.md](docs/jevq.md). This page is the user guide.

## Install

jevq needs Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv tool install --editable .
export TYPESAFE_API_KEY=...
```

`uv sync` sets up the development environment; `uv tool install --editable .`
puts a global `jevq` on your PATH that runs this checkout.

`uv tool install` can reuse a cached build, so the global `jevq` may drift
from the code on disk. `scripts/reinstall-cli.sh` forces a rebuild and
reinstall, reports what got installed, and smoke-tests it with `jevq --pass`:

```bash
scripts/reinstall-cli.sh               # editable reinstall plus smoke test
scripts/reinstall-cli.sh --dry-run     # print the uv command, change nothing
scripts/reinstall-cli.sh --no-editable # install a snapshot instead
scripts/reinstall-cli.sh --skip-smoke  # skip the passthrough smoke test
```

## Usage

```
jevq [options] QUESTION
```

Input is JSONL on stdin (typically from `jq -c`), one value per line. Blank
lines are skipped. QUESTION is required unless `--pass` is given. `--score`
and `--pass` are mutually exclusive.

| Flag | What it does | Default | Env var | Example |
| --- | --- | --- | --- | --- |
| (no mode flag) | Filter: emit each value whose score is at least the threshold, unchanged | on | | `jevq "the customer is angry"` |
| `-t N`, `--threshold N` | Cutoff in [0, 1] for the default filter | `0.5` | `JEV_THRESHOLD` | `jevq -t 0.8 "..."` |
| `-f a,b`, `--fields a,b` | Send only these keys of an object to Jev; stdout still gets the full original value | whole value | | `jevq -f subject,body "..."` |
| `--score` | Emit every value as `{"score":<noul>,"value":<original>}` | off | | `jevq --score "..."` |
| `--pass` | Emit every value unchanged. No API call, no key needed | off | | `jevq --pass` |
| `--model NAME` | System One model to ask | `jev-1.13.0` (pinned) | `JEV_MODEL` | `jevq --model jev-1.13.0 "..."` |
| `-v`, `--verbose` | Print end-of-run counts (read/emitted) and the answering model to stderr | off | | `jevq -v "..."` |
| `-h`, `--help` | Show help and exit | | | `jevq --help` |

A flag beats its env var; the env var beats the default.

## Environment

| Variable | Meaning | Default |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | API key. Required except with `--pass` | none |
| `JEV_MODEL` | Default model | `jev-1.13.0` (pinned) |
| `JEV_BASE_URL` | API base URL | `https://api.typesafe.ai/v1/systemone` |
| `JEV_THRESHOLD` | Default threshold | `0.5` |

## Use cases

The examples use the files in `samples/`, so they run from the repo root.

### (a) Open tickets asking for a refund

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq "the customer is asking for a refund" | jq -c '{id, subject}'
```

jq keeps the open tickets, jevq keeps the ones asking for money back, and the
last jq prints one `{"id":...,"subject":...}` line per match.

### (b) Network timeouts versus code bugs

```bash
jq -c 'select(.level == "error")' samples/app.ndjson | jevq "this error is caused by a network timeout, not a bug in our code"
```

Of the error lines in the log, prints the ones that look like a timeout
(e.g. `connect ETIMEDOUT ...`), each as the original log line.

### (c) Dev tools in runtime dependencies

```bash
jq -c '.dependencies | to_entries[]' samples/package.json | jevq "this npm package is a test, lint or build tool, not a runtime library" | jq -r .key
```

Prints one package name per line for dependencies that belong in
`devDependencies` (things like jest, eslint or webpack).

### (d) Rank GitHub issues with `--score`

```bash
gh api 'repos/itchyny/gojq/issues?state=open&per_page=100' | jq -c '.[] | select(.pull_request | not) | {number, title, body}' | jevq --score "reports a crash or wrong output, not a feature request" | jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"'
```

Scores every open issue (pull requests dropped), then prints the five most
bug-like as `number<TAB>title`. To try it offline without `gh`, swap the first
stage for the saved copy:

```bash
jq -c '.[] | select(.pull_request | not) | {number, title, body}' samples/gh-issues.json | jevq --score "reports a crash or wrong output, not a feature request" | jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"'
```

### (e) Failed logins, cut at 0.7

```bash
printf '%s\n' '{"level":"warn","msg":"failed login for alice from 10.0.0.5"}' '{"level":"info","msg":"user bob logged in"}' '{"level":"warn","msg":"invalid password for root from 203.0.113.9"}' '{"level":"info","msg":"cache warmed in 120ms"}' | jevq --score "this log line records a failed login" | jq -c 'select(.score >= 0.7) | .value'
```

`--score` wraps each line with its score and jq applies the cutoff, printing
the original log objects for the failed attempts.

### (f) Send only some fields with `-f`

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq -f subject,body "the customer is asking for a refund"
```

Only `subject` and `body` go to Jev, so customer names and other keys stay
out of the request and each row's state stays small. Stdout still gets the
full ticket. Non-object values are always sent as `{"value": ...}`.

### (g) Tighten or loosen with `-t`

```bash
jq -c '.[]' samples/tickets.json | jevq -t 0.8 "the customer is asking for a refund"
```

`-t 0.8` keeps only confident matches; a lower value such as `-t 0.3` keeps
borderline ones too. To choose a threshold, look at the score distribution
first:

```bash
jq -c '.[]' samples/tickets.json | jevq --score "the customer is asking for a refund" | jq -r .score | sort -n
```

### (h) Dry run with `--pass`

`--pass` emits every value unchanged, makes no API calls and needs no key.
Use it to check what a pipe would send before paying for it:

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq --pass | wc -l
```

prints how many rows the real run would ask about. It is also an identity:

```bash
f=$(mktemp) && jq -c '.[]' samples/tickets.json > "$f" && jevq --pass < "$f" | cmp - "$f" && echo identical
```

### (i) Counts and model with `-v`

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq -v "the customer is asking for a refund" > refunds.jsonl
```

On success jevq writes nothing to stderr. With `-v` it adds, at the end of
the run (also after an error):

```
jevq: read 14, emitted 5
jevq: model: jev-1.13.0
```

The model line names the model(s) that actually answered and appears only
after at least one API response. `--pass` prints only the counts line.

## Output contract

- Each emitted value is the original input bytes plus a newline, in input
  order. Input and output are JSONL; nothing is slurped.
- `--score` is the only wrapper: `{"score":<noul>,"value":<original>}`.
- stdout carries only results. stderr is silent on success unless `-v`.
- Errors go to stderr prefixed `jevq:` and exit nonzero.

| Exit | Meaning |
| --- | --- |
| `0` | Success, including a downstream pipe that closed early (e.g. `\| head -1`) |
| `1` | Runtime failure: an API error after retries, or an input line that is not valid JSON |
| `2` | Usage error: bad flags, `--score` with `--pass`, missing QUESTION without `--pass`, invalid threshold, empty `--fields`, or `TYPESAFE_API_KEY` not set |

See [docs/jevq.md](docs/jevq.md) for the HTTP request, state rules and retry
behavior.

## Tips

- Phrase QUESTION so a high score means yes to what you want to keep.
- For the opposite, invert on the score with jq instead of asking a negated
  question: `jevq --score "..." | jq -c 'select(.score < 0.5) | .value'`.
- Prefilter with jq and slim with jq or `-f` so each row's state stays small
  (a row can hold about 32k tokens).
- Scores are not calibrated probabilities. Tune the threshold on real data
  (see use case (g)).
- jevq makes one API call per row, sequentially. The account limit is about
  1,200 requests per minute.

## Testing

```bash
uv run pytest -q
bash tests/samples/run.sh
```

`tests/samples/run.sh` runs the sample pipes offline against a fake System
One on 127.0.0.1. To run them against the real API:

```bash
JEVQ_LIVE=1 TYPESAFE_API_KEY=... bash tests/samples/run.sh
```

## Not supported in v1

- `--path` (asking about a sub-path of each value)
- a `jev()` builtin inside jq
- concurrent requests
- caching of answers

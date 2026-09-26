# jevq

[![CI](https://github.com/who/jevq/actions/workflows/ci.yml/badge.svg)](https://github.com/who/jevq/actions/workflows/ci.yml)

`jq | jevq | jq`. jq handles structure; jevq reads one JSON value per line from stdin, asks
Jev (a TypeSafe System One model) a yes/no question about each, and passes through the yeses.
QUESTION is a yes/no claim about the current value, not a search query.

![jevq demo: filtering support tickets to open refund requests](https://raw.githubusercontent.com/who/jevq/main/docs/assets/jevq-demo.gif)

Video: [docs/assets/jevq-demo.mp4](https://github.com/who/jevq/blob/main/docs/assets/jevq-demo.mp4)

## Install

```bash
uv tool install jevq            # from PyPI (or: pipx install jevq)
uv tool install --editable .    # from a source checkout
export TYPESAFE_API_KEY=...
```

`scripts/reinstall-cli.sh` forces a rebuild (`--dry-run`, `--no-editable`, `--skip-smoke`).

## Options

`jevq [options] QUESTION` reads JSONL on stdin. QUESTION is required unless `--pass`.

| Flag | Default | Description |
| --- | --- | --- |
| `QUESTION` | none | Yes/no claim about each value |
| `-t N`, `--threshold N` | `0.5` (`$JEV_THRESHOLD`) | Keep values scoring at least N |
| `-f a,b`, `--fields a,b` | whole value | Send only these keys; output stays the full value |
| `--score` | off | Emit every value as `{"score":<noul>,"value":<original>}` |
| `--pass` | off | Emit every value unchanged; no API call, no key |
| `--model NAME` | `jev-1.13.0` (`$JEV_MODEL`) | Model to ask |
| `-v`, `--verbose` | off | Print counts and the answering model to stderr |
| `-h`, `--help` | | Show help and exit |

`--score` and `--pass` are mutually exclusive. A flag beats its env var.

## Environment

| Variable | Default | Description |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | none | API key; required except with `--pass` |
| `JEV_MODEL` | `jev-1.13.0` | Default model |
| `JEV_BASE_URL` | `https://api.typesafe.ai/v1/systemone` | API base URL |
| `JEV_THRESHOLD` | `0.5` | Default threshold |

## Use cases

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json |
  jevq "the customer is asking for a refund" |
  jq -c '{id, subject}'
```

Open tickets asking for money back, printed as `{id, subject}`.

```bash
jq -c 'select(.level == "error")' samples/app.ndjson |
  jevq "this error is caused by a network timeout, not a bug in our code"
```

Error log lines that look like a timeout rather than a code bug.

```bash
gh api 'repos/itchyny/gojq/issues?state=open&per_page=100' |
  jq -c '.[] | select(.pull_request | not) | {number, title, body}' |
  jevq --score "reports a crash or wrong output, not a feature request" |
  jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"'
```

The five most bug-like open issues, as `number<TAB>title`.

More examples: [docs/examples.md](https://github.com/who/jevq/blob/main/docs/examples.md)

Full contract (output rules, exit codes, HTTP, retries): [docs/jevq.md](https://github.com/who/jevq/blob/main/docs/jevq.md)

## Testing

```bash
uv run pytest -q
bash tests/samples/run.sh
```

`JEVQ_LIVE=1 TYPESAFE_API_KEY=... bash tests/samples/run.sh` runs the sample pipes live.

Not supported in v1: `--path`, a `jev()` builtin, concurrency, caching.

# jevq

[![CI](https://github.com/who/jevq/actions/workflows/ci.yml/badge.svg)](https://github.com/who/jevq/actions/workflows/ci.yml)

`jq | jevq | jq`. jq handles structure: it selects, reshapes and prints.
jevq handles judgement: it reads one JSON value per line from stdin, asks a
TypeSafe System One model a yes/no question about each value, and passes
through the values it answers yes to. You write QUESTION as a yes/no claim
about the current value ("the customer is asking for a refund"). It is not a
search query.

## Install

```bash
uv sync
uv tool install --editable .
export TYPESAFE_API_KEY=...
```

If the global `jevq` falls out of step with this checkout, run
`scripts/reinstall-cli.sh` (see [docs/jevq.md](docs/jevq.md)).

## Pipes

Open tickets where the customer wants a refund:

```bash
jq -c '.[] | select(.status == "open")' tickets.json | jevq "the customer is asking for a refund" | jq -c '{id, subject}'
```

Failed logins in an NDJSON log, keeping lines that score 0.7 or higher:

```bash
jq -c . events.ndjson | jevq --score "this log line records a failed login" | jq -c 'select(.score >= 0.7) | .value'
```

Testing libraries among a package's dependencies. `-f key` sends only the
package name to the model; stdout still gets the whole `{key, value}` line:

```bash
jq -c '.dependencies | to_entries[]' package.json | jevq -f key "this npm package is a testing library" | jq -r .key
```

## Modes

- Default: emit each value whose score is at least the threshold (0.5 unless
  `-t` or `$JEV_THRESHOLD` says otherwise), unchanged.
- `--score`: emit every value as `{"score":<noul>,"value":<original>}` and
  leave the cutoff to jq.
- `--pass`: emit every value unchanged. No API call, no key needed.

The full reference (flags, environment, HTTP request, output, exit codes and
retries) is in [docs/jevq.md](docs/jevq.md).

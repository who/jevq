# jevq MVP

Unix filter: `jq | jevq | jq`.
Python + uv. Command name `jevq`.

Jev judges each JSON value. Stock jq still does structure.

## Goal

```bash
jq -c '.[] | select(.status == "open")' tickets.json \
  | jevq "the customer is asking for a refund" \
  | jq -c '{id, subject}'
```

## Non-goals (v1)

- No `jev()` builtin inside jq
- Not the TypeSafe `jev` CLI
- No `--path`
- No question YAML packs
- No persistent cache, no PyPI, no concurrency beyond a simple sequential loop
- Do not wrap or rewrite default stdout

## CLI

```
jevq [options] QUESTION
```

Reads JSON values from stdin (JSONL from `jq -c`). One System One call per value.

| Flag | Behavior |
|---|---|
| (default) | Keep the original value iff noul ≥ threshold |
| `--score` | Emit every row as `{"score": <noul>, "value": <original>}` |
| `--pass` | Emit every input value unchanged. No API call. No key required |
| `-t, --threshold N` | Cutoff in `[0,1]`. Default `0.5` or `$JEV_THRESHOLD` |
| `-f, --fields a,b` | Slim **state** only. Output is still the full original value |
| `--model NAME` | Default `jev-latest` or `$JEV_MODEL` |
| `-h, --help` | Usage |

Env: `TYPESAFE_API_KEY` (required except `--pass`), `JEV_MODEL`, `JEV_BASE_URL`, `JEV_THRESHOLD`.

QUESTION is a yes/no claim about the current object, not a search query.

## HTTP

`POST $JEV_BASE_URL` default `https://api.typesafe.ai/v1/systemone`

```json
{
  "model": "jev-latest",
  "state": { "...stdin object or --fields projection..." },
  "questions": {
    "q": { "type": "noul", "instructions": "<QUESTION>" }
  }
}
```

Use `answers.q.noul`. Retry 429/5xx a few times. An API failure is an error on stderr, not a “no”.

## Output contract

Default and `--pass`: write the **original value bytes** plus a newline. Do not `json.dumps` the object back out.

`--score` is the only wrap. `.value` is the original value bytes.

JSONL in, JSONL out. Input order. Do not slurp into an array.

Stderr only: counts and errors.

## Layout

```
jevq/
  pyproject.toml
  src/jevq/__init__.py
  src/jevq/cli.py
  src/jevq/client.py
  tests/test_passthrough.py
  docs/jevq.md
```

Install:

```bash
uv sync
uv tool install --editable .
```

`pyproject.toml` script: `jevq = jevq.cli:main`.
Python ≥ 3.12. Deps: `httpx`. Dev: `pytest`.

## Acceptance (must pass before done)

1. `--pass` identity
   ```bash
   jq -c '.[] | select(.status == "open")' tickets.json > /tmp/a.jsonl
   jevq --pass < /tmp/a.jsonl > /tmp/b.jsonl
   diff -q /tmp/a.jsonl /tmp/b.jsonl
   test "$(jq -s 'length' /tmp/a.jsonl)" = "$(jq -s 'length' /tmp/b.jsonl)"
   ```
2. `--help` prints the filter / `--score` / `--pass` examples.
3. Missing `TYPESAFE_API_KEY` without `--pass` exits nonzero and writes nothing to stdout.
4. `--fields` changes only the POST body; stdout line still has every original key.
5. `--score` lines are objects with numeric `score` and `value` equal to the input object.

Fixture: a small `tickets.json` with mixed `open` / `closed` rows.

## Task order for Ortus

1. Scaffold uv package + `jevq --help`
2. JSONL reader + `--pass` byte passthrough + identity test
3. httpx client for `/v1/systemone` noul
4. Default filter + `-t` + `-f`
5. `--score` wrap
6. README with the three pipes (tickets, ndjson, package.json)

Stop after that. Do not add `--path`, config files, or a TUI.

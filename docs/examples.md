# jevq examples

More pipes beyond the three in the [README](../README.md). They use the files
in `samples/`, so run them from the repo root. Output rules and exit codes
are in [jevq.md](jevq.md).

## Dev tools in runtime dependencies

```bash
jq -c '.dependencies | to_entries[]' samples/package.json |
  jevq "this npm package is a test, lint or build tool, not a runtime library" |
  jq -r .key
```

Prints the dependencies that belong in `devDependencies`, one name per line.

## Failed logins, cut at 0.7

```bash
printf '%s\n' \
    '{"level":"warn","msg":"failed login for alice from 10.0.0.5"}' \
    '{"level":"info","msg":"user bob logged in"}' \
    '{"level":"warn","msg":"invalid password for root from 203.0.113.9"}' \
    '{"level":"info","msg":"cache warmed in 120ms"}' |
  jevq --score "this log line records a failed login" |
  jq -c 'select(.score >= 0.7) | .value'
```

`--score` wraps each line with its score and jq applies the cutoff.

## Send only some fields with `-f`

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json |
  jevq -f subject,body "the customer is asking for a refund"
```

Only `subject` and `body` go to Jev; stdout still gets the full ticket.

## Tune the threshold with `-t`

```bash
jq -c '.[]' samples/tickets.json |
  jevq -t 0.8 "the customer is asking for a refund"
```

`-t 0.8` keeps confident matches only. To pick a value, look at the scores
first:

```bash
jq -c '.[]' samples/tickets.json |
  jevq --score "the customer is asking for a refund" |
  jq -r .score |
  sort -n
```

## Dry run with `--pass`

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json |
  jevq --pass |
  wc -l
```

Counts the rows a real run would ask about, with no API call and no key.
`--pass` is also an identity:

```bash
f=$(mktemp) && jq -c '.[]' samples/tickets.json > "$f" &&
  jevq --pass < "$f" |
  cmp - "$f" &&
  echo identical
```

## Rank GitHub issues offline

```bash
jq -c '.[] | select(.pull_request | not) | {number, title, body}' samples/gh-issues.json |
  jevq --score "reports a crash or wrong output, not a feature request" |
  jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"'
```

The README's GitHub pipe with `gh api` swapped for a saved copy.

## Counts and model with `-v`

```bash
jq -c '.[] | select(.status == "open")' samples/tickets.json |
  jevq -v "the customer is asking for a refund" > refunds.jsonl
```

At the end of the run stderr gets:

```
jevq: read 14, emitted 5
jevq: model: jev-1.13.0
```

## Tips

- Phrase QUESTION so a high score means yes to what you want to keep.
- To invert, filter on the score: `jevq --score "..." | jq -c 'select(.score < 0.5) | .value'`.
- Prefilter with jq and slim with `-f` so each row stays small (about 32k tokens max).
- Scores are not calibrated probabilities; tune `-t` on real data.
- One API call per row, sequential; the account limit is about 1,200 requests per minute.

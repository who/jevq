#!/usr/bin/env bash
# End-to-end sample pipes: stock jq prefilters, jevq judges, jq post-processes.
#
# The default run starts tests/samples/fake_systemone.py on 127.0.0.1 and
# points jevq at it, so it needs no API key and makes no network calls. With
# JEVQ_LIVE=1 and a real TYPESAFE_API_KEY it also runs the four sample pipes
# against the real default endpoint, with looser checks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$REPO_ROOT"

# Captured before the default run overrides the environment.
LIVE_KEY="${TYPESAFE_API_KEY:-}"
LIVE="${JEVQ_LIVE:-}"
unset JEV_MODEL JEV_THRESHOLD JEV_BASE_URL JEVQ_LIVE

Q_REFUND="the customer is asking for a refund"
Q_TIMEOUT="this error is caused by a network timeout, not a bug in our code"
Q_TOOL="this npm package is a test, lint or build tool, not a runtime library"
Q_CRASH="reports a crash or wrong output, not a feature request"

WORK="$(mktemp -d)"
LOG="$WORK/requests.jsonl"
SERVER_PID=""
UV_PID=""
PASSED=0
FAILED=0
SKIPPED=0

start_server() {
  uv run --quiet python tests/samples/fake_systemone.py \
    --rules tests/samples/rules.json --log "$LOG" \
    --port-file "$WORK/port" --pid-file "$WORK/pid" 2>"$WORK/server.err" &
  UV_PID=$!
  local i
  for ((i = 0; i < 100; i++)); do
    if [[ -s $WORK/port ]]; then
      SERVER_PID="$(cat "$WORK/pid")"
      return 0
    fi
    sleep 0.1
  done
  echo "FAIL server: port file did not appear within 10s" >&2
  cat "$WORK/server.err" >&2 || true
  exit 1
}

stop_server() {
  local pid
  for pid in "$SERVER_PID" "$UV_PID"; do
    [[ -n $pid ]] && kill -TERM "$pid" 2>/dev/null || true
  done
  [[ -n $UV_PID ]] && wait "$UV_PID" 2>/dev/null || true
  SERVER_PID=""
  UV_PID=""
  rm -rf "$WORK"
}

trap stop_server EXIT
trap 'stop_server; exit 130' INT TERM

jevq() {
  uv run --quiet jevq "$@" 2>>"$WORK/jevq.err"
}

fail() {
  printf '%s\n' "$*" >"$WORK/reason"
  exit 1
}

run_case() {
  local name=$1 fn=$2
  : >"$WORK/reason"
  if ("$fn"); then
    echo "PASS $name"
    PASSED=$((PASSED + 1))
  else
    echo "FAIL $name: $(cat "$WORK/reason")"
    FAILED=$((FAILED + 1))
  fi
}

skip_case() {
  echo "SKIP $1"
  SKIPPED=$((SKIPPED + 1))
}

log_count() {
  wc -l <"$LOG" | tr -d ' '
}

pre_tickets() { jq -c '.[] | select(.status == "open")' samples/tickets.json; }
pre_logs() { jq -c 'select(.level == "error")' samples/app.ndjson; }
pre_deps() { jq -c '.dependencies | to_entries[]' samples/package.json; }
pre_issues() { jq -c '.[] | select(.pull_request | not) | {number, title, body}' samples/gh-issues.json; }

# Pipe 1: open refund tickets; 1010 is the borderline partial-credit ask.
EXPECT_TICKETS="1003,1007,1010,1012,1016"
EXPECT_TICKETS_STRICT="1003,1007,1012,1016"
CLOSED_REFUNDS="1002 1005 1014"

ticket_ids() {
  jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq "$@" "$Q_REFUND" | jq -c '{id, subject}' \
    | jq -r .id | paste -sd, -
}

case_tickets() {
  local out ids id
  out=$(jq -c '.[] | select(.status == "open")' samples/tickets.json | jevq "$Q_REFUND" | jq -c '{id, subject}') \
    || fail "pipe exited nonzero"
  ids=$(jq -r .id <<<"$out" | paste -sd, -)
  [[ $ids == "$EXPECT_TICKETS" ]] || fail "ids $ids, expected $EXPECT_TICKETS"
  for id in $CLOSED_REFUNDS; do
    ! jq -e "select(.id == $id)" <<<"$out" >/dev/null || fail "closed ticket $id emitted"
  done
}

# Pipe 2: timeout errors only; the warn-level timeout is dropped by jq.
EXPECT_TIMEOUTS="2026-09-01T12:01:00Z,2026-09-01T12:03:30Z,2026-09-01T12:06:00Z,2026-09-01T12:09:00Z"

case_logs() {
  local pre out ts line
  pre=$(pre_logs)
  out=$(pre_logs | jevq "$Q_TIMEOUT") || fail "pipe exited nonzero"
  ts=$(jq -r .ts <<<"$out" | paste -sd, -)
  [[ $ts == "$EXPECT_TIMEOUTS" ]] || fail "ts $ts, expected $EXPECT_TIMEOUTS"
  while IFS= read -r line; do
    grep -Fxq -- "$line" <<<"$pre" || fail "line not byte-identical to input: $line"
  done <<<"$out"
}

# Pipe 3: dev tooling that sits in dependencies.
EXPECT_TOOLS="jest,eslint,webpack,typescript,prettier"

case_deps() {
  local out
  out=$(jq -c '.dependencies | to_entries[]' samples/package.json | jevq "$Q_TOOL" | jq -r '.key') \
    || fail "pipe exited nonzero"
  out=$(paste -sd, - <<<"$out")
  [[ $out == "$EXPECT_TOOLS" ]] || fail "keys $out, expected $EXPECT_TOOLS"
}

# Pipe 4: rank non-PR issues; rules give the top six distinct scores.
EXPECT_TOP5="201,204,205,208,209"

case_issues() {
  local pre scored top i n
  pre=$(pre_issues)
  scored=$(pre_issues | jevq --score "$Q_CRASH") || fail "jevq --score exited nonzero"
  n=$(wc -l <<<"$pre")
  [[ $(wc -l <<<"$scored") -eq $n ]] || fail "expected $n scored lines"
  for ((i = 1; i <= n; i++)); do
    jq -e '.score | type == "number"' <<<"$(sed -n "${i}p" <<<"$scored")" >/dev/null \
      || fail "line $i: .score is not a number"
    [[ $(sed -n "${i}p" <<<"$scored" | jq -c .value) == "$(sed -n "${i}p" <<<"$pre")" ]] \
      || fail "line $i: .value differs from its input"
  done
  top=$(jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"' <<<"$scored") \
    || fail "post jq failed"
  top=$(cut -f1 <<<"$top" | paste -sd, -)
  [[ $top == "$EXPECT_TOP5" ]] || fail "top 5 $top, expected $EXPECT_TOP5"
}

case_fields() {
  local before plain slim keys
  plain=$(ticket_ids) || fail "plain pipe exited nonzero"
  before=$(log_count)
  slim=$(ticket_ids -f subject,body) || fail "--fields pipe exited nonzero"
  [[ $slim == "$plain" ]] || fail "stdout differs: $slim vs $plain"
  keys=$(tail -n +"$((before + 1))" "$LOG" | jq -c '.state | keys' | sort -u)
  [[ $keys == '["body","subject"]' ]] || fail "state keys $keys"
}

case_threshold() {
  local loose strict
  loose=$(ticket_ids) || fail "default pipe exited nonzero"
  strict=$(ticket_ids -t 0.8) || fail "-t 0.8 pipe exited nonzero"
  [[ $loose == "$EXPECT_TICKETS" ]] || fail "default ids $loose"
  [[ $strict == "$EXPECT_TICKETS_STRICT" ]] || fail "-t 0.8 ids $strict"
  [[ $(tr , '\n' <<<"$loose" | wc -l) -eq 5 && $(tr , '\n' <<<"$strict" | wc -l) -eq 4 ]] \
    || fail "counts not 5 then 4"
}

case_pass() {
  local before pre
  before=$(log_count)
  for pre in pre_tickets pre_logs pre_deps pre_issues; do
    "$pre" >"$WORK/pre"
    [[ -s $WORK/pre ]] || fail "$pre is empty"
    jevq --pass <"$WORK/pre" >"$WORK/out" || fail "$pre: --pass exited nonzero"
    cmp -s "$WORK/pre" "$WORK/out" || fail "$pre: --pass output differs"
  done
  [[ $(log_count) -eq $before ]] || fail "--pass made API calls"
}

case_calls() {
  local before n added models
  n=$(pre_tickets | wc -l)
  [[ $n -gt 0 ]] || fail "prefilter is empty"
  before=$(log_count)
  pre_tickets | jevq "$Q_REFUND" >/dev/null || fail "pipe exited nonzero"
  added=$(($(log_count) - before))
  [[ $added -eq $n ]] || fail "$added requests for $n values"
  models=$(tail -n +"$((before + 1))" "$LOG" | jq -r .model | sort -u)
  [[ $models == "jev-1.13.0" ]] || fail "models: $models"
}

case_missing_key() {
  local before code=0
  before=$(log_count)
  pre_tickets >"$WORK/pre"
  env -u TYPESAFE_API_KEY uv run --quiet jevq "$Q_REFUND" <"$WORK/pre" >"$WORK/out" 2>>"$WORK/jevq.err" || code=$?
  [[ $code -eq 2 ]] || fail "exit $code, expected 2"
  [[ ! -s $WORK/out ]] || fail "stdout not empty"
  [[ $(log_count) -eq $before ]] || fail "request made without a key"
}

# Pipe 1 again: a successful run is silent on stderr; -v adds counts and model.
case_quiet() {
  local ids
  pre_tickets >"$WORK/pre"
  uv run --quiet jevq "$Q_REFUND" <"$WORK/pre" >"$WORK/out" 2>"$WORK/quiet.err" \
    || fail "pipe exited nonzero"
  [[ ! -s $WORK/quiet.err ]] || fail "stderr not empty: $(head -c 200 "$WORK/quiet.err")"
  ids=$(jq -r .id "$WORK/out" | paste -sd, -)
  [[ $ids == "$EXPECT_TICKETS" ]] || fail "ids $ids, expected $EXPECT_TICKETS"
}

case_verbose() {
  local n m
  pre_tickets >"$WORK/pre"
  n=$(wc -l <"$WORK/pre" | tr -d ' ')
  m=$(tr , '\n' <<<"$EXPECT_TICKETS" | wc -l | tr -d ' ')
  uv run --quiet jevq -v "$Q_REFUND" <"$WORK/pre" >"$WORK/out" 2>"$WORK/verbose.err" \
    || fail "pipe exited nonzero"
  grep -Fxq "jevq: read $n, emitted $m" "$WORK/verbose.err" \
    || fail "no counts line: $(head -c 200 "$WORK/verbose.err")"
  grep -Fxq "jevq: model: jev-1.13.0" "$WORK/verbose.err" || fail "no model line"
}

# Live mode: real endpoint, so only shape checks.
live_filter() {
  local pre=$1
  shift
  "$pre" >"$WORK/pre"
  TYPESAFE_API_KEY="$LIVE_KEY" jevq "$@" <"$WORK/pre" >"$WORK/out" || fail "jevq exited nonzero"
  jq -e . "$WORK/out" >/dev/null 2>&1 || [[ ! -s $WORK/out ]] || fail "output is not JSON"
}

live_subset() {
  local line
  while IFS= read -r line; do
    grep -Fxq -- "$line" "$WORK/pre" || fail "output line not in input: $line"
  done <"$WORK/out"
}

live_tickets() {
  live_filter pre_tickets "$Q_REFUND"
  live_subset
  jq -c '{id, subject}' "$WORK/out" >/dev/null || fail "post jq failed"
}
live_logs() { live_filter pre_logs "$Q_TIMEOUT" && live_subset; }
live_deps() {
  live_filter pre_deps "$Q_TOOL"
  live_subset
  jq -r '.key' "$WORK/out" >/dev/null || fail "post jq failed"
}
live_issues() {
  live_filter pre_issues --score "$Q_CRASH"
  jq -se 'length > 0 and all(.[]; (.score | type == "number") and .score >= 0 and .score <= 1)' \
    "$WORK/out" >/dev/null || fail "scores not all in [0,1]"
  jq -rs 'sort_by(-.score) | .[:5][] | .value | "\(.number)\t\(.title)"' "$WORK/out" >/dev/null \
    || fail "post jq failed"
}

start_server
PORT="$(tr -d '[:space:]' <"$WORK/port")"
export TYPESAFE_API_KEY=test-key
export JEV_BASE_URL="http://127.0.0.1:$PORT/v1/systemone"
echo "samples: base_url=$JEV_BASE_URL"

run_case tickets case_tickets
run_case logs case_logs
run_case deps case_deps
run_case issues case_issues
run_case fields case_fields
run_case threshold case_threshold
run_case pass case_pass
run_case calls case_calls
run_case missing-key case_missing_key
run_case quiet case_quiet
run_case verbose case_verbose

if [[ $LIVE == 1 && -n $LIVE_KEY ]]; then
  unset JEV_BASE_URL
  run_case live-tickets live_tickets
  run_case live-logs live_logs
  run_case live-deps live_deps
  run_case live-issues live_issues
else
  for name in live-tickets live-logs live-deps live-issues; do
    skip_case "$name"
  done
fi

echo "samples: $PASSED passed, $FAILED failed, $SKIPPED skipped"
[[ $FAILED -eq 0 ]]

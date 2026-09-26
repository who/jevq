#!/usr/bin/env bash
# Rebuild and reinstall this checkout as the global `jevq` command.
#
# `uv tool install` may reuse a cached build or an existing tool environment,
# so the installed jevq can silently drift from the code on disk. This script
# always forces a rebuild (--force --reinstall), then reports what got
# installed and checks that the installed command actually works.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

usage() {
  cat <<'EOF'
usage: scripts/reinstall-cli.sh [--dry-run] [--no-editable] [--skip-smoke] [-h|--help]

Force-reinstall this jevq checkout as the global `jevq` uv tool.

options:
  --dry-run      print the uv command and change nothing
  --no-editable  install a snapshot instead of an editable install
  --skip-smoke   skip the `jevq --pass` passthrough smoke test
  -h, --help     show this help and exit

Respects UV_TOOL_DIR and UV_TOOL_BIN_DIR.
EOF
}

die() {
  printf 'reinstall-cli: error: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'reinstall-cli: warning: %s\n' "$*" >&2
}

installed_jevq() {
  local line
  line="$(uv tool list 2>/dev/null | grep -m 1 '^jevq v' || true)"
  printf '%s\n' "${line:-not installed}"
}

TMPFILES=()
cleanup() {
  if ((${#TMPFILES[@]})); then
    rm -f "${TMPFILES[@]}"
  fi
}
trap cleanup EXIT

smoke() {
  local bin="$1" out err expected
  out="$(mktemp)"
  err="$(mktemp)"
  expected="$(mktemp)"
  TMPFILES+=("$out" "$err" "$expected")
  printf '{"a":1}\n' >"$expected"
  if ! printf '{"a":1}\n' | env -u TYPESAFE_API_KEY "$bin" --pass >"$out" 2>"$err"; then
    printf 'reinstall-cli: error: smoke test failed: %s --pass exited nonzero\n' "$bin" >&2
    cat "$err" >&2
    exit 1
  fi
  if ! cmp -s "$expected" "$out"; then
    printf 'reinstall-cli: error: smoke test failed: %s --pass did not round-trip {"a":1}\n' "$bin" >&2
    cat "$err" >&2
    exit 1
  fi
}

dry_run=0
editable=1
skip_smoke=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --no-editable) editable=0 ;;
    --skip-smoke) skip_smoke=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'reinstall-cli: unknown argument: %s\n' "$arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v uv >/dev/null 2>&1 || die "uv not found on PATH (see https://docs.astral.sh/uv/)"

cmd=(uv tool install)
if ((editable)); then
  cmd+=(--editable)
  mode=editable
else
  mode=snapshot
fi
cmd+=(--force --reinstall "$REPO_ROOT")

if ((dry_run)); then
  printf 'dry-run:'
  printf ' %q' "${cmd[@]}"
  printf '\n'
  exit 0
fi

before="$(installed_jevq)"

head=unknown
if command -v git >/dev/null 2>&1 && head="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null)"; then
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
    head+=" (dirty)"
    warn "working tree is dirty; the installed tool includes uncommitted changes"
  fi
else
  head=unknown
fi

"${cmd[@]}"

after="$(installed_jevq)"
bin_dir="$(uv tool dir --bin)"
fresh="$bin_dir/jevq"

on_path="$(command -v jevq 2>/dev/null || true)"
if [[ -z "$on_path" ]]; then
  on_path="not on PATH"
elif [[ "$on_path" != "$fresh" ]]; then
  warn "$on_path shadows the fresh install at $fresh"
fi

smoke_status=skipped
if ((!skip_smoke)); then
  smoke "$fresh"
  smoke_status=ok
fi

cat <<EOF
jevq reinstalled
  before:  $before
  version: $after
  source:  $REPO_ROOT ($mode)
  head:    $head
  command: $on_path
  smoke:   $smoke_status
EOF

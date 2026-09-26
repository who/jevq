# Changelog

All notable changes to jevq are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and jevq uses
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-09-26

### Added

- The jq sidecar filter: read JSONL on stdin and keep each value whose System
  One noul is at or above the threshold, emitting the original bytes.
- `--score`, which wraps every value as `{"score":<noul>,"value":<original>}`.
- `--pass`, a byte passthrough with no API call and no key.
- `-t/--threshold` and `$JEV_THRESHOLD`.
- `-f/--fields`, which sends only the named keys as state.
- `--model`, with the default pinned to `jev-1.13.0`, and `$JEV_MODEL`.
- `-v/--verbose` for end-of-run counts and the answering model; stderr stays
  quiet on success otherwise.
- Retries with backoff on HTTP 429 and 5xx responses.
- `samples/` fixtures and offline sample pipe tests against a fake System One.
- GitHub Actions CI.
- `scripts/reinstall-cli.sh`.
- PyPI packaging with a tag-triggered release workflow.

[Unreleased]: https://github.com/who/jevq/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/who/jevq/releases/tag/v0.1.0

# jevq

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

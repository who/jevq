import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "reinstall-cli.sh"


@pytest.fixture
def tool_env(tmp_path):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env["UV_TOOL_DIR"] = str(tmp_path / "tools")
    env["UV_TOOL_BIN_DIR"] = str(tmp_path / "bin")
    env["PATH"] = str(tmp_path / "bin") + os.pathsep + os.environ["PATH"]
    return env


def run_script(*args, env, cwd=REPO_ROOT):
    return subprocess.run(
        [str(SCRIPT), *args], env=env, cwd=cwd, capture_output=True, text=True
    )


def test_script_is_executable_and_parses():
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text().splitlines()[0] == "#!/usr/bin/env bash"
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_help_lists_flags(tool_env):
    result = run_script("--help", env=tool_env)
    assert result.returncode == 0
    for flag in ("--dry-run", "--no-editable", "--skip-smoke"):
        assert flag in result.stdout


def test_dry_run_installs_nothing(tool_env, tmp_path):
    result = run_script("--dry-run", env=tool_env)
    assert result.returncode == 0, result.stderr
    (line,) = result.stdout.splitlines()
    assert line.startswith("dry-run: uv tool install ")
    assert "--editable" in line and "--reinstall" in line
    assert str(REPO_ROOT) in line
    for name in ("tools", "bin"):
        path = tmp_path / name
        assert not path.exists() or not any(path.iterdir())

    snapshot = run_script("--dry-run", "--no-editable", env=tool_env)
    assert "--editable" not in snapshot.stdout


def test_install_from_other_cwd(tool_env, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    result = run_script(env=tool_env, cwd=other)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bin" / "jevq").exists()
    head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head in result.stdout
    assert "jevq reinstalled" in result.stdout
    assert f"source:  {REPO_ROOT} (editable)" in result.stdout
    assert "smoke:   ok" in result.stdout


def test_missing_uv_fails_fast(tool_env):
    if shutil.which("uv", path="/usr/bin:/bin") is not None:
        pytest.skip("uv is installed in /usr/bin or /bin")
    tool_env["PATH"] = "/usr/bin:/bin"
    result = run_script("--dry-run", env=tool_env)
    assert result.returncode != 0
    assert "uv" in result.stderr
    assert result.stdout == ""


def test_unknown_flag_exits_2(tool_env):
    result = run_script("--definitely-not-a-flag", env=tool_env)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert result.stdout == ""

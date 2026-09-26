# Releasing jevq

The version comes from the git tag (hatch-vcs), so there is nothing to bump in
`pyproject.toml`.

## Cut a release

1. In `CHANGELOG.md`, move the `[Unreleased]` notes under
   `## [X.Y.Z] - YYYY-MM-DD` and update the compare links at the bottom.
2. Commit and push to `main`.
3. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. `.github/workflows/release.yml` builds the wheel and sdist, publishes them
   to PyPI, and creates a GitHub release whose notes are that version's
   CHANGELOG section.

A tag containing `-test` (for example `v0.2.0-test1`) builds and creates the
GitHub release but skips PyPI. A manual `workflow_dispatch` run only builds.

## One-time setup

Publishing uses PyPI trusted publishing; there are no tokens or secrets.

1. On pypi.org, add a pending publisher with these values:
   - PyPI project name: `jevq`
   - Owner: `who`
   - Repository: `jevq`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. In the GitHub repository settings, create an environment named `pypi`.

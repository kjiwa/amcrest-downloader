# Contributing

## Setup and checks

```sh
uv run python -m unittest discover
uv run --only-group dev ruff check
uv run --only-group dev ruff format --check
```

The repo tests run `shellcheck` on `scripts/*.sh` and skip that check when it is not
installed. The end-to-end checks need `ffmpeg`.

A defect found in review is fixed with a test for its class, not only its instance.

## Releasing

```sh
sh scripts/release.sh [--dry-run] <version>
```

`<version>` is bare (`0.3.0`, not `v0.3.0`). Run it on a clean, synced `main`.
The script runs the same checks CI runs, opens a `release-<version>` PR with the
`pyproject.toml` bump, waits for its checks, and squash-merges it. GitHub signs the
squash commit, so the release shows as Verified. It then tags the merged commit and
creates the GitHub release from the matching `CHANGELOG.md` section, so the version
needs a `## <version>` heading there before you run it. If the bump is already on
`main`, it skips the PR and only tags and releases, so a run that stopped after the
merge can be repeated. `--dry-run` runs every check and prints each mutating command
instead of running it.

The release event triggers `publish.yml`, which re-runs `scripts/check-release.sh`
(the tag, its title, and the `CHANGELOG.md` heading must all agree) before building
and publishing to PyPI.

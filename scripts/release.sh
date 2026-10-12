#!/bin/sh
# Cut an amcrest-downloader release: land the version bump through a pull request, run
# the same checks CI runs, tag the merged commit, and create the GitHub release
# from the matching CHANGELOG section. The next release should be reproducible
# from this script rather than reconstructed from memory.
#
# Usage: sh scripts/release.sh [--dry-run] <version>
#
# <version> is bare (0.1.8, not v0.1.8). --dry-run runs every check and
# prints each mutating command instead of running it.
#
# The bump goes through a squash-merged PR, not a push to main: GitHub signs
# the squash commit, so the release shows as Verified, and the main ruleset
# requires a PR. If pyproject.toml on main already reads <version> (the bump
# PR was merged by hand, or a previous run stopped after merging), the PR
# steps are skipped and the script only tags and releases.
set -eu

_run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ $*"
  else
    "$@"
  fi
}

_parse_args() {
  _parse_args_dry_run=0
  _parse_args_version=""
  while [ $# -gt 0 ]; do
    case $1 in
      --dry-run)
        _parse_args_dry_run=1
        shift
        ;;
      -*)
        echo "release: unknown option '$1'" >&2
        exit 2
        ;;
      *)
        if [ -n "$_parse_args_version" ]; then
          echo "release: unexpected argument '$1'" >&2
          exit 2
        fi
        _parse_args_version=$1
        shift
        ;;
    esac
  done

  if [ -z "$_parse_args_version" ]; then
    echo "usage: sh scripts/release.sh [--dry-run] <version>" >&2
    exit 2
  fi
  if ! echo "$_parse_args_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "release: version '$_parse_args_version' does not match X.Y.Z" >&2
    exit 1
  fi
  DRY_RUN=$_parse_args_dry_run
  VERSION=$_parse_args_version
  TAG="v$VERSION"
  BRANCH="release-$VERSION"
  readonly DRY_RUN VERSION TAG BRANCH
}

_check_preconditions() {
  sh "$REPO_ROOT/scripts/check-release.sh" --changelog "$TAG"

  _check_preconditions_branch=$(git -C "$REPO_ROOT" branch --show-current)
  if [ "$_check_preconditions_branch" != "main" ]; then
    echo "release: must be on main, not '$_check_preconditions_branch'" >&2
    exit 1
  fi

  if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
    echo "release: worktree is not clean" >&2
    exit 1
  fi

  git -C "$REPO_ROOT" fetch origin main

  _check_preconditions_local=$(git -C "$REPO_ROOT" rev-parse main)
  _check_preconditions_remote=$(git -C "$REPO_ROOT" rev-parse origin/main)
  if [ "$_check_preconditions_local" != "$_check_preconditions_remote" ]; then
    echo "release: main has diverged from origin/main" >&2
    exit 1
  fi

  if git -C "$REPO_ROOT" tag --list "$TAG" | grep -Fxq "$TAG"; then
    echo "release: tag '$TAG' already exists locally" >&2
    exit 1
  fi

  if git -C "$REPO_ROOT" ls-remote --tags origin "$TAG" | grep -q "$TAG"; then
    echo "release: tag '$TAG' already exists on origin" >&2
    exit 1
  fi

  if gh release view "$TAG" >/dev/null 2>&1; then
    echo "release: release '$TAG' already exists" >&2
    exit 1
  fi
}

_bump_version() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ set pyproject.toml version to $VERSION"
    return
  fi
  _bump_version_tmp=$(mktemp "${TMPDIR:-/tmp}/release-pyproject.XXXXXX")
  trap 'rm -f "$_bump_version_tmp"' EXIT
  sed "s/^version = \".*\"\$/version = \"$VERSION\"/" "$PYPROJECT" >"$_bump_version_tmp"
  cat "$_bump_version_tmp" >"$PYPROJECT"
  rm -f "$_bump_version_tmp"
  trap - EXIT
}

_run_release_check() {
  # check-release.sh reads the version straight from pyproject.toml, which
  # --dry-run never writes; simulate the bump for this one check, then
  # restore the file, so a dry run actually exercises the real gate instead
  # of failing on the version it deliberately didn't apply.
  if [ "$DRY_RUN" -eq 1 ]; then
    _run_release_check_tmp=$(mktemp "${TMPDIR:-/tmp}/release-pyproject.XXXXXX")
    cp "$PYPROJECT" "$_run_release_check_tmp"
    trap 'cat "$_run_release_check_tmp" >"$PYPROJECT"; rm -f "$_run_release_check_tmp"' EXIT
    trap 'exit 130' INT TERM
    sed "s/^version = \".*\"\$/version = \"$VERSION\"/" "$_run_release_check_tmp" >"$PYPROJECT"
    _run_release_check_status=0
    sh "$REPO_ROOT/scripts/check-release.sh" "$TAG" "$TAG" || _run_release_check_status=$?
    cat "$_run_release_check_tmp" >"$PYPROJECT"
    rm -f "$_run_release_check_tmp"
    trap - EXIT INT TERM
    return "$_run_release_check_status"
  fi
  sh "$REPO_ROOT/scripts/check-release.sh" "$TAG" "$TAG"
}

_run_tests() {
  (cd "$REPO_ROOT" && uv run python -m unittest discover)
  (cd "$REPO_ROOT" && uv run --only-group dev ruff check)
  (cd "$REPO_ROOT" && uv run --only-group dev ruff format --check)
}

_is_bumped() {
  _is_bumped_current=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$PYPROJECT" | head -n1)
  [ "$_is_bumped_current" = "$VERSION" ]
}

_check_branch_absent() {
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo "release: branch '$BRANCH' already exists locally" >&2
    exit 1
  fi
  if git -C "$REPO_ROOT" ls-remote --heads origin "$BRANCH" | grep -q .; then
    echo "release: branch '$BRANCH' already exists on origin" >&2
    exit 1
  fi
}

_commit_and_push_branch() {
  _run git -C "$REPO_ROOT" add "$PYPROJECT"
  _run git -C "$REPO_ROOT" commit -m "Release $VERSION"
  _run git -C "$REPO_ROOT" push -u origin "$BRANCH"
  _run git -C "$REPO_ROOT" switch main
}

_open_pr() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr create --base main --head $BRANCH --title 'Release $VERSION'" >&2
    echo "<pr-url>"
    return
  fi
  gh pr create --base main --head "$BRANCH" --title "Release $VERSION" \
    --body "Version bump for $VERSION; scripts/release.sh tags and publishes after merge."
}

_await_checks() {
  _await_checks_pr_url=$1
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr checks $_await_checks_pr_url --watch --fail-fast"
    return
  fi
  # A new PR reports no checks for a few seconds, and --watch on none exits
  # at once, so wait for the first check to register.
  _await_checks_tries=0
  while [ "$(gh pr checks "$_await_checks_pr_url" --json name --jq length 2>/dev/null || echo 0)" -eq 0 ]; do
    _await_checks_tries=$((_await_checks_tries + 1))
    if [ "$_await_checks_tries" -gt 24 ]; then
      echo "release: no checks reported on $_await_checks_pr_url after 2 minutes" >&2
      exit 1
    fi
    sleep 5
  done
  # All checks, not only the required ones: the ruleset's CodeQL rule also
  # blocks the merge until analysis finishes.
  gh pr checks "$_await_checks_pr_url" --watch --fail-fast
}

_merge_pr() {
  _merge_pr_pr_url=$1
  # --match-head-commit refuses to merge if the branch moved during the wait.
  # No --admin: bypassing the ruleset is what leaves the commit unsigned.
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh pr merge $_merge_pr_pr_url --squash --delete-branch --match-head-commit <branch-head>"
    return
  fi
  gh pr merge "$_merge_pr_pr_url" --squash --delete-branch \
    --match-head-commit "$(git -C "$REPO_ROOT" rev-parse "$BRANCH")"
}

_sync_main() {
  _sync_main_pr_url=$1
  _run git -C "$REPO_ROOT" pull --ff-only origin main
  if [ "$DRY_RUN" -eq 1 ]; then
    return
  fi
  # Tags go on HEAD, so HEAD must be the merge commit, not a later push.
  _sync_main_merged=$(gh pr view "$_sync_main_pr_url" --json mergeCommit --jq .mergeCommit.oid)
  if [ "$(git -C "$REPO_ROOT" rev-parse HEAD)" != "$_sync_main_merged" ]; then
    echo "release: main moved past the release commit $_sync_main_merged" >&2
    exit 1
  fi
}

_land_bump() {
  _check_branch_absent
  _run git -C "$REPO_ROOT" switch -c "$BRANCH"
  _bump_version
  _run_release_check
  _run_tests
  _commit_and_push_branch
  _land_bump_pr_url=$(_open_pr)
  _await_checks "$_land_bump_pr_url"
  _merge_pr "$_land_bump_pr_url"
  _sync_main "$_land_bump_pr_url"
}

_tag_and_push() {
  _run git -C "$REPO_ROOT" tag -a "$TAG" -m "$TAG"
  _run git -C "$REPO_ROOT" push origin "$TAG"
}

_create_github_release() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ gh release create $TAG --title $TAG --notes-file <## $VERSION CHANGELOG section>"
    return
  fi
  _create_github_release_notes=$(mktemp "${TMPDIR:-/tmp}/release-notes.XXXXXX")
  trap 'rm -f "$_create_github_release_notes"' EXIT
  awk -v ver="## $VERSION" '
    $0 == ver { found = 1; next }
    found && /^## / { exit }
    found { print }
  ' "$CHANGELOG" >"$_create_github_release_notes"
  gh release create "$TAG" --title "$TAG" --notes-file "$_create_github_release_notes"
  rm -f "$_create_github_release_notes"
  trap - EXIT
}

main() {
  REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
  readonly REPO_ROOT
  readonly PYPROJECT="$REPO_ROOT/pyproject.toml"
  readonly CHANGELOG="$REPO_ROOT/CHANGELOG.md"

  _parse_args "$@"
  _check_preconditions
  if _is_bumped; then
    _run_release_check
  else
    _land_bump
  fi
  _tag_and_push
  _create_github_release
}

main "$@"

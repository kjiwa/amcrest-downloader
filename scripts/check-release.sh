#!/bin/sh
# Check that a release's tag and title match the version in pyproject.toml
# and that CHANGELOG.md has a matching heading, so a hand-cut release
# cannot drift the way v0.1.7 did.
#
# Usage: sh scripts/check-release.sh <tag> <title>
#        sh scripts/check-release.sh --changelog <tag>
#
# --changelog checks only the CHANGELOG heading, for use before the version
# bump has landed in pyproject.toml.
set -eu

_check_tag_shape() {
  _check_tag_shape_tag=$1
  if ! echo "$_check_tag_shape_tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "check-release: tag '$_check_tag_shape_tag' does not match vX.Y.Z" >&2
    return 1
  fi
}

_check_tag_matches_version() {
  _check_tag_matches_version_tag=$1
  _check_tag_matches_version_version=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$PYPROJECT" | head -n1)
  if [ -z "$_check_tag_matches_version_version" ]; then
    echo "check-release: could not read version from $PYPROJECT" >&2
    return 1
  fi
  if [ "$_check_tag_matches_version_tag" != "v$_check_tag_matches_version_version" ]; then
    echo "check-release: tag '$_check_tag_matches_version_tag' does not match pyproject.toml version '$_check_tag_matches_version_version'" >&2
    return 1
  fi
}

_check_title_matches_tag() {
  _check_title_matches_tag_tag=$1
  _check_title_matches_tag_title=$2
  if [ "$_check_title_matches_tag_title" != "$_check_title_matches_tag_tag" ]; then
    echo "check-release: title '$_check_title_matches_tag_title' does not match tag '$_check_title_matches_tag_tag'" >&2
    return 1
  fi
}

_check_changelog_heading() {
  _check_changelog_heading_tag=$1
  _check_changelog_heading_version=${_check_changelog_heading_tag#v}
  if ! grep -Fxq "## $_check_changelog_heading_version" "$CHANGELOG"; then
    echo "check-release: CHANGELOG.md has no '## $_check_changelog_heading_version' heading" >&2
    return 1
  fi
}

main() {
  REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
  readonly REPO_ROOT
  readonly PYPROJECT="$REPO_ROOT/pyproject.toml"
  readonly CHANGELOG="$REPO_ROOT/CHANGELOG.md"

  if [ $# -eq 2 ] && [ "$1" = "--changelog" ]; then
    _check_changelog_heading "$2"
    exit $?
  fi
  if [ $# -ne 2 ]; then
    echo "usage: sh scripts/check-release.sh <tag> <title>" >&2
    echo "       sh scripts/check-release.sh --changelog <tag>" >&2
    exit 2
  fi

  _main_tag=$1
  _main_title=$2
  _main_status=0

  _check_tag_shape "$_main_tag" || _main_status=1
  if [ "$_main_status" -eq 0 ]; then
    _check_tag_matches_version "$_main_tag" || _main_status=1
  fi
  _check_title_matches_tag "$_main_tag" "$_main_title" || _main_status=1
  _check_changelog_heading "$_main_tag" || _main_status=1

  exit "$_main_status"
}

main "$@"

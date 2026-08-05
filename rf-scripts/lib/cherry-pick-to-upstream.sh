#!/usr/bin/env bash
set -euo pipefail

# lib/cherry-pick-to-upstream.sh
# Shared core logic for preparing an upstream branch from a master-rf feature branch.
#
# Usage: cherry-pick-to-upstream.sh <current_branch> <upstream_branch> [status_file]
#
# Exits 0 on success, 1 on failure.
# On success, prints commit list to stdout.
# On failure, prints error message to stderr.
#
# If a status_file path is given, this script writes two lines to it on success:
#   NEEDS_FORCE=true|false   whether the caller must force-push (history was rewritten)
#   NO_CHANGES=true|false    whether the upstream branch was already up to date
#
# Strategy:
#   We always cherry-pick with `-x`, which appends a
#   "(cherry picked from commit <sha>)" trailer to each resulting commit
#   message. That lets us later determine, from commit *metadata alone*
#   (no blob/diff content needed), which original internal commits are
#   already reflected on the upstream branch.
#
#   If the upstream branch already exists on origin, and the original SHAs
#   recorded in its commits' trailers are an in-order prefix of the current
#   commit range, we can cherry-pick just the *new* trailing commits onto the
#   existing upstream branch tip. This produces a fast-forward that does not
#   require a force-push.
#
#   Otherwise (upstream branch doesn't exist yet, trailers are missing e.g.
#   from a branch built before this feature existed, or history has diverged
#   because internal commits were amended/rebased) we fall back to
#   rebuilding the upstream branch fresh from master and cherry-picking the
#   full range, which requires a force-push.
#
#   Deliberately avoided: comparing by diff/patch-id. On a partial clone
#   (--filter=blob:none, used by our CI checkout to keep this large repo's
#   fetch fast) computing a diff requires downloading blob content that
#   isn't present locally, forcing slow on-demand blob fetches against
#   origin. Metadata-only comparisons (commit SHAs, trailers) don't have
#   this problem since commit objects are always fetched in full.

MASTER_BRANCH="master"
INTERNAL_BRANCH="master-rf"

CURRENT_BRANCH="${1:-}"
UPSTREAM_BRANCH="${2:-}"
STATUS_FILE="${3:-}"

[[ -z "$CURRENT_BRANCH" ]]  && { echo "Usage: $0 <current_branch> <upstream_branch> [status_file]" >&2; exit 1; }
[[ -z "$UPSTREAM_BRANCH" ]] && { echo "Usage: $0 <current_branch> <upstream_branch> [status_file]" >&2; exit 1; }

write_status() {
  [[ -n "$STATUS_FILE" ]] || return 0
  {
    echo "NEEDS_FORCE=$1"
    echo "NO_CHANGES=$2"
  } > "$STATUS_FILE"
}

fail_cherry_pick() {
  git cherry-pick --abort 2>/dev/null || true
  git checkout "$INTERNAL_BRANCH" 2>/dev/null || true
  git branch -D "$UPSTREAM_BRANCH" 2>/dev/null || true
  echo "Cherry-pick failed due to conflicts. Run ./rf-scripts/upstream-pr.sh locally to resolve." >&2
  exit 1
}

# Prints, in order (oldest first), the original source SHA recorded in each
# commit's "(cherry picked from commit <sha>)" trailer for the given range.
# Metadata-only (git log --format), no blob/diff content is touched.
# Prints an empty line for any commit that has no such trailer, so the
# output line count always matches the number of commits in the range
# (keeping index-based comparison against the full commit list valid).
original_shas_for_range() {
  git log --reverse --format='%B%x00' "$1" \
    | while IFS= read -r -d $'\0' body; do
        printf '%s\n' "$body" | grep -oE '\(cherry picked from commit [0-9a-f]{40}\)' \
          | tail -1 \
          | grep -oE '[0-9a-f]{40}' || echo ""
      done
}

# ── find commits on the current branch ───────────────────────────────────────

COMMIT_SHAS=$(git log --format="%H" --reverse "origin/${INTERNAL_BRANCH}..origin/${CURRENT_BRANCH}")
COMMIT_ONELINES=$(git log --oneline --reverse "origin/${INTERNAL_BRANCH}..origin/${CURRENT_BRANCH}")

if [[ -z "$COMMIT_SHAS" ]]; then
  echo "No commits found between '$INTERNAL_BRANCH' and '$CURRENT_BRANCH'." >&2
  exit 1
fi

echo "$COMMIT_ONELINES"

git fetch origin "$MASTER_BRANCH" --quiet >&2

# ── check whether the upstream branch already exists on origin ──────────────
# (ls-remote is a cheap, ref-only round-trip; avoids a second, potentially
# slow, failing fetch attempt when the branch doesn't exist yet.)

UPSTREAM_EXISTS=false
if git ls-remote --exit-code --heads origin "$UPSTREAM_BRANCH" >/dev/null 2>&1; then
  UPSTREAM_EXISTS=true
  git fetch origin "$UPSTREAM_BRANCH" --quiet >&2
fi

USE_INCREMENTAL=false
NEW_COMMIT_SHAS=""

if $UPSTREAM_EXISTS; then
  EXISTING_RANGE="origin/${MASTER_BRANCH}..origin/${UPSTREAM_BRANCH}"

  ALL_SHAS_ARR=()
  while IFS= read -r sha; do
    ALL_SHAS_ARR+=("$sha")
  done <<< "$COMMIT_SHAS"

  EXISTING_ORIGINAL_SHAS=()
  while IFS= read -r sha; do
    EXISTING_ORIGINAL_SHAS+=("$sha")
  done < <(original_shas_for_range "$EXISTING_RANGE")

  # Check that EXISTING_ORIGINAL_SHAS is an in-order prefix of ALL_SHAS_ARR,
  # with no missing/empty trailers along the way.
  PREFIX_MATCHES=true
  if (( ${#EXISTING_ORIGINAL_SHAS[@]} > ${#ALL_SHAS_ARR[@]} )); then
    PREFIX_MATCHES=false
  else
    for i in "${!EXISTING_ORIGINAL_SHAS[@]}"; do
      if [[ -z "${EXISTING_ORIGINAL_SHAS[$i]}" || "${EXISTING_ORIGINAL_SHAS[$i]}" != "${ALL_SHAS_ARR[$i]}" ]]; then
        PREFIX_MATCHES=false
        break
      fi
    done
  fi

  if $PREFIX_MATCHES; then
    USE_INCREMENTAL=true
    NUM_EXISTING=${#EXISTING_ORIGINAL_SHAS[@]}
    NUM_FULL=${#ALL_SHAS_ARR[@]}

    if (( NUM_EXISTING == NUM_FULL )); then
      # Nothing new to cherry-pick; upstream branch is already up to date.
      echo "Upstream branch '$UPSTREAM_BRANCH' is already up to date." >&2
      git checkout -b "$UPSTREAM_BRANCH" "origin/$UPSTREAM_BRANCH" >&2
      write_status "false" "true"
      exit 0
    fi

    NEW_COMMIT_SHAS=$(printf '%s\n' "${ALL_SHAS_ARR[@]:$NUM_EXISTING}")
  fi
fi

if $USE_INCREMENTAL; then
  # ── fast path: extend the existing upstream branch ─────────────────────────
  git checkout -b "$UPSTREAM_BRANCH" "origin/$UPSTREAM_BRANCH" >&2

  if ! git cherry-pick -x $NEW_COMMIT_SHAS >&2; then
    fail_cherry_pick
  fi

  write_status "false" "false"
else
  # ── fallback: rebuild the upstream branch fresh from master ────────────────
  git checkout -b "$UPSTREAM_BRANCH" "origin/$MASTER_BRANCH" >&2

  if ! git cherry-pick -x $COMMIT_SHAS >&2; then
    fail_cherry_pick
  fi

  write_status "true" "false"
fi

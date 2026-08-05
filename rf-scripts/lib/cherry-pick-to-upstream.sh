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
#   If the upstream branch already exists on origin, and its existing commits
#   (relative to master) are an in-order prefix of the current commit range's
#   patch-ids, we can cherry-pick just the *new* trailing commits onto the
#   existing upstream branch tip. This produces a fast-forward that does not
#   require a force-push.
#
#   Otherwise (upstream branch doesn't exist yet, or history has diverged e.g.
#   because internal commits were amended/rebased) we fall back to rebuilding
#   the upstream branch fresh from master and cherry-picking the full range,
#   which requires a force-push.

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

# Prints one patch-id per line (oldest first) for all commits in the given
# range, in a single batched invocation. This avoids spawning a separate
# `git show` per commit, which is important on partial clones (--filter=
# blob:none): each per-commit `git show` would otherwise trigger its own
# unbatched, lazy on-demand blob fetch round-trip against origin, which can
# be extremely slow on a large repository.
patch_ids_for_range() {
  git log --reverse -p "$1" | git patch-id --stable | awk '{print $1}'
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
  # Commits already on the upstream branch, relative to master.
  EXISTING_RANGE="origin/${MASTER_BRANCH}..origin/${UPSTREAM_BRANCH}"
  FULL_RANGE="origin/${INTERNAL_BRANCH}..origin/${CURRENT_BRANCH}"

  # Build order-preserving patch-id lists (batched, not per-commit).
  FULL_PATCH_IDS=()
  while IFS= read -r pid; do
    FULL_PATCH_IDS+=("$pid")
  done < <(patch_ids_for_range "$FULL_RANGE")

  EXISTING_PATCH_IDS=()
  while IFS= read -r pid; do
    EXISTING_PATCH_IDS+=("$pid")
  done < <(patch_ids_for_range "$EXISTING_RANGE")

  # Check that EXISTING_PATCH_IDS is an in-order prefix of FULL_PATCH_IDS.
  PREFIX_MATCHES=true
  if (( ${#EXISTING_PATCH_IDS[@]} > ${#FULL_PATCH_IDS[@]} )); then
    PREFIX_MATCHES=false
  else
    for i in "${!EXISTING_PATCH_IDS[@]}"; do
      if [[ "${EXISTING_PATCH_IDS[$i]}" != "${FULL_PATCH_IDS[$i]}" ]]; then
        PREFIX_MATCHES=false
        break
      fi
    done
  fi

  if $PREFIX_MATCHES; then
    USE_INCREMENTAL=true
    NUM_EXISTING=${#EXISTING_PATCH_IDS[@]}
    NUM_FULL=${#FULL_PATCH_IDS[@]}

    if (( NUM_EXISTING == NUM_FULL )); then
      # Nothing new to cherry-pick; upstream branch is already up to date.
      echo "Upstream branch '$UPSTREAM_BRANCH' is already up to date." >&2
      git checkout -b "$UPSTREAM_BRANCH" "origin/$UPSTREAM_BRANCH" >&2
      write_status "false" "true"
      exit 0
    fi

    ALL_SHAS_ARR=()
    while IFS= read -r sha; do
      ALL_SHAS_ARR+=("$sha")
    done <<< "$COMMIT_SHAS"
    NEW_COMMIT_SHAS=$(printf '%s\n' "${ALL_SHAS_ARR[@]:$NUM_EXISTING}")
  fi
fi

if $USE_INCREMENTAL; then
  # ── fast path: extend the existing upstream branch ─────────────────────────
  git checkout -b "$UPSTREAM_BRANCH" "origin/$UPSTREAM_BRANCH" >&2

  if ! git cherry-pick $NEW_COMMIT_SHAS >&2; then
    fail_cherry_pick
  fi

  write_status "false" "false"
else
  # ── fallback: rebuild the upstream branch fresh from master ────────────────
  git checkout -b "$UPSTREAM_BRANCH" "origin/$MASTER_BRANCH" >&2

  if ! git cherry-pick $COMMIT_SHAS >&2; then
    fail_cherry_pick
  fi

  write_status "true" "false"
fi

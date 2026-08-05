#!/usr/bin/env bash
set -euo pipefail

# upstream-pr.sh
# Takes the current feature branch (based on master-rf) and prepares a clean
# upstream branch based on master, then pushes and opens the PR creation URL.

# TODO improvements:
#  1. Run automatically on pushes to internal PRs that already had /upstream-pr on it

MASTER_BRANCH="master"
INTERNAL_BRANCH="master-rf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── helpers ───────────────────────────────────────────────────────────────────

red()   { echo -e "\033[0;31m$*\033[0m"; }
green() { echo -e "\033[0;32m$*\033[0m"; }
bold()  { echo -e "\033[1m$*\033[0m"; }

abort() { red "Error: $*"; exit 1; }

# ── checks ────────────────────────────────────────────────────────────────────

git rev-parse --git-dir > /dev/null 2>&1 || abort "Not inside a git repository."

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

[[ "$CURRENT_BRANCH" == "$MASTER_BRANCH" ]]   && abort "You are on '$MASTER_BRANCH'. Checkout a feature branch first."
[[ "$CURRENT_BRANCH" == "$INTERNAL_BRANCH" ]] && abort "You are on '$INTERNAL_BRANCH'. Checkout a feature branch first."
[[ "$CURRENT_BRANCH" == feat/* ]]              && abort "You are already on an upstream branch ('$CURRENT_BRANCH')."

# ── derive upstream branch name ───────────────────────────────────────────────

STRIPPED="${CURRENT_BRANCH#rf/}"
UPSTREAM_BRANCH="feat/${STRIPPED}"

# ── check if upstream branch already exists ───────────────────────────────────

LOCAL_EXISTS=false

git show-ref --verify --quiet "refs/heads/$UPSTREAM_BRANCH" && LOCAL_EXISTS=true || true

if $LOCAL_EXISTS; then
  read -r -p "$(bold "Local branch '$UPSTREAM_BRANCH' already exists. Overwrite? [y/N] ")" CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || abort "Aborted."
  git branch -D "$UPSTREAM_BRANCH"
fi

# Check for an existing open upstream PR so we can link to it instead of a new one
EXISTING_PR_URL=""
if command -v gh &>/dev/null; then
  EXISTING_PR_URL=$(gh pr list \
    --repo "$(git remote get-url origin | sed 's|.*github.com[:/]\(.*\)\.git|\1|;s|.*github.com[:/]\(.*\)|\1|')" \
    --head "$UPSTREAM_BRANCH" \
    --state open \
    --json url \
    --jq '.[0].url' 2>/dev/null || true)
fi

# ── run shared logic ──────────────────────────────────────────────────────────

bold "\nCommits to be cherry-picked onto '$UPSTREAM_BRANCH':"

STATUS_FILE=$(mktemp)
if ! COMMIT_LIST=$("$SCRIPT_DIR/lib/cherry-pick-to-upstream.sh" "$CURRENT_BRANCH" "$UPSTREAM_BRANCH" "$STATUS_FILE"); then
  rm -f "$STATUS_FILE"
  abort "$(cat)"
fi

echo "$COMMIT_LIST"
echo ""

# shellcheck disable=SC1090
source "$STATUS_FILE"
rm -f "$STATUS_FILE"

if [[ "${NO_CHANGES:-false}" == "true" ]]; then
  green "Upstream branch '$UPSTREAM_BRANCH' is already up to date. Nothing to push."
  exit 0
fi

# ── push and open PR URL ──────────────────────────────────────────────────────

PUSH_ARGS=(-u origin "$UPSTREAM_BRANCH")
if [[ "${NEEDS_FORCE:-true}" == "true" ]]; then
  PUSH_ARGS=(--force-with-lease "${PUSH_ARGS[@]}")
fi

TMP_FILE=$(mktemp)
git push "${PUSH_ARGS[@]}" 2>&1 | tee "$TMP_FILE"
OUTPUT=$(cat "$TMP_FILE")
rm -f "$TMP_FILE"

echo ""
if [[ -n "$EXISTING_PR_URL" ]]; then
  if [[ "${NEEDS_FORCE:-true}" == "true" ]]; then
    green "Existing upstream PR updated (force-pushed):"
  else
    green "Existing upstream PR updated:"
  fi
  echo "  $EXISTING_PR_URL"
  open "$EXISTING_PR_URL"
else
  PR_URL=$(echo "$OUTPUT" | grep -oE "https://github.com/.+/.+/pull/new/[^[:space:]]+" || true)
  if [[ -n "$PR_URL" ]]; then
    green "Opening PR creation URL..."
    open "$PR_URL"
  else
    bold "Branch pushed. Open a PR manually at:"
    echo "  https://github.com/recordedfuture/Azure-Sentinel/compare/$UPSTREAM_BRANCH"
  fi
fi

green "\nDone. Upstream branch: $UPSTREAM_BRANCH"

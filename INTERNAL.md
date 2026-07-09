# Recorded Future Internal Notes

This file is an example of internal-only content that lives on `master-rf` and is never submitted upstream to `Azure/Azure-Sentinel`.

## Branch workflow

- `master` — clean mirror of upstream `Azure/Azure-Sentinel`. Sync manually via GitHub's "Sync fork" button.
- `master-rf` — our default working branch. Based on `master`, contains internal files and changes.

### Day-to-day work

1. Branch from `master-rf`:
   ```
   git checkout master-rf
   git checkout -b rf/my-feature
   ```
2. Make changes, commit, push, open a PR into `master-rf`.

### Submitting a PR upstream to Microsoft

1. Branch from `master` (not `master-rf`):
   ```
   git checkout master
   git checkout -b my-upstream-feature
   ```
2. Make changes, open a PR into `Azure/Azure-Sentinel`.
   Internal files (`rf-*.yml`, this file, `.agents/`, etc.) will never appear since they don't exist on `master`.

### Syncing upstream changes into master-rf

1. Go to GitHub and click "Sync fork" on `master` to pull latest from `Azure/Azure-Sentinel`.
2. Locally rebase `master-rf` onto the updated `master`:
   ```
   git fetch origin
   git checkout master-rf
   git rebase origin/master
   git push origin master-rf --force-with-lease
   ```

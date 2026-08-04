# rf-e2e-tests

End-to-end tests for Recorded Future Azure Sentinel integrations.

## Structure

```
rf-e2e-tests/
    rf_e2e_tests/       ← shared Azure/ARM client and config base
    identity/           ← RFI Identity suite (behave identity/)
    sentinel/           ← RF Sentinel suite (behave sentinel/)
```

## Setup

```bash
cd rf-e2e-tests
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate
```

## Running

```bash
# Identity suite
export AZURE_IDENTITY_TOKEN_QA=<token>
behave identity/

# Sentinel suite
export AZURE_TOKEN_QA=<token>
behave sentinel/

# Both suites
behave identity/ sentinel/

# Tagged runs
behave --tags=pba identity/
behave --tags=v3 identity/
behave --tags=alerts sentinel/
behave --tags=threatmap sentinel/
```

## First-time setup

Some API connections require OAuth consent through the Azure portal.
The suite will detect unauthorized connections and open browser tabs
automatically. Authorize each tab, then press Enter to continue.

For role assignment (DCR Monitoring Metrics Publisher), ensure your
`az login` account has Owner or RBAC Administrator on the resource group.

## Environments

Both suites run against:
- **Resource group:** `rf-erik`
- **Log Analytics Workspace:** `ErikLogAnalyticWorkspace`
- **Subscription:** `5129b3ff-c0c6-4e86-bd1c-70e5fcd579cf`

## Bump test Logic App names

Logic App names are date-scoped (`rfi-al-law-20260803-v3-nouser`).
To force completely fresh apps (new MSIs, clean role assignments):

- **Identity:** bump `_SUFFIX` in `identity/support/config.py`
- **Sentinel:** bump `_SUFFIX` in `sentinel/support/config.py`

# RFI Alert Importer LAW — Integration Tests

End-to-end tests for the `RFI-Playbook-Alert-Importer-LAW` logic app. Each test deploys a dedicated logic app instance, triggers it against a live RF QA alert, and asserts on side effects in Azure Log Analytics, Entra ID, and the RF API.

## Scenarios

| Scenario | `save_to_law` | User found in Entra | What it tests |
|---|---|---|---|
| `nouser` | ✅ | ❌ (raw PBA identity, not in Entra) | Alert Dismissed · LAW row written · no Entra actions |
| `baseuser` | ✅ | ✅ (UPN override) | Alert Resolved · LAW row written · no group/risky actions |
| `entra` | ✅ | ✅ | Alert Resolved · user added to security group · confirm-risky called |
| `nolaw` | ❌ | ✅ | Alert Resolved · **no** LAW row written |

## Prerequisites

- `az` CLI installed and logged in (`az login`)
- Python 3.11+
- `AZURE_IDENTITY_TOKEN_QA` env var — RF QA API token (see 1Password)

## First-time setup (admin login required once)

When running against a new logic app suffix for the first time, ARM needs to assign the `Monitoring Metrics Publisher` role on the Data Collection Rule so the logic apps can write to Log Analytics. Your normal dev account lacks this permission, so:

```bash
az login   # log in with your admin account (niklas.logrenadmin@...)
# run the tests once (see below) — role assignments are created during deployment
az login   # log back in as your normal dev account
```

This is a one-time step per suffix. Once the role assignments exist you only need your normal dev account.

## Run the tests

First run (sets up the virtualenv):

```bash
cd tests
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
AZURE_IDENTITY_TOKEN_QA=<token> .venv/bin/behave --no-capture
```

Subsequent runs (virtualenv already exists):

```bash
cd tests
AZURE_IDENTITY_TOKEN_QA=<token> .venv/bin/behave --no-capture
```

`before_all` deploys all 4 logic apps in parallel (~2 min on first run, skips redeploy on subsequent same-day runs) then runs scenarios sequentially.

## Connection authorization (browser step, first run per suffix)

When a new suffix is used, the Entra ID and Azure Monitor connections need OAuth consent. The test runner pauses and prints Azure Portal URLs:

```
*** 2 required connection(s) need authorization:
    Azuread-rfi-al-law-20260727-v3-nouser: Error
    Azuremonitorlogs-rfi-al-law-20260727-v3-nouser: Error
Open the Logic App designer to authorize:
    https://portal.azure.com/...
Press Enter once all connections are authorized ...
```

Open each URL, click **Authorize** on the connection, and press Enter. Connections stay authorized for the lifetime of those logic apps — no reauth needed on subsequent runs of the same suffix.

## When to bump `_SUFFIX`

Logic apps are reused across runs using date-scoped names (e.g. `rfi-al-law-20260727-v3-*`). If connections expire, you get persistent auth errors, or you want a completely clean slate, bump `_SUFFIX` in `support/config.py`:

```python
_SUFFIX = "v4"   # was "v3"
```

Then re-run — new logic apps are deployed, new connections created, reauthorize in the browser once.

## Unit tests

Tests for the in-memory ARM template patcher (no Azure calls):

```bash
cd tests
.venv/bin/python test_template_patcher.py
```

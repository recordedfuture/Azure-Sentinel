# RFI Identity — Integration Tests

End-to-end tests for the RFI identity playbooks. Each test deploys dedicated logic app instances, triggers them against the live Azure environment, and asserts side effects in Azure Log Analytics, Entra ID, and the RF API.

Two test suites are included, selectable by tag:

| Tag | Suite | Logic Apps tested |
|---|---|---|
| `@pba` | Playbook Alert Importer (LAW) | `RFI-Playbook-Alert-Importer-LAW` |
| `@v3` | Identity API v3.0 | `RFI-search-workforce-user` + `RFI-lookup-and-save-user` |

---

## Scenarios

### `@pba` — Alert Importer LAW

| Scenario | `save_to_law` | User found in Entra | What it tests |
|---|---|---|---|
| `nouser` | ✅ | ❌ (raw PBA identity, not in Entra) | Alert Dismissed · LAW row written · no Entra actions |
| `baseuser` | ✅ | ✅ (UPN override) | Alert Resolved · LAW row written · no group/risky actions |
| `entra` | ✅ | ✅ | Alert Resolved · user added to security group · confirm-risky called |
| `nolaw` | ❌ | ✅ | Alert Resolved · **no** LAW row written |

### `@v3` — Identity API v3.0

| Scenario | Group configured | What it tests |
|---|---|---|
| `v3_workforce` | ✅ | Real RF search + fake UUID email → all 3 LAW tables written · user added to security group |
| `v3_workforce_nogroup` | ❌ | Same as above but no group configured · user NOT added to group |

**How v3 test isolation works:**

1. A unique test email `test-<uuid>@integrationsopsrecordedfutu.onmicrosoft.com` is generated per suite run.
2. The real RF credential/malware search API calls execute (tests real integration).
3. After the search, results are replaced with a single fake item containing the UUID email.
4. The real LAW dedup queries still run (tests the `azuremonitorlogs` connection). The UUID was never seen before so it always passes through as new.
5. All three LAW tables (`RFI_CredentialDumps_V2_CL`, `RFI_MalwareLogs_V2_CL`, `RFI_UsersLookupResults_V2_CL`) are written and asserted.
6. The sub-playbooks receive the UUID email — RF lookup runs against it (may return empty, but the write still happens). Entra actions use the UUID email for group/risky operations.

---

## Prerequisites

- `az` CLI installed and logged in (`az login`)
- Python 3.11+
- `AZURE_IDENTITY_TOKEN_QA` env var — RF QA API token (see Keeper)

---

## First-time setup (admin login required once)

When running against a new logic app for the first time, ARM needs to assign the `Monitoring Metrics Publisher` role on the Data Collection Rules so the logic apps can write to Log Analytics via DCE/DCR. Your normal dev account lacks this permission, so:

```bash
az login   # log in with your admin account (niklas.logrenadmin@...)
# run the tests once (see below) — role assignments are created during deployment
az login   # log back in as your normal dev account
```

This is a one-time step per suffix. Once the role assignments exist you only need your normal dev account.

---

## Run the tests

First run (sets up the virtualenv):

```bash
uv venv
uv pip install -r requirements.txt
```

Run all tests:
```bash
source .venv/bin/activate
export AZURE_IDENTITY_TOKEN_QA=<token>
behave
```

Run only PBA tests:
```bash
source .venv/bin/activate
export AZURE_IDENTITY_TOKEN_QA=<token>
behave --tags=pba
```

Run only v3 Identity API tests:
```bash
source .venv/bin/activate
export AZURE_IDENTITY_TOKEN_QA=<token>
behave --tags=v3
```

`before_all` deploys all logic apps in parallel (~2 min on first run, redeploys on every run to pick up template changes).

---

## Connection authorization (browser step, first run per suffix)

When a new suffix is used, OAuth-based connections (Entra ID, Azure Monitor Logs) need consent. The test runner pauses, opens all consent URLs in the browser at once, and prompts:

```
  3 connection(s) need authorization — opening in browser...
    Azuread-rfi-al-law-20260727-v3-nouser
    Azuremonitorlogs-rfi-al-law-20260727-v3-nouser
    Azuread-rfi-id-v3-20260727-v3-workforce
  Authorize each connection tab, then press Enter to continue...
```

Authorize each tab in the portal and press Enter. Connections stay authorized for the lifetime of those logic apps — no reauth needed on subsequent runs of the same suffix.

---

## When to bump `_SUFFIX`

Logic apps are reused across runs using date-scoped names (e.g. `rfi-al-law-20260727-v3-*`, `rfi-id-v3-20260727-v3-*`). If connections expire, you get persistent auth errors, or you want a completely clean slate, bump `_SUFFIX` in `support/config.py`:

```python
_SUFFIX = "v4"   # was "v3"
```

Then re-run — new logic apps are deployed, new connections created, reauthorize in the browser once.

---

## Unit tests

Tests for the in-memory ARM template patchers (no Azure calls):

```bash
cd tests
.venv/bin/python test_template_patcher.py
```

"""
Sentinel-specific Azure client.

Imports all generic functions from rf_e2e_tests.az_client and adds
Sentinel-specific functions (Sentinel incidents API, RF connection check).
"""
from typing import Optional
import time

# support/__init__.py adds rf-e2e-tests root to sys.path
from rf_e2e_tests.az_client import *  # noqa: F401, F403
from rf_e2e_tests.az_client import _rest, _run  # explicit for use below

from . import config


def verify_rf_connection(
    conn_name: str = config.RF_CONNECTION_NAME,
    rg: str = config.RESOURCE_GROUP,
) -> bool:
    """Return True if the shared RF connector is Connected."""
    from rf_e2e_tests.az_client import get_connection_status
    return get_connection_status(conn_name, rg) == "Connected"


def list_sentinel_incidents(
    workspace: str = config.LAW_NAME,
    rg: str = config.RESOURCE_GROUP,
    filter_expr: Optional[str] = None,
) -> list:
    """
    List Sentinel incidents via ARM REST.
    filter_expr: optional OData $filter string.
    """
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.OperationalInsights/workspaces/{workspace}"
        f"/providers/Microsoft.SecurityInsights/incidents?api-version=2023-02-01"
    )
    if filter_expr:
        url += f"&$filter={filter_expr}"
    result = _rest("GET", url, check=False)
    return result.get("value", []) if result else []


def wait_for_incident(
    title_substring: str,
    after: "datetime",
    timeout: int = 600,
    poll_interval: int = 30,
) -> dict:
    """
    Poll Sentinel incidents until one with title containing *title_substring*
    appears, created after *after*. Returns the incident. Raises on timeout.
    """
    from rf_e2e_tests.az_client import AzCliError
    from datetime import timezone
    import datetime as dt

    deadline = time.time() + timeout
    while time.time() < deadline:
        incidents = list_sentinel_incidents()
        for inc in incidents:
            props = inc.get("properties", {})
            created_str = props.get("createdTimeUtc", "")
            if not created_str:
                continue
            created = dt.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created >= after and title_substring.lower() in props.get("title", "").lower():
                return inc
        remaining = int(deadline - time.time())
        print(f"\n  No incident matching '{title_substring}' yet, retrying ({remaining}s remaining)...")
        time.sleep(poll_interval)
    raise AzCliError(
        f"Timed out waiting for Sentinel incident matching '{title_substring}' after {timeout}s"
    )


def deploy_and_enable_analytic_rule(
    rule_name: str,
    display_name: str,
    kind: str,
    query: str,
    severity: str = "Medium",
    workspace: str = config.LAW_NAME,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Deploy (PUT) an NRT analytic rule and enable it.
    Idempotent — safe to call on every before_all.
    """
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.OperationalInsights/workspaces/{workspace}"
        f"/providers/Microsoft.SecurityInsights/alertRules/{rule_name}"
        f"?api-version=2023-02-01"
    )
    body = {
        "kind": kind,
        "properties": {
            "displayName": display_name,
            "description": f"E2E test rule: {display_name}",
            "severity": severity,
            "enabled": True,
            "query": query,
            "suppressionEnabled": False,
            "suppressionDuration": "PT5H",
            "eventGroupingSettings": {"aggregationKind": "AlertPerResult"},
            "incidentConfiguration": {
                "createIncident": True,
                "groupingConfiguration": {
                    "enabled": False,
                    "reopenClosedIncident": False,
                    "lookbackDuration": "PT5M",
                    "matchingMethod": "AllEntities",
                },
            },
        },
    }
    _rest("PUT", url, body)
    print(f"  Analytic rule '{display_name}' deployed and enabled")


def wait_for_role_assignments(keys: list, timeout: int = 600, poll: int = 15) -> None:
    """
    Wait until all DCR (and LAW) role assignments for *keys* are both visible
    in the ARM API AND enforced by the Azure authz system.

    Phase 1: Poll until the assignments appear in the role-assignment list.
    Phase 2: If any were created within the last 15 minutes, wait an additional
             10 minutes for enforcement — role assignments are listed before they
             are enforced, and DCR scope has ~10-15 min lag in this subscription.
    """
    from datetime import datetime, timezone, timedelta

    dcr_map = {
        "playbook_alert_importer": "recorded-future-dcr-playbook-alerts",
        "alert_importer":          "recorded-future-dcr-classic-alerts",
        "threatmap":               "recorded-future-dcr-threatmap",
        "threatmap_malware":       "recorded-future-dcr-threatmap-malware",
    }
    extra_scope_map = {
        "alert_importer": (
            f"/subscriptions/{config.SUBSCRIPTION_ID}/resourceGroups/{config.RESOURCE_GROUP}"
            f"/providers/Microsoft.OperationalInsights/workspaces/{config.LAW_NAME}"
        ),
    }
    sub = config.SUBSCRIPTION_ID
    rg  = config.RESOURCE_GROUP

    pairs = [
        (
            config.LOGIC_APP_NAMES[k],
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Insights/dataCollectionRules/{dcr_map[k]}",
            extra_scope_map.get(k),
        )
        for k in keys if k in dcr_map
    ]
    if not pairs:
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = []
        for la_name, dcr_scope, extra_scope in pairs:
            la_url = (
                f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.Logic/workflows/{la_name}?api-version=2016-06-01"
            )
            wf = _rest("GET", la_url, check=False)
            if not wf:
                pending.append(la_name); continue
            msi = wf.get("identity", {}).get("principalId")
            if not msi:
                pending.append(la_name); continue

            assigned = _run(
                "role", "assignment", "list",
                "--scope", dcr_scope, "--assignee", msi,
                "--query", "[].principalId", check=False,
            ) or []
            if msi not in assigned:
                pending.append(la_name); continue

            if extra_scope:
                extra = _run(
                    "role", "assignment", "list",
                    "--scope", extra_scope, "--assignee", msi,
                    "--query", "[].principalId", check=False,
                ) or []
                if msi not in extra:
                    pending.append(la_name); continue

        if not pending:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
            recently_created = False
            for la_name, dcr_scope, _ in pairs:
                timestamps = _run(
                    "role", "assignment", "list",
                    "--scope", dcr_scope,
                    "--query", "[].createdOn", check=False,
                ) or []
                for ts in timestamps:
                    try:
                        if datetime.fromisoformat(ts.replace("Z", "+00:00")) > cutoff:
                            recently_created = True
                            break
                    except Exception:
                        pass
                if recently_created:
                    break

            if recently_created:
                print("  Role assignments visible — waiting 10 minutes for enforcement...")
                time.sleep(600)
            print("  All role assignments active")
            return

        remaining = int(deadline - time.time())
        print(f"  Waiting for role assignments on: {pending} ({remaining}s remaining)...")
        time.sleep(poll)

    raise RuntimeError(
        f"Role assignments did not propagate within {timeout}s. "
        f"Still pending: {[la for la, _, _ in pairs]}"
    )

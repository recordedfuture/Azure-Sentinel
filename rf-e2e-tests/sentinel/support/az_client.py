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


def ensure_rf_connection_configured(
    conn_name: str = config.RF_CUSTOM_CONNECTOR_NAME,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Ensure the RecordedFuture-CustomConnector connection (used by the
    ThreatMap playbooks) has a valid api_key connection parameter set.

    This connector's Microsoft.Web/customApis definition bakes host/basePath
    (api.recordedfuture.com/gw/azure) into its swagger — the only real
    connectionParameter is api_key (securestring). Azure never returns secure
    parameter values via GET, so staleness can't be detected; instead this
    always (re)sets api_key from config.RF_TOKEN via `az rest PUT`; each such
    PUT is a no-op from the connector's perspective if the value is already
    correct. This matters because the connection can report status
    "Connected" while api_key is unset/stale, in which case the ThreatMap
    playbooks 403 at runtime — not something the deploy step fixes on its own.
    """
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{conn_name}?api-version=2016-06-01"
    )
    body = _rest("GET", url, check=False)
    assert body, f"RF connection '{conn_name}' not found in {rg}"

    props = body.get("properties", {})
    props["customParameterValues"] = {"api_key": config.RF_TOKEN}
    body["properties"] = props
    for key in ("id", "name", "type"):
        body.pop(key, None)
    _rest("PUT", url, body)
    print(f"  RF connection '{conn_name}' api_key (re)set")

    statuses = props.get("statuses", [])
    status = statuses[0].get("status") if statuses else None
    valid = getattr(config, "VALID_CONN_STATUSES", {"Connected"})
    assert status in valid, (
        f"RF connection '{conn_name}' status is '{status}' after setting "
        f"api_key (expected one of {valid})."
    )
    print(f"\n  RF connector {conn_name}: {status} (api_key set)")


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
        f"/providers/Microsoft.SecurityInsights/incidents?api-version=2023-09-01-preview"
    )
    if filter_expr:
        url += f"&$filter={filter_expr}"
    result = _rest("GET", url, check=False)
    return result.get("value", []) if result else []


def wait_for_incident(
    after: "datetime",
    timeout: int = 600,
    poll_interval: int = 30,
    title_substring: str = "Alert:",
) -> dict:
    """
    Poll Sentinel incidents until one is found that:
      - was created after *after*
      - has *title_substring* anywhere in its title (default "Alert:")

    Returns the matching incident dict. Raises AzCliError on timeout.

    NOTE: this matches on a brand-new incident's title. It is NOT reliable for
    rules whose incidentConfiguration groups alerts coarsely (e.g. by a
    low-cardinality custom detail like "Category" with a lookback window) —
    such rules will often merge a fresh alert into an *existing* incident
    without creating a new one or changing its title. For those, use
    wait_for_incident_containing_alert() instead, which correlates via the
    alert's SystemAlertId rather than incident title/creation time.
    """
    from rf_e2e_tests.az_client import AzCliError
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
            title = props.get("title", "")
            if created >= after and title_substring.lower() in title.lower():
                return inc
        remaining = int(deadline - time.time())
        print(f"\n  No incident matching '{title_substring}' yet, retrying ({remaining}s remaining)...")
        time.sleep(poll_interval)
    raise AzCliError(
        f"Timed out waiting for Sentinel incident matching '{title_substring}' after {timeout}s"
    )


def wait_for_alert(
    alert_title_substring: str,
    after: "datetime",
    timeout: int = 300,
    poll_interval: int = 15,
) -> dict:
    """
    Poll the SecurityAlert table for a row whose AlertName contains
    *alert_title_substring*, generated after *after*. Returns the row (which
    includes SystemAlertId) once found. Raises AzCliError on timeout.
    """
    from rf_e2e_tests.az_client import AzCliError, query_law

    anchor = after.strftime("%Y-%m-%dT%H:%M:%SZ")
    escaped = alert_title_substring.replace('"', '\\"')
    kql = (
        f'SecurityAlert | where TimeGenerated >= datetime("{anchor}") '
        f'| where AlertName contains "{escaped}" '
        f'| order by TimeGenerated asc | limit 1'
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = query_law(kql)
        if rows:
            return rows[0]
        remaining = int(deadline - time.time())
        print(f"\n  No SecurityAlert matching '{alert_title_substring}' yet, retrying ({remaining}s remaining)...")
        time.sleep(poll_interval)
    raise AzCliError(
        f"Timed out waiting for SecurityAlert matching '{alert_title_substring}' after {timeout}s"
    )


def wait_for_incident_containing_alert(
    system_alert_id: str,
    timeout: int = 600,
    poll_interval: int = 30,
) -> dict:
    """
    Poll the SecurityIncident table until one is found whose AlertIds array
    contains *system_alert_id*. This correctly handles rules that group
    multiple alerts into a single (possibly pre-existing) incident — e.g. by
    a coarse custom-detail key with a lookback window — where a fresh alert
    may be silently attached to an older incident rather than creating a new
    one with a matching title.

    Returns the SecurityIncident row (IncidentNumber, Title, Status, Severity,
    etc). Raises AzCliError on timeout.
    """
    from rf_e2e_tests.az_client import AzCliError, query_law

    kql = (
        f'SecurityIncident | where AlertIds has "{system_alert_id}" '
        f'| order by TimeGenerated desc | limit 1'
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = query_law(kql)
        if rows:
            return rows[0]
        remaining = int(deadline - time.time())
        print(f"\n  No incident containing alert {system_alert_id} yet, retrying ({remaining}s remaining)...")
        time.sleep(poll_interval)
    raise AzCliError(
        f"Timed out waiting for a Sentinel incident containing alert {system_alert_id} after {timeout}s"
    )


def _to_iso8601_duration(value: str) -> str:
    """
    Convert shorthand durations like "1h", "5m", "30s" (used in the Sentinel
    analytic rule YAML DSL) to ISO 8601 duration strings ("PT1H", "PT5M",
    "PT30S") required by the alertRules ARM API. Already-ISO8601 values
    (starting with "P") are returned unchanged.
    """
    if value.upper().startswith("P"):
        return value
    unit = value[-1].lower()
    amount = value[:-1]
    unit_map = {"h": "H", "m": "M", "s": "S", "d": "D"}
    if unit not in unit_map:
        return value  # unrecognised — pass through, let ARM reject if invalid
    if unit == "d":
        return f"P{amount}D"
    return f"PT{amount}{unit_map[unit]}"


def _normalize_durations(props: dict) -> None:
    """Recursively convert known duration fields in *props* to ISO 8601, in place."""
    duration_keys = {"lookbackDuration", "queryPeriod", "queryFrequency", "suppressionDuration"}
    for key, value in props.items():
        if key in duration_keys and isinstance(value, str):
            props[key] = _to_iso8601_duration(value)
        elif isinstance(value, dict):
            _normalize_durations(value)


def deploy_analytic_rule_from_yaml(
    yaml_path,
    rule_name: str,
    workspace: str = config.LAW_NAME,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Deploy (PUT) an NRT analytic rule from a YAML source file and enable it.
    The YAML format matches the Sentinel analytic rule YAML schema used in the
    Solutions/Recorded Future/Analytic Rules/ directory.

    Copies the YAML fields into the ARM `properties` object as-is — the
    Sentinel alertRules API silently ignores fields it doesn't recognise
    (e.g. YAML-only fields like `status`, `queryFrequency`, `version`), so no
    per-field allow-list is needed. Adjustments made:
      - `id` is dropped (it's the YAML template GUID, not the ARM rule name)
      - `name` is renamed to `displayName` (ARM's field name for the same thing)
      - `kind` is hoisted out of properties to the top level (ARM requirement)
      - duration fields (e.g. lookbackDuration: "1h") are converted from the
        YAML DSL's shorthand to ISO 8601 ("PT1H"), which the raw ARM API requires
    Then `enabled`, `suppressionEnabled`, and `suppressionDuration` are added,
    since the YAML doesn't carry deployment-time state.

    Idempotent — safe to call on every before_all.
    """
    import yaml

    with open(yaml_path) as f:
        rule = yaml.safe_load(f)

    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.OperationalInsights/workspaces/{workspace}"
        f"/providers/Microsoft.SecurityInsights/alertRules/{rule_name}"
        f"?api-version=2023-09-01-preview"
    )

    props = dict(rule)
    props.pop("id", None)
    props["displayName"] = props.pop("name")
    kind = props.pop("kind", "NRT")
    props["enabled"] = True
    props["suppressionEnabled"] = False
    props["suppressionDuration"] = "PT5H"
    _normalize_durations(props)

    body = {"kind": kind, "properties": props}
    _rest("PUT", url, body)
    print(f"  Analytic rule '{rule['name']}' deployed and enabled")


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
        "sandbox_storage_account": "recorded-future-dcr-sandbox-results",
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

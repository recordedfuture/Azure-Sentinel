"""
Identity-specific Azure client.

Imports all generic functions from rf_e2e_tests.az_client and adds
Identity-specific functions (Entra ID, custom connector setup).
"""
from typing import Optional

# support/__init__.py adds rf-e2e-tests root to sys.path
from rf_e2e_tests.az_client import *  # noqa: F401, F403
from rf_e2e_tests.az_client import _run, _rest  # explicit for use below

from . import config


# ── Entra ID ──────────────────────────────────────────────────────────────────

def is_group_member(
    group_id: str = config.TEST_SECURITY_GROUP_ID,
    user_oid: str = config.TEST_USER_OID,
) -> bool:
    members = _run(
        "ad", "group", "member", "list",
        "--group", group_id,
        "--query", "[].id",
        check=False,
    )
    return user_oid in (members or [])


def remove_group_member(
    group_id: str = config.TEST_SECURITY_GROUP_ID,
    user_oid: str = config.TEST_USER_OID,
) -> None:
    _run(
        "ad", "group", "member", "remove",
        "--group", group_id,
        "--member-id", user_oid,
        check=False,
    )


def get_risky_user_state(user_oid: str = config.TEST_USER_OID) -> Optional[str]:
    """
    Returns riskState string, or None if P1/P2 not available or no permission.
    A None return causes the assertion step to skip rather than fail.
    """
    url = f"https://graph.microsoft.com/beta/riskyUsers/{user_oid}"
    result = _rest("GET", url, check=False)
    if not result or "riskState" not in result:
        return None
    return result["riskState"]


def dismiss_risky_user(user_oid: str = config.TEST_USER_OID) -> None:
    url = "https://graph.microsoft.com/beta/riskyUsers/dismiss"
    _rest("POST", url, {"userIds": [user_oid]}, check=False)


def setup_rfi_test_connection(
    connection_name: str,
    rf_api_key: str,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """
    Create (or update) a dedicated RFI Custom Connector connection with the
    given RF API key, then rewire all test logic apps to use it.
    """
    sub = config.SUBSCRIPTION_ID
    rg_info = _run("group", "show", "--name", rg)
    location = rg_info["location"]

    custom_api_id = (
        f"/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/customApis/RFI-CustomConnector-0-2-0"
    )
    conn_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{connection_name}?api-version=2016-06-01"
    )
    _rest("PUT", conn_url, {
        "location": location,
        "properties": {
            "api": {"id": custom_api_id},
            "displayName": connection_name,
            "parameterValues": {"api_key": rf_api_key},
        },
    })

    for key, la_name in config.LOGIC_APP_NAMES.items():
        la_url = (
            f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Logic/workflows/{la_name}?api-version=2016-06-01"
        )
        wf = _rest("GET", la_url, check=False)
        if not wf:
            continue
        conn_ref = (
            wf.get("properties", {})
            .get("parameters", {})
            .get("$connections", {})
            .get("value", {})
            .get("rfi-customconnector-0-2-0")
        )
        if conn_ref is None:
            continue
        conn_ref["connectionId"] = (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Web/connections/{connection_name}"
        )
        conn_ref["connectionName"] = connection_name
        for k in ("id", "name", "type"):
            wf.pop(k, None)
        _rest("PUT", la_url, wf, check=False)
        print(f"  Rewired {la_name} → {connection_name}")

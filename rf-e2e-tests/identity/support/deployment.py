"""
Identity suite deployment helpers.
"""
import copy
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from support import az_client, config, rf_client
from support.template_patcher import patch_template
from support.v3_template_patcher import (
    patch_lookup_template,
    patch_search_template,
)
from rf_e2e_tests.patchers import write_temp

_TEST_RFI_CONN = f"RFI-CC-test-{date.today().strftime('%Y%m%d')}-v3"
_V3_TEST_RFI_CONN = f"RFI-CC-v3id-test-{date.today().strftime('%Y%m%d')}-v3"


# ── PBA ───────────────────────────────────────────────────────────────────────

def _deploy_pba_scenario(key: str, alert_id: str) -> str:
    params = copy.deepcopy(config.SCENARIO_PARAMS[key])
    entra_user_upn = params.pop("entra_user_upn", None)
    with open(config.TEMPLATE_PATH) as f:
        template = json.load(f)
    patched = patch_template(template, alert_id, rf_api_key=config.RF_TOKEN, entra_user_upn=entra_user_upn)
    tmp = write_temp(patched)
    try:
        az_client.deploy_logic_app(tmp, params)
    finally:
        os.unlink(tmp)
    return key


def setup_pba(context) -> None:
    """Select a test alert, deploy all PBA apps, wire the RF connection."""
    print("\n=== [PBA] Cleaning up Entra state ===")
    az_client.remove_group_member()
    az_client.dismiss_risky_user()
    print("  Entra state clean")

    print("\n=== [PBA] Selecting test alert ===")
    items = rf_client.get_new_pba_via_gateway()
    assert items, (
        "No New identity PBAs available from the RF gateway. "
        "Ensure the RF test account has New identity_novel_exposures alerts."
    )
    test_local = config.TEST_USER_UPN.split("@")[0]
    preferred = [i for i in items if i["identity"].split("@")[0] == test_local]
    chosen = preferred[0] if preferred else items[-1]
    context.test_alert_id = chosen["alert_id"]
    context.test_alert_identity = chosen["identity"]
    print(f"  Selected alert: {context.test_alert_id} ({context.test_alert_identity})")

    print("\n=== [PBA] Deploying test logic apps (parallel) ===")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_deploy_pba_scenario, key, context.test_alert_id): key
            for key in config.LOGIC_APP_NAMES
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
                print(f"  [deploy] {key} ready")
            except Exception as exc:
                print(f"  [deploy] {key} FAILED: {exc}")
                raise

    print(f"\n=== [PBA] Wiring RFI test connection ({_TEST_RFI_CONN}) ===")
    az_client.setup_rfi_test_connection(_TEST_RFI_CONN, config.RF_TOKEN)


# ── v3 ────────────────────────────────────────────────────────────────────────

def _deploy_v3_lookup() -> None:
    with open(config.V3_LOOKUP_TEMPLATE_PATH) as f:
        template = json.load(f)
    patched = patch_lookup_template(template, rf_api_key=config.RF_TOKEN)
    tmp = write_temp(patched)
    params = {
        "PlaybookName":                config.V3_LOGIC_APP_NAMES["v3_lookup"],
        "IdentityCustomConnectorName": config.RFI_CUSTOM_CONNECTOR_V3,
        "create_role_assignment":      True,
    }
    try:
        az_client.deploy_logic_app(tmp, params)
    finally:
        os.unlink(tmp)


def _deploy_v3_search_scenario(key: str, test_email: str) -> str:
    params = copy.deepcopy(config.V3_SCENARIO_PARAMS[key])
    with open(config.V3_SEARCH_TEMPLATE_PATH) as f:
        template = json.load(f)
    security_group_id = config.TEST_SECURITY_GROUP_ID if key == "v3_workforce" else None
    patched = patch_search_template(
        template,
        test_email=test_email,
        lookup_app_name=config.V3_LOGIC_APP_NAMES["v3_lookup"],
        rf_api_key=config.RF_TOKEN,
        test_domain=config.V3_ORG_DOMAIN,
        entra_user_upn=config.TEST_USER_UPN,
        security_group_id=security_group_id,
    )
    tmp = write_temp(patched)
    try:
        az_client.deploy_logic_app(tmp, params)
    finally:
        os.unlink(tmp)
    return key


def _wire_v3_rfi_connection() -> None:
    sub = config.SUBSCRIPTION_ID
    rg = config.RESOURCE_GROUP
    rg_info = az_client._run("group", "show", "--name", rg)
    location = rg_info["location"]

    managed_api_id = (
        f"/subscriptions/{sub}/providers/Microsoft.Web/locations/{location}"
        f"/managedApis/recordedfutureidenti"
    )
    for key in ("v3_workforce", "v3_workforce_nogroup"):
        la_name = config.V3_LOGIC_APP_NAMES[key]
        conn_name = f"Recordedfutureidenti-{la_name}"
        conn_url = (
            f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Web/connections/{conn_name}?api-version=2016-06-01"
        )
        az_client._rest("PUT", conn_url, {
            "location": location,
            "properties": {
                "api": {"id": managed_api_id},
                "displayName": conn_name,
                "parameterValues": {"api_key": config.RF_TOKEN},
            },
        })
        print(f"  Authorized {conn_name}")

    lookup_name = config.V3_LOGIC_APP_NAMES["v3_lookup"]
    la_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Logic/workflows/{lookup_name}?api-version=2016-06-01"
    )
    wf = az_client._rest("GET", la_url, check=False)
    if wf:
        conn_value = (
            wf.get("properties", {})
            .get("parameters", {})
            .get("$connections", {})
            .get("value", {})
        )
        conn_key = next(
            (k for k, v in conn_value.items() if config.RFI_CUSTOM_CONNECTOR_V3 in v.get("id", "")),
            None,
        )
        if conn_key:
            conn_value[conn_key]["connectionId"] = (
                f"/subscriptions/{sub}/resourceGroups/RF-Erik"
                f"/providers/Microsoft.Web/connections/RFI-CustomConnector-0-1-0"
            )
            conn_value[conn_key]["connectionName"] = "RFI-CustomConnector-0-1-0"
            for k in ("id", "name", "type"):
                wf.pop(k, None)
            az_client._rest("PUT", la_url, wf, check=False)
            print(f"  Rewired {lookup_name} → RFI-CustomConnector-0-1-0")


def setup_v3(context) -> None:
    """Generate test emails, deploy v3 apps, wire RF connections."""
    short_uuid_wf = uuid.uuid4().hex[:8]
    short_uuid_ng = uuid.uuid4().hex[:8]
    context.v3_test_emails = {
        "v3_workforce":         f"test-{short_uuid_wf}@{config.V3_TEST_EMAIL_DOMAIN}",
        "v3_workforce_nogroup": f"test-{short_uuid_ng}@{config.V3_TEST_EMAIL_DOMAIN}",
    }
    print(f"\n=== [v3] Test emails for this run:")
    for k, v in context.v3_test_emails.items():
        print(f"  {k}: {v}")

    print("\n=== [v3] Deploying lookup sub-playbook ===")
    _deploy_v3_lookup()
    print("  v3_lookup ready")

    print("\n=== [v3] Deploying search test logic apps (parallel) ===")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_deploy_v3_search_scenario, key, context.v3_test_emails[key]): key
            for key in config.V3_SCENARIO_PARAMS
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
                print(f"  [deploy] {key} ready")
            except Exception as exc:
                print(f"  [deploy] {key} FAILED: {exc}")
                raise

    print(f"\n=== [v3] Wiring v3 RFI test connection ({_V3_TEST_RFI_CONN}) ===")
    _wire_v3_rfi_connection()


# ── Teardown ──────────────────────────────────────────────────────────────────

def teardown_entra(context) -> None:
    """Remove test user from security group and dismiss risky state."""
    print("\n  [teardown] Removing test user from security group (if present)...")
    az_client.remove_group_member()
    deadline = time.time() + 30
    while time.time() < deadline:
        if not az_client.is_group_member():
            break
        time.sleep(3)
    if context.scenario_key == "entra":
        print("  [teardown] Dismissing risky user state (if set)...")
        az_client.dismiss_risky_user()

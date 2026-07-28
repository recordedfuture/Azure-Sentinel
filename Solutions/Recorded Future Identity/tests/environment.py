"""
Behave environment hooks.

before_all:
  - Cleans up any leftover Entra state from prior runs.
  - Picks the first available New identity PBA from the RF gateway as the
    test alert (dynamic — no hardcoded ID).
  - Deploys all 4 test logic apps in parallel (ARM deployments, idempotent).
    Each deployment patches the template with the live alert ID.
  - Creates/updates a dedicated RFI Custom Connector connection with the QA
    RF API key and rewires all test logic apps to use it.
  - Checks all required API connections. If any are not yet authorized,
    opens all consent URLs in the browser at once and prompts once to continue.
  - Records the LAW baseline timestamp used for new-row assertions.

before_scenario:
  - Enables the logic app for this scenario (may have been disabled).

after_scenario:
  - For the 'entra' scenario: removes the test user from the security group
    and dismisses risky state, so the next run starts clean.

after_all:
  - Disables all 4 test logic apps (preserves run history, stops recurrence).
"""
import copy
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from support import az_client, config, rf_client
from support.template_patcher import patch_template, write_temp

# Shared test connection name (date + suffix scoped to match logic app names)
_TEST_RFI_CONN = f"RFI-CC-test-{date.today().strftime('%Y%m%d')}-v3"

# Required connections per scenario key: {prefix: required}
_REQUIRED_CONN_PREFIXES = {
    "nouser":   {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "baseuser": {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "entra":    {"Azuread": True,  "Azureadip": True,  "Azuremonitorlogs": True},
    "nolaw":    {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": False},
}


def _deploy_scenario(key: str, alert_id: str) -> str:
    """Deploy (or update) one test logic app patched with alert_id."""
    params = copy.deepcopy(config.SCENARIO_PARAMS[key])
    entra_user_upn = params.pop("entra_user_upn", None)

    with open(config.TEMPLATE_PATH) as f:
        template = json.load(f)

    patched = patch_template(
        template,
        alert_id,
        rf_api_key=config.RF_TOKEN,
        entra_user_upn=entra_user_upn,
    )
    tmp_path = write_temp(patched)
    try:
        az_client.deploy_logic_app(tmp_path, params)
    finally:
        os.unlink(tmp_path)
    return key


def _check_connections() -> dict[str, list[tuple[str, str]]]:
    """
    Return {key: [(conn_name, status), ...]} for required connections
    that are not yet Connected.
    """
    unconnected = {}
    for key, la_name in config.LOGIC_APP_NAMES.items():
        bad = []
        for prefix, required in _REQUIRED_CONN_PREFIXES[key].items():
            conn = f"{prefix}-{la_name}"
            status = az_client.get_connection_status(conn)
            if required and status != "Connected":
                bad.append((conn, status or "not found"))
        if bad:
            unconnected[key] = bad
    return unconnected


def _consent_url(conn_name: str) -> str | None:
    sub = config.SUBSCRIPTION_ID
    rg = config.RESOURCE_GROUP
    result = az_client._rest(
        "POST",
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{conn_name}"
        f"/listConsentLinks?api-version=2016-06-01",
        {"parameters": [{"parameterName": "token", "redirectUrl": "https://portal.azure.com/"}]},
        check=False,
    )
    if not result:
        return None
    links = result.get("value", [])
    return links[0].get("link") if links else None


def _authorize_connections_if_needed():
    """
    Check all required connections. If any are not yet Connected, open all
    consent URLs in the browser at once and prompt the user once to continue.
    """
    unconnected = _check_connections()
    if not unconnected:
        print("  All required connections are Connected.")
        return

    # Collect all consent URLs across all scenarios
    all_urls = []
    for key, bad_conns in unconnected.items():
        for conn_name, status in bad_conns:
            url = _consent_url(conn_name)
            if url:
                all_urls.append((conn_name, url))

    if not all_urls:
        return

    print(f"\n  {len(all_urls)} connection(s) need authorization — opening in browser...")
    for conn_name, url in all_urls:
        print(f"    {conn_name}")
        subprocess.run(["open", url], check=False)

    print("\n  Authorize each connection tab, then press Enter to continue...")
    try:
        with open("/dev/tty") as tty:
            tty.readline()
    except OSError:
        raise RuntimeError(
            "Cannot read from terminal. Run behave in an interactive terminal session."
        )

    # Re-verify
    still_bad = _check_connections()
    assert not still_bad, (
        f"Some connections still not authorized after confirmation:\n"
        + "\n".join(
            f"  {key}: {[c for c,_ in conns]}"
            for key, conns in still_bad.items()
        )
    )
    print("  All connections now Connected.")


def before_all(context):
    # ── 0. Clean up any leftover Entra state from prior runs ─────────────────
    print("\n=== Cleaning up Entra state ===")
    az_client.remove_group_member()
    az_client.dismiss_risky_user()
    print("  Entra state clean")

    # ── 1. Pick test alert dynamically ───────────────────────────────────────
    print("\n=== Selecting test alert ===")
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

    # ── 2. Deploy all 4 logic apps in parallel ────────────────────────────────
    print("\n=== Deploying test logic apps (parallel) ===")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_deploy_scenario, key, context.test_alert_id): key
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

    # ── 3. Wire dedicated RFI test connection ─────────────────────────────────
    print(f"\n=== Wiring RFI test connection ({_TEST_RFI_CONN}) ===")
    az_client.setup_rfi_test_connection(_TEST_RFI_CONN, config.RF_TOKEN)

    # ── 4. Authorize API connections if needed ────────────────────────────────
    print("\n=== Checking API connections ===")
    _authorize_connections_if_needed()

    # ── 5. Record suite start time for LAW assertions ─────────────────────────
    context.suite_start_time = datetime.now(timezone.utc)
    print(f"\n  Suite start time (LAW baseline): {context.suite_start_time.isoformat()}")


def before_scenario(context, scenario):
    context.trigger_time = None
    context.run = None
    context.scenario_key = scenario.name.split()[0]
    context.scenario_start_time = datetime.now(timezone.utc)

    name = config.LOGIC_APP_NAMES.get(context.scenario_key)
    if name and az_client.logic_app_exists(name):
        az_client.enable_logic_app(name)


def after_scenario(context, scenario):
    if context.scenario_key == "entra":
        import time
        print("\n  [teardown] Removing test user from security group (if present)...")
        az_client.remove_group_member()
        deadline = time.time() + 30
        while time.time() < deadline:
            if not az_client.is_group_member():
                break
            time.sleep(3)
        print("  [teardown] Dismissing risky user state (if set)...")
        az_client.dismiss_risky_user()


def after_all(context):
    print("\n=== Disabling test logic apps ===")
    for key, name in config.LOGIC_APP_NAMES.items():
        try:
            az_client.disable_logic_app(name)
            print(f"  [disable] {name} disabled")
        except Exception as exc:
            print(f"  [disable] {name} skipped: {exc}")


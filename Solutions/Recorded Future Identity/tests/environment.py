"""
Behave environment hooks.

before_all:
  PBA (@pba) setup:
  - Cleans up any leftover Entra state from prior runs.
  - Picks the first available New identity PBA from the RF gateway as the
    test alert (dynamic — no hardcoded ID).
  - Deploys all 4 PBA test logic apps in parallel (ARM deployments, idempotent).
    Each deployment patches the template with the live alert ID.
  - Creates/updates a dedicated RFI Custom Connector connection with the QA
    RF API key and rewires all PBA test logic apps to use it.

  v3 (@v3) setup:
  - Generates a unique test email (test-<uuid>@<domain>) for this suite run.
  - Deploys the lookup sub-playbook first (synchronous — search apps depend on it).
  - Deploys both v3 search test logic apps in parallel.
  - Creates/updates a dedicated v3 RFI Custom Connector connection with the QA
    RF API key and rewires both v3 search apps to use it.

  Shared:
  - Checks all required API connections. If any are not yet authorized,
    opens all consent URLs in the browser at once and prompts once to continue.
  - Records the LAW baseline timestamp used for new-row assertions.

before_scenario:
  - Enables the logic app for this scenario (may have been disabled).

after_scenario:
  - For the PBA 'entra' scenario: removes the test user from the security group
    and dismisses risky state, so the next run starts clean.
  - For the v3 'v3_workforce' scenario: removes the test user from the security
    group so the next run starts clean.

after_all:
  - Disables all test logic apps (preserves run history, stops recurrence).
"""
import copy
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from support import az_client, config, rf_client
from support.template_patcher import patch_template, write_temp
from support.v3_template_patcher import (
    patch_lookup_template,
    patch_search_template,
    write_temp as v3_write_temp,
)

# ── PBA shared test connection name ───────────────────────────────────────────
_TEST_RFI_CONN = f"RFI-CC-test-{date.today().strftime('%Y%m%d')}-v3"

# ── v3 shared test connection name ────────────────────────────────────────────
_V3_TEST_RFI_CONN = f"RFI-CC-v3id-test-{date.today().strftime('%Y%m%d')}-v3"

# ── PBA required connections per scenario ────────────────────────────────────
# (kept in environment.py only for the _authorize_connections_if_needed calls;
# the canonical definition lives in config.PBA_REQUIRED_CONN_PREFIXES)
_PBA_REQUIRED_CONN_PREFIXES = config.PBA_REQUIRED_CONN_PREFIXES


def _tag_active(context, tag: str) -> bool:
    """Return True if the suite is running with the given tag (or no tag filter)."""
    tags = context.config.tags
    if not tags:
        return True
    # behave tag expressions: check if tag appears anywhere in the expression
    return tag in str(tags)


# ── PBA deployment ────────────────────────────────────────────────────────────

def _deploy_pba_scenario(key: str, alert_id: str) -> str:
    """Deploy (or update) one PBA test logic app patched with alert_id."""
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


# ── v3 deployment ─────────────────────────────────────────────────────────────

def _deploy_v3_lookup() -> str:
    """Deploy (or update) the v3 lookup sub-playbook."""
    with open(config.V3_LOOKUP_TEMPLATE_PATH) as f:
        template = json.load(f)

    patched = patch_lookup_template(template, rf_api_key=config.RF_TOKEN)
    tmp_path = v3_write_temp(patched)
    params = {
        "PlaybookName":              config.V3_LOGIC_APP_NAMES["v3_lookup"],
        "IdentityCustomConnectorName": config.RFI_CUSTOM_CONNECTOR_V3,
        "create_role_assignment":    True,
    }
    try:
        az_client.deploy_logic_app(tmp_path, params)
    finally:
        os.unlink(tmp_path)
    return "v3_lookup"


def _deploy_v3_search_scenario(key: str, test_email: str) -> str:
    """Deploy (or update) one v3 search test logic app."""
    params = copy.deepcopy(config.V3_SCENARIO_PARAMS[key])

    with open(config.V3_SEARCH_TEMPLATE_PATH) as f:
        template = json.load(f)

    # Only the workforce scenario has a security group configured
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
    tmp_path = v3_write_temp(patched)
    try:
        az_client.deploy_logic_app(tmp_path, params)
    finally:
        os.unlink(tmp_path)
    return key


def _setup_v3_rfi_connection() -> None:
    """
    Authorize the RF Identity connections for all v3 logic apps:

    - Search apps use the managed 'recordedfutureidenti' Power Platform connector.
      These are created by the ARM template but need api_key injected.
    - Lookup sub-playbook uses the custom API connector — rewire it to use the
      already-authorized RFI-CustomConnector-0-1-0 connection (authorized via portal).
    """
    sub = config.SUBSCRIPTION_ID
    rg = config.RESOURCE_GROUP
    rg_info = az_client._run("group", "show", "--name", rg)
    location = rg_info["location"]

    # ── Inject api_key into recordedfutureidenti connections on search apps ───
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

    # ── Rewire lookup sub-playbook to use the already-authorized connection ───
    # RFI-CustomConnector-0-1-0 connection was authorized via portal with the
    # RF API key. Reuse it instead of creating a new connection.
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
            (k for k, v in conn_value.items()
             if config.RFI_CUSTOM_CONNECTOR_V3 in v.get("id", "")),
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


# ── Connection checks ─────────────────────────────────────────────────────────

def _check_connections(
    app_names: dict,
    required_prefixes: dict,
) -> dict:
    """
    Return {key: [(conn_name, status), ...]} for required connections
    that are not yet Connected.
    """
    unconnected = {}
    for key, la_name in app_names.items():
        bad = []
        for prefix, required in required_prefixes.get(key, {}).items():
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


def _authorize_connections_if_needed(app_names: dict, required_prefixes: dict) -> None:
    """
    Check all required connections. If any are not yet Connected, open all
    consent URLs in the browser at once and prompt the user once to continue.
    """
    unconnected = _check_connections(app_names, required_prefixes)
    if not unconnected:
        print("  All required connections are Connected.")
        return

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

    still_bad = _check_connections(app_names, required_prefixes)
    assert not still_bad, (
        f"Some connections still not authorized after confirmation:\n"
        + "\n".join(
            f"  {key}: {[c for c, _ in conns]}"
            for key, conns in still_bad.items()
        )
    )
    print("  All connections now Connected.")


# ── Behave hooks ──────────────────────────────────────────────────────────────

def before_all(context):
    run_pba = _tag_active(context, "pba")
    run_v3 = _tag_active(context, "v3")

    # ── PBA setup ─────────────────────────────────────────────────────────────
    if run_pba:
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

        print("\n=== [PBA] Checking API connections ===")
        _authorize_connections_if_needed(config.LOGIC_APP_NAMES, _PBA_REQUIRED_CONN_PREFIXES)

    # ── v3 setup ──────────────────────────────────────────────────────────────
    if run_v3:
        # Generate a fresh UUID email PER SCENARIO for this suite run.
        # Using the same email across both scenarios would cause the second
        # scenario's dedup query to find rows written by the first scenario,
        # treating the email as already seen and skipping all processing.
        short_uuid_wf = uuid.uuid4().hex[:8]
        short_uuid_ng = uuid.uuid4().hex[:8]
        context.v3_test_emails = {
            "v3_workforce":         f"test-{short_uuid_wf}@{config.V3_TEST_EMAIL_DOMAIN}",
            "v3_workforce_nogroup": f"test-{short_uuid_ng}@{config.V3_TEST_EMAIL_DOMAIN}",
        }
        print(f"\n=== [v3] Test emails for this run:")
        for k, v in context.v3_test_emails.items():
            print(f"  {k}: {v}")

        # Deploy lookup sub-playbook first (synchronous) — search apps depend on it
        print("\n=== [v3] Deploying lookup sub-playbook ===")
        _deploy_v3_lookup()
        print("  v3_lookup ready")

        # Deploy search apps in parallel
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
        _setup_v3_rfi_connection()

        print("\n=== [v3] Checking API connections ===")
        _authorize_connections_if_needed(config.V3_LOGIC_APP_NAMES, config.V3_REQUIRED_CONN_PREFIXES)

    # ── Shared ────────────────────────────────────────────────────────────────
    context.suite_start_time = datetime.now(timezone.utc)
    context.completed_runs = []  # populated by after_scenario
    print(f"\n  Suite start time (LAW baseline): {context.suite_start_time.isoformat()}")


def before_scenario(context, scenario):
    context.trigger_time = None
    context.run = None
    context.scenario_key = scenario.name.split()[0]
    context.scenario_start_time = datetime.now(timezone.utc)

    # Enable the logic app for this scenario
    name = config.ALL_LOGIC_APP_NAMES.get(context.scenario_key)
    if name and az_client.logic_app_exists(name):
        az_client.enable_logic_app(name)


def after_scenario(context, scenario):
    import time

    # Accumulate run info for the end-of-suite browser prompt
    if context.run:
        app_name = config.ALL_LOGIC_APP_NAMES.get(context.scenario_key, "")
        if app_name:
            context.completed_runs.append({
                "scenario": context.scenario_key,
                "app_name": app_name,
                "status": context.run["properties"]["status"],
            })

    if context.scenario_key == "entra":
        print("\n  [teardown] Removing test user from security group (if present)...")
        az_client.remove_group_member()
        deadline = time.time() + 30
        while time.time() < deadline:
            if not az_client.is_group_member():
                break
            time.sleep(3)
        print("  [teardown] Dismissing risky user state (if set)...")
        az_client.dismiss_risky_user()

    elif context.scenario_key == "v3_workforce":
        print("\n  [teardown] Removing test user from security group (if present)...")
        az_client.remove_group_member()
        deadline = time.time() + 30
        while time.time() < deadline:
            if not az_client.is_group_member():
                break
            time.sleep(3)


def after_all(context):
    print("\n=== Disabling test logic apps ===")
    for key, name in config.ALL_LOGIC_APP_NAMES.items():
        try:
            az_client.disable_logic_app(name)
            print(f"  [disable] {name} disabled")
        except Exception as exc:
            print(f"  [disable] {name} skipped: {exc}")

    # ── Offer to open runs in browser ─────────────────────────────────────────
    runs = getattr(context, "completed_runs", [])
    if runs and sys.stdin.isatty():
        print(f"\nOpen {len(runs)} logic app run(s) in browser? [y/N] ", end="", flush=True)
        try:
            with open("/dev/tty") as tty:
                answer = tty.readline().strip().lower()
        except OSError:
            answer = ""

        if answer == "y":
            sub = config.SUBSCRIPTION_ID
            rg = config.RESOURCE_GROUP
            tenant = config.PORTAL_TENANT
            for r in runs:
                url = (
                    f"https://portal.azure.com/#@{tenant}"
                    f"/resource/subscriptions/{sub}/resourceGroups/{rg}"
                    f"/providers/Microsoft.Logic/workflows/{r['app_name']}/logicApp"
                )
                print(f"  Opening {r['scenario']} ({r['status']}): {r['app_name']}")
                subprocess.run(["open", url], check=False)

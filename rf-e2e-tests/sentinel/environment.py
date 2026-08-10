"""
Behave environment hooks for the RF Sentinel E2E suite.
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from rf_e2e_tests import connections, shared_hooks
from support import az_client, config, rf_client
from support import deployment, sandbox_client


def _keys_to_deploy(context) -> list:
    keys = []
    if shared_hooks.tag_active(context, "alerts"):
        keys += ["playbook_alert_importer", "alert_importer"]
    if shared_hooks.tag_active(context, "threatmap"):
        keys += ["threatmap", "threatmap_malware"]
    if shared_hooks.tag_active(context, "sandbox"):
        keys += ["sandbox_storage_account"]
    return keys


def before_all(context):
    if shared_hooks.tag_active(context, "alerts"):
        print("\n=== [alerts] Selecting test alerts ===")
        pba = rf_client.get_new_playbook_alert()
        assert pba, "No Playbook Alerts available — ensure $AZURE_TOKEN_QA has access."
        context.test_playbook_alert_id = pba.get("playbook_alert_id") or pba.get("id")
        print(f"  Playbook alert: {context.test_playbook_alert_id}")

        # Deploy analytic rules BEFORE Logic Apps so NRT rules are active
        # when data lands — rules only pick up rows written after they are enabled.
        deployment.deploy_analytic_rules()

    sandbox_active = shared_hooks.tag_active(context, "sandbox")
    if sandbox_active:
        print("\n=== [sandbox] Ensuring storage fixture ===")
        sandbox_storage_key = sandbox_client.ensure_sandbox_storage_fixture()
        print("\n=== [sandbox] Fixing Sandbox connector configuration ===")
        sandbox_client.ensure_sandbox_connector_configured()

    keys = _keys_to_deploy(context)
    if keys:
        deployment.deploy_all(keys, context)

        active_apps = {k: v for k, v in config.LOGIC_APP_NAMES.items() if k in keys}
        print("\n=== Checking API connections ===")
        connections.authorize_if_needed(
            active_apps,
            config.REQUIRED_CONN_PREFIXES,
            config.SUBSCRIPTION_ID,
            config.RESOURCE_GROUP,
            config.VALID_CONN_STATUSES,
        )

        if sandbox_active and "sandbox_storage_account" in keys:
            print("\n=== [sandbox] Wiring Azureblob connection ===")
            sandbox_client.ensure_blob_connection_configured(
                playbook_name=config.LOGIC_APP_NAMES["sandbox_storage_account"],
                account_key=sandbox_storage_key,
            )

        print("\n=== Waiting for role assignment propagation ===")
        az_client.wait_for_role_assignments(keys)
        print("  Roles active")

    context.completed_workbook_deploys = []
    if shared_hooks.tag_active(context, "threatmap"):
        print("\n=== Fixing RF custom connector configuration ===")
        az_client.ensure_rf_connection_configured()

        context.completed_workbook_deploys = deployment.deploy_workbooks()

    context.suite_start_time = datetime.now(timezone.utc)
    context.completed_runs = []
    print(f"\n  Suite start time: {context.suite_start_time.isoformat()}")


def before_scenario(context, scenario):
    shared_hooks.before_scenario(context, scenario, config, az_client)


def after_scenario(context, scenario):
    shared_hooks.accumulate_run(context, config)


def after_all(context):
    shared_hooks.after_all(context, config)

    workbooks = getattr(context, "completed_workbook_deploys", [])
    labeled_urls = [
        (
            wb["display_name"],
            f"https://portal.azure.com/#@{config.PORTAL_TENANT}"
            f"/resource{wb['resource_id']}/workbook",
        )
        for wb in workbooks
    ]
    shared_hooks.prompt_open_in_browser(labeled_urls, noun="workbook")

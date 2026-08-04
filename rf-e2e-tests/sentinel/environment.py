"""
Behave environment hooks for the RF Sentinel E2E suite.
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from rf_e2e_tests import connections, shared_hooks
from support import az_client, config, rf_client
from support import deployment


def _keys_to_deploy(context) -> list:
    keys = []
    if shared_hooks.tag_active(context, "alerts"):
        keys += ["playbook_alert_importer", "alert_importer"]
    if shared_hooks.tag_active(context, "threatmap"):
        keys += ["threatmap", "threatmap_malware"]
    return keys


def before_all(context):
    if shared_hooks.tag_active(context, "alerts"):
        print("\n=== [alerts] Selecting test alerts ===")
        pba = rf_client.get_new_playbook_alert()
        assert pba, "No Playbook Alerts available — ensure $AZURE_TOKEN_QA has access."
        context.test_playbook_alert_id = pba.get("playbook_alert_id") or pba.get("id")
        print(f"  Playbook alert: {context.test_playbook_alert_id}")

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

        print("\n=== Waiting for role assignment propagation ===")
        az_client.wait_for_role_assignments(keys)
        print("  Roles active")

    context.suite_start_time = datetime.now(timezone.utc)
    context.completed_runs = []
    print(f"\n  Suite start time: {context.suite_start_time.isoformat()}")


def before_scenario(context, scenario):
    shared_hooks.before_scenario(context, scenario, config, az_client)


def after_scenario(context, scenario):
    shared_hooks.accumulate_run(context, config)


def after_all(context):
    shared_hooks.after_all(context, config)

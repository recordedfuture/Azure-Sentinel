"""
Logic App trigger and wait steps.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from behave import given, when

from support import az_client, config, rf_client


@given('the test RF alert is reset to "New"')
def step_reset_alert(context):
    alert_id = context.test_alert_id
    rf_client.reset_alert_to_new(alert_id)
    print(f"\n  Alert {alert_id} reset to New, waiting for gateway propagation...")
    # Poll until the alert appears in the gateway (max 30s)
    deadline = time.time() + 30
    while time.time() < deadline:
        items = rf_client.get_new_pba_via_gateway()
        if any(i["alert_id"] == alert_id for i in items):
            break
        time.sleep(3)
    else:
        raise AssertionError(
            f"Alert {alert_id} did not appear as New in gateway within 30s after reset"
        )
    # Extra buffer to let the BFI stabilise
    time.sleep(2)
    print(f"\n  Alert {alert_id} confirmed New in gateway")


@given('the test user is removed from security group "{group_id}" if present')
def step_remove_from_group(context, group_id):
    was_member = az_client.is_group_member(group_id)
    if not was_member:
        print(f"\n  Test user not in group {group_id} — no cleanup needed")
        return

    az_client.remove_group_member(group_id)
    time.sleep(3)  # propagation delay
    still_member = az_client.is_group_member(group_id)
    if still_member:
        context.scenario.skip(
            f"Test user is already a member of security group {group_id} "
            f"and could not be removed (insufficient CLI permissions). "
            f"Remove manually or grant Group.ReadWrite.All to run the entra scenario."
        )
        return
    print(f"\n  Test user removed from group {group_id}")


@given('the test user risky state is dismissed in Entra ID if set')
def step_dismiss_risky(context):
    az_client.dismiss_risky_user()
    print("\n  Risky user state dismissed (or not set)")


@when('I trigger logic app "{key}" and wait for completion')
def step_trigger_and_wait(context, key):
    name = config.LOGIC_APP_NAMES[key]
    print(f"\n  Triggering {name} ...")
    context.trigger_time = az_client.trigger_logic_app(name)
    print(f"  Triggered at {context.trigger_time.isoformat()}, waiting up to {config.RUN_TIMEOUT_SECONDS}s ...")
    context.run = az_client.wait_for_run(name, context.trigger_time)
    run_name = context.run["name"]
    status = context.run["properties"]["status"]
    print(f"  Run {run_name} finished with status: {status}")
    # Fetch action-level statuses for use in assertion steps
    context.action_statuses = az_client.get_run_action_statuses(name, run_name)
    print(f"  Actions: {context.action_statuses}")

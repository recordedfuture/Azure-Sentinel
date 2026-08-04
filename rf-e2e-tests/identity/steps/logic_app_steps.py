"""
Identity-specific Logic App steps.

The shared step_trigger_and_wait is loaded via steps/__init__.py.
"""
import time

from behave import given, when

from support import az_client, config, rf_client


@given('the test RF alert is reset to "New"')
def step_reset_alert(context):
    alert_id = context.test_alert_id
    rf_client.reset_alert_to_new(alert_id)
    print(f"\n  Alert {alert_id} reset to New, waiting for gateway propagation...")
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
    time.sleep(2)
    print(f"\n  Alert {alert_id} confirmed New in gateway")


@given('the test user is removed from security group "{group_id}" if present')
def step_remove_from_group(context, group_id):
    was_member = az_client.is_group_member(group_id)
    if not was_member:
        print(f"\n  Test user not in group {group_id} — no cleanup needed")
        return

    az_client.remove_group_member(group_id)
    time.sleep(3)
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

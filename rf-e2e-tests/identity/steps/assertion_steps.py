"""
Identity-specific assertion steps.

The shared steps (run_status, law_has_new_row) are loaded via steps/__init__.py.
"""
import time

from behave import then

from support import az_client, config, rf_client


@then('table "{table}" has no new rows within {minutes:d} minute')
@then('table "{table}" has no new rows within {minutes:d} minutes')
def step_law_has_no_new_row(context, table, minutes):
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = f'{table} | where TimeGenerated >= datetime("{anchor}") | limit 1'
    wait_seconds = minutes * 60
    print(f"\n  Waiting {wait_seconds}s to confirm no rows appear in {table}...")
    time.sleep(wait_seconds)
    rows = az_client.query_law(kql)
    assert not rows, (
        f"Expected NO new rows in '{table}' after {anchor}, "
        f"but found {len(rows)} row(s)"
    )
    print(f"\n  Confirmed: no new rows in {table} (negative assertion passed)")


@then('the RF test alert status is "{expected}"')
def step_rf_alert_status(context, expected):
    actual = rf_client.get_alert_status(context.test_alert_id)
    assert actual.lower() == expected.lower(), (
        f"Expected RF alert status '{expected}', got '{actual}'"
    )


@then('the test user is a member of security group "{group_id}"')
def step_user_in_group(context, group_id):
    deadline = time.time() + 30
    while time.time() < deadline:
        if az_client.is_group_member(group_id):
            print(f"\n  Test user confirmed in group {group_id}")
            return
        time.sleep(5)
    raise AssertionError(
        f"Test user {config.TEST_USER_UPN} is NOT a member of group {group_id} "
        f"after waiting 30s"
    )


@then('the test user is not a member of security group "{group_id}"')
def step_user_not_in_group(context, group_id):
    deadline = time.time() + 30
    while time.time() < deadline:
        if not az_client.is_group_member(group_id):
            print(f"\n  Confirmed: test user NOT in group {group_id}")
            return
        time.sleep(5)
    raise AssertionError(
        f"Test user {config.TEST_USER_UPN} IS a member of group {group_id} "
        f"(expected NOT to be) after waiting 30s"
    )


@then('if Entra ID P1/P2 is available the test user is marked as confirmed compromised')
def step_risky_user_if_available(context):
    state = az_client.get_risky_user_state()
    if state is None:
        context.scenario.skip(
            "Entra ID P1/P2 licence not available or CLI lacks "
            "IdentityRiskyUser.Read.All — risky user assertion skipped"
        )
        return
    assert state == "confirmedCompromised", (
        f"Expected riskState 'confirmedCompromised', got '{state}'"
    )
    print(f"\n  Test user riskState: {state}")


@then('the test user is not marked as confirmed compromised in Entra ID')
def step_user_not_risky(context):
    state = az_client.get_risky_user_state()
    if state is None:
        print("\n  Risky user check skipped (no P1/P2 or permission)")
        return
    assert state != "confirmedCompromised", (
        f"Test user riskState is '{state}' but expected NOT confirmedCompromised"
    )
    print(f"\n  Confirmed: test user riskState is '{state}' (not confirmedCompromised)")

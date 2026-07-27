"""
Assertion steps for run status, LAW rows, RF alert status, and Entra ID state.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from behave import then

from support import az_client, config, rf_client


@then('the logic app run status is "{expected}"')
def step_run_status(context, expected):
    actual = context.run["properties"]["status"]
    assert actual == expected, (
        f"Expected run status '{expected}', got '{actual}'. "
        f"Run: {context.run['name']}"
    )


@then('within {minutes:d} minutes table "{table}" has at least 1 new row')
def step_law_has_new_row(context, minutes, table):
    # Anchor to just before the trigger so we don't pick up pre-existing rows
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = f'{table} | where TimeGenerated >= datetime("{anchor}") | limit 1'
    timeout = minutes * 60
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = az_client.query_law(kql)
        if rows:
            print(f"\n  Found {len(rows)} new row(s) in {table} after {anchor}")
            return
        remaining = int(deadline - time.time())
        print(f"\n  No rows yet in {table}, retrying ({remaining}s remaining)...")
        time.sleep(config.LAW_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Table '{table}' has no new rows after {minutes} minutes "
        f"(anchored to {anchor})"
    )


@then('table "{table}" has no new rows within {minutes:d} minutes')
def step_law_has_no_new_row(context, table, minutes):
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = f'{table} | where TimeGenerated >= datetime("{anchor}") | limit 1'
    # Use config wait (not the Gherkin minutes) so it can be tuned without changing the feature file
    wait_seconds = config.LAW_NEGATIVE_WAIT_SECONDS
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
    # Poll for up to 30s — Entra group membership can take a moment to propagate
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
    # Poll for up to 30s — removal from a prior scenario may still be propagating
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
def step_risky_user_if_available(context, ):
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
        # No P1/P2 or no permission — can't assert either way, treat as pass
        print("\n  Risky user check skipped (no P1/P2 or permission)")
        return
    assert state != "confirmedCompromised", (
        f"Test user riskState is '{state}' but expected NOT confirmedCompromised"
    )
    print(f"\n  Confirmed: test user riskState is '{state}' (not confirmedCompromised)")

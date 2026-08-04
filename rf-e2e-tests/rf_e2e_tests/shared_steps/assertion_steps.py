"""
Shared assertion step definitions.
"""
import time

from behave import then

from support import az_client, config


@then('the logic app run status is "{expected}"')
def step_run_status(context, expected):
    actual = context.run["properties"]["status"]
    assert actual == expected, (
        f"Expected run status '{expected}', got '{actual}'. "
        f"Run: {context.run['name']}"
    )


@then('within {minutes:d} minutes table "{table}" has at least 1 new row')
def step_law_has_new_row(context, minutes, table):
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
        f"Table '{table}' has no new rows after {minutes} minutes (anchored to {anchor})"
    )

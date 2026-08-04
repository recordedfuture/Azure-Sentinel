"""
Sentinel-specific assertion steps.

The shared steps (run_status, law_has_new_row) are loaded via steps/__init__.py.
"""
import time

from behave import then

from support import az_client, config


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals the pinned playbook alert id')
def step_law_has_pinned_playbook_alert_row(context, minutes, table, column):
    _wait_for_specific_row(context, table, column, context.test_playbook_alert_id, minutes)


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals the pinned portal alert id')
def step_law_has_pinned_portal_alert_row(context, minutes, table, column):
    _wait_for_specific_row(context, table, column, context.test_portal_alert_id, minutes)


def _wait_for_specific_row(context, table, column, value, minutes):
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = (
        f'{table} | where TimeGenerated >= datetime("{anchor}") '
        f'| where {column} == "{value}" | limit 1'
    )
    timeout = minutes * 60
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = az_client.query_law(kql)
        if rows:
            print(f"\n  Found row in {table} where {column}=={value}")
            return
        remaining = int(deadline - time.time())
        print(f"\n  No row in {table} where {column}=={value} yet, retrying ({remaining}s remaining)...")
        time.sleep(config.LAW_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Table '{table}' has no row where {column}=='{value}' after {minutes} minutes"
    )

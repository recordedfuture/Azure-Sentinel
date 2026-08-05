"""
Sentinel-specific assertion steps.

The shared steps (run_status, law_has_new_row) are loaded via steps/__init__.py.
"""
import time

from behave import then

from support import az_client, config


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals the pinned playbook alert id')
def step_law_has_pinned_playbook_alert_row(context, minutes, table, column):
    row = _wait_for_specific_row(context, table, column, context.test_playbook_alert_id, minutes)
    context.pinned_playbook_alert_row = row


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals the pinned portal alert id')
def step_law_has_pinned_portal_alert_row(context, minutes, table, column):
    _wait_for_specific_row(context, table, column, context.test_portal_alert_id, minutes)


def _wait_for_specific_row(context, table, column, value, minutes) -> dict:
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
            print(f"\n  Found row in {table} where {column}=={value}:")
            print(f"  {rows[0]}")
            return rows[0]
        remaining = int(deadline - time.time())
        print(f"\n  No row in {table} where {column}=={value} yet, retrying ({remaining}s remaining)...")
        time.sleep(config.LAW_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Table '{table}' has no row where {column}=='{value}' after {minutes} minutes"
    )


@then('within {minutes:d} minutes a Sentinel incident is created for the pinned playbook alert')
def step_incident_created_for_pba(context, minutes):
    row = context.pinned_playbook_alert_row
    # The NRT rule titles new incidents as "Alert: {rule_label} - {alert_title}",
    # but its groupingConfiguration (groupByCustomDetails: ["Category"]) can
    # silently merge this alert into an existing incident of the same category
    # within the lookback window — in which case the incident's title reflects
    # whichever alert created it first, not necessarily ours. So we correlate
    # by SystemAlertId instead of matching on incident title/creation time:
    #   1. find the SecurityAlert row generated from our pinned LAW row
    #      (matched by alert_title, which is unique enough given trigger_time)
    #   2. find the incident whose AlertIds contains that alert's SystemAlertId
    alert_title = row.get("alert_title", "")
    remaining_budget = minutes * 60

    alert_deadline_share = min(remaining_budget, 300)
    alert_row = az_client.wait_for_alert(
        alert_title_substring=alert_title,
        after=context.trigger_time,
        timeout=alert_deadline_share,
    )
    system_alert_id = alert_row["SystemAlertId"]
    print(f"\n  Found alert '{alert_row['AlertName']}' (SystemAlertId={system_alert_id})")

    remaining_budget = max(remaining_budget - alert_deadline_share, 60)
    incident = az_client.wait_for_incident_containing_alert(
        system_alert_id=system_alert_id,
        timeout=remaining_budget,
    )
    print(f"\n  Incident #{incident['IncidentNumber']}: {incident['Title']}")
    print(f"  Severity: {incident.get('Severity')}")
    print(f"  Status:   {incident.get('Status')}")


@then('within {minutes:d} minutes at least 1 Sentinel incident is created after the trigger')
def step_incident_created_count(context, minutes):
    inc = az_client.wait_for_incident(
        after=context.trigger_time,
        timeout=minutes * 60,
    )
    props = inc["properties"]
    print(f"\n  Incident: {props['title']}")
    print(f"  Severity: {props['severity']}")
    print(f"  Status:   {props['status']}")

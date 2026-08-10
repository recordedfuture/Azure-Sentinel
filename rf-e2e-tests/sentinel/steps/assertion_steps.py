"""
Sentinel-specific assertion steps.

The shared steps (run_status, law_has_new_row) are loaded via steps/__init__.py.
"""
import json
import time

from behave import then

from support import az_client, config


@then('within {minutes:d} minutes table "{table}" has a row with JSON "data" array where each entry has keys "{keys}"')
def step_law_has_json_array_row(context, minutes, table, keys):
    """
    For playbooks (e.g. ThreatMap/ThreatMapMalware) that write one row per run
    containing a JSON-encoded array string in the "data" column — rather than
    one row per entity. Asserts the row exists, "data" parses as a non-empty
    JSON array, and its first entry has the expected keys. This catches shape
    regressions (e.g. a renamed/missing field), not just outright ingestion
    failures that a plain row-count check would catch.

    Safe against pre-existing rows — see trigger_logic_app()'s docstring.
    """
    required_keys = [k.strip() for k in keys.split(",")]
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = (
        f'{table} | where TimeGenerated >= datetime("{anchor}") '
        f'| order by TimeGenerated desc | limit 1'
    )
    timeout = minutes * 60
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = az_client.query_law(kql)
        if rows:
            row = rows[0]
            raw_data = row.get("data")
            assert raw_data, f"Row in {table} has empty/missing 'data' column: {row}"
            try:
                entries = json.loads(raw_data)
            except (TypeError, json.JSONDecodeError) as exc:
                raise AssertionError(
                    f"'data' column in {table} is not valid JSON: {exc}\n{raw_data!r}"
                )
            assert isinstance(entries, list) and entries, (
                f"'data' column in {table} did not parse to a non-empty JSON "
                f"array (got {type(entries).__name__} with "
                f"{len(entries) if hasattr(entries, '__len__') else '?'} items)"
            )
            missing = [k for k in required_keys if k not in entries[0]]
            assert not missing, (
                f"First entry in {table}'s 'data' array is missing expected "
                f"keys: {missing}. Entry keys present: {sorted(entries[0].keys())}"
            )
            print(
                f"\n  Row in {table}: 'data' array has {len(entries)} "
                f"entries, first entry has keys {required_keys}"
            )
            return
        remaining = int(deadline - time.time())
        print(f"\n  No row in {table} yet, retrying ({remaining}s remaining)...")
        time.sleep(config.LAW_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Table '{table}' has no new rows after {minutes} minutes (anchored to {anchor})"
    )


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals the pinned playbook alert id')
def step_law_has_pinned_playbook_alert_row(context, minutes, table, column):
    row = _wait_for_specific_row(context, table, column, context.test_playbook_alert_id, minutes)
    context.pinned_playbook_alert_row = row


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


@then('within {minutes:d} minutes table "{table}" has a row where "{column}" equals "{value}" with non-empty columns "{columns}"')
def step_law_has_row_with_columns(context, minutes, table, column, value, columns):
    """
    For playbooks that write one flat row per event (e.g. Sandbox results) —
    as opposed to ThreatMap's one-JSON-array-per-run shape. Asserts a new row
    exists where {column} == {value}, and that each of the given {columns} is
    present and non-empty/non-null on that row. Catches both outright
    ingestion failures (no row) and shape regressions (row landed but a field
    is missing/empty, e.g. an upstream mapping bug).

    Safe against pre-existing rows — see trigger_logic_app()'s docstring.
    """
    required_columns = [c.strip() for c in columns.split(",")]
    anchor = context.trigger_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    kql = (
        f'{table} | where TimeGenerated >= datetime("{anchor}") '
        f'| where {column} == "{value}" | order by TimeGenerated desc | limit 1'
    )
    timeout = minutes * 60
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = az_client.query_law(kql)
        if rows:
            row = rows[0]
            empty = [c for c in required_columns if not row.get(c)]
            assert not empty, (
                f"Row in {table} where {column}=='{value}' has empty/missing "
                f"columns: {empty}. Row: {row}"
            )
            print(f"\n  Found row in {table} where {column}=='{value}' "
                  f"with all expected columns populated: {required_columns}")
            return
        remaining = int(deadline - time.time())
        print(f"\n  No row in {table} where {column}=='{value}' yet, "
              f"retrying ({remaining}s remaining)...")
        time.sleep(config.LAW_POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Table '{table}' has no row where {column}=='{value}' after {minutes} minutes"
    )

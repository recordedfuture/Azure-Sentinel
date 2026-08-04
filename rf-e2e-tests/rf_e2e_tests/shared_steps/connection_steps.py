"""
Shared connection authorization step definition.

Uses config.VALID_CONN_STATUSES to determine what counts as "authorized".
Suites that use MSI-authenticated connections (which report "Ready" rather
than "Connected") should set VALID_CONN_STATUSES = {"Connected", "Ready"}
in their support/config.py.
"""
from behave import given

from support import az_client, config

_DEFAULT_VALID = {"Connected"}


@given('API connections for logic app "{key}" are authorized')
def step_connections_authorized(context, key):
    valid = getattr(config, "VALID_CONN_STATUSES", _DEFAULT_VALID)
    la_name = config.ALL_LOGIC_APP_NAMES[key]
    bad = []
    for prefix, required in config.ALL_REQUIRED_CONN_PREFIXES.get(key, {}).items():
        conn = f"{prefix}-{la_name}"
        status = az_client.get_connection_status(conn)
        marker = status if status in valid else (status or "not found")
        print(f"\n  Connection {conn}: {marker}")
        if required and status not in valid:
            bad.append((conn, status))

    assert not bad, (
        f"Required connection(s) not authorized for {key}: "
        + ", ".join(f"{c} ({s})" for c, s in bad)
        + "\nRe-run the suite — before_all will open consent URLs automatically."
    )

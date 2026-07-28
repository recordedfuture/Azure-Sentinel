"""
Connection authorization check steps.

Connection authorization (opening browser tabs, prompting) is handled
in before_all. This step only verifies that required connections are
Connected and fails fast with a clear message if not.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from behave import given

from support import az_client, config

_REQUIRED_CONN_PREFIXES = {
    "nouser":   {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "baseuser": {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": True},
    "entra":    {"Azuread": True,  "Azureadip": True,  "Azuremonitorlogs": True},
    "nolaw":    {"Azuread": True,  "Azureadip": False, "Azuremonitorlogs": False},
}


@given('API connections for logic app "{key}" are authorized')
def step_connections_authorized(context, key):
    la_name = config.LOGIC_APP_NAMES[key]
    bad = []
    for prefix, required in _REQUIRED_CONN_PREFIXES.get(key, {}).items():
        conn = f"{prefix}-{la_name}"
        status = az_client.get_connection_status(conn)
        marker = "OK" if status == "Connected" else status or "not found"
        print(f"\n  Connection {conn}: {marker}")
        if required and status != "Connected":
            bad.append((conn, status))

    assert not bad, (
        f"Required connection(s) not authorized for {key}: "
        + ", ".join(f"{c} ({s})" for c, s in bad)
        + "\nRe-run the suite — before_all will open consent URLs automatically."
    )

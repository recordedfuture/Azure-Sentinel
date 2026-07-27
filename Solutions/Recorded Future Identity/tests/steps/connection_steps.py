"""
Connection authorization check steps.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from behave import given

from support import az_client, config

# Connections that are strictly required per scenario.
# Azureadip (Identity Protection) is optional — P1/P2 only.
# The RF custom connector is injected with the API key at deploy time (always Connected).
_REQUIRED_CONNECTIONS = {
    "nouser":   ["Azuread", "Azuremonitorlogs"],
    "baseuser": ["Azuread", "Azuremonitorlogs"],
    "entra":    ["Azuread", "Azureadip", "Azuremonitorlogs"],
    "nolaw":    ["Azuread"],
}


def _connection_names_for(key: str) -> dict[str, bool]:
    """Return {connection_name: required} for a scenario key."""
    name = config.LOGIC_APP_NAMES[key]
    required = _REQUIRED_CONNECTIONS.get(key, [])
    return {
        f"Azuread-{name}": "Azuread" in required,
        f"Azureadip-{name}": "Azureadip" in required,
        f"Azuremonitorlogs-{name}": "Azuremonitorlogs" in required,
        config.RFI_CUSTOM_CONNECTOR: True,  # Always required; pre-authorized at deploy
    }


@given('API connections for logic app "{key}" are authorized')
def step_connections_authorized(context, key):
    connections = _connection_names_for(key)
    unconnected = []
    for conn, required in connections.items():
        status = az_client.get_connection_status(conn)
        if status is None:
            print(f"\n  Connection {conn}: not found (may not be provisioned)")
            continue
        state = "OK" if status == "Connected" else status
        print(f"\n  Connection {conn}: {state}" + ("" if status == "Connected" else f" (required={required})"))
        if status != "Connected" and required:
            unconnected.append((conn, status))

    if unconnected:
        la_name = config.LOGIC_APP_NAMES[key]
        sub = config.SUBSCRIPTION_ID
        rg = config.RESOURCE_GROUP
        portal_url = (
            f"https://portal.azure.com/#resource/subscriptions/{sub}"
            f"/resourceGroups/{rg}/providers/Microsoft.Logic/workflows/{la_name}/designer"
        )
        print(f"\n  *** {len(unconnected)} required connection(s) need authorization:")
        for conn, st in unconnected:
            print(f"      {conn}: {st}")
        print(f"\n  Open the Logic App designer to authorize:")
        print(f"      {portal_url}")
        try:
            with open("/dev/tty") as tty:
                tty.write("\n  Press Enter once all connections are authorized ... ")
                tty.flush()
                tty.readline()
        except OSError:
            raise AssertionError(
                f"Connections not authorized and no TTY available for interactive prompt. "
                f"Please authorize connections manually at:\n      {portal_url}"
            )

        # Re-verify
        still_broken = []
        for conn, _ in unconnected:
            status = az_client.get_connection_status(conn)
            if status != "Connected":
                still_broken.append((conn, status))
        assert not still_broken, (
            f"Connections still not authorized after user confirmation: {still_broken}"
        )


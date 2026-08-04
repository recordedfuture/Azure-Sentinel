"""
Sentinel-specific environment/background steps.

The shared steps (az_authenticated, rg_exists, law_accessible, rf_api_reachable)
are loaded via steps/__init__.py from rf_e2e_tests.shared_steps.
"""
from behave import given

from support import az_client, config


@given('the shared RF connector "{conn_name}" is connected')
def step_rf_connector_connected(context, conn_name):
    ok = az_client.verify_rf_connection(conn_name)
    assert ok, (
        f"RF connection '{conn_name}' is not Connected in {config.RESOURCE_GROUP}. "
        "Deploy a playbook using this connector to create and authorize it."
    )
    print(f"\n  RF connector {conn_name}: Connected")

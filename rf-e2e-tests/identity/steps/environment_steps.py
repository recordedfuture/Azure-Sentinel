"""
Identity-specific environment/background steps.

The shared steps (az_authenticated, rg_exists, law_accessible, rf_api_reachable)
are loaded via steps/__init__.py from rf_e2e_tests.shared_steps.
"""
from behave import given

from support import az_client, config, rf_client


@given('there is at least 1 New identity PBA available via the RF gateway')
def step_pba_available(context):
    items = rf_client.get_new_pba_via_gateway()
    context.available_pba_ids = [i["alert_id"] for i in items]
    assert len(items) >= 1, (
        f"Expected at least 1 New PBA via gateway, got 0. "
        "Ensure the RF test account has New identity_novel_exposures alerts."
    )
    print(f"\n  {len(items)} New PBAs available via gateway")


@given('the test user "{upn}" exists in Entra ID')
def step_test_user_exists(context, upn):
    result = az_client._run("ad", "user", "show", "--id", upn, check=False)
    assert result, f"Test user '{upn}' not found in Entra ID"
    print(f"\n  Test user OID: {result.get('id')}")


@given('the test security group "{group_id}" exists in Entra ID')
def step_security_group_exists(context, group_id):
    result = az_client._run("ad", "group", "show", "--group", group_id, check=False)
    assert result, f"Security group '{group_id}' not found"
    print(f"\n  Security group: {result.get('displayName')}")

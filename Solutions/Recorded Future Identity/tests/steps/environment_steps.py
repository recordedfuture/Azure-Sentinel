"""
Environment assertion steps (Background section).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from behave import given

from support import az_client, config, rf_client


@given('az CLI is authenticated')
def step_az_authenticated(context):
    acc = az_client.check_auth()
    assert acc, "az CLI is not authenticated"
    print(f"\n  Authenticated as: {acc['user']['name']}")


@given('resource group "{rg}" exists')
def step_rg_exists(context, rg):
    result = az_client.check_resource_group(rg)
    assert result, f"Resource group '{rg}' not found"


@given('Log Analytics Workspace "{law}" is accessible')
def step_law_accessible(context, law):
    result = az_client.check_law(law=law)
    assert result, f"Log Analytics Workspace '{law}' not found"


@given('the RF API is reachable with token from "{env_var}"')
def step_rf_api_reachable(context, env_var):
    token = os.environ.get(env_var.strip("$"))
    assert token, f"Environment variable {env_var} is not set"
    # Verify we can reach the gateway
    items = rf_client.get_new_pba_via_gateway()
    assert items is not None, "RF gateway returned no response"
    print(f"\n  RF gateway reachable — {len(items)} New PBAs available")


@given('there is at least 1 New identity PBA available via the RF gateway')
def step_pba_available(context):
    items = rf_client.get_new_pba_via_gateway()
    context.available_pba_ids = [i["alert_id"] for i in items]
    assert len(items) >= 1, (
        f"Expected at least 1 New PBA via gateway, got 0. "
        "Ensure the RF test account has New identity_novel_exposures alerts."
    )
    print(f"\n  {len(items)} New PBAs available via gateway")
    # Note: the test_alert_id may currently be Dismissed (from a prior scenario);
    # it will be reset to New in the 'the test RF alert is reset to New' step.


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

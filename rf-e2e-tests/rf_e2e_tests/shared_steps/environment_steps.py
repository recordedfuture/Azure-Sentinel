"""
Shared environment/background step definitions.
"""
import os

from behave import given

from support import az_client, config, rf_client


@given("az CLI is authenticated")
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
    """
    Verify the RF token env var is set and the RF API is reachable.
    Delegates to rf_client.check_reachable() for a lightweight API ping —
    each suite's rf_client implements this against its own gateway endpoint.
    """
    token = os.environ.get(env_var.strip("$"))
    assert token, f"Environment variable {env_var} is not set"
    rf_client.check_reachable()

"""
Behave environment hooks for the RF Identity E2E suite.
"""
from datetime import datetime, timezone

from rf_e2e_tests import connections, shared_hooks
from support import az_client, config
from support import deployment


def before_all(context):
    run_pba = shared_hooks.tag_active(context, "pba")
    run_v3  = shared_hooks.tag_active(context, "v3")

    if run_pba:
        deployment.setup_pba(context)
        connections.authorize_if_needed(
            config.LOGIC_APP_NAMES,
            config.PBA_REQUIRED_CONN_PREFIXES,
            config.SUBSCRIPTION_ID,
            config.RESOURCE_GROUP,
        )

    if run_v3:
        deployment.setup_v3(context)
        connections.authorize_if_needed(
            config.V3_LOGIC_APP_NAMES,
            config.V3_REQUIRED_CONN_PREFIXES,
            config.SUBSCRIPTION_ID,
            config.RESOURCE_GROUP,
        )

    context.suite_start_time = datetime.now(timezone.utc)
    context.completed_runs = []
    print(f"\n  Suite start time (LAW baseline): {context.suite_start_time.isoformat()}")


def before_scenario(context, scenario):
    shared_hooks.before_scenario(context, scenario, config, az_client)


def after_scenario(context, scenario):
    shared_hooks.accumulate_run(context, config)
    if context.scenario_key in ("entra", "v3_workforce"):
        deployment.teardown_entra(context)


def after_all(context):
    shared_hooks.after_all(context, config)

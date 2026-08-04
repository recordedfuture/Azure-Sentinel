"""
Shared Logic App trigger and wait step definition.
"""
from behave import when

from support import az_client, config


@when('I trigger logic app "{key}" and wait for completion')
def step_trigger_and_wait(context, key):
    name = config.ALL_LOGIC_APP_NAMES[key]
    print(f"\n  Triggering {name} ...")
    context.trigger_time = az_client.trigger_logic_app(name)
    print(f"  Triggered at {context.trigger_time.isoformat()}, waiting up to {config.RUN_TIMEOUT_SECONDS}s ...")
    context.run = az_client.wait_for_run(name, context.trigger_time)
    run_name = context.run["name"]
    status = context.run["properties"]["status"]
    print(f"  Run {run_name} finished with status: {status}")
    context.action_statuses = az_client.get_run_action_statuses(name, run_name)
    print(f"  Actions: {context.action_statuses}")

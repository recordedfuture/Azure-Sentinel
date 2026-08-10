"""
Shared Logic App trigger and wait step definition.
"""
import time

from behave import when

from support import az_client, config

# Max total time to keep retrying a run that fails purely due to DCR
# role-assignment propagation lag (observed up to ~30+ min in this
# subscription), before giving up and reporting the failure for real.
_RBAC_RETRY_MAX_SECONDS = 2400  # 40 minutes
_RBAC_RETRY_INTERVAL_SECONDS = 90


@when('I trigger logic app "{key}" and wait for completion')
def step_trigger_and_wait(context, key):
    name = config.ALL_LOGIC_APP_NAMES[key]
    # Some scenarios (e.g. RF Sandbox, which submits-and-polls a real external
    # API for several minutes) need longer than the default RUN_TIMEOUT_SECONDS
    # — suites can opt a specific key into a longer wait via a
    # RUN_TIMEOUT_OVERRIDES = {key: seconds} dict in their support/config.py,
    # without changing the default for every other (fast) scenario.
    run_timeout = getattr(config, "RUN_TIMEOUT_OVERRIDES", {}).get(
        key, config.RUN_TIMEOUT_SECONDS
    )
    deadline = time.time() + _RBAC_RETRY_MAX_SECONDS
    attempt = 0

    while True:
        attempt += 1
        suffix = f" (attempt {attempt})" if attempt > 1 else ""
        print(f"\n  Triggering {name}{suffix} ...")
        trigger_time = az_client.trigger_logic_app(name)
        print(f"  Triggered at {trigger_time.isoformat()}, waiting up to {run_timeout}s ...")
        run = az_client.wait_for_run(name, trigger_time, timeout=run_timeout)
        run_name = run["name"]
        status = run["properties"]["status"]
        print(f"  Run {run_name} finished with status: {status}")
        action_statuses = az_client.get_run_action_statuses(name, run_name)
        print(f"  Actions: {action_statuses}")

        if status == "Succeeded" or time.time() >= deadline:
            break

        if az_client.is_dcr_rbac_propagation_error(name, run_name, action_statuses):
            remaining = int(deadline - time.time())
            print(
                "  Failure is due to DCR role-assignment propagation lag "
                f"(not yet enforced) — retrying in {_RBAC_RETRY_INTERVAL_SECONDS}s "
                f"({remaining}s left before giving up)..."
            )
            time.sleep(_RBAC_RETRY_INTERVAL_SECONDS)
            continue

        # A different, real failure — don't mask it with retries.
        break

    context.trigger_time = trigger_time
    context.run = run
    context.action_statuses = action_statuses

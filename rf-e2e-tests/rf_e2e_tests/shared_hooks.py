"""
Shared behave lifecycle hooks and helpers.

Suites import these and call them from their own hook functions,
adding suite-specific logic on top where needed.
"""
import subprocess
import sys
from datetime import datetime, timezone


def tag_active(context, tag: str) -> bool:
    """Return True if *tag* is active (or no tag filter is set)."""
    tags = context.config.tags
    if not tags:
        return True
    return tag in str(tags)


def before_scenario(context, scenario, config, az_client):
    """Standard before_scenario: reset run state and enable the Logic App."""
    context.trigger_time = None
    context.run = None
    context.scenario_key = scenario.name.split()[0]
    context.scenario_start_time = datetime.now(timezone.utc)

    name = config.ALL_LOGIC_APP_NAMES.get(context.scenario_key)
    if name and az_client.logic_app_exists(name):
        az_client.enable_logic_app(name)


def accumulate_run(context, config):
    """Record the completed run for the after_all browser prompt."""
    if context.run:
        app_name = config.ALL_LOGIC_APP_NAMES.get(context.scenario_key, "")
        if app_name:
            context.completed_runs.append({
                "scenario": context.scenario_key,
                "app_name": app_name,
                "status": context.run["properties"]["status"],
            })


def after_all(context, config):
    """Disable all test Logic Apps and offer to open run URLs in browser."""
    print("\n=== Disabling test logic apps ===")
    from rf_e2e_tests.az_client import disable_logic_app
    for key, name in config.ALL_LOGIC_APP_NAMES.items():
        try:
            disable_logic_app(name)
            print(f"  [disable] {name} disabled")
        except Exception as exc:
            print(f"  [disable] {name} skipped: {exc}")

    runs = getattr(context, "completed_runs", [])
    if runs and sys.stdin.isatty():
        print(f"\nOpen {len(runs)} logic app run(s) in browser? [y/N] ", end="", flush=True)
        try:
            with open("/dev/tty") as tty:
                answer = tty.readline().strip().lower()
        except OSError:
            answer = ""

        if answer == "y":
            tenant = config.PORTAL_TENANT
            sub = config.SUBSCRIPTION_ID
            rg = config.RESOURCE_GROUP
            for r in runs:
                url = (
                    f"https://portal.azure.com/#@{tenant}"
                    f"/resource/subscriptions/{sub}/resourceGroups/{rg}"
                    f"/providers/Microsoft.Logic/workflows/{r['app_name']}/logicApp"
                )
                print(f"  Opening {r['scenario']} ({r['status']}): {r['app_name']}")
                subprocess.run(["open", url], check=False)

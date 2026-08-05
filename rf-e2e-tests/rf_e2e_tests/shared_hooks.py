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


def prompt_open_in_browser(labeled_urls: list, noun: str) -> None:
    """
    Offer to open each (label, url) pair in *labeled_urls* in the browser.
    Reads the y/N answer from /dev/tty (bypassing behave's captured stdin,
    which would otherwise swallow interactive input). No-op if there's
    nothing to offer or stdin isn't a real terminal (e.g. CI runs).
    """
    if not labeled_urls or not sys.stdin.isatty():
        return

    print(f"\nOpen {len(labeled_urls)} {noun}(s) in browser? [y/N] ", end="", flush=True)
    try:
        with open("/dev/tty") as tty:
            answer = tty.readline().strip().lower()
    except OSError:
        answer = ""

    if answer == "y":
        for label, url in labeled_urls:
            print(f"  Opening {label}")
            subprocess.run(["open", url], check=False)


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
    tenant = config.PORTAL_TENANT
    sub = config.SUBSCRIPTION_ID
    rg = config.RESOURCE_GROUP
    labeled_urls = [
        (
            f"{r['scenario']} ({r['status']}): {r['app_name']}",
            f"https://portal.azure.com/#@{tenant}"
            f"/resource/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Logic/workflows/{r['app_name']}/logicApp",
        )
        for r in runs
    ]
    prompt_open_in_browser(labeled_urls, noun="logic app run")

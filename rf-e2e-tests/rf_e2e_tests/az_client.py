"""
Shared Azure/ARM client for RF E2E test suites.

Provides thin wrappers around `az` CLI and ARM REST API calls that are
common to both the Identity and Sentinel test suites. Suite-specific
functions (Entra ID, Sentinel incidents, custom connector setup) live
in the suite's own support/az_client.py alongside a
`from rf_e2e_tests.az_client import *` import.
"""
import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from . import config_base as config


class AzCliError(Exception):
    pass


def _extract_arm_error(stderr: str) -> str:
    """
    Parse ARM/az CLI stderr and return a concise human-readable message.
    Falls back to the raw stderr if parsing fails.
    """
    import re
    raw = stderr.strip()

    json_str = raw.removeprefix("ERROR:").strip()
    try:
        data = json.loads(json_str)
        err = data.get("error", data)
        msg = err.get("message", "")
        details = err.get("details", [])
        if details and isinstance(details, list):
            msg = details[0].get("message", msg)
        if msg:
            if (
                "roleassignment" in msg.lower()
                or "authorization" in msg.lower()
                or "AuthorizationFailed" in err.get("code", "")
            ):
                msg += (
                    "\n\n  Hint: this account lacks permission to assign roles on the DCR. "
                    "Re-run `az login` with an admin account for first-time setup (see README.md)."
                )
            return msg
    except (json.JSONDecodeError, AttributeError):
        pass

    match = re.search(r"\((\w+)\) (.+?)(?:\nCode:|$)", raw, re.DOTALL)
    if match:
        code, msg = match.group(1), match.group(2).strip()
        result = f"{code}: {msg[:300]}"
        if "roleassignment" in msg.lower() or "authorization" in msg.lower():
            result += (
                "\n\n  Hint: this account lacks permission to assign roles on the DCR. "
                "Re-run `az login` with an admin account for first-time setup (see README.md)."
            )
        return result

    return raw[:500]


def _run(*args, check=True) -> Optional[dict | list]:
    """Run `az <args> --output json` and return parsed output, or None."""
    cmd = ["az"] + list(args) + ["--output", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AzCliError(_extract_arm_error(result.stderr))
    stdout = result.stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _rest(method: str, url: str, body: Optional[dict] = None, check: bool = True) -> Optional[dict | list]:
    """Thin wrapper for `az rest`."""
    args = ["rest", "--method", method, "--url", url]
    if body:
        args += ["--body", json.dumps(body)]
    return _run(*args, check=check)


# ── Environment assertions ────────────────────────────────────────────────────

def check_auth() -> dict:
    return _run("account", "show")


def check_resource_group(rg: str = config.RESOURCE_GROUP) -> dict:
    return _run("group", "show", "--name", rg)


def check_law(rg: str = config.RESOURCE_GROUP, law: str = config.LAW_NAME) -> dict:
    return _run(
        "monitor", "log-analytics", "workspace", "show",
        "--resource-group", rg,
        "--workspace-name", law,
    )


# ── Logic App deployment ──────────────────────────────────────────────────────

def logic_app_exists(name: str, rg: str = config.RESOURCE_GROUP) -> bool:
    result = _run(
        "logic", "workflow", "show",
        "--resource-group", rg,
        "--name", name,
        check=False,
    )
    return result is not None


def deploy_logic_app(
    template_path: str,
    params: dict,
    rg: str = config.RESOURCE_GROUP,
) -> None:
    """Deploy via ARM. params is a flat {key: value} dict."""
    arm_params = {k: {"value": v} for k, v in params.items()}
    inline_json = json.dumps(arm_params)

    print(f"  Deploying {params.get('PlaybookName', '?')} ...")
    _run(
        "deployment", "group", "create",
        "--resource-group", rg,
        "--template-file", template_path,
        "--parameters", inline_json,
        "--mode", "Incremental",
    )
    print(f"  Deployed {params.get('PlaybookName', '?')}")


def enable_logic_app(name: str, rg: str = config.RESOURCE_GROUP) -> None:
    _set_logic_app_state(name, "Enabled", rg)


def disable_logic_app(name: str, rg: str = config.RESOURCE_GROUP) -> None:
    _set_logic_app_state(name, "Disabled", rg)


def _set_logic_app_state(name: str, state: str, rg: str) -> None:
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Logic/workflows/{name}?api-version=2016-06-01"
    )
    body = _rest("GET", url, check=False)
    if not body:
        return
    body["properties"]["state"] = state
    for key in ("id", "name", "type"):
        body.pop(key, None)
    _rest("PUT", url, body, check=False)


# ── Logic App triggering & run tracking ──────────────────────────────────────

def trigger_logic_app(name: str, rg: str = config.RESOURCE_GROUP) -> datetime:
    """Fire the Recurrence trigger and return the time just before firing."""
    sub = config.SUBSCRIPTION_ID
    trigger_time = datetime.now(timezone.utc)
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Logic/workflows/{name}"
        f"/triggers/Recurrence/run?api-version=2016-06-01"
    )
    _rest("POST", url)
    return trigger_time


def _list_runs(name: str, rg: str = config.RESOURCE_GROUP) -> list:
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Logic/workflows/{name}"
        f"/runs?api-version=2016-06-01&$top=10"
    )
    result = _rest("GET", url)
    return result.get("value", []) if result else []


def wait_for_run(
    name: str,
    after: datetime,
    timeout: int = 180,
    rg: str = config.RESOURCE_GROUP,
) -> dict:
    """
    Poll until a run started >= *after* finishes (status != Running).
    Returns the run dict. Raises AzCliError on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for run in _list_runs(name, rg):
            start_str = run["properties"].get("startTime", "")
            if not start_str:
                continue
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            if start >= after:
                status = run["properties"]["status"]
                if status != "Running":
                    return run
        time.sleep(5)
    raise AzCliError(
        f"Timed out waiting for {name} run to complete after {timeout}s"
    )


def get_run_action_statuses(
    name: str, run_name: str, rg: str = config.RESOURCE_GROUP
) -> dict:
    """Return {action_name: status} for a completed run."""
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Logic/workflows/{name}"
        f"/runs/{run_name}/actions?api-version=2016-06-01"
    )
    result = _rest("GET", url)
    return {
        a["name"]: a["properties"]["status"]
        for a in (result.get("value", []) if result else [])
    }


# ── Log Analytics ─────────────────────────────────────────────────────────────

def query_law(kql: str, workspace: str = config.LAW_WORKSPACE_ID) -> list:
    """Run a KQL query and return the rows as a list of dicts."""
    result = _run(
        "monitor", "log-analytics", "query",
        "--workspace", workspace,
        "--analytics-query", kql,
    )
    if result is None:
        return []
    if isinstance(result, list):
        return result
    tables = result.get("tables", [])
    if not tables:
        return []
    cols = [c["name"] for c in tables[0]["columns"]]
    return [dict(zip(cols, row)) for row in tables[0]["rows"]]


# ── API connections ───────────────────────────────────────────────────────────

def get_connection_status(
    connection_name: str, rg: str = config.RESOURCE_GROUP
) -> Optional[str]:
    """Return the first status string for an API connection, or None."""
    sub = config.SUBSCRIPTION_ID
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Web/connections/{connection_name}"
        f"?api-version=2016-06-01"
    )
    result = _rest("GET", url, check=False)
    if not result:
        return None
    statuses = result.get("properties", {}).get("statuses", [])
    return statuses[0].get("status") if statuses else None

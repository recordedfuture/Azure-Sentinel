"""
In-memory ARM template patcher for test isolation.

Applies surgical mutations to azuredeploy.json (loaded as a dict):
  1. Sets lookback_days and max_lookback_days in the search action body to 21.
  2. Removes the priorities filter (test alerts may be Informational).
  3. Inserts a Filter_alerts_for_testing Query action after the search.
  4. Rewires For_each to iterate over the filter output instead of raw search result.
  5. Injects the RF API key into the RFI Custom Connector connection resource
     so it is pre-authorized on deploy (no manual portal step needed).
  6. (Optional) When entra_user_upn is provided, inserts an
     Overwrite_user_principal_name Compose action that hardcodes the UPN,
     and replaces all references to Compute_user_principal_name with
     Overwrite_user_principal_name. This makes Get_User find a known Entra
     user regardless of the actual PBA identity.

The original file is never written to. The patched dict is written to a
temporary file for use with `az deployment group create`, then deleted.
"""
import copy
import json
import tempfile
from typing import Optional

SEARCH_ACTION = "Playbook_Alerts_-_Search_for_novel_identity_exposures"
FILTER_ACTION = "Filter_alerts_for_testing"
FOREACH_ACTION = "For_each"
COMPUTE_ACTION = "Compute_user_principal_name"
OVERRIDE_ACTION = "Overwrite_user_principal_name"

_FILTER_ACTION_TEMPLATE = {
    "type": "Query",
    "inputs": {
        "from": f"@body('{SEARCH_ACTION}')?['pba_items']",
        "where": "@equals(item()?['alert_id'], 'ALERT_ID_PLACEHOLDER')",
    },
    "runAfter": {SEARCH_ACTION: ["Succeeded"]},
}


def patch_template(
    template: dict,
    alert_id: str,
    lookback_days: int = 21,
    rf_api_key: Optional[str] = None,
    entra_user_upn: Optional[str] = None,
) -> dict:
    """
    Return a deep copy of *template* with test-isolation mutations applied.

    Args:
        template:       Parsed azuredeploy.json dict.
        alert_id:       RF alert ID to pin (e.g. "task:67d143bc-...").
        lookback_days:  Value to set in the search body (default 21).
        rf_api_key:     If provided, inject into the RFI Custom Connector
                        connection resource so it is pre-authorized on deploy.
        entra_user_upn: If provided, insert an Overwrite_user_principal_name
                        Compose action hardcoded to this UPN, and replace all
                        references to Compute_user_principal_name with it.
                        Use this for "user found" scenarios so Get_User hits
                        a known Entra user regardless of the PBA identity.
    """
    t = copy.deepcopy(template)

    for resource in t["resources"]:
        # ── Logic App workflow mutations ──────────────────────────────────────
        if resource.get("type") == "Microsoft.Logic/workflows":
            actions = resource["properties"]["definition"]["actions"]
            foreach_actions = actions[FOREACH_ACTION]["actions"]

            # 1. lookback_days + max_lookback_days + remove priority filter
            search = actions[SEARCH_ACTION]
            search["inputs"]["body"]["lookback_days"] = lookback_days
            search["inputs"]["body"]["max_lookback_days"] = lookback_days
            search["inputs"]["body"].pop("priorities", None)

            # 2. Insert Filter_alerts_for_testing
            filter_action = copy.deepcopy(_FILTER_ACTION_TEMPLATE)
            filter_action["inputs"]["where"] = filter_action["inputs"]["where"].replace(
                "ALERT_ID_PLACEHOLDER", alert_id
            )
            actions[FILTER_ACTION] = filter_action

            # 3. Rewire For_each
            actions[FOREACH_ACTION]["runAfter"] = {FILTER_ACTION: ["Succeeded"]}
            actions[FOREACH_ACTION]["foreach"] = f"@body('{FILTER_ACTION}')"

            # 4. (Optional) Override the computed UPN for user-found scenarios
            if entra_user_upn:
                # Insert override Compose immediately after Compute
                foreach_actions[OVERRIDE_ACTION] = {
                    "type": "Compose",
                    "description": (
                        "Test isolation: hardcode UPN to a known Entra user "
                        "regardless of the PBA identity."
                    ),
                    "inputs": entra_user_upn,
                    "runAfter": {COMPUTE_ACTION: ["Succeeded"]},
                }
                # Replace all output references in the foreach actions
                patched_str = json.dumps(foreach_actions).replace(
                    f"outputs('{COMPUTE_ACTION}')",
                    f"outputs('{OVERRIDE_ACTION}')",
                )
                new_foreach_actions = json.loads(patched_str)
                # Fix runAfter: any action that depended on Compute must now depend
                # on Override instead (so Azure's dependency validation passes)
                for action in new_foreach_actions.values():
                    ra = action.get("runAfter", {})
                    if COMPUTE_ACTION in ra and action is not new_foreach_actions.get(OVERRIDE_ACTION):
                        ra[OVERRIDE_ACTION] = ra.pop(COMPUTE_ACTION)
                actions[FOREACH_ACTION]["actions"] = new_foreach_actions

        # ── 5. Inject RF API key into the RFI Custom Connector connection ─────
        if rf_api_key and resource.get("type") == "Microsoft.Web/connections":
            api_id = resource.get("properties", {}).get("api", {}).get("id", "")
            if "customApis" in api_id:
                resource["properties"]["parameterValues"] = {"api_key": rf_api_key}

    return t


def write_temp(template: dict) -> str:
    """
    Serialise *template* to a named temp file and return its path.
    The caller is responsible for deleting the file after use.
    """
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="rfi-test-"
    )
    json.dump(template, f, indent=2)
    f.close()
    return f.name

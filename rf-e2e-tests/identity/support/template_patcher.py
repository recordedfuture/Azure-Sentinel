"""
In-memory ARM template patcher for RFI-Playbook-Alert-Importer-LAW.

Patches applied:
  1. Widens lookback_days / max_lookback_days to 21 and removes the priorities
     filter so Informational alerts are included.
  2. Inserts Filter_alerts_for_testing after the search, pinning the run to
     one known alert ID.
  3. Rewires For_each to iterate over the filter output.
  4. (Optional) Inserts Overwrite_user_principal_name to force a known Entra
     user for "user found" scenarios, and rewires all downstream references.
  5. (Optional) Injects the RF API key into the RFI Custom Connector connection
     resource so it is pre-authorized at deploy time.

The original file is never written to. Use rf_e2e_tests.patchers.write_temp()
to serialise the result for `az deployment group create`.
"""
import copy
import json
from typing import Optional

SEARCH_ACTION = "Playbook_Alerts_-_Search_for_novel_identity_exposures"
FILTER_ACTION = "Filter_alerts_for_testing"
FOREACH_ACTION = "For_each"
COMPUTE_ACTION = "Compute_user_principal_name"
OVERRIDE_ACTION = "Overwrite_user_principal_name"


def patch_template(
    template: dict,
    alert_id: str,
    lookback_days: int = 21,
    rf_api_key: Optional[str] = None,
    entra_user_upn: Optional[str] = None,
) -> dict:
    """
    Return a deep copy of *template* with test-isolation patches applied.

    Args:
        template:       Parsed azuredeploy.json dict.
        alert_id:       RF alert ID to pin (e.g. "task:67d143bc-...").
        lookback_days:  Value to set in the search body (default 21).
        rf_api_key:     If provided, inject into the RFI Custom Connector so it
                        is pre-authorized on deploy.
        entra_user_upn: If provided, insert Overwrite_user_principal_name to
                        force a known Entra user regardless of the PBA identity.
    """
    t = copy.deepcopy(template)

    for resource in t["resources"]:
        if resource.get("type") == "Microsoft.Logic/workflows":
            actions = resource["properties"]["definition"]["actions"]
            foreach_actions = actions[FOREACH_ACTION]["actions"]

            # 1. Widen search window and drop priority filter
            search = actions[SEARCH_ACTION]
            search["inputs"]["body"]["lookback_days"] = lookback_days
            search["inputs"]["body"]["max_lookback_days"] = lookback_days
            search["inputs"]["body"].pop("priorities", None)
            search["description"] = (
                f"[TEST] lookback_days set to {lookback_days}, "
                "priorities filter removed so Informational alerts are included."
            )

            # 2. Insert filter — pins the run to one specific alert
            actions[FILTER_ACTION] = {
                "type": "Query",
                "description": f"[TEST] Filters pba_items to alert_id == {alert_id}.",
                "inputs": {
                    "from": f"@body('{SEARCH_ACTION}')?['pba_items']",
                    "where": f"@equals(item()?['alert_id'], '{alert_id}')",
                },
                "runAfter": {SEARCH_ACTION: ["Succeeded"]},
            }

            # 3. Rewire For_each to the filter output
            actions[FOREACH_ACTION]["description"] = (
                "[TEST] foreach and runAfter rewired to iterate over "
                "Filter_alerts_for_testing output instead of raw search results."
            )
            actions[FOREACH_ACTION]["runAfter"] = {FILTER_ACTION: ["Succeeded"]}
            actions[FOREACH_ACTION]["foreach"] = f"@body('{FILTER_ACTION}')"

            # 4. (Optional) Force a known Entra UPN for user-found scenarios
            if entra_user_upn:
                foreach_actions[OVERRIDE_ACTION] = {
                    "type": "Compose",
                    "description": (
                        f"[TEST] Hardcodes UPN to {entra_user_upn} so Get_User "
                        "always finds a known Entra user regardless of PBA identity."
                    ),
                    "inputs": entra_user_upn,
                    "runAfter": {COMPUTE_ACTION: ["Succeeded"]},
                }
                patched_str = json.dumps(foreach_actions).replace(
                    f"outputs('{COMPUTE_ACTION}')",
                    f"outputs('{OVERRIDE_ACTION}')",
                )
                new_foreach_actions = json.loads(patched_str)
                for action in new_foreach_actions.values():
                    ra = action.get("runAfter", {})
                    if COMPUTE_ACTION in ra and action is not new_foreach_actions.get(OVERRIDE_ACTION):
                        ra[OVERRIDE_ACTION] = ra.pop(COMPUTE_ACTION)
                actions[FOREACH_ACTION]["actions"] = new_foreach_actions

        # 5. (Optional) Pre-authorize the RFI Custom Connector
        if rf_api_key and resource.get("type") == "Microsoft.Web/connections":
            api_id = resource.get("properties", {}).get("api", {}).get("id", "")
            if "customApis" in api_id:
                resource["properties"]["parameterValues"] = {"api_key": rf_api_key}

    return t

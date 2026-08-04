"""
In-memory ARM template patcher for RecordedFuture-Playbook-Alert-Importer.

Patches applied:
  1. Widens Search_Playbook_Alerts window from 1h to 24h so the pinned alert
     is guaranteed to be in the search results.
  2. Inserts Filter_alerts_for_testing after the search, pinning the run to
     a single known alert ID.
  3. Rewires For_each to iterate over the filter output.

The original file is never written to. Use rf_e2e_tests.patchers.write_temp()
to serialise the result for `az deployment group create`.
"""
import copy

SEARCH_ACTION = "Search_Playbook_Alerts"
FILTER_ACTION = "Filter_alerts_for_testing"
FOREACH_ACTION = "For_each"


def patch_template(template: dict, alert_id: str) -> dict:
    """
    Return a deep copy of *template* with test-isolation patches applied.

    Args:
        template:  Parsed azuredeploy.json dict.
        alert_id:  RF Playbook Alert ID to pin (e.g. "task:abc123-...").
    """
    t = copy.deepcopy(template)

    for resource in t["resources"]:
        if resource.get("type") != "Microsoft.Logic/workflows":
            continue

        actions = resource["properties"]["definition"]["actions"]

        # 1. Widen search window so the pinned alert is in range
        actions[SEARCH_ACTION]["inputs"]["body"]["updated_from_relative"] = "-24"
        actions[SEARCH_ACTION]["description"] = (
            "[TEST] updated_from_relative widened from -1 to -24 "
            "so the pinned alert is always within the search window."
        )

        # 2. Insert filter — pins the run to one specific alert
        actions[FILTER_ACTION] = {
            "type": "Query",
            "description": f"[TEST] Filters search results to alert_id == {alert_id}.",
            "inputs": {
                "from": f"@body('{SEARCH_ACTION}')",
                "where": f"@equals(item()?['playbook_alert_id'], '{alert_id}')",
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

    return t

"""
In-memory ARM template patcher for RecordedFuture-Alert-Importer.

Patches applied:
  1. Replaces the Run_query_and_list_results KQL body with a fixed
     "print LatestEvent=ago(30d)" so the watermark always falls 30 days
     back, ensuring all recent alerts are fetched regardless of LAW state.

The original file is never written to. Use rf_e2e_tests.patchers.write_temp()
to serialise the result for `az deployment group create`.
"""
import copy

WATERMARK_ACTION = "Run_query_and_list_results"


def patch_template(template: dict) -> dict:
    """Return a deep copy of *template* with test-isolation patches applied."""
    t = copy.deepcopy(template)

    for resource in t["resources"]:
        if resource.get("type") != "Microsoft.Logic/workflows":
            continue

        actions = resource["properties"]["definition"]["actions"]

        if WATERMARK_ACTION in actions:
            actions[WATERMARK_ACTION]["inputs"]["body"] = "print LatestEvent=ago(30d)"
            actions[WATERMARK_ACTION]["description"] = (
                "[TEST] KQL body replaced with a fixed ago(30d) watermark "
                "so all recent alerts fall within the fetch window."
            )

    return t

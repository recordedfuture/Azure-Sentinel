"""
Unit tests for support/template_patcher.py.

Loads the real azuredeploy.json, applies the patch, and verifies:
  - All mutations are correct.
  - Everything else is unchanged.
  - The original dict is not mutated.
"""
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from support.template_patcher import (
    COMPUTE_ACTION,
    FILTER_ACTION,
    FOREACH_ACTION,
    OVERRIDE_ACTION,
    SEARCH_ACTION,
    patch_template,
    write_temp,
)
from support.config import TEMPLATE_PATH, TEST_USER_UPN

ALERT_ID = "task:3c6e6ab5-a319-4a1f-8ae9-56e36e099c26"  # stable test value
LOOKBACK = 21


def load_template():
    with open(TEMPLATE_PATH) as f:
        return json.load(f)


def get_workflow(template):
    for r in template["resources"]:
        if r.get("type") == "Microsoft.Logic/workflows":
            return r
    raise AssertionError("No Microsoft.Logic/workflows resource found")


def test_original_not_mutated():
    original = load_template()
    original_copy = copy.deepcopy(original)
    patch_template(original, ALERT_ID, LOOKBACK)
    assert original == original_copy, "patch_template mutated the original"
    print("PASS: original not mutated")


def test_lookback_days_set():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK)
    wf = get_workflow(t)
    body = wf["properties"]["definition"]["actions"][SEARCH_ACTION]["inputs"]["body"]
    assert body["lookback_days"] == LOOKBACK
    assert body.get("max_lookback_days") == LOOKBACK
    assert "priorities" not in body
    print(f"PASS: lookback_days={LOOKBACK}, max_lookback_days={LOOKBACK}, priorities removed")


def test_filter_action_inserted():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK)
    actions = get_workflow(t)["properties"]["definition"]["actions"]
    assert FILTER_ACTION in actions
    fa = actions[FILTER_ACTION]
    assert fa["type"] == "Query"
    assert fa["runAfter"] == {SEARCH_ACTION: ["Succeeded"]}
    assert ALERT_ID in fa["inputs"]["where"]
    print(f"PASS: {FILTER_ACTION} inserted with correct alert_id")


def test_foreach_rewired():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK)
    actions = get_workflow(t)["properties"]["definition"]["actions"]
    fe = actions[FOREACH_ACTION]
    assert fe["runAfter"] == {FILTER_ACTION: ["Succeeded"]}
    assert fe["foreach"] == f"@body('{FILTER_ACTION}')"
    print("PASS: For_each rewired to Filter_alerts_for_testing")


def test_all_other_resources_unchanged():
    original = load_template()
    patched = patch_template(original, ALERT_ID, LOOKBACK)
    orig_non_wf = [r for r in original["resources"] if r.get("type") != "Microsoft.Logic/workflows"]
    patch_non_wf = [r for r in patched["resources"] if r.get("type") != "Microsoft.Logic/workflows"]
    assert orig_non_wf == patch_non_wf
    for key in original:
        if key == "resources":
            continue
        assert original[key] == patched[key], f"Top-level key '{key}' changed"
    print("PASS: all non-workflow content unchanged")


def test_write_temp_creates_valid_json():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK)
    path = write_temp(t)
    try:
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == t
        print(f"PASS: write_temp produced valid JSON at {path}")
    finally:
        os.unlink(path)


def test_rf_api_key_injected():
    TEST_KEY = "test-rf-api-key-12345"
    t = patch_template(load_template(), ALERT_ID, LOOKBACK, rf_api_key=TEST_KEY)
    found = False
    for r in t["resources"]:
        if r.get("type") == "Microsoft.Web/connections":
            api_id = r.get("properties", {}).get("api", {}).get("id", "")
            if "customApis" in api_id:
                pv = r["properties"].get("parameterValues", {})
                assert pv.get("api_key") == TEST_KEY
                found = True
    assert found, "No Microsoft.Web/connections resource with customApis found"
    print("PASS: RF API key injected into connection resource")


def test_no_api_key_leaves_connections_unchanged():
    orig = load_template()
    t = patch_template(orig, ALERT_ID, LOOKBACK, rf_api_key=None)
    orig_conns = [r for r in orig["resources"] if r.get("type") == "Microsoft.Web/connections"]
    patch_conns = [r for r in t["resources"] if r.get("type") == "Microsoft.Web/connections"]
    assert orig_conns == patch_conns
    print("PASS: no rf_api_key leaves connection resources unchanged")


def test_entra_user_upn_inserts_override_action():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK, entra_user_upn=TEST_USER_UPN)
    wf = get_workflow(t)
    foreach_actions = wf["properties"]["definition"]["actions"][FOREACH_ACTION]["actions"]
    assert OVERRIDE_ACTION in foreach_actions, f"'{OVERRIDE_ACTION}' not inserted"
    oa = foreach_actions[OVERRIDE_ACTION]
    assert oa["type"] == "Compose"
    assert oa["inputs"] == TEST_USER_UPN, f"Expected UPN '{TEST_USER_UPN}', got '{oa['inputs']}'"
    assert oa["runAfter"] == {COMPUTE_ACTION: ["Succeeded"]}
    print(f"PASS: {OVERRIDE_ACTION} inserted with correct UPN")


def test_entra_user_upn_replaces_compute_references():
    t = patch_template(load_template(), ALERT_ID, LOOKBACK, entra_user_upn=TEST_USER_UPN)
    wf = get_workflow(t)
    foreach_actions = wf["properties"]["definition"]["actions"][FOREACH_ACTION]["actions"]
    serialised = json.dumps(foreach_actions)
    # No output references to Compute should remain
    assert f"outputs('{COMPUTE_ACTION}')" not in serialised, (
        f"Found remaining output reference to '{COMPUTE_ACTION}' after replacement"
    )
    assert f"outputs('{OVERRIDE_ACTION}')" in serialised
    # Get_User's runAfter should point to Override, not Compute
    get_user_ra = foreach_actions.get(
        "Get_User_-_Check_if_the_user_exists_in_Active_Directory", {}
    ).get("runAfter", {})
    assert OVERRIDE_ACTION in get_user_ra, (
        f"Get_User runAfter should reference '{OVERRIDE_ACTION}', got {get_user_ra}"
    )
    assert COMPUTE_ACTION not in get_user_ra, (
        f"Get_User runAfter still references '{COMPUTE_ACTION}'"
    )
    print("PASS: output references replaced and runAfter dependency updated")


def test_no_entra_user_upn_leaves_compute_unchanged():
    orig = load_template()
    t = patch_template(orig, ALERT_ID, LOOKBACK, entra_user_upn=None)
    foreach_actions = get_workflow(t)["properties"]["definition"]["actions"][FOREACH_ACTION]["actions"]
    assert OVERRIDE_ACTION not in foreach_actions, "Override action inserted when entra_user_upn=None"
    assert COMPUTE_ACTION in foreach_actions, "Compute action removed unexpectedly"
    print("PASS: no entra_user_upn leaves Compute_user_principal_name intact")


if __name__ == "__main__":
    tests = [
        test_original_not_mutated,
        test_lookback_days_set,
        test_filter_action_inserted,
        test_foreach_rewired,
        test_all_other_resources_unchanged,
        test_write_temp_creates_valid_json,
        test_rf_api_key_injected,
        test_no_api_key_leaves_connections_unchanged,
        test_entra_user_upn_inserts_override_action,
        test_entra_user_upn_replaces_compute_references,
        test_no_entra_user_upn_leaves_compute_unchanged,
    ]
    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed.append(test.__name__)

    print()
    if failed:
        print(f"FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests passed.")
